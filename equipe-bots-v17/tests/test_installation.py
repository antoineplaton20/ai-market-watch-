"""Installation serveur : scripts shell valides, préparation automatique et ses messages Telegram."""
import os
import subprocess
import pytest
import preparer

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("script", ["installer.sh", "configurer.sh", "bots"])
def test_scripts_shell_sans_erreur_de_syntaxe(script):
    assert subprocess.run(["bash", "-n", os.path.join(RACINE, script)]).returncode == 0


def _simuler(monkeypatch, codes, rapport_backtest):
    messages, lances = [], []

    def faux_lancer(arguments, journal):
        lances.append(arguments[0])
        if arguments[0] == "backtest.py":
            open(journal, "w", encoding="utf-8").write(rapport_backtest)
        return codes.get(arguments[0], 0)
    monkeypatch.setattr(preparer, "lancer", faux_lancer)
    monkeypatch.setattr(preparer, "alerte", lambda m, important=True: messages.append(m))
    return messages, lances


RAPPORT = "...\n=== COMPARAISON HORS ÉCHANTILLON ===\n  15m : espérance -0.02 R\n   1h : espérance 0.11 R\n{fin}"


def test_unite_differente_conseillee_sans_changer_seul(monkeypatch):
    messages, lances = _simuler(monkeypatch, {}, RAPPORT.format(fin='→ Recommandation : mettre UNITE_BOUGIE = "1h"'))
    preparer.main()
    assert "bots unite 1h" in messages[-1] and "evolution.py" not in lances     # c'est TOI qui décides


def test_bonne_unite_lance_la_premiere_evolution(monkeypatch):
    messages, lances = _simuler(monkeypatch, {}, RAPPORT.format(fin='→ Recommandation : mettre UNITE_BOUGIE = "15m"'))
    preparer.main()
    assert lances[-1] == "evolution.py"


def test_aucun_avantage_prouve_reste_en_demo(monkeypatch):
    messages, lances = _simuler(monkeypatch, {}, RAPPORT.format(fin="→ Aucune unité n'a d'avantage prouvé"))
    preparer.main()
    assert any("AUCUN passage au réel" in m for m in messages)


def test_tests_en_echec_arretent_la_preparation(monkeypatch):
    messages, lances = _simuler(monkeypatch, {"verifier.py": 1}, "")
    assert preparer.main() == 1 and lances == ["verifier.py"] and "❌" in messages[-1]
