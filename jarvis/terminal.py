# -*- coding: utf-8 -*-
"""Jarvis dans le terminal (Termius / SSH)."""
from pathlib import Path

from .cerveau import Jarvis
from .config import MEMOIRES, NOM_UTILISATEUR

BANNIERE = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
  /oubli nouvelle conversation · /memoire · /fichier <chemin> · /quitter
"""
CONV = "terminal"


def confirmer(question: str) -> bool:
    return input(f"\n⚠️  Jarvis veut exécuter {question}\n   Confirmer ? [o/N] ").strip().lower() in ("o", "oui", "y", "yes")


def lancer():
    try:
        import readline  # noqa: F401  (historique ↑/↓ dans la saisie)
    except ImportError:
        pass
    jarvis = Jarvis()
    print(BANNIERE)
    print(f"JARVIS : À votre service, {NOM_UTILISATEUR}.\n")
    while True:
        try:
            texte = input("vous › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nJARVIS : À bientôt.")
            return
        if not texte:
            continue
        if texte in ("/quitter", "/exit", "/q"):
            print("JARVIS : À bientôt.")
            return
        if texte == "/oubli":
            jarvis.oublier(CONV)
            print("JARVIS : Conversation effacée (mémoire long terme conservée).\n")
            continue
        if texte == "/memoire":
            for p in sorted(x for x in MEMOIRES.rglob("*") if x.is_file()):
                print(f"── {p.relative_to(MEMOIRES)}\n{p.read_text(encoding='utf-8')}")
            print()
            continue
        if texte.startswith("/fichier "):
            chemin, _, question = texte[len("/fichier "):].partition(" ")
            p = Path(chemin).expanduser()
            if not p.is_file():
                print(f"JARVIS : fichier introuvable : {p}\n")
                continue
            texte = f"Fichier {p.name} :\n{p.read_text(encoding='utf-8', errors='replace')}\n\n{question or 'Analyse ce fichier.'}"
        print("JARVIS réfléchit…", end="\r", flush=True)
        try:
            reponse = jarvis.repondre(CONV, texte, confirmer=confirmer)
        except KeyboardInterrupt:
            print("\n(interrompu)\n")
            continue
        print(" " * 20, end="\r")
        print(f"JARVIS › {reponse}\n")
