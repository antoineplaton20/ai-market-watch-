"""Vérifie en une commande que tout le système fonctionne : python verifier.py
À lancer après chaque modification ou mise à jour, AVANT de relancer le bot."""
import os
import sys
import pytest

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("Vérification de l'équipe de bots (sans réseau, sans argent, ~1 minute)...\n")
    # v17 : la plateforme (tests) + la fabrique v15, l'armée v16 et le moteur v17 (tests_v15 à tests_v17)
    dossiers = [d for d in ("tests", "tests_v15", "tests_v16", "tests_v17") if os.path.isdir(d)]
    code = pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", *dossiers])
    print("\n✅ Tout fonctionne : le bot peut être relancé." if code == 0 else
          "\n❌ Au moins un test échoue : NE PAS relancer le bot, envoie-moi le message ci-dessus.")
    sys.exit(code)
