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
        "mod.sub2": "One encryption engine, eight concrete services for your communities. "
                    "Kaddu is not just about voting.",
        "mod.alert.h3": "Alert vault",
        "mod.alert.p": "Report corruption or harassment without being alone: an alert only surfaces "
                       "once several people flag the same target. Below the threshold, it stays invisible.",
        # --- Accueil international : héros, piliers, monde, mission, final ---
        "index.tagline": "Confidentiality in service of communities",
        "hero.lead2": "Kaddu gives communities everywhere — associations, cooperatives, savings "
                      "circles and unions — the tools to decide, save and organize, so no one, "
                      "not even the organizer, can see or tamper with the choices.",
        "hero.cta_tools": "Discover our tools",
        "hero.cap": "Every voice protected",
        "hero.img_alt": "Communities everywhere, coming together to decide",
        "pil.decide.h": "Decide", "pil.decide.p": "Truly secret, verifiable votes.",
        "pil.save.h": "Save", "pil.save.p": "Tamper-proof savings circles, with no all-powerful manager.",
        "pil.attrib.h": "Award", "pil.attrib.p": "Sealed-bid tenders — anti-corruption.",
        "pil.pool.h": "Pool", "pil.pool.p": "Combine figures without exposing them.",
        "world.eyebrow": "A universal problem",
        "world.h2": "The same trust to protect, everywhere in the world",
        "world.sub": "Community savings and collective decisions exist on every continent — a vast "
                     "informal market, largely overlooked. Kaddu speaks their language.",
        "world.flag.h": "Where we start: French-speaking Africa",
        "world.flag.p": "Kaddu was born in Dakar, built first for the savings circles, associations "
                        "and cooperatives of French-speaking Africa — on any phone, in French, with "
                        "no bank account. It's our proving ground before the rest of the world.",
        "mis.eyebrow": "Our mission",
        "mis.h2": "Making trust independent of people",
        "mis.p": "Everywhere in the world, wherever communities decide and save together, trust is "
                 "fragile. Kaddu replaces it with a mathematical guarantee — free, on any phone, for everyone.",
        "mis.s1": "of votes encrypted end-to-end",
        "mis.s2": "individual choice ever exposed",
        "mis.s3": "civic tools in a single app",
        "mis.s4": "Zama's encryption, for real",
        "mod.offres.p2": "Each bid is sealed at submission. In encrypted mode, losers never reveal "
                         "their price. Anti-corruption through mathematics.",
        "mod.idea.h3b": "Idea wall",
        "mod.idea.p2": "Anyone posts an idea for the community or for Kaddu. Members vote, the best rise.",
        "mod.place.h3": "Public square",
        "mod.place.p": "Discover votes open to the public, take part and exchange with the Kaddu community.",
        "mod.place.go": "Explore &#8594;",
        "final.eyebrow": "Get started now",
        "final.h2b": "Your first protected decision, in 2 minutes",
        "final.p2": "Free, no account. Create a vote, a savings circle or a tender and invite your community.",
        "final.cta1b": "Open Kaddu for free",
        # --- Comptes (partagé) ---
        "auth.signin": "Sign in", "auth.signup": "Create an account",
        # --- Mise en commun protégée (pool.*) ---
        "pool.title": "Protected pooling",
        "pool.view.note": "Each figure is <b>encrypted on the phone</b> before it's sent. The server "
                          "adds up the encrypted data: only the <b>total</b> is revealed, never an individual amount.",
        "pool.contribs": "Contributions", "pool.closed": "Closed", "pool.open": "Open",
        "pool.total.label": "Total pooled (computed on the encrypted data)",
        "pool.avg.label": "Average per participant",
        "pool.total.note": "No individual figure was decrypted to get this total.",
        "pool.add.h": "Add my figure",
        "pool.full": "The maximum number of participants has been reached.",
        "pool.name": "Your name (optional)", "pool.name.ph": "e.g. Awa",
        "pool.amount": "Your amount (FCFA)", "pool.amount.ph": "e.g. 25000",
        "pool.add.btn": "Encrypt and add",
        "pool.add.note": "Your amount is encrypted <b>before</b> being stored. Even the organizer "
                         "can't read it: they'll only see the final total.",
        "pool.close.confirm": "Close and reveal the total? No new contribution will be possible.",
        "pool.close.btn": "Close and reveal the total",
        "pool.close.note": "As the organizer, you can close whenever you like. The total is computed "
                           "by homomorphic addition on the encrypted data.",
        "pool.all": "All my pools",
        "pool.hero.h": "Add up without exposing",
        "pool.hero.lead": "Combine sensitive figures — budgets, contributions, donations — to get a "
                          "<b>total and an average</b>, without anyone, not even the organizer, "
                          "seeing anyone else's figure.",
        "pool.login": "Sign in to create a pool.",
        "pool.contrib.count": "contribution(s)", "pool.total.short": "total",
        "pool.new": "New pool",
        "pool.field.title": "Title", "pool.field.title.ph": "e.g. Association's forecast budget",
        "pool.field.q": "Detail (optional)", "pool.field.q.ph": "e.g. How much can each person commit this quarter?",
        "pool.create": "Create",
        "pool.new.note": "You get a link to share. Everyone adds their figure, encrypted. At closing, "
                         "Kaddu reveals only the total and the average.",
        # --- Comparateur privé (cmp.*) ---
        "cmp.title": "Private comparator",
        "cmp.view.note": "Everyone submits their <b>bracket</b>, encrypted. Only the group "
                         "<b>distribution</b> is revealed: you see where you stand, never anyone's exact figure.",
        "cmp.contribs": "Participations", "cmp.closed": "Closed", "cmp.open": "Open",
        "cmp.distrib": "Group distribution (computed on the encrypted data)",
        "cmp.distrib.note": "No individual figure was decrypted. Only the number of people per bracket is known.",
        "cmp.situate.h": "Place myself",
        "cmp.full": "The maximum number of participants has been reached.",
        "cmp.your": "Your figure", "cmp.range": "e.g.",
        "cmp.situate.btn": "Encrypt and place me",
        "cmp.situate.note": "Your exact figure is never stored: only your bracket is encrypted. You "
                            "learn your position without exposing your amount.",
        "cmp.close.confirm": "Close and reveal the distribution?",
        "cmp.close.btn": "Close and reveal the distribution",
        "cmp.all": "All my comparators",
        "cmp.hero.h": "Know where I stand",
        "cmp.hero.lead": "Compare <b>salaries, prices or contributions</b> within a group and know "
                         "where you stand — without anyone seeing anyone else's figure.",
        "cmp.login": "Sign in to create a comparator.",
        "cmp.levels": "brackets", "cmp.new": "New comparator",
        "cmp.field.title": "Title", "cmp.field.title.ph": "e.g. Salaries in the team",
        "cmp.field.unit": "Unit (optional)", "cmp.field.unit.ph": "e.g. FCFA",
        "cmp.field.min": "Minimum", "cmp.field.max": "Maximum",
        "cmp.field.levels": "Number of brackets (2 to 10)",
        "cmp.create": "Create",
        "cmp.new.note": "You get a link to share. Everyone submits their figure (encrypted), and at "
                        "closing Kaddu reveals only how many people per bracket.",
        # --- Coffre-fort d'alertes (alr.*) ---
        "alr.title": "Alert vault",
        "alr.view.note": "An alert stays <b>invisible as long as it's alone</b>. It only appears when",
        "alr.people": "people",
        "alr.view.note2": "independently report the same target. You are never the lone reporter.",
        "alr.threshold.label": "Reveal threshold", "alr.concordant": "matching alerts",
        "alr.evaluated": "Evaluated", "alr.open": "Open",
        "alr.reached": "Targets that reached the threshold",
        "alr.signal.note": "A signal, not a verdict. This case must be handed to a trusted third "
                           "party / the appropriate channel. Reporters stay anonymous.",
        "alr.none.reached": "No target reached the threshold.",
        "alr.none.revealed": "No alert is revealed.",
        "alr.deposited": "Alerts filed (content invisible)",
        "alr.eval.confirm": "Evaluate the register? Only targets reaching the threshold will be revealed.",
        "alr.eval.btn": "Evaluate (reveal what passes the threshold)",
        "alr.eval.note": "Even you, the organizer, see nothing before evaluation — and nothing about "
                         "targets below the threshold.",
        "alr.deposit.h": "File an alert",
        "alr.login": "Sign in to file an alert (one per person).",
        "alr.already": "You have already filed an alert in this register. Thank you.",
        "alr.full": "Maximum number of alerts reached.",
        "alr.whom": "Who are you reporting?",
        "alr.deposit.btn": "Encrypt and file",
        "alr.deposit.note1": "Your choice is encrypted. Until",
        "alr.deposit.note2": "people have named the same target, it stays completely invisible. No "
                             "tool guarantees absolute safety: in case of immediate danger, contact "
                             "emergency services or someone you trust.",
        "alr.all": "All my registers",
        "alr.hero.h": "Report without being alone",
        "alr.hero.lead": "Corruption, harassment, abuse of authority: an alert stays invisible as "
                         "long as one person carries it. It only appears when several people report "
                         "the same target, independently.",
        "alr.login.open": "Sign in to open a register.",
        "alr.disclaimer": "A register is opened by a <b>trusted third party</b> (union, NGO, "
                          "mediator). Targets are a list of roles/functions, not a free text field. "
                          "Kaddu reveals a collective signal — it does not pass judgment.",
        "alr.threshold.short": "Threshold",
        "alr.open.h": "Open a register",
        "alr.field.title": "Title", "alr.field.title.ph": "e.g. Anti-corruption reporting — town hall of X",
        "alr.field.ctx": "Context (optional)", "alr.field.ctx.ph": "e.g. reserved for service users",
        "alr.field.threshold": "Reveal threshold (2 to 10)",
        "alr.field.targets": "Possible targets — one per line (roles / functions)",
        "alr.field.targets.ph": "Counter agent A&#10;Service head B&#10;Manager C",
        "alr.open.btn": "Open the register",
        "alr.open.note": "You get a link to share. Each person files at most one alert. At "
                         "evaluation, only targets that reached the threshold appear — the others reveal nothing.",
        # --- Lot 1 : navigation, comptes, communauté, idées, vote, partage ---
        "nav.back": "Back", "nav.home": "Home",
        "auth.email": "Email", "auth.email.ph": "you@example.com",
        "auth.pw": "Password", "auth.pw.ph": "Your password", "auth.pw.min": "6 characters minimum",
        "auth.no_account": "No account yet?", "auth.have_account": "Already registered?",
        "auth.new_account": "New account", "auth.join_h": "Join the community",
        "auth.join_p": "An account lets you take part in the public square, comment and suggest "
                       "ideas. Free, and your vote always stays secret.",
        "auth.name": "Display name", "auth.name.ph": "e.g. Awa D.",
        "auth.signup.btn": "Create my account",
        "comm.h": "The Kaddu community",
        "comm.lead": "Discover votes open to the public, take part and exchange.",
        "comm.create": "Create a vote", "comm.closed": "Closed", "comm.open": "Open",
        "comm.votes": "vote(s)",
        "comm.empty": "No public vote yet.",
        "comm.empty2": "Be the first: create a vote and tick « Make public » so it shows up here.",
        "idea.h": "Suggest, vote, push to the top",
        "idea.lead": "An idea for your community or for Kaddu? Share it. The best-rated rise to the top.",
        "idea.your": "Your idea", "idea.your.ph": "e.g. A digital savings circle for our cooperative",
        "idea.body": "Details (optional)", "idea.body.ph": "Explain in a few words…",
        "idea.publish": "Post the idea",
        "idea.login": "Sign in to suggest an idea and vote.",
        "idea.for": "For", "idea.against": "Against", "idea.by": "by",
        "idea.empty": "No ideas yet. Post the first one!",
        "idea.back": "Back to the community",
        "creer.h": "Create a vote",
        "creer.sub": "A unique encryption key will be generated for this vote.",
        "creer.title": "Vote title", "creer.title.ph": "e.g. Association general assembly 2026",
        "creer.q": "The question", "creer.q.ph": "e.g. Who should we elect as president?",
        "creer.choices": "The choices", "creer.choice": "Choice", "creer.del": "Remove",
        "creer.add": "Add a choice",
        "creer.public": "Make this vote <b>public</b>",
        "creer.public.note": "It will appear on the public square. Votes stay secret.",
        "creer.generate": "Generate the vote",
        "vote.closed": "This vote is closed. Thank you!",
        "vote.see_result": "See the result",
        "vote.already": "You have already voted on this device.",
        "vote.already2": "Your ballot is sealed. Thank you for taking part.",
        "vote.token_bad": "This vote is members-only. Use the <b>personal link</b> that was sent to "
                          "you — it works only once. If it doesn't work, it has <b>already been used to vote</b>.",
        "vote.seal": "Seal my vote",
        "vote.seal_note": "Your choice will be encrypted before being stored. No one will be able to read it.",
        "vote.discussion": "Discussion",
        "vote.no_comments": "No comments yet. Start the discussion!",
        "vote.comment_ph": "Your comment…", "vote.comment_btn": "Comment",
        "vote.login_link": "Sign in", "vote.login_link2": "to join the discussion.",
        "res.title": "Result",
        "res.pending": "Vote in progress. The result will appear after the organizer closes it.",
        "res.voted": "person(s) have already voted.",
        "res.pending2": "Totals stay encrypted until closing — secrecy is preserved even during the vote.",
        "res.none": "No vote was recorded.",
        "res.final_pre": "Final tally over", "res.final_post": "vote(s).",
        "res.wins": "wins", "res.proof": "confidentiality proof",
        "res.proof2": "These totals were obtained by adding up the <b>encrypted</b> ballots, then "
                      "decrypting only the sum. No individual vote was read.",
        "merci.title": "Vote recorded", "merci.h": "Your vote is sealed",
        "merci.p": "It has been encrypted and recorded. No one — not even the organizer — can know "
                   "what you chose.",
        "merci.b1": "Encrypted ballot", "merci.b2": "Anonymous", "merci.result": "See the result page",
        "join.h": "Join a vote", "join.sub": "Paste the link you received, or enter the vote code.",
        "join.field": "Link or code", "join.ph": "e.g. https://…/v/aB3xY  or  aB3xY",
        "join.continue": "Continue",
        "err.oops": "Oops", "err.home": "Back to home",
        "partage.title": "Vote created", "partage.created": "Vote created",
        "partage.scan": "Have this code scanned, or share the link below.",
        "partage.copy": "Copy", "partage.copied": "Copied", "partage.share": "Share…",
        "partage.direct": "Or share directly:", "partage.email": "Email", "partage.done": "Done",
        "partage.mail_subj": "Kaddu vote: ",
        "partage.msg_pre": "Take part in the vote « ",
        "partage.msg_post": " » on Kaddu — a 100% secret vote: ",
        "partage.msg_post_short": " » on Kaddu — 100% secret",
        "partage.admin_h": "Your private organizer link",
        "partage.admin_p": "Keep this link for yourself. It lets you <b>track participation</b> and "
                           "<b>close the vote</b> to reveal the result. Don't share it with voters.",
        "partage.admin_btn": "Open my dashboard",
        # --- Lot 2 : tontines + appels d'offres (listes/création) ---
        "tont.h": "Your tontines",
        "tont.lead": "A <b>tamper-proof ledger</b>: contributions, order of beneficiaries and proofs "
                     "— each entry is sealed by a fingerprint linked to the previous one.",
        "tont.login": "Sign in to create and manage a tontine.",
        "tont.members": "members", "tont.done": "Finished", "tont.round": "Round",
        "tont.new": "New tontine",
        "tont.name": "Tontine name", "tont.name.ph": "e.g. Grand-Yoff mothers' tontine",
        "tont.amount": "Amount per round (FCFA, optional)", "tont.amount.ph": "e.g. 10000",
        "tont.freq": "Frequency (optional)", "tont.freq.ph": "e.g. every month",
        "tont.members_lbl": "Members — one per line, in order of beneficiaries",
        "tont.validation": "Contribution validation",
        "tont.mode_simple": "<b>Simple</b> — the organizer marks the contributions (small trusted group)",
        "tont.mode_p2p": "<b>Double validation (P2P)</b> — the member confirms « I paid » AND the "
                         "beneficiary confirms « I received ». The organizer can no longer validate "
                         "alone. Each member gets a private link.",
        "tont.create": "Create the tontine",
        "tont.note": "The money flows between you (mobile money, hand to hand). Kaddu only keeps the "
                     "<b>tamper-proof ledger</b>: who contributed, whose turn it is, and the proof "
                     "that nothing was changed.",
        "off.h": "Your tenders",
        "off.lead": "Anti-corruption: each bid is <b>sealed</b> at submission (fingerprint of the "
                    "amount + secret word). No one — not even the organizer — sees the amounts before opening.",
        "off.login": "Sign in to create and manage a tender.",
        "off.high": "highest-bid (highest amount)", "off.low": "lowest-bid (lowest amount)",
        "off.st_reveal": "Open (reveal)", "off.st_open": "Submissions open",
        "off.new": "New tender",
        "off.title": "Title", "off.title.ph": "e.g. Supply of 100 tables for the school",
        "off.desc": "Description (optional)", "off.desc.ph": "Details, criteria, deadline…",
        "off.type": "Tender type",
        "off.mode_reveal": "<b>Classic (sealed)</b> — bids are opened at the end; everyone reveals their amount.",
        "off.mode_fhe": "<b>Encrypted (FHE)</b> — the winner is computed on the <b>encrypted</b> bids. "
                        "<b>Losers never reveal</b> their price. (Lowest-bid.)",
        "off.criterion": "Winning criterion",
        "off.crit_low": "Lowest-bid — the <b>lowest</b> amount wins",
        "off.crit_high": "Highest-bid — the <b>highest</b> amount wins",
        "off.grid": "Price grid: bidders will propose a price on this grid (from min to max, by "
                    "step). 2 to 30 levels.",
        "off.pmin": "Min price (FCFA)", "off.pmax": "Max price (FCFA)", "off.pstep": "Step (FCFA)",
        "off.deadline": "Submission deadline (optional)",
        "off.deadline_note": "After this date, no more bids are accepted and the count opens "
                             "automatically. The timing becomes indisputable.",
        "off.minbids": "Minimum number of bids (optional)",
        "off.minbids_note": "Below this number at closing, the tender is cancelled (no winner) — "
                            "guarantees real competition.",
        "off.invite": "<b>By invitation</b> — only listed companies can submit (1 private link each, "
                      "one bid only). Blocks fake bids and duplicates.",
        "off.invites": "Invited companies (one per line)",
        "off.create": "Create the tender",
        # --- Tontine (tableau de bord) ---
        "tdet.back": "My tontines", "tdet.kicker": "Tontine", "tdet.round_unit": "round",
        "tdet.finished": "Tontine finished — all rounds are done",
        "tdet.benef": "Beneficiary this round",
        "tdet.ledger_ok": "Ledger intact", "tdet.ledger_bad": "Ledger tampered!",
        "tdet.fingerprint": "Ledger fingerprint",
        "tdet.settle_h": "Final settlement", "tdet.dissolved_tag": "tontine dissolved",
        "tdet.settle_note": "Net = received − contributed. To settle between members (outside the "
                            "app, mobile money). Sealed in the ledger.",
        "tdet.left": "left", "tdet.contributed": "contributed", "tdet.received": "received",
        "tdet.owes": "owes", "tdet.owed": "is owed", "tdet.uptodate": "settled",
        "tdet.dissolve_vote": "Dissolution vote in progress",
        "tdet.dissolve_p": "Proposal to <b>stop the tontine</b>. Members vote in <b>secret</b>; you "
                           "(organizer) don't vote.",
        "tdet.turn_req": "Turn request in progress",
        "tdet.turn_p": "asks to take the pot this round. Members vote in <b>secret</b>; you "
                       "(organizer) don't vote.",
        "tdet.votes_cast": "vote(s) cast.",
        "tdet.close_confirm": "Close the vote and count (FHE tally)?",
        "tdet.close_btn": "Close the vote & count",
        "tdet.members_h": "Members & contributions",
        "tdet.receives": "receives this round", "tdet.validated": "validated",
        "tdet.member": "member", "tdet.benef_short": "benef", "tdet.mark_paid": "Mark contributed",
        "tdet.pending": "pending",
        "tdet.next_confirm": "Not all members are validated yet. Move to the next round anyway?",
        "tdet.close_round": "Close this round & go to the next", "tdet.next_round": "Go to the next round",
        "tdet.links_h": "Members' private links",
        "tdet.links_p": "Send each member <b>their</b> link (via WhatsApp). Everyone confirms their "
                        "own contributions — you can no longer validate for them.",
        "tdet.manage_h": "Manage",
        "tdet.manage_p": "Removing a member computes and seals their settlement (owed / debt). "
                         "Stopping the tontine goes through a member vote.",
        "tdet.remove_confirm": "Remove this member from the tontine?", "tdet.remove": "Remove",
        "tdet.dissolve_confirm": "Stop the tontine? Members will vote in secret.",
        "tdet.dissolve_btn": "Propose stopping the tontine (member vote)",
        "tdet.ledger_h": "Ledger (append-only)",
        "tdet.ledger_p": "Each entry is sealed by a fingerprint linked to the previous one. "
                         "Impossible to change the past without breaking the chain.",
        "tdet.k_contribution": "contribution", "tdet.k_member_paid": "the member confirmed paying",
        "tdet.k_benef_received": "the beneficiary confirmed receiving",
        "tdet.k_payout": "payout to the beneficiary", "tdet.k_turn_granted": "turn request GRANTED",
        "tdet.k_turn_denied": "turn request denied", "tdet.k_member_left": "a member left",
        "tdet.k_dissolved": "TONTINE DISSOLVED (member vote)", "tdet.k_dissolve_denied": "dissolution denied",
        # --- Tontine (page membre) ---
        "tmem.title": "My tontine", "tmem.hello": "Hello", "tmem.finished": "This tontine is finished.",
        "tmem.dissolve_h": "Dissolution vote",
        "tmem.dissolve_p": "The organizer proposes to <b>stop the tontine</b>. The group decides by a "
                           "<b>secret vote</b> (the organizer doesn't vote).",
        "tmem.turn_p": "asks to take the pot this round. The group decides by a <b>secret vote</b> "
                       "(the organizer doesn't vote).",
        "tmem.your_req": "This is your request — awaiting the other members' vote.",
        "tmem.yes": "Yes, grant", "tmem.no": "No",
        "tmem.vote_note": "Your vote is <b>encrypted</b>: no one will know what you chose, only the "
                          "total will be revealed.",
        "tmem.voted": "You voted (secret)",
        "tmem.request_p": "Urgent need? You can ask to take the pot this round — the other members "
                          "will vote (secret vote).",
        "tmem.request_btn": "Ask to take this round",
        "tmem.your_turn": "It's your turn — you receive the pot",
        "tmem.confirm_h": "Confirm the contributions received",
        "tmem.confirm_p": "Click « I received » for each member who paid you. A contribution is only "
                          "<b>validated</b> if the member confirmed « paid » AND you « received ».",
        "tmem.paid_ok": "confirmed paying", "tmem.paid_no": "hasn't confirmed yet",
        "tmem.received": "received", "tmem.i_received": "I received",
        "tmem.you_paid": "You confirmed paying for this round",
        "tmem.await_benef": "Awaiting the beneficiary's confirmation to validate definitively.",
        "tmem.did_you_pay": "Did you pay your contribution to", "tmem.the_benef": "the beneficiary",
        "tmem.this_round": "for this round?", "tmem.i_paid": "I paid my contribution",
        "tmem.money_note": "The money is paid outside the app (mobile money). Here you only confirm.",
        "tmem.done": "Tontine finished — thank you!",
        "tmem.leave_confirm": "Leave the tontine? Your settlement will be computed and sealed in the ledger.",
        "tmem.leave": "Leave the tontine", "tmem.see_ledger": "See the public ledger",
        # --- Admin (tableau de bord d'un vote) ---
        "adm.title": "Dashboard", "adm.owner": "Organizer", "adm.votes": "vote(s) received",
        "adm.closed": "Closed", "adm.open": "Open", "adm.result_visible": "result visible",
        "adm.ongoing": "in progress", "adm.gen_link": "General link to share with voters",
        "adm.limit": "Limit to your members (1 vote each)",
        "adm.tokens_p": "personal link(s). Send <b>a different one</b> to each member: each link "
                        "votes <b>only once</b>.",
        "adm.voted_tag": "voted",
        "adm.default_p": "By default, anyone with the general link can vote. For a serious ballot, "
                         "generate a <b>unique link per member</b>: each can only vote once.",
        "adm.howmany": "How many?", "adm.generate": "Generate",
        "adm.max_pre": "Maximum", "adm.max_post": "voters in total for this vote.",
        "adm.close_confirm": "Close the vote and reveal the result? This action is final.",
        "adm.close_btn": "Close the vote and reveal the result",
        "adm.close_note": "While the vote is open, even you see no result — only the <b>number</b> of voters.",
        # --- Offre (invitation) ---
        "oinv.title": "Submit a bid", "oinv.invite": "Invitation",
        "oinv.closed": "Submissions are closed for this tender.", "oinv.see": "See the tender",
        "oinv.used": "A bid has already been submitted with this link. One bid per company.",
        "oinv.deposit_h": "Submit your bid",
        "oinv.fhe_note": "Your price is <b>encrypted</b> (FHE): no one, not even the organizer, sees "
                         "it. If you don't win, it stays <b>secret forever</b>. Choose a value from the grid.",
        "oinv.classic_note": "Your amount is <b>not</b> stored: only a fingerprint is. Note your "
                             "<b>amount</b> and your <b>secret word</b> carefully for the reveal.",
        "oinv.company": "Company", "oinv.price_grid": "Your price (a value from the grid)",
        "oinv.amount": "Your amount (FCFA, integer)", "oinv.amount.ph": "e.g. 850000",
        "oinv.secret": "Secret word (keep it)", "oinv.secret.ph": "e.g. lion2026",
        "oinv.deposit_btn": "Submit my bid",
        # --- Offre (tableau de bord) ---
        "odet.tender": "Tender", "odet.back": "My tenders",
        "odet.kicker_fhe": "Encrypted tender (FHE)", "odet.kicker_sealed": "Sealed tender",
        "odet.fhe_sub": "Blind auction — lowest-bid. The winner is computed on the <b>encrypted</b> "
                        "bids: losers <b>never</b> reveal their price.",
        "odet.criterion": "Criterion", "odet.cancelled": "Cancelled — not enough bids",
        "odet.subs_closed": "Submissions closed", "odet.reveal_phase": "reveal phase",
        "odet.n_sealed": "bid(s) submitted", "odet.deadline": "Deadline",
        "odet.min_pre": "Minimum required", "odet.min_post": "bid(s) — otherwise the tender is cancelled.",
        "odet.invite_only": "By invitation only.",
        "odet.invites_h": "Private links for invited companies",
        "odet.invites_p": "Send each company <b>their</b> link. One bid per link.",
        "odet.submitted": "submitted", "odet.pending": "pending",
        "odet.grid": "Accepted price grid (choose one of these values)",
        "odet.invite_notice": "<b>By-invitation</b> tender: invited companies submit their bid via "
                              "their <b>private link</b>.",
        "odet.deposit_fhe_h": "Submit an encrypted bid",
        "odet.deposit_fhe_p": "Your price is <b>encrypted</b> (FHE): no one, not even the organizer, "
                              "sees it. If you don't win, it stays <b>secret forever</b>. ⚠️ Note "
                              "your <b>amount</b> and <b>secret word</b> to prove your win.",
        "odet.your_name": "Your name / your company", "odet.your_name.ph": "e.g. Diallo Company",
        "odet.your_price": "Your price (choose a value from the grid)",
        "odet.secret": "Secret word (keep it)", "odet.secret.ph": "e.g. lion2026",
        "odet.encrypt_deposit": "Encrypt & submit my bid",
        "odet.bids_h": "Submitted bids", "odet.encrypted_tag": "encrypted", "odet.no_bids": "No bid yet.",
        "odet.close_fhe_confirm": "Close and count (FHE computation of the winning price)?",
        "odet.close_fhe_btn": "Close & count (FHE)",
        "odet.winning_price": "Winning price (computed on the encrypted bids)", "odet.winner": "Winner",
        "odet.winner_declare": "The winner can now come forward below.",
        "odet.losers_secret": "The losers' prices were <b>never</b> decrypted — they stay secret forever.",
        "odet.no_winner": "No valid bid — no winner",
        "odet.prove_h": "Are you the winner? Prove it",
        "odet.prove_p": "If you offered the winning price, enter it with your secret word. The system "
                        "checks your fingerprint. Losers do nothing — their price stays secret.",
        "odet.the_winning_price": "The winning price", "odet.secret_word": "Your secret word",
        "odet.confirm_win": "Confirm my win & verify",
        "odet.deposit_sealed_h": "Submit a sealed bid",
        "odet.deposit_sealed_p": "Your amount is <b>not</b> stored: only a fingerprint is. ⚠️ Note "
                                 "your <b>amount</b> and <b>secret word</b> — you'll need them to "
                                 "reveal after closing.",
        "odet.your_amount": "Your amount (FCFA, integer)", "odet.your_amount.ph": "e.g. 850000",
        "odet.seal_btn": "Seal my bid", "odet.sealed_tag": "sealed",
        "odet.close_sealed_confirm": "Close submissions and open the reveal?",
        "odet.close_sealed_btn": "Close submissions",
        "odet.reveal_h": "Reveal your bid",
        "odet.reveal_p": "Enter exactly the same amount and secret word as at submission. The system "
                         "checks the fingerprint: cheating is impossible.",
        "odet.reveal_amount": "Your amount (FCFA)", "odet.secret_word2": "Secret word",
        "odet.reveal_btn": "Reveal & verify", "odet.results_h": "Results", "odet.winner_tag": "winner",
        "odet.no_reveal": "No bid revealed yet. Bidders must reveal above.",
        "odet.awaiting_reveal": "Awaiting reveal",
        "odet.js_in": "in", "odet.js_days": "d", "odet.js_hours": "h", "odet.js_reached": "deadline reached",
        # --- Guide ---
        "gd.kicker": "Guide",
        "gd.lead": "Kaddu isn't just a voting tool: it's a trust toolkit for your communities. They "
                   "all rest on the same principle — secrecy guaranteed by <b>mathematics</b> "
                   "(Zama's FHE encryption), not by trust. No technical skills.",
        "gd.services": "5 services online",
        "gd.choose": "Choose the tool that fits your need. Each takes a few minutes, free, no account "
                     "to take part.",
        "gd.vote_h": "Decide together, in secret",
        "gd.demo_alt": "Demo: create a vote, share, vote, result",
        "gd.v1t": "Create the vote", "gd.v1d": "A title, a question, choices. Kaddu gives you a link + a QR code.",
        "gd.v2t": "Share on WhatsApp",
        "gd.v2d": "Everyone opens the link, chooses and seals their ballot — encrypted instantly, invisible to all.",
        "gd.v3t": "Close and reveal",
        "gd.v3d": "The result is computed on the encrypted ballots then shown, verifiable by all.",
        "gd.vote_tip": "Tip: generate a <b>unique link per member</b> so each votes only once.",
        "gd.tont_h": "Save together, with no all-powerful manager",
        "gd.t1t": "Create the tontine",
        "gd.t1d": "The members, the amount per round, the order. Each member gets their private link.",
        "gd.t2t": "Double validation each round",
        "gd.t2d": "A payment only counts if the <b>payer</b> AND the <b>beneficiary</b> confirm. The "
                  "manager can't falsify anything alone.",
        "gd.t3t": "Tamper-proof ledger",
        "gd.t3d": "Each operation is sealed in a chain of fingerprints: impossible to rewrite "
                  "history. The money flows <b>outside the app</b> — Kaddu is only the referee.",
        "gd.t4t": "Priority decided in secret",
        "gd.t4d": "A member asks to go earlier? The others decide by an <b>encrypted vote</b> — no "
                  "one sees who voted what.",
        "gd.tont_btn": "Open tontines",
        "gd.off_h": "Award without corruption",
        "gd.o1t": "Create the tender",
        "gd.o1d": "Two modes: <b>sealed</b> (amounts stay hidden until opening) or <b>encrypted</b> (blind auction).",
        "gd.o2t": "Everyone submits their bid",
        "gd.o2d": "The bid is sealed at submission: no one, not even the organizer, sees the prices before the time.",
        "gd.o3t": "The winner, proven",
        "gd.o3d": "In encrypted mode, the winner is computed <b>on the encrypted bids</b>: losers "
                  "<b>never</b> reveal their price.",
        "gd.off_btn": "Open tenders",
        "gd.idea_h": "Surface the best ideas",
        "gd.idea_p": "Anyone posts an idea for the community or for Kaddu. Members vote, and the "
                     "best-rated rise to the top. Simple and transparent.",
        "gd.idea_btn": "Open the idea wall",
        "gd.place_h": "Discover and take part",
        "gd.place_p": "Browse votes open to the public, take part and exchange with the Kaddu community.",
        "gd.place_btn": "See the public square",
        "gd.why_h": "Why it's truly secret",
        "gd.why_p": "Your data is <b>encrypted</b> the moment you click. Kaddu computes (counts "
                    "votes, determines a winner…) <b>without ever opening it</b>, thanks to Zama's "
                    "FHE encryption. Neither the organizer, nor the server, nor a hacker can read an "
                    "individual piece of data — only the final result is revealed.",
        "gd.faq_h": "Frequently asked questions",
        "gd.a1": "No. The ballot is encrypted on the spot; the organizer only sees the final result.",
        "gd.q2": "Does Kaddu touch the tontine money?",
        "gd.a2": "No. The money flows <b>outside the app</b> (mobile money, cash…). Kaddu is only the "
                 "impartial referee and the tamper-proof ledger.",
        "gd.q3": "Do I need an account to take part?",
        "gd.a3": "No. A simple link is enough. The account is only for organizing (creating votes, "
                 "managing a tontine, suggesting ideas).",
        "gd.a4": "Yes, entirely free.",
        "gd.see_comm": "See the community",
        # --- Mentions légales ---
        "ml.updated": "Last updated", "ml.editor_h": "Site publisher",
        "ml.editor_p": "The <b>Kaddu</b> service is published by Pape Alamine Sarr, in Dakar (Senegal).",
        "ml.contact": "Contact",
        "ml.editor_note": "If Kaddu is run by an association or an organization, replace this section "
                          "with its name, address and, where applicable, its registration number.",
        "ml.pub_h": "Publication director", "ml.host_h": "Hosting",
        "ml.host_p": "The application is hosted by <b>Render Services, Inc.</b> (render.com) and its "
                     "database by <b>Neon, Inc.</b> (neon.tech). The application servers are located "
                     "in the United States (Oregon region).",
        "ml.ip_h": "Intellectual property",
        "ml.ip_p": "The name « Kaddu », the visual identity and the site content are the property of "
                   "their publisher. Fully homomorphic encryption (FHE) is provided by <b>Zama</b>'s "
                   "technology (Concrete library), under its own licenses.",
        "ml.resp_h": "Liability",
        "ml.resp_p": "Kaddu is provided « as is », with no guarantee of continuous availability. The "
                     "publisher strives to ensure the accuracy of information but cannot be held "
                     "responsible for any use made of it by vote organizers.",
        "ml.model_note": "This document is a basic template. For official use, have it adapted to "
                         "your situation and applicable regulations.",
        # --- Confidentialité ---
        "pc.title": "Privacy",
        "pc.intro": "Kaddu is built around a simple principle: <b>collect the strict minimum</b>. "
                    "There is no account to create, no profile, no advertising, no commercial tracking.",
        "pc.secret_h": "The secrecy of your vote",
        "pc.secret_p": "Each ballot is <b>encrypted on your device or on the server before "
                       "storage</b>, thanks to Zama's fully homomorphic encryption (FHE). The tally "
                       "is computed on encrypted data: neither the server, nor the organizer, nor "
                       "the publisher can read an individual vote. Only the <b>total result</b> is "
                       "revealed, once the vote is closed.",
        "pc.data_h": "Data processed",
        "pc.data_p": "To run a vote, Kaddu keeps: the <b>title, question and choices</b> you enter; "
                     "the <b>encrypted ballots</b>; and, if you enable member links, <b>anonymous "
                     "tokens</b> (no identity is associated). A small <b>technical cookie</b> is "
                     "placed on the voter's device to prevent double voting — it contains no "
                     "personal data. Like any site, the host may keep temporary <b>technical "
                     "logs</b> (IP address, timestamp) for security.",
        "pc.not_h": "What Kaddu does not do",
        "pc.not_p": "No request for name, email or phone to vote. No selling of data. No advertising "
                    "cookies or third-party trackers.",
        "pc.keep_h": "Retention",
        "pc.keep_p": "A vote's data is kept for the duration of its organization. You can request "
                     "the deletion of a vote you created by writing to us.",
        "pc.sub_h": "Technical subcontractors",
        "pc.sub_p": "The application and its database are hosted by Render and Neon (see the",
        "pc.sub_p2": "), which act only as hosting providers.",
        "pc.rights_h": "Your rights & contact",
        "pc.rights_p": "You can request access, correction or deletion of data concerning you by writing to",
        # --- Messages flash (serveur) ---
        "flash.1": "Give a title, a question and at least 2 choices.",
        "flash.2": "This vote has reached its maximum capacity.",
        "flash.3": "Choose an option to vote.",
        "flash.4": "This link has already been used to vote.",
        "flash.5": "Code not found. Check and try again.",
        "flash.6": "Name, valid email and password (6 characters min.) required.",
        "flash.7": "An account already exists with this email. Please sign in.",
        "flash.8": "Incorrect email or password.",
        "flash.9": "Give a name and at least 2 members (one per line).",
        "flash.10": "Voting capacity reached.",
        "flash.11": "Give the tender a title.",
        "flash.12": "Provide a valid min price, max price and step for the encrypted auction.",
        "flash.13": "Submissions are closed.",
        "flash.14": "This tender is by invitation: use your valid private link.",
        "flash.15": "This invitation has already been used to submit a bid.",
        "flash.16": "Name, amount (positive integer) and secret word are required.",
        "flash.17": "Your amount must be an exact value from the price grid shown.",
        "flash.18": "This name has already submitted a bid.",
        "flash.19": "Bid sealed. Keep your amount + secret word for the reveal. ",
        "flash.20": "A deadline is set: the count will open automatically at the deadline.",
        "flash.21": "Tender closed: fewer than %d bid(s) received, no winner.",
        "flash.22": "The reveal opens after submissions close.",
        "flash.23": "No winner (no valid bid).",
        "flash.24": "The winner is already confirmed.",
        "flash.25": "To declare yourself the winner, enter EXACTLY the winning price shown.",
        "flash.26": "Name + amount + secret word don't match any submitted bid.",
        "flash.27": "Win confirmed and verified! The others' prices stay secret.",
        "flash.28": "No bid under this name.",
        "flash.29": "This bid is already revealed.",
        "flash.30": "Amount + secret word don't match the sealed bid.",
        "flash.31": "Bid revealed and verified.",
        "flash.32": "Give the pool a title.",
        "flash.33": "This pool is closed: you can no longer add a figure.",
        "flash.34": "Enter a positive integer amount.",
        "flash.35": "The amount exceeds the allowed maximum (%d).",
        "flash.36": "You have already contributed to this pool.",
        "flash.37": "Maximum number of participants reached for this pool.",
        "flash.38": "Your figure has been encrypted and added. No one can read it — only the total will be revealed.",
        "flash.39": "Give a title and a valid range (max greater than min).",
        "flash.40": "This comparator is closed.",
        "flash.41": "Enter your figure.",
        "flash.42": "You have already answered this comparator.",
        "flash.43": "Maximum number of participants reached.",
        "flash.44": "Your answer is encrypted. Your bracket: %s–%s %s. No one sees your exact figure.",
        "flash.45": "Comparator closed: the distribution was computed on the encrypted data.",
        "flash.46": "Give a title and at least 2 targets (one per line).",
        "flash.47": "This register is closed: you can no longer report.",
        "flash.48": "Choose a target from the list.",
        "flash.49": "You have already filed an alert in this register.",
        "flash.50": "Maximum number of alerts reached for this register.",
        "flash.51": "Evaluation complete: %d target(s) reached the threshold. The others revealed nothing.",
        "flash.52": "Evaluation complete: no target reached the threshold. No alert is revealed.",
        "flash.recu": "Receipt: fingerprint %s… filed on %s — keep it, it proves your submission.",
        "flash.53": "The price grid must have between 2 and 30 levels (adjust the step or the min–max range).",
        "flash.54": "Encrypted bid submitted. If you don't win, your price stays secret forever. "
                    "Keep your amount + secret word to prove your win. ",
        "flash.55": "Pool closed: the total was computed on the encrypted data, without any individual "
                    "figure ever being decrypted.",
        "flash.56": "Your alert is encrypted. Until the threshold is reached, no one — not even the "
                    "organizer — can see it. You are never the lone reporter.",
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
    """Choix explicite (session) > détection automatique. Kaddu vise le monde :
    le français est servi aux visiteurs francophones (Afrique francophone, France,
    diaspora), l'anglais est la langue par défaut pour tous les autres."""
    chosen = session.get("lang")
    if chosen in SUPPORTED_LANGS:
        return chosen
    accept = (request.headers.get("Accept-Language") or "").lower()
    for part in accept.replace(" ", "").split(","):
        code = part.split(";")[0][:2]
        if code == "fr":      # navigateur francophone -> français
            return "fr"
        if code == "en":      # navigateur anglophone -> anglais
            return "en"
    return "en"               # défaut international : anglais


@app.context_processor
def inject_i18n():
    lang = pick_lang()

    def t(key, default=""):
        if lang == "fr":
            return Markup(default)
        return Markup(TRANSLATIONS.get(lang, {}).get(key, default))

    # Exposé sous le nom "tr" (et pas "t") pour ne pas entrer en collision avec les
    # variables "t" (objet tontine / appel d'offres) passées par certaines pages.
    return {"LANG": lang, "tr": t}


def t_srv(key, default_fr):
    """Traduction côté serveur, pour les messages flash. Même logique que le `tr`
    des gabarits : en français on renvoie le texte source ; sinon la traduction
    (repli sur le français si la clé manque)."""
    lang = pick_lang()
    if lang == "fr":
        return default_fr
    return TRANSLATIONS.get(lang, {}).get(key, default_fr)


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
                mode          TEXT NOT NULL DEFAULT 'reveal',
                price_min     INTEGER NOT NULL DEFAULT 0,
                price_step    INTEGER NOT NULL DEFAULT 0,
                n_levels      INTEGER NOT NULL DEFAULT 0,
                winning_level INTEGER,
                winning_price INTEGER,
                winner_name   TEXT,
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
        # Offre chiffrée (enchère aveugle FHE) : 1 bit chiffré par palier de prix.
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS bid_levels (
                bid_id INTEGER NOT NULL,
                level  INTEGER NOT NULL,
                blob   {BLOB_TYPE} NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_bid_levels ON bid_levels(bid_id, level)")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS tender_invites (
                id        {ID_PK},
                tender_id INTEGER NOT NULL,
                name      TEXT NOT NULL,
                token     TEXT NOT NULL,
                used      INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_tinvites ON tender_invites(tender_id)")

        # --- Mise en commun protégée (somme homomorphe) ----------------------
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS pools (
                id            {ID_PK},
                owner_user_id INTEGER NOT NULL,
                title         TEXT NOT NULL,
                question      TEXT NOT NULL DEFAULT '',
                closed        INTEGER NOT NULL DEFAULT 0,
                total         INTEGER,
                n_contrib     INTEGER NOT NULL DEFAULT 0,
                created_at    INTEGER NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS pool_items (
                pool_id     INTEGER NOT NULL,
                slot        INTEGER NOT NULL,
                contributor TEXT NOT NULL DEFAULT '',
                blob        {BLOB_TYPE} NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_poolitems ON pool_items(pool_id, slot)")
        # Anti-bourrage : une contribution par compte (sans lier le montant au compte).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pool_participants (
                pool_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (pool_id, user_id)
            )
        """)

        # --- Comparateur privé (histogramme chiffré par tranches) ------------
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS compares (
                id            {ID_PK},
                owner_user_id INTEGER NOT NULL,
                title         TEXT NOT NULL,
                unit          TEXT NOT NULL DEFAULT '',
                vmin          INTEGER NOT NULL DEFAULT 0,
                vmax          INTEGER NOT NULL DEFAULT 0,
                n_levels      INTEGER NOT NULL DEFAULT 5,
                closed        INTEGER NOT NULL DEFAULT 0,
                results       TEXT,
                created_at    INTEGER NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS compare_items (
                compare_id INTEGER NOT NULL,
                slot       INTEGER NOT NULL,
                level      INTEGER NOT NULL,
                blob       {BLOB_TYPE} NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_cmpitems ON compare_items(compare_id, level)")
        # Anti-bourrage : une réponse par compte (sans lier la valeur au compte).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS compare_participants (
                compare_id INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                PRIMARY KEY (compare_id, user_id)
            )
        """)

        # --- Coffre-fort d'alertes (révélation à seuil, FHE) -----------------
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS registers (
                id            {ID_PK},
                owner_user_id INTEGER NOT NULL,
                title         TEXT NOT NULL,
                context       TEXT NOT NULL DEFAULT '',
                threshold     INTEGER NOT NULL DEFAULT 3,
                closed        INTEGER NOT NULL DEFAULT 0,
                results       TEXT,
                created_at    INTEGER NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS register_targets (
                id          {ID_PK},
                register_id INTEGER NOT NULL,
                position    INTEGER NOT NULL,
                name        TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_rtargets ON register_targets(register_id, position)")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS register_alerts (
                register_id INTEGER NOT NULL,
                target_pos  INTEGER NOT NULL,
                slot        INTEGER NOT NULL,
                blob        {BLOB_TYPE} NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_ralerts ON register_alerts(register_id, target_pos)")
        # Empêche un même compte de signaler deux fois SANS lier le compte à sa
        # cible : on sait qu'il a signalé, jamais QUI il a visé (secret préservé).
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS register_participants (
                register_id INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                PRIMARY KEY (register_id, user_id)
            )
        """)

    # --- Migrations douces (colonnes ajoutées après coup) ---------------------
    # IMPORTANT : ces ALTER TABLE s'exécutent APRÈS la fermeture du bloc `with`
    # ci-dessus, donc APRÈS le commit qui crée les tables. Sur une base neuve,
    # une connexion ouverte avant ce commit ne verrait pas encore les tables :
    # l'ALTER échouerait et le `except: pass` masquerait l'erreur en silence,
    # laissant la base incomplète. En sortant ces boucles du `with`, les tables
    # sont déjà validées et visibles quand on ajoute les colonnes.
    _migrations = [
        ('polls',           '"public"',      "INTEGER NOT NULL DEFAULT 0"),
        ('polls',           'owner_user_id', "INTEGER"),
        ('tontines',        'mode',          "TEXT NOT NULL DEFAULT 'simple'"),
        ('tontine_members', 'member_token',  "TEXT NOT NULL DEFAULT ''"),
        ('tontine_members', 'active',        "INTEGER NOT NULL DEFAULT 1"),
        ('turn_requests',   'kind',          "TEXT NOT NULL DEFAULT 'turn'"),
        ('tenders',         'mode',          "TEXT NOT NULL DEFAULT 'reveal'"),
        ('tenders',         'price_min',     "INTEGER NOT NULL DEFAULT 0"),
        ('tenders',         'price_step',    "INTEGER NOT NULL DEFAULT 0"),
        ('tenders',         'n_levels',      "INTEGER NOT NULL DEFAULT 0"),
        ('tenders',         'winning_level', "INTEGER"),
        ('tenders',         'winning_price', "INTEGER"),
        ('tenders',         'winner_name',   "TEXT"),
        ('tenders',         'closes_at',     "INTEGER"),
        ('tenders',         'min_bids',      "INTEGER NOT NULL DEFAULT 0"),
        ('tenders',         'invite_only',   "INTEGER NOT NULL DEFAULT 0"),
        ('tenders',         'cancelled',     "INTEGER NOT NULL DEFAULT 0"),
    ]
    for table, col, ddl in _migrations:
        try:
            with closing(db()) as c2, c2:
                c2.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ddl}")
        except Exception:
            # SQLite ne supporte pas "ADD COLUMN IF NOT EXISTS" : on retente sans,
            # et si la colonne existe déjà l'erreur est sans conséquence.
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
            flash(t_srv("flash.1", "Donne un titre, une question et au moins 2 choix."))
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
                         'created_at, closed, "public", owner_user_id) VALUES (?,?,?,?,?,?,0,?,?)',
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
            flash(t_srv("flash.2", "Ce vote a atteint sa capacité maximale."))
            return page()
        try:
            choice = int(request.form.get("choice", "-1"))
        except ValueError:
            choice = -1
        if choice < 0 or choice >= len(options):
            flash(t_srv("flash.3", "Choisis une option pour voter."))
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
                    flash(t_srv("flash.4", "Ce lien a déjà servi à voter."))
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
        flash(t_srv("flash.5", "Code introuvable. Vérifie et réessaie."))
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
            flash(t_srv("flash.6", "Nom, e-mail valide et mot de passe (6 caractères min.) requis."))
            return render_template("inscription.html", name=name, email=email)
        if get_user_by_email(email):
            flash(t_srv("flash.7", "Un compte existe déjà avec cet e-mail. Connectez-vous."))
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
            flash(t_srv("flash.8", "E-mail ou mot de passe incorrect."))
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
            'FROM polls p WHERE "public" = 1 ORDER BY created_at DESC LIMIT 60').fetchall()
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
            flash(t_srv("flash.9", "Donne un nom et au moins 2 membres (un par ligne)."))
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
        flash(t_srv("flash.10", "Capacité de vote atteinte."))
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


# --- Enchère aveugle FHE (les perdants ne révèlent jamais leur prix) ----------
# Les prix sont découpés en paliers. Chaque offre est chiffrée en "thermomètre" :
# pour chaque palier j, un bit chiffré = 1 si (mon prix <= prix du palier j), sinon 0.
# À la clôture, on SOMME ces bits chiffrés par palier (moteur FHE de Kaddu). Le prix
# gagnant est le plus petit palier dont la somme >= 1 — et on ne révèle QUE ce prix.
# Les montants des perdants ne sont jamais déchiffrés.
def _tender_levels(t):
    """Liste des prix de la grille (du plus bas au plus haut)."""
    return [t["price_min"] + j * t["price_step"] for j in range(t["n_levels"])]


def _price_level(t, amount):
    """Indice de palier d'un montant, ou None s'il n'est pas exactement sur la grille."""
    if t["price_step"] <= 0 or amount < t["price_min"]:
        return None
    off = amount - t["price_min"]
    if off % t["price_step"] != 0:
        return None
    lvl = off // t["price_step"]
    return lvl if 0 <= lvl < t["n_levels"] else None


def _fhe_bid_ids(tid):
    with closing(db()) as conn:
        rows = conn.execute("SELECT id FROM bids WHERE tender_id=? ORDER BY id", (tid,)).fetchall()
    return [r["id"] for r in rows]


def _level_blobs(bid_ids, level):
    """Récupère le bit chiffré de chaque offre pour un palier donné."""
    if not bid_ids:
        return []
    with closing(db()) as conn:
        blobs = []
        for bid_id in bid_ids:
            r = conn.execute("SELECT blob FROM bid_levels WHERE bid_id=? AND level=?",
                             (bid_id, level)).fetchone()
            if r is not None:
                blobs.append(bytes(r["blob"]))
    return blobs


def _compute_winning_level(t):
    """Prix gagnant (moins-disant) SANS déchiffrer les offres perdantes.
    On monte palier par palier depuis le plus bas ; dès qu'un palier a une somme
    chiffrée >= 1, c'est le prix minimum proposé → on s'arrête (on ne va pas plus
    haut, donc on ne révèle rien de la répartition des perdants)."""
    bid_ids = _fhe_bid_ids(t["id"])
    if not bid_ids:
        return None
    for j in range(t["n_levels"]):
        count = fhe.tally(_level_blobs(bid_ids, j))
        if count >= 1:
            return j
    return None


def _bid_commitment(amount, secret):
    return hashlib.sha256(("%d|%s" % (int(amount), secret)).encode("utf-8")).hexdigest()


def _bid_hash(prev, tid, name, commitment, ts):
    payload = "%s|%s|%s|%s|%s" % (prev, tid, name, commitment, ts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tender_invites(tid):
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM tender_invites WHERE tender_id=? ORDER BY id",
                            (tid,)).fetchall()
    return [dict(r) for r in rows]


def _parse_deadline(s):
    """Convertit une date/heure de formulaire ('YYYY-MM-DDTHH:MM') en horodatage unix."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        st = time.strptime(s[:16], "%Y-%m-%dT%H:%M")
        return int(time.mktime(st))
    except Exception:
        return None


def _subs_open(t):
    """Les soumissions sont-elles encore acceptées ? (statut ouvert, non annulé, avant l'échéance)"""
    if t["status"] != "open" or t["cancelled"]:
        return False
    return t["closes_at"] is None or int(time.time()) < t["closes_at"]


def _finalize_tender(tid):
    """Clôt un appel d'offres et applique les règles : minimum d'offres puis dépouillement FHE."""
    t = dict(_tender(tid))
    n = len(_bids(tid))
    if t["min_bids"] and n < t["min_bids"]:
        with closing(db()) as conn, conn:
            conn.execute("UPDATE tenders SET status='closed', cancelled=1 WHERE id=?", (tid,))
        return
    with closing(db()) as conn, conn:
        conn.execute("UPDATE tenders SET status='closed' WHERE id=?", (tid,))
    if t["mode"] == "fhe":
        t = dict(_tender(tid))
        win_lvl = _compute_winning_level(t)
        win_price = (t["price_min"] + win_lvl * t["price_step"]) if win_lvl is not None else None
        with closing(db()) as conn, conn:
            conn.execute("UPDATE tenders SET winning_level=?, winning_price=? WHERE id=?",
                         (win_lvl, win_price, tid))


def _maybe_autoclose(t):
    """Ferme automatiquement l'appel d'offres si l'échéance est dépassée."""
    if t["status"] == "open" and t["closes_at"] and int(time.time()) >= t["closes_at"]:
        _finalize_tender(t["id"])
        return dict(_tender(t["id"]))
    return t


@app.route("/offres", methods=["GET", "POST"])
def offres():
    me = current_user()
    if request.method == "POST":
        if not me:
            return redirect(url_for("connexion", next=url_for("offres")))
        title = (request.form.get("title") or "").strip()[:140]
        description = (request.form.get("description") or "").strip()[:1000]
        direction = "high" if request.form.get("direction") == "high" else "low"
        mode = "fhe" if request.form.get("mode") == "fhe" else "reveal"
        if not title:
            flash(t_srv("flash.11", "Donne un intitulé à l'appel d'offres."))
            return render_template("offres.html", tenders=_my_tenders(me),
                                   title=title, description=description)
        price_min = price_step = n_levels = 0
        if mode == "fhe":
            # Enchère aveugle : moins-disant uniquement (le plus courant pour un marché).
            direction = "low"
            try:
                price_min = int(request.form.get("price_min") or "")
                price_max = int(request.form.get("price_max") or "")
                price_step = int(request.form.get("price_step") or "")
            except ValueError:
                price_min = price_max = price_step = -1
            if price_min < 0 or price_step <= 0 or price_max < price_min:
                flash(t_srv("flash.12", "Renseigne un prix min, un prix max et un pas valides pour l'enchère chiffrée."))
                return render_template("offres.html", tenders=_my_tenders(me),
                                       title=title, description=description)
            n_levels = (price_max - price_min) // price_step + 1
            if n_levels < 2 or n_levels > 30:
                flash(t_srv("flash.53", "La grille de prix doit compter entre 2 et 30 paliers "
                      "(ajuste le pas ou l'écart min–max)."))
                return render_template("offres.html", tenders=_my_tenders(me),
                                       title=title, description=description)
        closes_at = _parse_deadline(request.form.get("deadline"))
        try:
            min_bids = max(0, int(request.form.get("min_bids") or "0"))
        except ValueError:
            min_bids = 0
        invite_only = 1 if request.form.get("invite_only") else 0
        invited = []
        if invite_only:
            for line in (request.form.get("invites") or "").splitlines():
                nm = line.strip()[:60]
                if nm:
                    invited.append(nm)
            invited = invited[:50]
            if not invited:
                invite_only = 0  # coché mais aucune société listée → traité comme ouvert
        with closing(db()) as conn, conn:
            tid = _insert_returning_id(conn,
                "INSERT INTO tenders (owner_user_id, title, description, direction, status, "
                "mode, price_min, price_step, n_levels, created_at, closes_at, min_bids, invite_only) "
                "VALUES (?,?,?,?, 'open', ?,?,?,?,?,?,?,?)",
                (me["id"], title, description, direction, mode,
                 price_min, price_step, n_levels, int(time.time()),
                 closes_at, min_bids, invite_only))
            for nm in invited:
                conn.execute("INSERT INTO tender_invites (tender_id, name, token) VALUES (?,?,?)",
                             (tid, nm, secrets.token_urlsafe(9)))
        return redirect(url_for("offre", tid=tid))
    return render_template("offres.html", tenders=_my_tenders(me), title="", description="")


@app.route("/offre/<int:tid>")
def offre(tid):
    t = _tender(tid)
    if not t:
        abort(404)
    t = dict(t)
    t = _maybe_autoclose(t)
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
    if t["status"] == "closed" and t["mode"] != "fhe":
        revealed = [b for b in bids if b["revealed"] and b["amount"] is not None]
        revealed.sort(key=lambda b: b["amount"], reverse=(t["direction"] == "high"))
        results = revealed
    levels = _tender_levels(t) if t["mode"] == "fhe" else []
    invites = _tender_invites(tid)
    return render_template("offre.html", t=t, bids=bids, is_owner=is_owner,
                           integrity=integrity, results=results, n_sealed=len(bids),
                           levels=levels, subs_open=_subs_open(t), invites=invites,
                           invite=None, base_url=base_url())


@app.route("/offre/<int:tid>/soumettre", methods=["POST"])
def offre_soumettre(tid):
    t = _tender(tid)
    if not t:
        abort(404)
    t = _maybe_autoclose(dict(t))
    if not _subs_open(t):
        flash(t_srv("flash.13", "Les soumissions sont closes."))
        return redirect(url_for("offre", tid=tid))
    invite = None
    if t["invite_only"]:
        token = (request.form.get("token") or "").strip()
        with closing(db()) as conn:
            invite = conn.execute("SELECT * FROM tender_invites WHERE tender_id=? AND token=?",
                                  (tid, token)).fetchone()
        if not token or not invite:
            flash(t_srv("flash.14", "Cet appel d'offres est sur invitation : utilise ton lien privé valide."))
            return redirect(url_for("offre", tid=tid))
        if invite["used"]:
            flash(t_srv("flash.15", "Cette invitation a déjà servi à déposer une offre."))
            return redirect(url_for("offre", tid=tid))
    if invite:
        name = (invite["name"] or "").strip()[:60]
    else:
        name = (request.form.get("name") or "").strip()[:60]
    secret = (request.form.get("secret") or "").strip()
    try:
        amount = int(request.form.get("amount") or "")
    except ValueError:
        amount = None
    if not name or not secret or amount is None or amount < 0:
        flash(t_srv("flash.16", "Nom, montant (entier positif) et mot secret sont requis."))
        return redirect(url_for("offre", tid=tid))

    level = None
    if t["mode"] == "fhe":
        level = _price_level(t, amount)
        if level is None:
            flash(t_srv("flash.17", "Ton montant doit être une valeur exacte de la grille de prix affichée."))
            return redirect(url_for("offre", tid=tid))

    with closing(db()) as conn, conn:
        r = conn.execute("SELECT COUNT(*) c FROM bids WHERE tender_id=? AND bidder_name=?",
                         (tid, name)).fetchone()
        if r["c"] > 0:
            flash(t_srv("flash.18", "Ce nom a déjà soumis une offre."))
            return redirect(url_for("offre", tid=tid))
        last = conn.execute("SELECT hash FROM bids WHERE tender_id=? ORDER BY id DESC LIMIT 1",
                            (tid,)).fetchone()
        prev = last["hash"] if last else ""
        ts = int(time.time())
        commitment = _bid_commitment(amount, secret)
        h = _bid_hash(prev, tid, name, commitment, ts)
        bid_id = _insert_returning_id(conn,
            "INSERT INTO bids (tender_id, bidder_name, commitment, created_at, prev_hash, "
            "hash, revealed, amount) VALUES (?,?,?,?,?,?,0,NULL)",
            (tid, name, commitment, ts, prev, h))
        if t["mode"] == "fhe":
            # Thermomètre chiffré : bit(j) = 1 si (mon prix <= prix du palier j), sinon 0.
            # Le montant en clair n'est JAMAIS stocké : seuls ces bits chiffrés le sont.
            slot = min(bid_id % fhe.capacity(), fhe.capacity() - 1)
            for j in range(t["n_levels"]):
                bit = 1 if level <= j else 0
                blob = fhe.encrypt_ballot(slot, bit)
                conn.execute("INSERT INTO bid_levels (bid_id, level, blob) VALUES (?,?,?)",
                             (bid_id, j, blob))
        if invite:
            conn.execute("UPDATE tender_invites SET used=1 WHERE id=?", (invite["id"],))
    recu = (t_srv("flash.recu", "Reçu : empreinte %s… déposée le %s — garde-le, il prouve ton dépôt.")
            % (h[:16], time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))))
    if t["mode"] == "fhe":
        flash(t_srv("flash.54", "Offre chiffrée déposée. Si tu ne gagnes pas, ton prix reste secret à vie. "
              "Garde ton montant + mot secret pour prouver ta victoire. ") + recu)
    else:
        flash(t_srv("flash.19", "Offre scellée. Garde ton montant + mot secret pour la révélation. ")+ recu)
    return redirect(url_for("offre", tid=tid))


@app.route("/offre/<int:tid>/i/<token>")
def offre_invite(tid, token):
    t = _tender(tid)
    if not t:
        abort(404)
    t = _maybe_autoclose(dict(t))
    with closing(db()) as conn:
        inv = conn.execute("SELECT * FROM tender_invites WHERE tender_id=? AND token=?",
                           (tid, token)).fetchone()
    if not inv:
        abort(404)
    levels = _tender_levels(t) if t["mode"] == "fhe" else []
    return render_template("offre_invite.html", t=t, invite=dict(inv), token=token,
                           levels=levels, subs_open=_subs_open(t))


@app.route("/offre/<int:tid>/clore", methods=["POST"])
def offre_clore(tid):
    t = _tender(tid)
    if not t:
        abort(404)
    t = dict(t)
    me = current_user()
    if not me or me["id"] != t["owner_user_id"]:
        abort(403)
    if t["closes_at"] and int(time.time()) < t["closes_at"]:
        flash(t_srv("flash.20", "Une échéance est fixée : le dépouillement s'ouvrira automatiquement à la date limite."))
        return redirect(url_for("offre", tid=tid))
    _finalize_tender(tid)
    if dict(_tender(tid))["cancelled"]:
        flash(t_srv("flash.21", "Appel d'offres clos : moins de %d offre(s) reçue(s), aucun gagnant.")% t["min_bids"])
    return redirect(url_for("offre", tid=tid))


@app.route("/offre/<int:tid>/reveler", methods=["POST"])
def offre_reveler(tid):
    t = _tender(tid)
    if not t:
        abort(404)
    if t["status"] != "closed":
        flash(t_srv("flash.22", "La révélation ouvre après la clôture des soumissions."))
        return redirect(url_for("offre", tid=tid))
    name = (request.form.get("name") or "").strip()[:60]
    secret = (request.form.get("secret") or "").strip()
    try:
        amount = int(request.form.get("amount") or "")
    except ValueError:
        amount = None
    # Mode chiffré : SEUL le gagnant (à exactement le prix gagnant) peut se déclarer.
    # Les perdants ne révèlent jamais leur montant.
    if t["mode"] == "fhe":
        if t["winning_price"] is None:
            flash(t_srv("flash.23", "Aucun gagnant (aucune offre valide)."))
            return redirect(url_for("offre", tid=tid))
        if t["winner_name"]:
            flash(t_srv("flash.24", "Le gagnant est déjà confirmé."))
            return redirect(url_for("offre", tid=tid))
        if amount is None or amount != t["winning_price"]:
            flash(t_srv("flash.25", "Pour te déclarer gagnant, indique EXACTEMENT le prix gagnant affiché."))
            return redirect(url_for("offre", tid=tid))
        with closing(db()) as conn, conn:
            b = conn.execute("SELECT * FROM bids WHERE tender_id=? AND bidder_name=?",
                             (tid, name)).fetchone()
            if not b or _bid_commitment(amount, secret) != b["commitment"]:
                flash(t_srv("flash.26", "Nom + montant + mot secret ne correspondent pas à une offre déposée."))
                return redirect(url_for("offre", tid=tid))
            conn.execute("UPDATE bids SET revealed=1, amount=? WHERE id=?", (amount, b["id"]))
            conn.execute("UPDATE tenders SET winner_name=? WHERE id=?", (name, tid))
        flash(t_srv("flash.27", "Victoire confirmée et vérifiée ! Les prix des autres restent secrets."))
        return redirect(url_for("offre", tid=tid))

    with closing(db()) as conn, conn:
        b = conn.execute("SELECT * FROM bids WHERE tender_id=? AND bidder_name=?",
                         (tid, name)).fetchone()
        if not b:
            flash(t_srv("flash.28", "Aucune offre à ce nom."))
            return redirect(url_for("offre", tid=tid))
        if b["revealed"]:
            flash(t_srv("flash.29", "Cette offre est déjà révélée."))
            return redirect(url_for("offre", tid=tid))
        if amount is None or _bid_commitment(amount, secret) != b["commitment"]:
            flash(t_srv("flash.30", "Montant + mot secret ne correspondent pas à l'offre scellée."))
            return redirect(url_for("offre", tid=tid))
        conn.execute("UPDATE bids SET revealed=1, amount=? WHERE id=?", (amount, b["id"]))
    flash(t_srv("flash.31", "Offre révélée et vérifiée."))
    return redirect(url_for("offre", tid=tid))


# ═══════════════════════════════════════════════════════════════════════════
#  MISE EN COMMUN PROTÉGÉE — somme homomorphe (FHE)
#  Chaque participant chiffre son chiffre (budget, cotisation, don). Le serveur
#  additionne sur les données CHIFFRÉES et ne révèle que le total et la moyenne.
#  Aucun montant individuel n'est jamais déchiffré ni stocké en clair.
# ═══════════════════════════════════════════════════════════════════════════

def _pool(pid):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM pools WHERE id=?", (pid,)).fetchone()


def _my_pools(me):
    if not me:
        return []
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM pools WHERE owner_user_id=? ORDER BY id DESC",
                            (me["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.route("/commun", methods=["GET", "POST"])
def commun():
    me = current_user()
    if request.method == "POST":
        if not me:
            return redirect(url_for("connexion", next=url_for("commun")))
        title = (request.form.get("title") or "").strip()[:120]
        question = (request.form.get("question") or "").strip()[:200]
        if not title:
            flash(t_srv("flash.32", "Donne un intitulé à la mise en commun."))
            return render_template("commun.html", pools=_my_pools(me), me=me,
                                   title=title, question=question, pool=None,
                                   pool_max=fhe.pool_max())
        with closing(db()) as conn, conn:
            pid = _insert_returning_id(conn,
                "INSERT INTO pools (owner_user_id, title, question, closed, n_contrib, "
                "created_at) VALUES (?,?,?,0,0,?)",
                (me["id"], title, question, int(time.time())))
        return redirect(url_for("commun_voir", pid=pid))
    return render_template("commun.html", pools=_my_pools(me), me=me,
                           title="", question="", pool=None, pool_max=fhe.pool_max())


@app.route("/commun/<int:pid>")
def commun_voir(pid):
    p = _pool(pid)
    if not p:
        abort(404)
    p = dict(p)
    me = current_user()
    with closing(db()) as conn:
        n = conn.execute("SELECT COUNT(*) c FROM pool_items WHERE pool_id=?", (pid,)).fetchone()["c"]
    p["n_contrib"] = n
    p["is_owner"] = bool(me and me["id"] == p["owner_user_id"])
    p["capacity"] = fhe.capacity()
    p["full"] = n >= fhe.capacity()
    p["average"] = (p["total"] // n) if (p["closed"] and p["total"] is not None and n) else None
    return render_template("commun.html", pools=_my_pools(me), me=me,
                           title="", question="", pool=p, pool_max=fhe.pool_max())


@app.route("/commun/<int:pid>/ajouter", methods=["POST"])
def commun_ajouter(pid):
    p = _pool(pid)
    if not p:
        abort(404)
    me = current_user()
    if not me:   # anti-bourrage : connexion requise
        return redirect(url_for("connexion", next=url_for("commun_voir", pid=pid)))
    if p["closed"]:
        flash(t_srv("flash.33", "Cette mise en commun est close : on ne peut plus ajouter de chiffre."))
        return redirect(url_for("commun_voir", pid=pid))
    contributor = (request.form.get("contributor") or "").strip()[:60]
    try:
        value = int(request.form.get("value") or "")
    except ValueError:
        value = None
    if value is None or value < 0:
        flash(t_srv("flash.34", "Entre un montant entier positif."))
        return redirect(url_for("commun_voir", pid=pid))
    if value > fhe.pool_max():
        flash(t_srv("flash.35", "Le montant dépasse le maximum autorisé (%d).")% fhe.pool_max())
        return redirect(url_for("commun_voir", pid=pid))
    with closing(db()) as conn, conn:
        # une seule contribution par compte (sans lier le montant au compte)
        dup = conn.execute("SELECT 1 FROM pool_participants WHERE pool_id=? AND user_id=?",
                           (pid, me["id"])).fetchone()
        if dup:
            flash(t_srv("flash.36", "Tu as déjà contribué à cette mise en commun."))
            return redirect(url_for("commun_voir", pid=pid))
        n = conn.execute("SELECT COUNT(*) c FROM pool_items WHERE pool_id=?", (pid,)).fetchone()["c"]
        if n >= fhe.capacity():
            flash(t_srv("flash.37", "Nombre maximum de participants atteint pour cette mise en commun."))
            return redirect(url_for("commun_voir", pid=pid))
        slot = n
        blob = fhe.encrypt_value(slot, value)   # le montant en clair n'est PAS stocké
        conn.execute("INSERT INTO pool_items (pool_id, slot, contributor, blob) VALUES (?,?,?,?)",
                     (pid, slot, contributor, blob))
        conn.execute("INSERT INTO pool_participants (pool_id, user_id) VALUES (?,?)", (pid, me["id"]))
        conn.execute("UPDATE pools SET n_contrib=? WHERE id=?", (n + 1, pid))
    flash(t_srv("flash.38", "Ton chiffre a été chiffré et ajouté. Personne ne peut le lire — seul le total sera révélé."))
    return redirect(url_for("commun_voir", pid=pid))


@app.route("/commun/<int:pid>/cloturer", methods=["POST"])
def commun_cloturer(pid):
    p = _pool(pid)
    if not p:
        abort(404)
    me = current_user()
    if not me or me["id"] != p["owner_user_id"]:
        abort(403)
    if p["closed"]:
        return redirect(url_for("commun_voir", pid=pid))
    with closing(db()) as conn, conn:
        rows = conn.execute("SELECT blob FROM pool_items WHERE pool_id=? ORDER BY slot", (pid,)).fetchall()
        blobs = [r["blob"] for r in rows]
        total = fhe.pool_sum(blobs) if blobs else 0   # somme calculée sur les chiffrés
        conn.execute("UPDATE pools SET closed=1, total=?, n_contrib=? WHERE id=?",
                     (total, len(blobs), pid))
    flash(t_srv("flash.55", "Mise en commun close : le total a été calculé sur les données chiffrées, "
          "sans qu'aucun chiffre individuel ne soit jamais déchiffré."))
    return redirect(url_for("commun_voir", pid=pid))


# ═══════════════════════════════════════════════════════════════════════════
#  COMPARATEUR PRIVÉ — histogramme chiffré par tranches (FHE)
#  Chacun soumet sa TRANCHE (fourchette) chiffrée. On révèle uniquement la
#  distribution : combien de personnes par tranche. Chacun voit « où il se
#  situe » sans que quiconque connaisse le chiffre exact d'un autre.
#  Réutilise le circuit de vote déjà éprouvé (encrypt_ballot / tally).
# ═══════════════════════════════════════════════════════════════════════════

def _compare(cid):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM compares WHERE id=?", (cid,)).fetchone()


def _my_compares(me):
    if not me:
        return []
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM compares WHERE owner_user_id=? ORDER BY id DESC",
                            (me["id"],)).fetchall()
    return [dict(r) for r in rows]


def _level_of(c, value):
    """Range une valeur dans sa tranche [0 .. n_levels-1] (calcul en clair, non stocké)."""
    vmin, vmax, n = c["vmin"], c["vmax"], c["n_levels"]
    if vmax <= vmin:
        return 0
    v = max(vmin, min(int(value), vmax))
    lvl = (v - vmin) * n // (vmax - vmin)
    return min(lvl, n - 1)


def _level_bounds(c):
    """Libellés des tranches, ex. '0–20 000'."""
    vmin, vmax, n = c["vmin"], c["vmax"], c["n_levels"]
    step = (vmax - vmin) / n if n else 0
    out = []
    for j in range(n):
        lo = int(vmin + j * step)
        hi = int(vmin + (j + 1) * step) if j < n - 1 else vmax
        out.append((lo, hi))
    return out


@app.route("/comparer", methods=["GET", "POST"])
def comparer():
    me = current_user()
    if request.method == "POST":
        if not me:
            return redirect(url_for("connexion", next=url_for("comparer")))
        title = (request.form.get("title") or "").strip()[:120]
        unit = (request.form.get("unit") or "").strip()[:20]
        try:
            vmin = int(request.form.get("vmin") or "0")
            vmax = int(request.form.get("vmax") or "0")
            n_levels = int(request.form.get("n_levels") or "5")
        except ValueError:
            vmin, vmax, n_levels = 0, 0, 5
        n_levels = max(2, min(n_levels, 10))
        if not title or vmax <= vmin:
            flash(t_srv("flash.39", "Donne un intitulé et une fourchette valide (max supérieur au min)."))
            return render_template("comparer.html", compares=_my_compares(me), me=me,
                                   title=title, unit=unit, vmin=vmin, vmax=vmax,
                                   n_levels=n_levels, compare=None)
        with closing(db()) as conn, conn:
            cid = _insert_returning_id(conn,
                "INSERT INTO compares (owner_user_id, title, unit, vmin, vmax, n_levels, "
                "closed, created_at) VALUES (?,?,?,?,?,?,0,?)",
                (me["id"], title, unit, vmin, vmax, n_levels, int(time.time())))
        return redirect(url_for("comparer_voir", cid=cid))
    return render_template("comparer.html", compares=_my_compares(me), me=me,
                           title="", unit="", vmin="", vmax="", n_levels=5, compare=None)


@app.route("/comparer/<int:cid>")
def comparer_voir(cid):
    c = _compare(cid)
    if not c:
        abort(404)
    c = dict(c)
    me = current_user()
    with closing(db()) as conn:
        n = conn.execute("SELECT COUNT(DISTINCT slot) c FROM compare_items WHERE compare_id=?",
                         (cid,)).fetchone()["c"]
    c["n_contrib"] = n
    c["is_owner"] = bool(me and me["id"] == c["owner_user_id"])
    c["capacity"] = fhe.capacity()
    c["full"] = n >= fhe.capacity()
    c["bounds"] = _level_bounds(c)
    c["histogram"] = None
    if c["closed"] and c["results"]:
        import json
        c["histogram"] = json.loads(c["results"])
    return render_template("comparer.html", compares=_my_compares(me), me=me,
                           title="", unit="", vmin="", vmax="", n_levels=5, compare=c)


@app.route("/comparer/<int:cid>/ajouter", methods=["POST"])
def comparer_ajouter(cid):
    c = _compare(cid)
    if not c:
        abort(404)
    c = dict(c)
    me = current_user()
    if not me:   # anti-bourrage : connexion requise
        return redirect(url_for("connexion", next=url_for("comparer_voir", cid=cid)))
    if c["closed"]:
        flash(t_srv("flash.40", "Ce comparateur est clos."))
        return redirect(url_for("comparer_voir", cid=cid))
    try:
        value = int(request.form.get("value") or "")
    except ValueError:
        value = None
    if value is None:
        flash(t_srv("flash.41", "Entre ton chiffre."))
        return redirect(url_for("comparer_voir", cid=cid))
    level = _level_of(c, value)   # tranche calculée en clair, JAMAIS stockée
    with closing(db()) as conn, conn:
        # une seule réponse par compte (sans lier la valeur au compte)
        dup = conn.execute("SELECT 1 FROM compare_participants WHERE compare_id=? AND user_id=?",
                           (cid, me["id"])).fetchone()
        if dup:
            flash(t_srv("flash.42", "Tu as déjà répondu à ce comparateur."))
            return redirect(url_for("comparer_voir", cid=cid))
        n = conn.execute("SELECT COUNT(DISTINCT slot) c FROM compare_items WHERE compare_id=?",
                         (cid,)).fetchone()["c"]
        if n >= fhe.capacity():
            flash(t_srv("flash.43", "Nombre maximum de participants atteint."))
            return redirect(url_for("comparer_voir", cid=cid))
        slot = n
        # Encodage one-hot chiffré : bit=1 sur ma tranche, 0 sur les autres.
        for j in range(c["n_levels"]):
            bit = 1 if j == level else 0
            blob = fhe.encrypt_ballot(slot, bit)
            conn.execute("INSERT INTO compare_items (compare_id, slot, level, blob) VALUES (?,?,?,?)",
                         (cid, slot, j, blob))
        conn.execute("INSERT INTO compare_participants (compare_id, user_id) VALUES (?,?)",
                     (cid, me["id"]))
    lo, hi = _level_bounds(c)[level]
    flash(t_srv("flash.44", "Ta réponse est chiffrée. Ta tranche : %s–%s %s. Personne ne voit ton chiffre exact.")% ("{:,}".format(lo).replace(",", " "), "{:,}".format(hi).replace(",", " "), c["unit"]))
    return redirect(url_for("comparer_voir", cid=cid))


@app.route("/comparer/<int:cid>/cloturer", methods=["POST"])
def comparer_cloturer(cid):
    c = _compare(cid)
    if not c:
        abort(404)
    c = dict(c)
    me = current_user()
    if not me or me["id"] != c["owner_user_id"]:
        abort(403)
    if c["closed"]:
        return redirect(url_for("comparer_voir", cid=cid))
    import json
    histo = []
    with closing(db()) as conn, conn:
        for j in range(c["n_levels"]):
            rows = conn.execute("SELECT blob FROM compare_items WHERE compare_id=? AND level=?",
                               (cid, j)).fetchall()
            blobs = [r["blob"] for r in rows]
            histo.append(fhe.tally(blobs) if blobs else 0)   # décompte par tranche sur les chiffrés
        conn.execute("UPDATE compares SET closed=1, results=? WHERE id=?",
                     (json.dumps(histo), cid))
    flash(t_srv("flash.45", "Comparateur clos : la distribution a été calculée sur les données chiffrées."))
    return redirect(url_for("comparer_voir", cid=cid))


# ═══════════════════════════════════════════════════════════════════════════
#  COFFRE-FORT D'ALERTES — révélation à seuil (FHE)
#  Une alerte reste INVISIBLE tant qu'elle est isolée. Elle n'apparaît que
#  lorsque PLUSIEURS personnes signalent indépendamment la même cible (seuil).
#  Sous le seuil : zéro information, pas même « 1 personne a signalé ».
#  Les cibles sont choisies dans une liste définie par l'ouvreur (anti-doxxing).
#  Les signaleurs ne sont jamais révélés, même quand le seuil tombe.
#  ⚠ Outil de signalement, pas de jugement : une alerte franchie ouvre un
#  dossier vers un humain de confiance / le canal approprié.
# ═══════════════════════════════════════════════════════════════════════════

def _register(rid):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM registers WHERE id=?", (rid,)).fetchone()


def _register_targets(rid):
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM register_targets WHERE register_id=? ORDER BY position",
                            (rid,)).fetchall()
    return [dict(r) for r in rows]


def _my_registers(me):
    if not me:
        return []
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM registers WHERE owner_user_id=? ORDER BY id DESC",
                            (me["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.route("/alertes", methods=["GET", "POST"])
def alertes():
    me = current_user()
    if request.method == "POST":
        if not me:
            return redirect(url_for("connexion", next=url_for("alertes")))
        title = (request.form.get("title") or "").strip()[:120]
        context = (request.form.get("context") or "").strip()[:200]
        try:
            threshold = int(request.form.get("threshold") or "3")
        except ValueError:
            threshold = 3
        threshold = max(2, min(threshold, 10))
        targets = [t.strip()[:80] for t in (request.form.get("targets") or "").splitlines() if t.strip()]
        targets = targets[:fhe.capacity()]
        if not title or len(targets) < 2:
            flash(t_srv("flash.46", "Donne un intitulé et au moins 2 cibles (une par ligne)."))
            return render_template("alertes.html", registers=_my_registers(me), me=me,
                                   title=title, context=context, threshold=threshold,
                                   targets="\n".join(targets), register=None)
        with closing(db()) as conn, conn:
            rid = _insert_returning_id(conn,
                "INSERT INTO registers (owner_user_id, title, context, threshold, closed, "
                "created_at) VALUES (?,?,?,?,0,?)",
                (me["id"], title, context, threshold, int(time.time())))
            for i, tname in enumerate(targets):
                conn.execute("INSERT INTO register_targets (register_id, position, name) VALUES (?,?,?)",
                             (rid, i, tname))
        return redirect(url_for("alerte_voir", rid=rid))
    return render_template("alertes.html", registers=_my_registers(me), me=me,
                           title="", context="", threshold=3, targets="", register=None)


@app.route("/alertes/<int:rid>")
def alerte_voir(rid):
    r = _register(rid)
    if not r:
        abort(404)
    r = dict(r)
    me = current_user()
    targets = _register_targets(rid)
    with closing(db()) as conn:
        n = conn.execute("SELECT COUNT(*) c FROM register_alerts WHERE register_id=?", (rid,)).fetchone()["c"]
        already = False
        if me:
            already = conn.execute("SELECT 1 FROM register_participants WHERE register_id=? AND user_id=?",
                                   (rid, me["id"])).fetchone() is not None
    r["n_alerts"] = n
    r["is_owner"] = bool(me and me["id"] == r["owner_user_id"])
    r["already"] = already
    r["capacity"] = fhe.capacity()
    r["full"] = n >= fhe.capacity()
    r["revealed"] = None
    if r["closed"] and r["results"]:
        import json
        counts = json.loads(r["results"])
        # ne montre QUE les cibles ayant franchi le seuil (compte > 0)
        r["revealed"] = [{"name": targets[i]["name"], "count": counts[i]}
                         for i in range(len(targets)) if i < len(counts) and counts[i] > 0]
    return render_template("alertes.html", registers=_my_registers(me), me=me,
                           title="", context="", threshold=3, targets="",
                           register=r, target_list=targets)


@app.route("/alertes/<int:rid>/signaler", methods=["POST"])
def alerte_signaler(rid):
    r = _register(rid)
    if not r:
        abort(404)
    r = dict(r)
    me = current_user()
    if not me:
        return redirect(url_for("connexion", next=url_for("alerte_voir", rid=rid)))
    if r["closed"]:
        flash(t_srv("flash.47", "Ce registre est clos : on ne peut plus signaler."))
        return redirect(url_for("alerte_voir", rid=rid))
    try:
        target_pos = int(request.form.get("target_pos"))
    except (TypeError, ValueError):
        target_pos = None
    targets = _register_targets(rid)
    if target_pos is None or target_pos < 0 or target_pos >= len(targets):
        flash(t_srv("flash.48", "Choisis une cible dans la liste."))
        return redirect(url_for("alerte_voir", rid=rid))
    with closing(db()) as conn, conn:
        # un seul signalement par compte (sans lier le compte à la cible choisie)
        dup = conn.execute("SELECT 1 FROM register_participants WHERE register_id=? AND user_id=?",
                           (rid, me["id"])).fetchone()
        if dup:
            flash(t_srv("flash.49", "Tu as déjà déposé une alerte dans ce registre."))
            return redirect(url_for("alerte_voir", rid=rid))
        n = conn.execute("SELECT COUNT(*) c FROM register_alerts WHERE register_id=?", (rid,)).fetchone()["c"]
        if n >= fhe.capacity():
            flash(t_srv("flash.50", "Nombre maximum d'alertes atteint pour ce registre."))
            return redirect(url_for("alerte_voir", rid=rid))
        slot = n
        # 1 bit chiffré (=1) sur la cible choisie. La cible en clair n'est PAS
        # stockée côté compte : seul ce bit chiffré l'est.
        blob = fhe.encrypt_alert(r["threshold"], slot, 1)
        conn.execute("INSERT INTO register_alerts (register_id, target_pos, slot, blob) VALUES (?,?,?,?)",
                     (rid, target_pos, slot, blob))
        conn.execute("INSERT INTO register_participants (register_id, user_id) VALUES (?,?)",
                     (rid, me["id"]))
    flash(t_srv("flash.56", "Ton alerte est chiffrée. Tant que le seuil n'est pas atteint, personne — pas même "
          "l'organisateur — ne peut la voir. Tu n'es jamais le signaleur isolé."))
    return redirect(url_for("alerte_voir", rid=rid))


@app.route("/alertes/<int:rid>/evaluer", methods=["POST"])
def alerte_evaluer(rid):
    r = _register(rid)
    if not r:
        abort(404)
    r = dict(r)
    me = current_user()
    if not me or me["id"] != r["owner_user_id"]:
        abort(403)
    if r["closed"]:
        return redirect(url_for("alerte_voir", rid=rid))
    import json
    targets = _register_targets(rid)
    counts = []
    with closing(db()) as conn, conn:
        for tg in targets:
            rows = conn.execute("SELECT blob FROM register_alerts WHERE register_id=? AND target_pos=?",
                               (rid, tg["position"])).fetchall()
            blobs = [row["blob"] for row in rows]
            # révélation à seuil : renvoie le compte SI >= seuil, sinon 0
            counts.append(fhe.alert_reveal(r["threshold"], blobs) if blobs else 0)
        conn.execute("UPDATE registers SET closed=1, results=? WHERE id=?", (json.dumps(counts), rid))
    revealed = sum(1 for c in counts if c > 0)
    if revealed:
        flash(t_srv("flash.51", "Évaluation terminée : %d cible(s) ont atteint le seuil. Les autres n'ont rien révélé.")% revealed)
    else:
        flash(t_srv("flash.52", "Évaluation terminée : aucune cible n'a atteint le seuil. Aucune alerte n'est révélée."))
    return redirect(url_for("alerte_voir", rid=rid))


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
