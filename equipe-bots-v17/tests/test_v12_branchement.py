"""v12 branché : scanner universel dans le SCOUT, moteur de corrélation, univers Trade Republic en suivi,
et mêmes caractéristiques qu'en backtest (sup1 / MULTI_UNITES) pour les génomes."""
import numpy as np
import config
import donnees
import main
import equipe as E
import gardien as G
from fausse_binance import FausseBinance


def _sans_reseau(monkeypatch):
    for nom, valeur in {"peur_avidite": lambda: 55, "fundings": lambda: {"SOLUSDT": 0.0001, "ETHUSDT": 0.001},
                        "open_interest": lambda s: [100, 101, 104], "actualites": lambda: [],
                        "tendances": lambda: set(), "annuaire": lambda: {}, "commits_4_semaines": lambda b: None,
                        "stablecoins_7j": lambda: 0.8, "macro": lambda: (True, False),
                        "positionnement": lambda s: (1.4, 1.9), "marches_mondiaux": lambda: (True, False, 17.0),
                        "attention": lambda: 1.1}.items():
        monkeypatch.setattr(donnees, nom, valeur)
    monkeypatch.setattr(main.E, "contradicteur", lambda *a: (None, "IA désactivée"))


def test_scout_passe_par_le_scanner_universel(monkeypatch):
    ex = FausseBinance(paires=("BTC", "SOL", "ETH", "LARGE", "MORT"))
    ex.markets["MORT/USDT"]["active"] = False
    ex.markets["BTC/USDT:USDT"] = {"active": True, "spot": False, "type": "swap", "quote": "USDT", "base": "BTC"}
    tickers = ex.fetch_tickers()
    tickers["LARGE/USDT"].update(bid=90.0, ask=110.0)                  # spread 20 % : rejeté
    tickers["BTC/USDT:USDT"] = dict(tickers["BTC/USDT"])
    monkeypatch.setattr(ex, "fetch_tickers", lambda: tickers)
    symboles = [c["symbole"] for c in E.scout(ex)]
    assert set(symboles) == {"BTC/USDT", "SOL/USDT", "ETH/USDT"}    # ni spread large, ni inactif, ni futures
    assert E.DERNIER_SCAN["rejets"].get("spread") == 1
    assert "→ 3 assez échangées pour être étudiées" in E.texte_univers()


def test_univers_trade_republic_suivi_sans_bloquer(monkeypatch, tmp_path):
    f = tmp_path / "tr.csv"
    f.write_text("symbol,kind,currency,active,min_order,fixed_fee\nDE0001,stock,EUR,true,1,1\nIE0002,etf,EUR,true,1,1\n",
                 encoding="utf-8")
    monkeypatch.setattr(config, "UNIVERS_TR_FICHIER", str(f))
    assert len(E.scout(FausseBinance())) == 3                        # Trade Republic n'entre jamais dans le trading
    assert "2 titres suivis" in E.texte_univers()
    f.write_text("pas un csv valide \x00", encoding="utf-8")
    monkeypatch.setattr(config, "UNIVERS_TR_FICHIER", str(tmp_path / "absent.csv"))
    assert len(E.scout(FausseBinance())) == 3


def test_correlation_avec_position_ouverte_ne_plante_plus():
    ex, etat = FausseBinance(), G.charger_etat()
    etat["positions"]["ETH/USDT"] = {"entree": 100, "stop": 95}
    ok, raison = E.correlation(ex, "SOL/USDT", etat, {})              # cache vide : plantait en v11
    assert isinstance(ok, bool) and raison


def test_correlation_moteur_v12_bloque_le_meme_pari():
    import pandas as pd
    ex, etat = FausseBinance(), G.charger_etat()
    etat["positions"]["ETH/USDT"] = {"entree": 100, "stop": 95}
    c = pd.Series(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 120)))
    cache = {"SOL/USDT": pd.DataFrame({"c": c}), "ETH/USDT": pd.DataFrame({"c": c * 2})}
    ok, raison = E.correlation(ex, "SOL/USDT", etat, cache)
    assert not ok and "ETH/USDT" in raison
    cache["ETH/USDT"] = pd.DataFrame({"c": 300 - c})                   # sens inverse : diversifie
    assert E.correlation(ex, "SOL/USDT", etat, cache)[0]


def test_analyse_fournit_sup1_comme_le_backtest(monkeypatch):
    _sans_reseau(monkeypatch)
    ex, etat = FausseBinance(), G.charger_etat()
    capital = G.verifier_jour(ex, etat)
    vus = []
    original = main.S.caracteristiques_live

    def espion(d, *a, **k):
        F = original(d, *a, **k)
        vus.append(F["sup1"])
        return F
    monkeypatch.setattr(main.S, "caracteristiques_live", espion)
    main.cycle_achat(ex, etat, capital, 1.0)
    assert vus and all(v in (0.0, 1.0) for v in vus)                  # plus jamais NaN en direct


def test_deuxieme_position_possible(monkeypatch):
    _sans_reseau(monkeypatch)
    ex, etat = FausseBinance(), G.charger_etat()
    capital = G.verifier_jour(ex, etat)
    etat["positions"]["BTC/USDT"] = {"entree": 100, "stop": 95, "quantite": 0.1, "securise": False}
    journal = []
    monkeypatch.setattr(main, "log", lambda m: journal.append(m))
    main.cycle_achat(ex, etat, capital, 1.0)
    assert not any("analyse interrompue" in m for m in journal)
