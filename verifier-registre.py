#!/usr/bin/env python3
"""
Verificateur INDEPENDANT du registre de bulletins de Kaddu.

Ce script ne depend ni de Kaddu, ni d'internet, ni d'aucune bibliotheque
externe : seulement la bibliotheque standard de Python. Vous pouvez le lire en
entier en deux minutes, le reecrire vous-meme, ou le faire executer par
quelqu'un qui ne nous fait pas confiance. C'est precisement l'interet.

CE QU'IL PROUVE
  1. La chaine d'empreintes est continue de bout en bout : chaque entree engage
     la precedente. Retirer, ajouter, reordonner ou modifier un bulletin apres
     coup casse la chaine.
  2. Le nombre de bulletins scelles correspond au total publie : l'organisateur
     ne peut pas annoncer un resultat portant sur plus ou moins de bulletins
     qu'il n'en a recu.
  3. Si vous fournissez votre recu : que votre bulletin figure bien dans le
     registre, et a quelle position.

CE QU'IL NE PROUVE PAS, et il faut le dire clairement
  Que le dechiffrement final est honnete. Dans la version web de Kaddu, la cle
  FHE est detenue par le serveur : ce registre garantit l'integrite des
  bulletins, pas celle du dechiffrement. Cette garantie-la est apportee par la
  couche on-chain (fhEVM), ou personne ne detient la cle.

  Il ne prouve pas non plus qu'un registre entierement fabrique avant
  publication soit faux. Sa force vient des recus : si ne serait-ce qu'UN votant
  ne retrouve pas le sien, la fraude est etablie.

USAGE
  python3 verifier-registre.py registre-xxxx.json
  python3 verifier-registre.py registre-xxxx.json --recu VOTRE_RECU
"""
import hashlib
import json
import sys


def empreinte_entree(prev_hash, poll_id, voter, digest, created_at):
    """Exactement la regle annoncee dans le champ 'regle_de_calcul' du JSON."""
    charge = "%s|%s|%s|%s|%s" % (prev_hash, poll_id, voter, digest, created_at)
    return hashlib.sha256(charge.encode("utf-8")).hexdigest()


def verifier(registre, recu=None):
    poll_id = registre["poll_id"]
    entrees = registre["entrees"]
    problemes = []

    # 1. Continuite de la chaine
    prev = ""
    for i, e in enumerate(entrees):
        if e["prev_hash"] != prev:
            problemes.append(
                "entree %d : prev_hash ne correspond pas a l'empreinte precedente" % (i + 1))
            break
        attendu = empreinte_entree(prev, poll_id, e["voter"], e["digest"], e["created_at"])
        if e["hash"] != attendu:
            problemes.append(
                "entree %d : empreinte recalculee differente de celle publiee" % (i + 1))
            break
        if e["voter"] != i:
            problemes.append("entree %d : position incoherente (%s)" % (i + 1, e["voter"]))
            break
        prev = e["hash"]

    chaine_ok = not problemes

    # 2. Racine annoncee
    racine_calculee = entrees[-1]["hash"] if entrees else ""
    racine_ok = (racine_calculee == registre.get("racine", ""))
    if not racine_ok:
        problemes.append("la racine publiee ne correspond pas a la derniere empreinte")

    # 3. Totaux
    total_ok = None
    if registre.get("clos"):
        total_ok = (registre.get("total_compte") == len(entrees))
        if not total_ok:
            problemes.append(
                "le resultat porte sur %s bulletin(s) alors que %d sont scelles"
                % (registre.get("total_compte"), len(entrees)))

    # 4. Recu
    place = None
    if recu:
        r = recu.strip().lower()
        for e in entrees:
            if e["hash"].lower() == r or e["hash"].lower().startswith(r):
                place = e["voter"] + 1
                break

    return {
        "chaine_ok": chaine_ok, "racine_ok": racine_ok, "total_ok": total_ok,
        "racine": racine_calculee, "n": len(entrees),
        "place_recu": place, "problemes": problemes,
    }


def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        print(__doc__)
        return 2
    chemin = args[0]
    recu = None
    if "--recu" in args:
        i = args.index("--recu")
        if i + 1 < len(args):
            recu = args[i + 1]

    with open(chemin, encoding="utf-8") as f:
        registre = json.load(f)

    if registre.get("format") != "kaddu-registre-bulletins-v1":
        print("Ce fichier n'est pas un registre Kaddu v1.")
        return 2

    r = verifier(registre, recu)
    coche = lambda b: "OK   " if b else "ECHEC"

    print()
    print("  Scrutin : %s" % registre.get("titre", "?"))
    print("  Question: %s" % registre.get("question", "?"))
    print("  Statut  : %s" % ("clos" if registre.get("clos") else "en cours"))
    print()
    print("  [%s] chaine d'empreintes continue sur %d bulletin(s)" % (coche(r["chaine_ok"]), r["n"]))
    print("  [%s] racine conforme  %s" % (coche(r["racine_ok"]), r["racine"][:32] + "..." if r["racine"] else "-"))
    if r["total_ok"] is not None:
        print("  [%s] le total publie porte sur les %d bulletins scelles"
              % (coche(r["total_ok"]), r["n"]))
    if recu:
        if r["place_recu"]:
            print("  [OK   ] votre recu figure au rang %d / %d" % (r["place_recu"], r["n"]))
        else:
            print("  [ECHEC] votre recu est INTROUVABLE dans ce registre")
    print()

    if registre.get("clos") and registre.get("resultats"):
        print("  Resultat publie :")
        for nom, n in zip(registre.get("options", []), registre["resultats"]):
            print("    %-28s %s" % (nom, n))
        print()

    if r["problemes"]:
        print("  PROBLEMES DETECTES :")
        for pb in r["problemes"]:
            print("    - %s" % pb)
        print()
        return 1

    if recu and not r["place_recu"]:
        return 1

    print("  Registre integre.")
    print("  Rappel : ceci prouve l'integrite des bulletins, pas celle du")
    print("  dechiffrement. Voir l'en-tete de ce script.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
