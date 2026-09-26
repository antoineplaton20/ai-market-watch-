"""python -m armee_or <commande>

  chef         chef d'orchestre et toute l'armée (service armee-or-chef)
  flux         vigies du cours en direct (service armee-or-flux)
  importer     importer l'historique livré dans la base
  etat         rapport actuel            levier      fiches de levier        bilan    bilan historique
  bibliotheque connaissances utilisées   test        contrôle complet sans réseau ni Telegram
  commande X   transmettre « pause », « reprise » ou « rapport » au chef
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import config


def _journal():
    config.JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s",
                        handlers=[RotatingFileHandler(config.JOURNAL, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
                                  logging.StreamHandler()])


def test():
    """Contrôle complet sur l'historique livré : données, analystes, pronostiqueurs, levier, papier."""
    import time
    from . import base, chandeliers, chef, donnees, levier, rythme
    t = time.time()
    if not base.lire("historique_importe"):
        print("Import de l'historique…", donnees.importer_tout())
    inv = donnees.inventaire()
    print("✔ Base :", ", ".join(f"{r['source']} {r['tf']} {r['n']}" for r in inv))
    b = donnees.charger(chef.SOURCE_DECISION, "1h", limite=3000)
    print("✔ Rythme :", rythme.etat(b)["regime"])
    print("✔ Chandeliers :", len(chandeliers.detecter(b)), "motifs surveillés")
    bh = chef.bilan_historique()
    print("✔ Bilan historique :", ", ".join(f"{tf} {u['decisions']} décisions" for tf, u in bh["unites"].items()))
    print("✔ Levier :", len(levier.PROFILS), "profils")
    print(f"Contrôle terminé en {time.time() - t:.0f} s.")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "etat"
    if cmd in ("chef", "flux"):
        _journal()
        from . import chef, flux
        return (chef.main if cmd == "chef" else flux.main)()
    from . import chef, donnees
    if cmd == "importer":
        print(donnees.importer_tout())
    elif cmd == "etat":
        print(chef.rapport())
    elif cmd == "levier":
        print(chef.rapport_levier())
    elif cmd == "bilan":
        chef.bilan_historique()
        print(chef.rapport_bilan())
    elif cmd == "bibliotheque":
        from . import bibliotheque
        print(bibliotheque.texte())
    elif cmd == "test":
        return test()
    elif cmd == "commande" and len(argv) > 1 and argv[1] in ("pause", "reprise", "rapport", "levier", "bilan"):
        fichier = config.RACINE / "runtime" / "commandes.txt"
        fichier.parent.mkdir(parents=True, exist_ok=True)
        with open(fichier, "a") as f:
            f.write(argv[1] + "\n")
        print(f"Commande « {argv[1]} » transmise au chef (appliquée dans les 10 secondes).")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
