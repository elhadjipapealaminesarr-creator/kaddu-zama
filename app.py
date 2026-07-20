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
import hashlib
from contextlib import closing

from flask import (
    Flask, request, redirect, url_for, render_template,
    make_response, abort, flash, send_from_directory, session
)
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup

import fhe_engine as fhe   # compile + génère les clés FHE au démarrage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("KADDU_DB", os.path.join(BASE_DIR, "kaddu_zama.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", secrets.token_hex(16))
app.jinja_env.globals["ANNEE"] = time.strftime("%Y")
app.jinja_env.globals["ZAMA"] = True
app.jinja_env.filters["dateh"] = lambda ts: time.strftime("%d/%m/%Y", time.localtime(int(ts)))

# --- Langue : détection automatique (navigateur) + choix manuel FR/EN --------
SUPPORTED_LANGS = ("fr", "en")

# Le français est la langue source. On ne stocke ici QUE les traductions anglaises ;
# toute clé absente retombe automatiquement sur le texte français fourni en défaut.
TRANSLATIONS = {
    "en": {
        # Barre de navigation (coquille de l'app)
        "nav.communaute": "Community", "nav.idees": "Ideas", "nav.tontines": "Tontines",
        "nav.offres": "Tenders", "nav.guide": "Guide", "nav.creer": "Create",
        "nav.connexion": "Sign in", "nav.sortir": "Sign out",
        "nav.solutions": "Solutions", "nav.comment": "How it works", "nav.ouvrir": "Open Kaddu",
        # Pied de page (coquille)
        "foot.chiffres": "Your votes are end-to-end encrypted.",
        "foot.cree": "Made with Kaddu — create your own vote &#8594;",
        "foot.edition": "Zama edition &middot; powered by Zama's FHE encryption &middot;",
        "foot.mentions": "Legal notice", "foot.confidentialite": "Privacy", "foot.contact": "Contact",
        # Accueil — héros
        "hero.kick": "&#128274; Protected by Zama's FHE encryption",
        "hero.title_pre": "Confidentiality in service of the ", "hero.title_hl": "community",
        "hero.lead": "Secret votes, tamper-proof tontines and collective decisions — where no one, "
                     "not even the organizer, can see your choices. Built for associations, "
                     "cooperatives, tontines and unions across French-speaking Africa.",
        "hero.cta_create": "&#10133;&nbsp; Create a free vote",
        "hero.cta_code": "I have a code to vote",
        "hero.trust1": "&#10004; Free, no account", "hero.trust2": "&#128241; Installs like an app",
        "hero.trust3": "&#9878; Verifiable result",
        # Accueil — modules
        "mod.eyebrow": "One platform, many uses",
        "mod.h2": "Everything that needs trust and discretion",
        "mod.sub": "A single encryption engine, several concrete solutions for your communities.",
        "mod.live": "&#9679; Online", "mod.new": "New", "mod.soon": "Soon", "mod.prep": "In preparation",
        "mod.open": "Open &#8594;",
        "mod.vote.h3": "Confidential voting",
        "mod.vote.p": "Board elections, assembly decisions, internal polls. Each ballot is encrypted; "
                      "the result is public and verifiable, the votes stay secret.",
        "mod.vote.go": "Use it now &#8594;",
        "mod.tontine.h3": "Tamper-proof tontine",
        "mod.tontine.p": "Manage members, rounds and contributions cleanly, with no cheating possible — "
                         "a tamper-evident ledger (hash chain); the money flows outside the app.",
        "mod.offres.h3": "Sealed-bid tenders",
        "mod.offres.p": "Each bid is sealed at submission (commit-reveal): no one sees the amounts "
                        "before opening. Anti-corruption through mathematics.",
        "mod.pool.h3": "Protected pooling",
        "mod.pool.p": "Combine a group's sensitive data (budgets, figures) to get a total or an average "
                      "— without anyone exposing their individual numbers.",
        "mod.compare.h3": "Private comparator",
        "mod.compare.p": "Compare salaries or prices within a group and know “where I stand”, "
                         "without anyone seeing the others' figures.",
        "mod.idea.h3": "An idea for your community?",
        "mod.idea.p": "Post it on the idea wall: the community votes, the best ones rise.",
        "mod.idea.go": "Open the idea wall &#8594;",
        # Accueil — comment ça marche
        "how.eyebrow": "Simple for everyone", "how.h2": "Three steps, no technical skills",
        "how.s1.h3": "You create",
        "how.s1.p": "A question, some choices, and a link + QR code to share with your members on WhatsApp.",
        "how.s2.h3": "Everyone takes part in secret",
        "how.s2.p": "The choice is encrypted on the spot. Neither the server nor the organizer can read it.",
        "how.s3.h3": "The result, verifiable",
        "how.s3.p": "The total is computed on the encrypted data. No individual answer is revealed.",
        "img.caption": "United communities, every voice protected.",
        # Accueil — technologie Zama
        "zama.eyebrow": "The technology",
        "zama.h2": "Secrecy guaranteed by mathematics, not by trust",
        "zama.p1": "Kaddu relies on Zama's <b>fully homomorphic encryption (FHE)</b>: it computes "
                   "directly on encrypted data, without ever decrypting it.",
        "zama.p2": "In practice: your ballots travel and are counted <b>under seal</b>. Only the final "
                   "result is revealed — never the individual answers.",
        "zama.badge1": "&#128274; End-to-end encryption", "zama.badge2": "&#9878; Verifiable result",
        # Accueil — pourquoi
        "why.eyebrow": "Why Kaddu", "why.h2": "Built for trust, designed for here",
        "why.secret.h3": "Truly secret",
        "why.secret.p": "Each answer is encrypted. Neither the organizer, nor the server, nor a hacker "
                        "can see an individual choice.",
        "why.free.h3": "Free, no account",
        "why.free.p": "Nothing to pay, nothing to install to vote. Share a link, everyone takes part in one click.",
        "why.phone.h3": "Built for the phone",
        "why.phone.p": "Light, fast on a small data plan, and installable like a real app on Android and iPhone.",
        "why.verif.h3": "Verifiable result",
        "why.verif.p": "The tally is computed on the encrypted data, then published. Transparency without "
                       "sacrificing secrecy.",
        # Accueil — FAQ
        "faq.eyebrow": "Frequently asked questions", "faq.h2": "Your questions, our answers",
        "faq.q1": "Can the organizer see my vote?",
        "faq.a1": "No. Your ballot is encrypted on the spot. Even the person who created the vote only "
                  "sees the final result, never the individual choices.",
        "faq.q2": "Do I need to install an app?",
        "faq.a2": "No. A simple link (or a QR code) is enough to vote. If you wish, you can still "
                  "“install” Kaddu on your home screen.",
        "faq.q3": "Is it free?",
        "faq.a3": "Yes, it's free. Kaddu is designed to be accessible to every community.",
        "faq.q4": "Is it really secure?",
        "faq.a4": "Yes. Kaddu relies on Zama's homomorphic encryption (FHE): it computes on encrypted "
                  "data without ever decrypting it. Secrecy is guaranteed by mathematics.",
        "faq.q5": "Who is Kaddu for?",
        "faq.a5": "For associations, cooperatives, tontines, unions, alumni groups, student councils — "
                  "anywhere people make decisions together and trust matters.",
        # Accueil — appel final
        "final.h2": "Ready to run a truly secret vote?",
        "final.p": "Free, no account, ready in a minute. Share the link, your members vote, the result appears.",
        "final.cta1": "&#10133;&nbsp; Create my first vote", "final.cta2": "I have a code to vote",
        # Accueil — pied
        "foot.desc": "Confidentiality in service of communities — associations, cooperatives, tontines, "
                     "unions, alumni groups. Powered by Zama's FHE encryption.",
        "foot.produit": "Product", "foot.creervote": "Create a vote", "foot.murIdees": "Idea wall",
        "foot.informations": "Information", "foot.contactus": "Contact us",
        "foot.copyright": "Kaddu &middot; Made for French-speaking Africa.",
        # Accueil — fenêtre d'accueil
        "intro.title": "Welcome to Kaddu \U0001F44B",
        "intro.sub": "Truly secret votes for your communities. In 3 steps:",
        "intro.s1.t": "Create a vote", "intro.s1.d": "A question, some choices. That's all.",
        "intro.s2.t": "Share the link", "intro.s2.d": "On WhatsApp, in one click (or a QR code).",
        "intro.s3.t": "Everyone votes in secret", "intro.s3.d": "The ballot is encrypted. Only the result appears.",
        "intro.cta": "Create a free vote", "intro.explore": "Explore first",
        "intro.guide": "See the full guide &#8594;",
    }
}


def pick_lang():
    """Choix explicite (session) > langue du navigateur (Accept-Language) > français."""
    chosen = session.get("lang")
    if chosen in SUPPORTED_LANGS:
        return chosen
    accept = (request.headers.get("Accept-Language") or "").lower()
    for part in accept.replace(" ", "").split(","):
        code = part.split(";")[0][:2]
        if code in SUPPORTED_LANGS:
            return code
        if code:            # première langue déclarée non supportée -> défaut français
            break
    return "fr"


@app.context_processor
def inject_i18n():
    lang = pick_lang()

    def t(key, default=""):
        if lang == "fr":
            return Markup(default)
        return Markup(TRANSLATIONS.get(lang, {}).get(key, default))

    return {"LANG": lang, "t": t}


@app.route("/lang/<code>")
def set_lang(code):
    if code in SUPPORTED_LANGS:
        session["lang"] = code
    return redirect(request.referrer or url_for("index"))


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
        # connect_timeout : échec rapide si la base est injoignable.
        # NB : on NE passe PAS 'options=-c statement_timeout' au connect, car le pooler
        # de Supabase (Supavisor) refuse ce paramètre de démarrage. On règle plutôt le
        # timeout via une commande SET juste après la connexion (compatible partout).
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=8)
        try:
            with raw.cursor() as _c:
                _c.execute("SET statement_timeout = 8000")
            raw.commit()
        except Exception:
            pass  # non bloquant : si SET échoue, on garde la connexion telle quelle
        return _Conn(raw)
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

        # --- Tontine inviolable (registre à chaîne d'empreintes) --------------
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS tontines (
                id            {ID_PK},
                owner_user_id INTEGER NOT NULL,
                name          TEXT NOT NULL,
                amount        INTEGER NOT NULL DEFAULT 0,
                frequency     TEXT NOT NULL DEFAULT '',
                member_count  INTEGER NOT NULL DEFAULT 0,
                current_cycle INTEGER NOT NULL DEFAULT 1,
                closed        INTEGER NOT NULL DEFAULT 0,
                mode          TEXT NOT NULL DEFAULT 'simple',
                created_at    INTEGER NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS tontine_members (
                id           {ID_PK},
                tontine_id   INTEGER NOT NULL,
                position     INTEGER NOT NULL,
                name         TEXT NOT NULL,
                member_token TEXT NOT NULL DEFAULT '',
                active       INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS tontine_ledger (
                id         {ID_PK},
                tontine_id INTEGER NOT NULL,
                cycle      INTEGER NOT NULL,
                member_id  INTEGER NOT NULL,
                kind       TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                prev_hash  TEXT NOT NULL DEFAULT '',
                hash       TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_tmembers ON tontine_members(tontine_id, position)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_tledger ON tontine_ledger(tontine_id, cycle)")

        # --- Demande de tour + vote SECRET des membres (FHE) ------------------
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS turn_requests (
                id           {ID_PK},
                tontine_id   INTEGER NOT NULL,
                requester_id INTEGER NOT NULL,
                cycle        INTEGER NOT NULL,
                kind         TEXT NOT NULL DEFAULT 'turn',
                status       TEXT NOT NULL DEFAULT 'open',
                yes_count    INTEGER,
                votes_cast   INTEGER,
                created_at   INTEGER NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS turn_votes (
                request_id INTEGER NOT NULL,
                member_id  INTEGER NOT NULL,
                slot       INTEGER NOT NULL,
                blob       {BLOB_TYPE} NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_turnvotes ON turn_votes(request_id, slot)")

        # --- Appels d'offres scellés (engagement-révélation) ------------------
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS tenders (
                id            {ID_PK},
                owner_user_id INTEGER NOT NULL,
                title         TEXT NOT NULL,
                description   TEXT NOT NULL DEFAULT '',
                direction     TEXT NOT NULL DEFAULT 'low',
                status        TEXT NOT NULL DEFAULT 'open',
                created_at    INTEGER NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS bids (
                id          {ID_PK},
                tender_id   INTEGER NOT NULL,
                bidder_name TEXT NOT NULL,
                commitment  TEXT NOT NULL,
                created_at  INTEGER NOT NULL,
                prev_hash   TEXT NOT NULL DEFAULT '',
                hash        TEXT NOT NULL DEFAULT '',
                revealed    INTEGER NOT NULL DEFAULT 0,
                amount      INTEGER
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_bids ON bids(tender_id, id)")

        # Migration douce : rendre un vote visible sur la place publique.
        for col, ddl in (("public", "INTEGER NOT NULL DEFAULT 0"),
                         ("owner_user_id", "INTEGER")):
            try:
                with closing(db()) as c2, c2:
                    c2.execute(f"ALTER TABLE polls ADD COLUMN {col} {ddl}")
            except Exception:
                pass  # la colonne existe déjà
        for table, col, ddl in (("tontines", "mode", "TEXT NOT NULL DEFAULT 'simple'"),
                                ("tontine_members", "member_token", "TEXT NOT NULL DEFAULT ''"),
                                ("tontine_members", "active", "INTEGER NOT NULL DEFAULT 1"),
                                ("turn_requests", "kind", "TEXT NOT NULL DEFAULT 'turn'")):
            try:
                with closing(db()) as c2, c2:
                    c2.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            except Exception:
                pass  # la colonne existe déjà


_DB_READY = False


def _init_db_bg():
    """Initialise la base EN ARRIÈRE-PLAN (jamais dans le chemin d'une requête, jamais
    au blocage du port). Réessaie tant que Neon n'est pas joignable. Les tables existent
    déjà en prod : c'est surtout un filet de sécurité pour d'éventuelles colonnes/tables
    manquantes."""
    global _DB_READY
    for _ in range(60):
        try:
            init_db()
            _DB_READY = True
            print("[init_db] base initialisée ✔", flush=True)
            return
        except Exception as e:
            print(f"[init_db] arrière-plan : nouvel essai ({e})", flush=True)
            time.sleep(5)
    print("[init_db] abandon après plusieurs essais (les tables existent déjà en prod).",
          flush=True)


if IS_PG:
    # Prod : thread d'arrière-plan → le port s'ouvre immédiatement, aucune requête n'est
    # bloquée par l'init, et Neon est retenté tranquillement jusqu'à ce qu'il réponde.
    import threading
    threading.Thread(target=_init_db_bg, daemon=True).start()
else:
    # Local (SQLite) : instantané et sans risque.
    init_db()
    _DB_READY = True


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
    # Résilient : si la base est momentanément indisponible (Neon endormi/injoignable),
    # on renvoie None au lieu de faire planter TOUTE la page (même celles sans base).
    try:
        return get_user(session.get("uid"))
    except Exception:
        return None


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
        toks = conn.execute("SELECT token, used FROM tokens WHERE poll_id = ? ORDER BY token",
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


@app.route("/guide")
def guide():
    return render_template("guide.html")


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


# --- Tontine inviolable (registre à chaîne d'empreintes) ---------------------
def _insert_returning_id(conn, sql, params):
    if IS_PG:
        row = conn.execute(sql + " RETURNING id", params).fetchone()
        return row["id"]
    return conn.execute(sql, params).lastrowid


def _my_tontines(me):
    if not me:
        return []
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM tontines WHERE owner_user_id = ? ORDER BY id DESC",
                            (me["id"],)).fetchall()
    return [dict(r) for r in rows]


def _tontine(tid):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM tontines WHERE id = ?", (tid,)).fetchone()


def _tontine_members(tid):
    """Membres ACTIFS (roster vivant, bénéficiaires, votes)."""
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM tontine_members WHERE tontine_id = ? AND active = 1 "
                            "ORDER BY position", (tid,)).fetchall()
    return [dict(r) for r in rows]


def _all_members(tid):
    """Tous les membres, y compris ceux qui ont quitté (pour le règlement / historique)."""
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM tontine_members WHERE tontine_id = ? ORDER BY position",
                            (tid,)).fetchall()
    return [dict(r) for r in rows]


def _settlement(tid):
    """Calcule, pour chaque membre, cotisé / reçu / net (convention montant fixe)."""
    t = dict(_tontine(tid))
    allm = _all_members(tid)
    ledger = _tontine_ledger(tid)
    amount = t["amount"] or 0
    mode = t.get("mode", "simple")
    n_active = sum(1 for m in allm if m["active"])
    pot = amount * (max(n_active, 1) - 1)
    rows = []
    for m in allm:
        # cycles où sa cotisation est validée
        cycles = set(e["cycle"] for e in ledger if e["member_id"] == m["id"])
        contrib = 0
        for cyc in cycles:
            if mode == "p2p":
                if (_has_evt(ledger, "member_paid", cyc, m["id"])
                        and _has_evt(ledger, "benef_received", cyc, m["id"])):
                    contrib += 1
            else:
                if _has_evt(ledger, "contribution", cyc, m["id"]):
                    contrib += 1
        received = sum(1 for e in ledger if e["kind"] == "payout" and e["member_id"] == m["id"])
        cotise = amount * contrib
        recu = pot * received
        rows.append({"name": m["name"], "active": m["active"], "contrib": contrib,
                     "received": received, "cotise": cotise, "recu": recu, "net": recu - cotise})
    return rows


def _tontine_ledger(tid):
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM tontine_ledger WHERE tontine_id = ? ORDER BY id",
                            (tid,)).fetchall()
    return [dict(r) for r in rows]


def _hash_row(prev, tid, cycle, member_id, kind, ts):
    payload = "%s|%s|%s|%s|%s|%s" % (prev, tid, cycle, member_id, kind, ts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ledger_add(conn, tid, cycle, member_id, kind):
    r = conn.execute("SELECT hash FROM tontine_ledger WHERE tontine_id = ? ORDER BY id DESC LIMIT 1",
                     (tid,)).fetchone()
    prev = r["hash"] if r else ""
    ts = int(time.time())
    h = _hash_row(prev, tid, cycle, member_id, kind, ts)
    conn.execute("INSERT INTO tontine_ledger (tontine_id, cycle, member_id, kind, created_at, "
                 "prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
                 (tid, cycle, member_id, kind, ts, prev, h))
    return h


def _ledger_ok(ledger, tid):
    """Recalcule la chaîne d'empreintes : renvoie False si un enregistrement a été altéré."""
    prev = ""
    for e in ledger:
        h = _hash_row(prev, tid, e["cycle"], e["member_id"], e["kind"], e["created_at"])
        if h != e["hash"] or e["prev_hash"] != prev:
            return False
        prev = e["hash"]
    return True


@app.route("/tontines", methods=["GET", "POST"])
def tontines():
    me = current_user()
    if request.method == "POST":
        if not me:
            return redirect(url_for("connexion", next=url_for("tontines")))
        name = (request.form.get("name") or "").strip()[:120]
        try:
            amount = int(request.form.get("amount") or "0")
        except ValueError:
            amount = 0
        frequency = (request.form.get("frequency") or "").strip()[:40]
        members = [m.strip()[:60] for m in (request.form.get("members") or "").splitlines() if m.strip()]
        if not name or len(members) < 2:
            flash("Donne un nom et au moins 2 membres (un par ligne).")
            return render_template("tontines.html", tontines=_my_tontines(me), name=name,
                                   amount=amount, frequency=frequency, members="\n".join(members))
        members = members[:60]
        mode = "p2p" if request.form.get("mode") == "p2p" else "simple"
        with closing(db()) as conn, conn:
            tid = _insert_returning_id(conn,
                "INSERT INTO tontines (owner_user_id, name, amount, frequency, member_count, "
                "current_cycle, closed, mode, created_at) VALUES (?,?,?,?,?,1,0,?,?)",
                (me["id"], name, amount, frequency, len(members), mode, int(time.time())))
            for i, mname in enumerate(members, start=1):
                conn.execute("INSERT INTO tontine_members (tontine_id, position, name, member_token) "
                             "VALUES (?,?,?,?)", (tid, i, mname, secrets.token_urlsafe(8)))
        return redirect(url_for("tontine", tid=tid))
    return render_template("tontines.html", tontines=_my_tontines(me),
                           name="", amount="", frequency="", members="")


def _has_evt(ledger, kind, cycle, mid):
    return any(e["kind"] == kind and e["cycle"] == cycle and e["member_id"] == mid for e in ledger)


def _fill_status(members, ledger, cycle, mode):
    """Ajoute à chaque membre son statut de cotisation pour le tour courant."""
    for m in members:
        m["is_beneficiary"] = (m["position"] == cycle)
        if mode == "p2p":
            m["member_paid"] = _has_evt(ledger, "member_paid", cycle, m["id"])
            m["benef_received"] = _has_evt(ledger, "benef_received", cycle, m["id"])
            m["validated"] = m["member_paid"] and m["benef_received"]
        else:
            m["member_paid"] = _has_evt(ledger, "contribution", cycle, m["id"])
            m["benef_received"] = m["member_paid"]
            m["validated"] = m["member_paid"]
    return members


@app.route("/tontine/<int:tid>")
def tontine(tid):
    t = _tontine(tid)
    if not t:
        abort(404)
    t = dict(t)
    members = _tontine_members(tid)
    ledger = _tontine_ledger(tid)
    me = current_user()
    is_owner = bool(me and me["id"] == t["owner_user_id"])
    cycle = t["current_cycle"]
    mode = t.get("mode", "simple")
    _fill_status(members, ledger, cycle, mode)
    beneficiary = next((m for m in members if m["position"] == cycle), None)
    all_paid = bool(members) and all(m["validated"] for m in members)
    req = _open_request(tid)
    req_ctx = None
    if req:
        req = dict(req)
        rq = next((m for m in members if m["id"] == req["requester_id"]), None)
        req_ctx = {"id": req["id"], "kind": req.get("kind", "turn"),
                   "requester_name": rq["name"] if rq else "",
                   "votes_cast": _votes_cast(req["id"])}
    settle = _settlement(tid) if t["closed"] else None
    dissolved = any(e["kind"] == "dissolved" for e in ledger)
    return render_template("tontine.html", t=t, members=members, ledger=ledger,
                           is_owner=is_owner, cycle=cycle, beneficiary=beneficiary,
                           all_paid=all_paid, mode=mode, base=base_url(), req=req_ctx,
                           settle=settle, dissolved=dissolved,
                           integrity=_ledger_ok(ledger, tid),
                           fingerprint=(ledger[-1]["hash"] if ledger else ""))


@app.route("/tontine/<int:tid>/m/<token>")
def tontine_membre(tid, token):
    t = _tontine(tid)
    if not t:
        abort(404)
    t = dict(t)
    members = _tontine_members(tid)
    mem = next((m for m in members if m["member_token"] == token and token), None)
    if not mem:
        abort(404)
    ledger = _tontine_ledger(tid)
    cycle = t["current_cycle"]
    my_paid = (_has_evt(ledger, "member_paid", cycle, mem["id"])
               or _has_evt(ledger, "contribution", cycle, mem["id"]))
    is_benef = (mem["position"] == cycle)
    payers = []
    if is_benef:
        for m in members:
            if m["id"] == mem["id"]:
                continue
            payers.append({"id": m["id"], "name": m["name"],
                           "member_paid": _has_evt(ledger, "member_paid", cycle, m["id"]),
                           "benef_received": _has_evt(ledger, "benef_received", cycle, m["id"])})
    beneficiary = next((m for m in members if m["position"] == cycle), None)
    req = _open_request(tid)
    req_ctx = None
    if req:
        req = dict(req)
        rq = next((m for m in members if m["id"] == req["requester_id"]), None)
        req_ctx = {"id": req["id"], "kind": req.get("kind", "turn"),
                   "requester_name": rq["name"] if rq else "",
                   "is_requester": (req["requester_id"] == mem["id"]),
                   "can_vote": (req["requester_id"] != mem["id"]) and not _has_voted(req["id"], mem["id"]),
                   "i_voted": _has_voted(req["id"], mem["id"])}
    can_request = ((not req) and (not t["closed"]) and (mem["position"] != cycle)
                   and (len(members) >= 3))
    return render_template("tontine_membre.html", t=t, mem=mem, token=token, cycle=cycle,
                           my_paid=my_paid, is_benef=is_benef, payers=payers,
                           beneficiary=beneficiary, req=req_ctx, can_request=can_request)


@app.route("/tontine/<int:tid>/m/<token>/verse", methods=["POST"])
def tontine_verse(tid, token):
    t = _tontine(tid)
    if not t:
        abort(404)
    mem = next((m for m in _tontine_members(tid) if m["member_token"] == token and token), None)
    if not mem:
        abort(404)
    if not t["closed"]:
        cycle = t["current_cycle"]
        with closing(db()) as conn, conn:
            if not _has_evt(_tontine_ledger(tid), "member_paid", cycle, mem["id"]):
                _ledger_add(conn, tid, cycle, mem["id"], "member_paid")
    return redirect(url_for("tontine_membre", tid=tid, token=token))


@app.route("/tontine/<int:tid>/m/<token>/recu", methods=["POST"])
def tontine_recu(tid, token):
    t = _tontine(tid)
    if not t:
        abort(404)
    mem = next((m for m in _tontine_members(tid) if m["member_token"] == token and token), None)
    if not mem:
        abort(404)
    cycle = t["current_cycle"]
    if mem["position"] == cycle and not t["closed"]:
        try:
            payer_id = int(request.form.get("payer_id") or "0")
        except ValueError:
            payer_id = 0
        if payer_id:
            with closing(db()) as conn, conn:
                if not _has_evt(_tontine_ledger(tid), "benef_received", cycle, payer_id):
                    _ledger_add(conn, tid, cycle, payer_id, "benef_received")
    return redirect(url_for("tontine_membre", tid=tid, token=token))


@app.route("/tontine/<int:tid>/payer", methods=["POST"])
def tontine_payer(tid):
    t = _tontine(tid)
    if not t:
        abort(404)
    me = current_user()
    if not me or me["id"] != t["owner_user_id"]:
        abort(403)
    if t["closed"] or t["mode"] == "p2p":
        # en mode P2P, la validation se fait par le membre + le bénéficiaire, pas par l'organisateur.
        return redirect(url_for("tontine", tid=tid))
    try:
        mid = int(request.form.get("member_id") or "0")
    except ValueError:
        mid = 0
    cycle = t["current_cycle"]
    with closing(db()) as conn, conn:
        r = conn.execute("SELECT COUNT(*) c FROM tontine_ledger WHERE tontine_id=? AND cycle=? "
                         "AND member_id=? AND kind='contribution'", (tid, cycle, mid)).fetchone()
        if mid and r["c"] == 0:
            _ledger_add(conn, tid, cycle, mid, "contribution")
    return redirect(url_for("tontine", tid=tid))


@app.route("/tontine/<int:tid>/cycle-suivant", methods=["POST"])
def tontine_cycle(tid):
    t = _tontine(tid)
    if not t:
        abort(404)
    me = current_user()
    if not me or me["id"] != t["owner_user_id"]:
        abort(403)
    if t["closed"]:
        return redirect(url_for("tontine", tid=tid))
    cycle = t["current_cycle"]
    beneficiary = next((m for m in _tontine_members(tid) if m["position"] == cycle), None)
    with closing(db()) as conn, conn:
        if beneficiary:
            _ledger_add(conn, tid, cycle, beneficiary["id"], "payout")
        new_cycle = cycle + 1
        closed = 1 if new_cycle > t["member_count"] else 0
        conn.execute("UPDATE tontines SET current_cycle=?, closed=? WHERE id=?",
                     (new_cycle, closed, tid))
    return redirect(url_for("tontine", tid=tid))


# --- Demande de tour + vote SECRET des membres (FHE) -------------------------
def _open_request(tid):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM turn_requests WHERE tontine_id=? AND status='open' "
                            "ORDER BY id DESC LIMIT 1", (tid,)).fetchone()


def _has_voted(rid, member_id):
    with closing(db()) as conn:
        r = conn.execute("SELECT COUNT(*) c FROM turn_votes WHERE request_id=? AND member_id=?",
                         (rid, member_id)).fetchone()
    return r["c"] > 0


def _votes_cast(rid):
    with closing(db()) as conn:
        return conn.execute("SELECT COUNT(*) c FROM turn_votes WHERE request_id=?", (rid,)).fetchone()["c"]


@app.route("/tontine/<int:tid>/m/<token>/demander", methods=["POST"])
def tontine_demander(tid, token):
    t = _tontine(tid)
    if not t:
        abort(404)
    members = _tontine_members(tid)
    mem = next((m for m in members if m["member_token"] == token and token), None)
    if not mem:
        abort(404)
    cycle = t["current_cycle"]
    if (not t["closed"] and mem["position"] != cycle
            and not _open_request(tid) and len(members) >= 3):
        with closing(db()) as conn, conn:
            _insert_returning_id(conn,
                "INSERT INTO turn_requests (tontine_id, requester_id, cycle, status, created_at) "
                "VALUES (?,?,?, 'open', ?)", (tid, mem["id"], cycle, int(time.time())))
    return redirect(url_for("tontine_membre", tid=tid, token=token))


@app.route("/tontine/<int:tid>/m/<token>/voter-tour", methods=["POST"])
def tontine_voter_tour(tid, token):
    t = _tontine(tid)
    if not t:
        abort(404)
    mem = next((m for m in _tontine_members(tid) if m["member_token"] == token and token), None)
    if not mem:
        abort(404)
    req = _open_request(tid)
    if not req:
        return redirect(url_for("tontine_membre", tid=tid, token=token))
    rid = req["id"]
    if mem["id"] == req["requester_id"] or _has_voted(rid, mem["id"]):
        return redirect(url_for("tontine_membre", tid=tid, token=token))
    n = _votes_cast(rid)
    if n >= fhe.capacity():
        flash("Capacité de vote atteinte.")
        return redirect(url_for("tontine_membre", tid=tid, token=token))
    bit = 1 if request.form.get("choice") == "oui" else 0
    blob = fhe.encrypt_ballot(n, bit)
    with closing(db()) as conn, conn:
        conn.execute("INSERT INTO turn_votes (request_id, member_id, slot, blob) VALUES (?,?,?,?)",
                     (rid, mem["id"], n, blob))
    return redirect(url_for("tontine_membre", tid=tid, token=token))


@app.route("/tontine/<int:tid>/demande/<int:rid>/clore", methods=["POST"])
def tontine_demande_clore(tid, rid):
    t = _tontine(tid)
    if not t:
        abort(404)
    me = current_user()
    if not me or me["id"] != t["owner_user_id"]:
        abort(403)
    with closing(db()) as conn:
        req = conn.execute("SELECT * FROM turn_requests WHERE id=? AND tontine_id=?",
                           (rid, tid)).fetchone()
    if not req or req["status"] != "open":
        return redirect(url_for("tontine", tid=tid))
    with closing(db()) as conn:
        rows = conn.execute("SELECT blob FROM turn_votes WHERE request_id=? ORDER BY slot",
                            (rid,)).fetchall()
    req = dict(req)
    blobs = [bytes(r["blob"]) for r in rows]
    votes_cast = len(blobs)
    yes = fhe.tally(blobs) if blobs else 0
    granted = votes_cast > 0 and (yes * 2 > votes_cast)
    cycle = req["cycle"]
    rkind = req.get("kind", "turn")
    with closing(db()) as conn, conn:
        conn.execute("UPDATE turn_requests SET status=?, yes_count=?, votes_cast=? WHERE id=?",
                     ("granted" if granted else "denied", yes, votes_cast, rid))
        if rkind == "dissolve":
            if granted:
                conn.execute("UPDATE tontines SET closed=1 WHERE id=?", (tid,))
                _ledger_add(conn, tid, cycle, 0, "dissolved")
            else:
                _ledger_add(conn, tid, cycle, 0, "dissolve_denied")
        else:
            if granted:
                benef = conn.execute("SELECT id, position FROM tontine_members WHERE tontine_id=? "
                                     "AND position=? AND active=1", (tid, cycle)).fetchone()
                reqm = conn.execute("SELECT id, position FROM tontine_members WHERE id=?",
                                   (req["requester_id"],)).fetchone()
                if benef and reqm and benef["id"] != reqm["id"]:
                    conn.execute("UPDATE tontine_members SET position=? WHERE id=?",
                                 (reqm["position"], benef["id"]))
                    conn.execute("UPDATE tontine_members SET position=? WHERE id=?",
                                 (cycle, reqm["id"]))
            _ledger_add(conn, tid, cycle, req["requester_id"],
                        "turn_granted" if granted else "turn_denied")
    return redirect(url_for("tontine", tid=tid))


def _do_leave(tid, mem):
    """Retire un membre : recalage de l'ordre si tour non encore re&ccedil;u, scell&eacute; au registre."""
    t = dict(_tontine(tid))
    if t["closed"]:
        return
    ledger = _tontine_ledger(tid)
    received = any(e["kind"] == "payout" and e["member_id"] == mem["id"] for e in ledger)
    cycle = t["current_cycle"]
    with closing(db()) as conn, conn:
        conn.execute("UPDATE tontine_members SET active=0 WHERE id=?", (mem["id"],))
        if not received:
            after = conn.execute("SELECT id, position FROM tontine_members WHERE tontine_id=? "
                                 "AND active=1 AND position > ?", (tid, mem["position"])).fetchall()
            for a in after:
                conn.execute("UPDATE tontine_members SET position=? WHERE id=?",
                             (a["position"] - 1, a["id"]))
            conn.execute("UPDATE tontines SET member_count = member_count - 1 WHERE id=?", (tid,))
            conn.execute("UPDATE tontines SET closed=1 WHERE id=? AND current_cycle > member_count",
                         (tid,))
        _ledger_add(conn, tid, cycle, mem["id"], "member_left")


@app.route("/tontine/<int:tid>/m/<token>/quitter", methods=["POST"])
def tontine_quitter(tid, token):
    t = _tontine(tid)
    if not t:
        abort(404)
    mem = next((m for m in _tontine_members(tid) if m["member_token"] == token and token), None)
    if mem:
        _do_leave(tid, mem)
    return redirect(url_for("tontine", tid=tid))


@app.route("/tontine/<int:tid>/membre/<int:mid>/retirer", methods=["POST"])
def tontine_retirer(tid, mid):
    t = _tontine(tid)
    if not t:
        abort(404)
    me = current_user()
    if not me or me["id"] != t["owner_user_id"]:
        abort(403)
    mem = next((m for m in _tontine_members(tid) if m["id"] == mid), None)
    if mem:
        _do_leave(tid, mem)
    return redirect(url_for("tontine", tid=tid))


@app.route("/tontine/<int:tid>/dissoudre-proposer", methods=["POST"])
def tontine_dissoudre(tid):
    t = _tontine(tid)
    if not t:
        abort(404)
    me = current_user()
    if not me or me["id"] != t["owner_user_id"]:
        abort(403)
    if not t["closed"] and not _open_request(tid) and len(_tontine_members(tid)) >= 2:
        with closing(db()) as conn, conn:
            _insert_returning_id(conn,
                "INSERT INTO turn_requests (tontine_id, requester_id, cycle, kind, status, created_at) "
                "VALUES (?,0,?, 'dissolve', 'open', ?)", (tid, t["current_cycle"], int(time.time())))
    return redirect(url_for("tontine", tid=tid))


# --- Appels d'offres scellés (engagement-révélation) -------------------------
def _tender(tid):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM tenders WHERE id = ?", (tid,)).fetchone()


def _bids(tid):
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM bids WHERE tender_id = ? ORDER BY id", (tid,)).fetchall()
    return [dict(r) for r in rows]


def _my_tenders(me):
    if not me:
        return []
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM tenders WHERE owner_user_id = ? ORDER BY id DESC",
                            (me["id"],)).fetchall()
    return [dict(r) for r in rows]


def _bid_commitment(amount, secret):
    return hashlib.sha256(("%d|%s" % (int(amount), secret)).encode("utf-8")).hexdigest()


def _bid_hash(prev, tid, name, commitment, ts):
    payload = "%s|%s|%s|%s|%s" % (prev, tid, name, commitment, ts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@app.route("/offres", methods=["GET", "POST"])
def offres():
    me = current_user()
    if request.method == "POST":
        if not me:
            return redirect(url_for("connexion", next=url_for("offres")))
        title = (request.form.get("title") or "").strip()[:140]
        description = (request.form.get("description") or "").strip()[:1000]
        direction = "high" if request.form.get("direction") == "high" else "low"
        if not title:
            flash("Donne un intitulé à l'appel d'offres.")
            return render_template("offres.html", tenders=_my_tenders(me),
                                   title=title, description=description)
        with closing(db()) as conn, conn:
            tid = _insert_returning_id(conn,
                "INSERT INTO tenders (owner_user_id, title, description, direction, status, "
                "created_at) VALUES (?,?,?,?, 'open', ?)",
                (me["id"], title, description, direction, int(time.time())))
        return redirect(url_for("offre", tid=tid))
    return render_template("offres.html", tenders=_my_tenders(me), title="", description="")


@app.route("/offre/<int:tid>")
def offre(tid):
    t = _tender(tid)
    if not t:
        abort(404)
    t = dict(t)
    bids = _bids(tid)
    me = current_user()
    is_owner = bool(me and me["id"] == t["owner_user_id"])
    prev = ""
    integrity = True
    for b in bids:
        h = _bid_hash(prev, tid, b["bidder_name"], b["commitment"], b["created_at"])
        if h != b["hash"] or b["prev_hash"] != prev:
            integrity = False
            break
        prev = b["hash"]
    results = None
    if t["status"] == "closed":
        revealed = [b for b in bids if b["revealed"] and b["amount"] is not None]
        revealed.sort(key=lambda b: b["amount"], reverse=(t["direction"] == "high"))
        results = revealed
    return render_template("offre.html", t=t, bids=bids, is_owner=is_owner,
                           integrity=integrity, results=results, n_sealed=len(bids))


@app.route("/offre/<int:tid>/soumettre", methods=["POST"])
def offre_soumettre(tid):
    t = _tender(tid)
    if not t:
        abort(404)
    if t["status"] != "open":
        flash("Les soumissions sont closes.")
        return redirect(url_for("offre", tid=tid))
    name = (request.form.get("name") or "").strip()[:60]
    secret = (request.form.get("secret") or "").strip()
    try:
        amount = int(request.form.get("amount") or "")
    except ValueError:
        amount = None
    if not name or not secret or amount is None or amount < 0:
        flash("Nom, montant (entier positif) et mot secret sont requis.")
        return redirect(url_for("offre", tid=tid))
    with closing(db()) as conn, conn:
        r = conn.execute("SELECT COUNT(*) c FROM bids WHERE tender_id=? AND bidder_name=?",
                         (tid, name)).fetchone()
        if r["c"] > 0:
            flash("Ce nom a déjà soumis une offre.")
            return redirect(url_for("offre", tid=tid))
        last = conn.execute("SELECT hash FROM bids WHERE tender_id=? ORDER BY id DESC LIMIT 1",
                            (tid,)).fetchone()
        prev = last["hash"] if last else ""
        ts = int(time.time())
        commitment = _bid_commitment(amount, secret)
        h = _bid_hash(prev, tid, name, commitment, ts)
        conn.execute("INSERT INTO bids (tender_id, bidder_name, commitment, created_at, prev_hash, "
                     "hash, revealed, amount) VALUES (?,?,?,?,?,?,0,NULL)",
                     (tid, name, commitment, ts, prev, h))
    flash("Offre scellée. Garde bien ton montant + mot secret pour la révélation.")
    return redirect(url_for("offre", tid=tid))


@app.route("/offre/<int:tid>/clore", methods=["POST"])
def offre_clore(tid):
    t = _tender(tid)
    if not t:
        abort(404)
    me = current_user()
    if not me or me["id"] != t["owner_user_id"]:
        abort(403)
    with closing(db()) as conn, conn:
        conn.execute("UPDATE tenders SET status='closed' WHERE id=?", (tid,))
    return redirect(url_for("offre", tid=tid))


@app.route("/offre/<int:tid>/reveler", methods=["POST"])
def offre_reveler(tid):
    t = _tender(tid)
    if not t:
        abort(404)
    if t["status"] != "closed":
        flash("La révélation ouvre après la clôture des soumissions.")
        return redirect(url_for("offre", tid=tid))
    name = (request.form.get("name") or "").strip()[:60]
    secret = (request.form.get("secret") or "").strip()
    try:
        amount = int(request.form.get("amount") or "")
    except ValueError:
        amount = None
    with closing(db()) as conn, conn:
        b = conn.execute("SELECT * FROM bids WHERE tender_id=? AND bidder_name=?",
                         (tid, name)).fetchone()
        if not b:
            flash("Aucune offre à ce nom.")
            return redirect(url_for("offre", tid=tid))
        if b["revealed"]:
            flash("Cette offre est déjà révélée.")
            return redirect(url_for("offre", tid=tid))
        if amount is None or _bid_commitment(amount, secret) != b["commitment"]:
            flash("Montant + mot secret ne correspondent pas à l'offre scellée.")
            return redirect(url_for("offre", tid=tid))
        conn.execute("UPDATE bids SET revealed=1, amount=? WHERE id=?", (amount, b["id"]))
    flash("Offre révélée et vérifiée.")
    return redirect(url_for("offre", tid=tid))


@app.errorhandler(Exception)
def handle_unexpected(e):
    """Filet de sécurité : si une page échoue (ex. base indisponible), on affiche un
    message propre au lieu d'un 500 brut. Les erreurs HTTP normales (404/403) passent."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    app.logger.exception("Erreur non gérée")
    try:
        return render_template(
            "erreur.html", code=503,
            msg="Service momentanément indisponible (base de données). Réessaie dans un instant."), 503
    except Exception:
        return "Service momentanément indisponible. Réessaie dans un instant.", 503


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
