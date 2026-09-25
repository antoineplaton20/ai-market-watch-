"""PRÉPARATION après installation (lancée automatiquement, en arrière-plan) :
tests -> backtest comparatif 15 min / 1 h / 4 h -> première évolution. Chaque résultat arrive sur Telegram.
Le bot, lui, tourne déjà en mode démo pendant ce temps (argent fictif, aucun risque)."""
import re
import subprocess
import sys
import config
from alertes import alerte


def lancer(arguments, journal):
    with open(journal, "w", encoding="utf-8") as f:
        return subprocess.run([sys.executable] + arguments, stdout=f, stderr=subprocess.STDOUT).returncode


def main():
    alerte("🧪 Préparation lancée : tests, puis backtest sur 2 ans (le premier téléchargement des archives prend "
           "30 à 90 min), puis première évolution. Le bot tourne déjà en mode démo pendant ce temps.", important=False)
    if lancer(["verifier.py"], "preparation_tests.log") != 0:
        alerte("❌ Préparation arrêtée : des tests échouent. Sur le serveur : bots verifier (et envoie le résultat à Claude).")
        return 1
    if lancer(["backtest.py", "--comparer"], "preparation_backtest.log") != 0:
        alerte("❌ Le backtest a échoué (souvent un problème de réseau). Relance-le plus tard : bots backtest")
        return 1
    texte = open("preparation_backtest.log", encoding="utf-8").read()
    comparaison = texte.split("=== COMPARAISON HORS ÉCHANTILLON ===")[-1].strip() if "COMPARAISON" in texte else ""
    reco = re.search(r'UNITE_BOUGIE = "(\w+)"', texte)
    message = "📊 Backtest terminé (détails : backtest_rapport_*.txt)\n" + comparaison[:1500]
    if reco and reco.group(1) != config.UNITE_BOUGIE:
        alerte(message + f"\n\n👉 Le backtest recommande des bougies de {reco.group(1)} au lieu de {config.UNITE_BOUGIE}.\n"
               f"Sur le serveur, tape : bots unite {reco.group(1)}\npuis : bots evolution")
        return 0
    if not reco:
        alerte(message + "\n\n⚠️ Aucune unité n'a d'avantage prouvé : le bot reste en démo, AUCUN passage au réel. "
               "L'évolution quotidienne va continuer à chercher.")
    else:
        alerte(message + f"\n\n✅ L'unité actuelle ({config.UNITE_BOUGIE}) est la bonne. Lancement de la première évolution.")
    lancer(["evolution.py"], "preparation_evolution.log")          # l'évolution envoie elle-même son bilan
    return 0


if __name__ == "__main__":
    sys.exit(main())
