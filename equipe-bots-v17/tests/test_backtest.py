"""BACKTESTEUR : le rapport se construit sur toutes les unités, sans erreur, avec un bulletin cohérent."""
import backtest as B
from test_evolution import _charger


def test_backtest_trois_unites():
    donnees15, externes = _charger(1.0)(240, 5)
    for unite in ("15m", "1h", "4h"):
        r = B.analyser(unite, donnees15, externes, 240)
        assert r is not None and r["bulletin"]
        texte = B.rapport(unite, r, 240)
        assert "VERDICT" in texte
        for v in r["bulletin"].values():
            assert 0 <= v["note_retenue"] <= 10
