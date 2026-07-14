"""
Kaddu — édition Zama. Vote confidentiel propulsé par le VRAI chiffrement FHE de Zama
(bibliothèque Concrete). Chaque bulletin est chiffré ; le décompte est calculé sur les
bulletins chiffrés (addition homomorphe FHE) et seul le total est déchiffré. Personne —
ni le serveur, ni l'organisateur — ne voit un vote individuel.
"""
import os
import json
import time
import secrets
import sqlite3
from contextlib import closing

from flask import (
    Flask, request, redirect, url_for, render_template,
    make_response, abort, flash, send_from_directory, session
)
from werkzeug.security import generate_password_hash, check_password_hash

import fhe_engine as fhe   # compile + génère les clés FHE au démarrage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("KADDU_DB", os.path.join(BASE_DIR, "kaddu_zama.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", secrets.token_hex(16))
app.jinja_env.globals["ANNEE"] = time.strftime("%Y")
app.jinja_env.globals["ZAMA"] = True
app.jinja_env.filters["dateh"] = lambda ts: time.strftime("%d/%m/%Y", time.localtime(int(ts)))


# Base durable : PostgreSQL (Neon) si DATABASE_URL est défini, sinon SQLite en local.
DATABASE_URL = os.environ.get("DATABASE_URL")
IS_PG = bool(DATABASE_URL)
BLOB_TYPE = "BYTEA" if IS_PG else "BLOB"
ID_PK = "BIGSERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"

if IS_PG:
    import psycopg
    from psycopg.rows import dict_row


class _Conn:
    """Adaptateur : même interface (execute / with / close) pour SQLite et Postgres."""
    def __init__(self, raw):
        self._raw = raw

    def _q(self, sql):
        return sql.replace("?", "%s") if IS_PG else sql

    def execute(self, sql, params=()):
        cur = self._raw.cursor()
        cur.execute(self._q(sql), params)
        return cur

    def executemany(self, sql, seq):
        cur = self._raw.cursor()
        cur.executemany(self._q(sql), seq)
        return cur

    def __enter__(self):
        self._raw.__enter__()
        return self

    def __exit__(self, *a):
        return self._raw.__exit__(*a)

    def close(self):
        self._raw.close()


def db():
    if IS_PG:
        return _Conn(psycopg.connect(DATABASE_URL, row_factory=dict_row))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return _Conn(conn)


def init_db():
    with closing(db()) as conn, conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                id          TEXT PRIMARY KEY,
                admin_token TEXT NOT NULL,
                title       TEXT NOT NULL,
                question    TEXT NOT NULL,
                options     TEXT NOT NULL,
                created_at  INTEGER NOT NULL,
                closed      INTEGER NOT NULL DEFAULT 0,
                results     TEXT
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS ballots (
                poll_id    TEXT NOT NULL,
                voter      INTEGER NOT NULL,
                option_idx INTEGER NOT NULL,
                blob       {BLOB_TYPE} NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_ballots ON ballots(poll_id, option_idx, voter)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                poll_id TEXT NOT NULL,
                token   TEXT NOT NULL,
                used    INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_tokens ON tokens(poll_id, token)")

        # --- Espace communauté ------------------------------------------------
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id           {ID_PK},
                email        TEXT UNIQUE NOT NULL,
                pw_hash      TEXT NOT NULL,
                display_name TEXT NOT NULL,
                is_admin     INTEGER NOT NULL DEFAULT 0,
                created_at   INTEGER NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS comments (
                id         {ID_PK},
                poll_id    TEXT NOT NULL,
                user_id    INTEGER NOT NULL,
                body       TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                hidden     INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_comments ON comments(poll_id, created_at)")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS ideas (
                id         {ID_PK},
                user_id    INTEGER NOT NULL,
                title      TEXT NOT NULL,
                body       TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                hidden     INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS idea_votes (
                idea_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                value   INTEGER NOT NULL,
                PRIMARY KEY (idea_id, user_id)
            )
        """)
        # Migration douce : rendre un vote visible sur la place publique.
        for col, ddl in (("public", "INTEGER NOT NULL DEFAULT 0"),
                         ("owner_user_id", "INTEGER")):
            try:
                with closing(db()) as c2, c2:
                    c2.execute(f"ALTER TABLE polls ADD COLUMN {col} {ddl}")
            except Exception:
                pass  # la colonne existe déjà


init_db()


# --- Utilisateurs / session --------------------------------------------------
def get_user(uid):
    if not uid:
        return None
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def get_user_by_email(email):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def current_user():
    return get_user(session.get("uid"))


@app.context_processor
def inject_user():
    return {"me": current_user()}


def get_poll(poll_id):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()


def voter_count(poll_id):
    with closing(db()) as conn:
        r = conn.execute("SELECT COALESCE(MAX(voter)+1, 0) n FROM ballots WHERE poll_id = ?",
                         (poll_id,)).fetchone()
    return r["n"]


def has_tokens(poll_id):
    """Le vote est 'restreint' dès qu'au moins un jeton membre existe."""
    with closing(db()) as conn:
        r = conn.execute("SELECT COUNT(*) c FROM tokens WHERE poll_id = ?", (poll_id,)).fetchone()
    return r["c"] > 0


def token_ok(poll_id, tok):
    if not tok:
        return False
    with closing(db()) as conn:
        r = conn.execute("SELECT used FROM tokens WHERE poll_id = ? AND token = ?",
                         (poll_id, tok)).fetchone()
    return r is not None and r["used"] == 0


def base_url():
    return request.url_root.rstrip("/")


@app.route("/ping")
def ping():
    return "ok", 200


@app.route("/sw.js")
def service_worker():
    resp = make_response(send_from_directory(os.path.join(BASE_DIR, "static"), "sw.js"))
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/creer", methods=["GET", "POST"])
def creer():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        question = (request.form.get("question") or "").strip()
        options = [o.strip() for o in request.form.getlist("option") if o.strip()]
        if not title or not question or len(options) < 2:
            flash("Donne un titre, une question et au moins 2 choix.")
            return render_template("creer.html", title=title, question=question,
                                   options=options or ["", ""])
        options = options[:8]
        poll_id = secrets.token_urlsafe(5).replace("-", "a").replace("_", "b")
        admin_token = secrets.token_urlsafe(16)
        me = current_user()
        pub = 1 if request.form.get("public") else 0
        owner = me["id"] if me else None
        with closing(db()) as conn, conn:
            conn.execute("INSERT INTO polls (id, admin_token, title, question, options, "
                         "created_at, closed, public, owner_user_id) VALUES (?,?,?,?,?,?,0,?,?)",
                         (poll_id, admin_token, title, question, json.dumps(options),
                          int(time.time()), pub, owner))
        return redirect(url_for("partage", poll_id=poll_id, t=admin_token))
    return render_template("creer.html", title="", question="", options=["", ""])


@app.route("/partage/<poll_id>")
def partage(poll_id):
    poll = get_poll(poll_id)
    if not poll:
        abort(404)
    admin_token = request.args.get("t", "")
    show_admin = admin_token == poll["admin_token"]
    vote_url = f"{base_url()}{url_for('voter', poll_id=poll_id)}"
    admin_url = (f"{base_url()}{url_for('admin', poll_id=poll_id, t=poll['admin_token'])}"
                 if show_admin else "")
    return render_template("partage.html", poll=poll, vote_url=vote_url, admin_url=admin_url)


@app.route("/v/<poll_id>", methods=["GET", "POST"])
def voter(poll_id):
    poll = get_poll(poll_id)
    if not poll:
        abort(404)
    options = json.loads(poll["options"])
    restricted = has_tokens(poll_id)
    tok = (request.values.get("k") or "").strip()
    already = request.cookies.get(f"kv_{poll_id}") == "1"
    full = voter_count(poll_id) >= fhe.capacity()

    comments = get_comments(poll_id)

    def page(**kw):
        base = dict(poll=poll, options=options, closed=False, already=already,
                    full=full, restricted=restricted, token=tok, token_bad=False,
                    comments=comments)
        base.update(kw)
        return render_template("voter.html", **base)

    if poll["closed"]:
        return render_template("voter.html", poll=poll, options=options, closed=True,
                               already=already, restricted=restricted, token=tok,
                               token_bad=False, comments=comments)

    # Mode restreint : un lien membre valide et non utilisé est obligatoire.
    if restricted:
        already = False
        if not token_ok(poll_id, tok):
            return page(token_bad=True)

    if request.method == "POST":
        if not restricted and already:
            return redirect(url_for("merci", poll_id=poll_id))
        if full:
            flash("Ce vote a atteint sa capacité maximale.")
            return page()
        try:
            choice = int(request.form.get("choice", "-1"))
        except ValueError:
            choice = -1
        if choice < 0 or choice >= len(options):
            flash("Choisis une option pour voter.")
            return page()
        n = voter_count(poll_id)
        rows = [(poll_id, n, m, fhe.encrypt_ballot(n, 1 if m == choice else 0))
                for m in range(len(options))]
        with closing(db()) as conn, conn:
            if restricted:
                cur = conn.execute(
                    "UPDATE tokens SET used = 1 WHERE poll_id = ? AND token = ? AND used = 0",
                    (poll_id, tok))
                if cur.rowcount == 0:
                    flash("Ce lien a déjà servi à voter.")
                    return page(token_bad=True)
            conn.executemany("INSERT INTO ballots (poll_id, voter, option_idx, blob) "
                             "VALUES (?,?,?,?)", rows)
        resp = make_response(redirect(url_for("merci", poll_id=poll_id)))
        if not restricted:
            resp.set_cookie(f"kv_{poll_id}", "1", max_age=60*60*24*365, samesite="Lax")
        return resp

    return page()


@app.route("/v/<poll_id>/merci")
def merci(poll_id):
    poll = get_poll(poll_id)
    if not poll:
        abort(404)
    return render_template("merci.html", poll=poll)


@app.route("/r/<poll_id>")
def resultat(poll_id):
    poll = get_poll(poll_id)
    if not poll:
        abort(404)
    options = json.loads(poll["options"])
    if not poll["closed"]:
        return render_template("resultat.html", poll=poll, options=options,
                               ready=False, participants=voter_count(poll_id))
    results = json.loads(poll["results"] or "[]")
    total = sum(results) if results else 0
    rows = []
    for i, opt in enumerate(options):
        n = results[i] if i < len(results) else 0
        pct = round(n / total * 100) if total else 0
        rows.append({"label": opt, "n": n, "pct": pct})
    rows_sorted = sorted(rows, key=lambda r: r["n"], reverse=True)
    win = rows_sorted[0]["label"] if rows_sorted and total else None
    return render_template("resultat.html", poll=poll, options=options, ready=True,
                           rows=rows, rows_sorted=rows_sorted, total=total, win=win)


@app.route("/admin/<poll_id>")
def admin(poll_id):
    poll = get_poll(poll_id)
    if not poll:
        abort(404)
    if request.args.get("t", "") != poll["admin_token"]:
        abort(403)
    options = json.loads(poll["options"])
    vote_url = f"{base_url()}{url_for('voter', poll_id=poll_id)}"
    with closing(db()) as conn:
        toks = conn.execute("SELECT token, used FROM tokens WHERE poll_id = ? ORDER BY rowid",
                            (poll_id,)).fetchall()
    return render_template("admin.html", poll=poll, options=options,
                           participants=voter_count(poll_id), vote_url=vote_url,
                           token=poll["admin_token"],
                           tokens=[dict(t) for t in toks], capacity=fhe.capacity())


@app.route("/admin/<poll_id>/clore", methods=["POST"])
def clore(poll_id):
    poll = get_poll(poll_id)
    if not poll:
        abort(404)
    if request.form.get("t", "") != poll["admin_token"]:
        abort(403)
    options = json.loads(poll["options"])
    results = []
    with closing(db()) as conn:
        for m in range(len(options)):
            blobs = [bytes(r["blob"]) for r in conn.execute(
                "SELECT blob FROM ballots WHERE poll_id=? AND option_idx=? ORDER BY voter",
                (poll_id, m)).fetchall()]
            results.append(fhe.tally(blobs) if blobs else 0)
    with closing(db()) as conn, conn:
        conn.execute("UPDATE polls SET closed=1, results=? WHERE id=?",
                     (json.dumps(results), poll_id))
    return redirect(url_for("resultat", poll_id=poll_id))


@app.route("/admin/<poll_id>/liens", methods=["POST"])
def gen_tokens(poll_id):
    """Génère des liens de vote nominatifs : 1 par membre, 1 seul vote chacun."""
    poll = get_poll(poll_id)
    if not poll:
        abort(404)
    if request.form.get("t", "") != poll["admin_token"]:
        abort(403)
    try:
        n = int(request.form.get("n", "0"))
    except ValueError:
        n = 0
    with closing(db()) as conn:
        existing = conn.execute("SELECT COUNT(*) c FROM tokens WHERE poll_id = ?",
                                (poll_id,)).fetchone()["c"]
    n = max(0, min(n, fhe.capacity() - existing))
    if n:
        with closing(db()) as conn, conn:
            conn.executemany(
                "INSERT INTO tokens (poll_id, token, used) VALUES (?,?,0)",
                [(poll_id, secrets.token_urlsafe(6)) for _ in range(n)])
    return redirect(url_for("admin", poll_id=poll_id, t=poll["admin_token"]))


@app.route("/mentions-legales")
def mentions():
    return render_template("mentions.html")


@app.route("/confidentialite")
def confidentialite():
    return render_template("confidentialite.html")


@app.route("/rejoindre", methods=["GET", "POST"])
def rejoindre():
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        if "/v/" in code:
            code = code.rsplit("/v/", 1)[-1].split("/")[0].split("?")[0]
        elif "/" in code:
            code = code.rstrip("/").rsplit("/", 1)[-1]
        if code and get_poll(code):
            return redirect(url_for("voter", poll_id=code))
        flash("Code introuvable. Vérifie et réessaie.")
    return render_template("rejoindre.html")


# --- Comptes (inscription / connexion) --------------------------------------
@app.route("/inscription", methods=["GET", "POST"])
def inscription():
    if current_user():
        return redirect(url_for("communaute"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        if not name or "@" not in email or "." not in email or len(pw) < 6:
            flash("Nom, e-mail valide et mot de passe (6 caractères min.) requis.")
            return render_template("inscription.html", name=name, email=email)
        if get_user_by_email(email):
            flash("Un compte existe déjà avec cet e-mail. Connectez-vous.")
            return redirect(url_for("connexion"))
        with closing(db()) as conn, conn:
            conn.execute(
                "INSERT INTO users (email, pw_hash, display_name, created_at) VALUES (?,?,?,?)",
                (email, generate_password_hash(pw, method="pbkdf2:sha256"), name, int(time.time())))
        u = get_user_by_email(email)
        session["uid"] = u["id"]
        return redirect(request.args.get("next") or url_for("communaute"))
    return render_template("inscription.html", name="", email="")


@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    if current_user():
        return redirect(url_for("communaute"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        u = get_user_by_email(email)
        if not u or not check_password_hash(u["pw_hash"], pw):
            flash("E-mail ou mot de passe incorrect.")
            return render_template("connexion.html", email=email)
        session["uid"] = u["id"]
        return redirect(request.args.get("next") or url_for("communaute"))
    return render_template("connexion.html", email="")


@app.route("/deconnexion")
def deconnexion():
    session.pop("uid", None)
    return redirect(url_for("index"))


# --- Place publique ----------------------------------------------------------
@app.route("/communaute")
def communaute():
    with closing(db()) as conn:
        polls = conn.execute(
            "SELECT id, title, question, closed, created_at, "
            "(SELECT COALESCE(MAX(voter)+1,0) FROM ballots b WHERE b.poll_id = p.id) n "
            "FROM polls p WHERE public = 1 ORDER BY created_at DESC LIMIT 60").fetchall()
    return render_template("communaute.html", polls=[dict(p) for p in polls])


# --- Commentaires ------------------------------------------------------------
def get_comments(poll_id):
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT c.body, c.created_at, u.display_name name FROM comments c "
            "JOIN users u ON u.id = c.user_id "
            "WHERE c.poll_id = ? AND c.hidden = 0 ORDER BY c.created_at", (poll_id,)).fetchall()
    return [dict(r) for r in rows]


@app.route("/v/<poll_id>/commenter", methods=["POST"])
def commenter(poll_id):
    poll = get_poll(poll_id)
    if not poll:
        abort(404)
    me = current_user()
    if not me:
        return redirect(url_for("connexion", next=url_for("voter", poll_id=poll_id)))
    body = (request.form.get("body") or "").strip()[:1000]
    if body:
        with closing(db()) as conn, conn:
            conn.execute("INSERT INTO comments (poll_id, user_id, body, created_at) "
                         "VALUES (?,?,?,?)", (poll_id, me["id"], body, int(time.time())))
    return redirect(url_for("voter", poll_id=poll_id) + "#discussion")


# --- Mur d'idées -------------------------------------------------------------
@app.route("/idees", methods=["GET", "POST"])
def idees():
    me = current_user()
    if request.method == "POST":
        if not me:
            return redirect(url_for("connexion", next=url_for("idees")))
        title = (request.form.get("title") or "").strip()[:140]
        body = (request.form.get("body") or "").strip()[:1000]
        if title:
            with closing(db()) as conn, conn:
                conn.execute("INSERT INTO ideas (user_id, title, body, created_at) "
                             "VALUES (?,?,?,?)", (me["id"], title, body, int(time.time())))
        return redirect(url_for("idees"))
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT i.id, i.title, i.body, i.created_at, u.display_name name, "
            "COALESCE(SUM(v.value),0) score, COUNT(v.value) nvotes "
            "FROM ideas i JOIN users u ON u.id = i.user_id "
            "LEFT JOIN idea_votes v ON v.idea_id = i.id "
            "WHERE i.hidden = 0 "
            "GROUP BY i.id, i.title, i.body, i.created_at, u.display_name "
            "ORDER BY score DESC, i.created_at DESC LIMIT 100").fetchall()
    return render_template("idees.html", ideas=[dict(r) for r in rows])


@app.route("/idees/<int:idea_id>/vote", methods=["POST"])
def idea_vote(idea_id):
    me = current_user()
    if not me:
        return redirect(url_for("connexion", next=url_for("idees")))
    try:
        val = int(request.form.get("v", "0"))
    except ValueError:
        val = 0
    val = 1 if val > 0 else (-1 if val < 0 else 0)
    if val:
        with closing(db()) as conn, conn:
            conn.execute(
                "INSERT INTO idea_votes (idea_id, user_id, value) VALUES (?,?,?) "
                "ON CONFLICT (idea_id, user_id) DO UPDATE SET value = excluded.value",
                (idea_id, me["id"], val))
    return redirect(url_for("idees"))


@app.errorhandler(404)
def not_found(e):
    return render_template("erreur.html", code=404,
                           msg="Ce vote n'existe pas ou a été supprimé."), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("erreur.html", code=403,
                           msg="Accès réservé à l'organisateur du vote."), 403


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "7860")), debug=False)
