"""De bout en bout : scan, équipe, génome, achat, stop, ombres — sans réseau."""
import donnees
import main
import gardien as G
from fausse_binance import FausseBinance


def test_cycle_complet(monkeypatch):
    for nom, valeur in {"peur_avidite": lambda: 55, "fundings": lambda: {"SOLUSDT": 0.0001, "ETHUSDT": 0.001},
                        "open_interest": lambda s: [100, 101, 104], "actualites": lambda: [],
                        "tendances": lambda: set(), "annuaire": lambda: {}, "commits_4_semaines": lambda b: None,
                        "stablecoins_7j": lambda: 0.8, "macro": lambda: (True, False),
                        "positionnement": lambda s: (1.4, 1.9), "marches_mondiaux": lambda: (True, False, 17.0),
                        "attention": lambda: 1.1}.items():
        monkeypatch.setattr(donnees, nom, valeur)
    monkeypatch.setattr(main.E, "contradicteur", lambda *a: (None, "IA désactivée"))
    ex, etat = FausseBinance(), G.charger_etat()
    capital = G.verifier_jour(ex, etat)
    main.cycle_achat(ex, etat, capital, 1.0)
    assert "SOL/USDT" in etat["positions"]
    assert "ETH/USDT" not in etat["positions"]          # bloqué par le funding trop élevé
    for p in etat["positions"].values():
        assert ex.ordres[p["id_stop"]]["status"] == "open"
