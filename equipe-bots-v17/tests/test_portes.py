"""LES 3 PORTES avant tout argent réel — et le « critique » qui cherche comment le backtest pourrait mentir.

Porte 1 : aucune fuite du futur (vérifié ici, à chaque mise à jour, par bots verifier)
Porte 2 : Sharpe dégonflé (corrigé du nombre d'essais) au-dessus de la barre
Porte 3 : walk-forward — apprendre sur le passé, être jugé sur la période suivante, fenêtre après fenêtre
"""
import numpy as np
import pandas as pd
import pytest

import backtest as B
import config
import evolution as EV
import strategie as S
from moteurs import chandeliers as CH
from simulation import simuler_sortie


def bougies15(n=4000, graine=3):
    rng = np.random.default_rng(graine)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.004, n)))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.001, n))
    df = pd.DataFrame({"t": 1_700_000_000_000 + np.arange(n) * 900000, "o": o,
                       "h": np.maximum(o, c) * (1 + rng.uniform(0, 0.004, n)),
                       "l": np.minimum(o, c) * (1 - rng.uniform(0, 0.004, n)), "c": c,
                       "v": rng.uniform(500, 1500, n)})
    df["v_achat"] = df["v"] * rng.uniform(0.4, 0.6, n)
    return df


def externes(df15):
    return {"btc": B.regime(df15, "1h"), "btc15": df15, "fng": None, "stables": None, "macro": None, "monde": None,
            "attention": None, "fundings": {}, "positions": {}}


def futur_modifie(df, coupure, graine=9):
    """Même passé, futur complètement différent après la bougie `coupure`."""
    rng = np.random.default_rng(graine)
    x = df.copy()
    k = len(x) - coupure - 1
    for col in ("o", "h", "l", "c"):
        x.loc[coupure + 1:, col] = x.loc[coupure + 1:, col].to_numpy() * rng.uniform(0.5, 1.5, k)
    x.loc[coupure + 1:, "h"] = x.loc[coupure + 1:, ["o", "h", "l", "c"]].max(axis=1)
    x.loc[coupure + 1:, "l"] = x.loc[coupure + 1:, ["o", "h", "l", "c"]].min(axis=1)
    x.loc[coupure + 1:, "v"] = rng.uniform(1, 1e5, k)
    return x


def identiques(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return np.array_equal(np.isnan(a), np.isnan(b)) and np.allclose(np.nan_to_num(a), np.nan_to_num(b))


# ---------------------------------------------------------------- PORTE 1 : le critique
@pytest.mark.parametrize("unite", ["15m", "1h", "4h"])
def test_critique_aucune_donnee_du_futur(unite):
    """Si on change TOUT le futur, rien de ce que les bots voyaient avant ne doit bouger."""
    df = bougies15()
    coupure = 3000
    fin_connue = int(df["t"].iloc[coupure]) + 900000                   # fermeture de la dernière bougie connue
    a = EV.caracteristiques(B.preparer(df, unite, externes(df), "X"), unite)
    df2 = futur_modifie(df, coupure)
    b = EV.caracteristiques(B.preparer(df2, unite, externes(df2), "X"), unite)
    connues = a["t_ferme"] <= fin_connue
    assert connues.sum() > 100
    fuites = [k for k in a["F"] if not identiques(np.asarray(a["F"][k])[connues], np.asarray(b["F"][k])[connues])]
    assert not fuites, f"données du futur utilisées par : {fuites}"


def test_critique_le_signal_est_decale_avant_de_devenir_une_position():
    """Le signal de la bougie i s'achète à l'ouverture de i+1, jamais au prix de i."""
    df = B.preparer(bougies15(), "1h", externes(bougies15()), "X")
    trades = B.candidats("X", df, "1h")
    assert trades
    for t in trades[:50]:
        i = int(np.searchsorted(df["t"].to_numpy(), t["t"]))
        assert df["t"].iloc[i] == t["t"] and i >= 1                   # entrée = début de la bougie SUIVANTE


def test_critique_bougies_japonaises_causales():
    df = bougies15(1500)
    o, h, l, c = (df[k].to_numpy() for k in "ohlc")
    tout = CH.figures(o, h, l, c)
    for k in (300, 800, 1200):
        coupe = CH.figures(o[:k + 1], h[:k + 1], l[:k + 1], c[:k + 1])
        for nom in tout:
            assert np.array_equal(tout[nom][:k + 1], coupe[nom]), nom


def test_meme_lecture_des_bougies_en_backtest_et_en_reel():
    df = bougies15(600)
    brut = CH.caracteristiques(*(df[k].to_numpy() for k in "ohlc"))
    for fin in (200, 350, 599):
        d = {"df": df.iloc[:fin + 1].assign(ema20=1.0, rsi=50.0, atr=1.0, vol_moy=1.0), "hausse24h": 0.0}
        F = S.caracteristiques_live(d, {}, [], {})
        for k, v in brut.items():
            attendu = v[fin - 1]                                        # live : avant-dernière bougie = dernière fermée
            assert (F[k] == pytest.approx(float(attendu), nan_ok=True)) if k == "h_prec" else F[k] == bool(attendu)


# ---------------------------------------------------------------- PORTES 2 et 3
def _trade(t, r):
    return {"t": t, "t_sortie": t + 1, "r": r, "pnl_pct": r, "votes": {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0},
            "vetos": {"V": False}}


def test_walk_forward_et_sharpe_degonfle():
    rng = np.random.default_rng(0)
    def resultat(esperance):
        trades = [_trade(i, float(rng.normal(esperance, 1.0))) for i in range(800)]
        fen = B.walk_forward(B.decouper(trades, 4))
        return {"rs_wf": np.array([x for *_, rs in fen for x in rs]),
                "e_fenetres": [float(np.mean(rs)) for *_, rs in fen]}
    bon = resultat(0.4)
    assert len(bon["e_fenetres"]) == 3                                  # 3 fenêtres jugées l'une après l'autre
    assert B.portes(bon)["ok"]
    assert not B.portes(resultat(0.0))["ok"]                            # le hasard ne passe pas
    # plus on a fait d'essais, plus la barre monte
    moyen = resultat(0.12)
    assert B.portes(moyen, 0.01, 1)["dsr"] > B.portes(moyen, 0.01, 1000)["dsr"]


def test_regimes_de_marche():
    t = np.arange(300) * 900000
    prix = np.r_[np.linspace(100, 200, 150), np.linspace(200, 90, 150)]
    btc = pd.DataFrame({"t": t, "c": prix})
    r = B.regime_marche(btc, 0, int(t[-1]))
    assert r["deux_regimes"] and "hausse +100 %" in r["texte"] and "baisse -55 %" in r["texte"]
    assert not B.regime_marche(btc, 0, int(t[140]))["deux_regimes"]


def test_backtest_sans_biais_du_survivant_par_defaut():
    import inspect
    assert config.BACKTEST_UNIVERS == "complet"
    assert "a.univers" in inspect.getsource(B.main)


def test_stop_limite_glissement_realiste():
    r_stop = simuler_sortie([(100, 100.5, 98.0, 98.2)], 100, 1.0)[1]
    assert r_stop == pytest.approx(-1.5 - 98.5 * config.GLISSEMENT_STOP_PCT / 100 - config.FRAIS_ALLER_RETOUR_PCT,
                                   abs=0.01)
    # le stop « sécurisé » couvre frais + glissement du stop : un gagnant ne redevient pas perdant
    r_secu = simuler_sortie([(100, 101.6, 99.8, 101.5), (101.5, 101.5, 99.0, 99.2)], 100, 1.0)
    assert r_secu[2] == "stop sécurisé" and r_secu[1] > 0
