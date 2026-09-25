"""Les gènes : bornes, compatibilité, sécurité intouchable, même décision en backtest et en réel."""
import random
import numpy as np
import pandas as pd
import pytest
import strategie as S


def test_genome_defaut_complet():
    g = S.genome_defaut()
    for k in S.CONTINUS:
        assert k in g
    for v in S.VETOS:
        assert f"veto_{v}" in g


def test_mutations_restent_dans_les_bornes():
    random.seed(0)
    for e in S.ESPECES:
        g = S.aleatoire(e)
        for _ in range(50):
            g = S.muter(g, taux=1.0)
        for k, (a, b) in S.CONTINUS.items():
            assert a <= g[k] <= b
        assert g["espece"] == e


def test_securite_hors_d_atteinte_de_l_evolution():
    interdits = ("risque", "perte_jour", "positions_max", "capital")
    for k in list(S.genome_defaut()) + list(S.CONTINUS):
        assert not any(x in k.lower() for x in interdits)


def test_ancien_genome_complete():
    vieux = {k: v for k, v in S.genome_defaut().items() if k not in ("part_frac", "veto_ATTENTION_VETO")}
    g = S.completer(vieux)
    assert g["part_frac"] == 0.0 and g["veto_ATTENTION_VETO"] is True


def _caracteristiques_synthetiques():
    import evolution as EV
    rng = np.random.default_rng(3)
    n = 3000
    c = 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.004, n)))
    o = np.r_[c[0], c[:-1]]
    df = pd.DataFrame({"t": np.arange(n) * 900000, "o": o, "h": np.maximum(o, c) * 1.002,
                       "l": np.minimum(o, c) * 0.998, "c": c, "v": rng.uniform(500, 1500, n)})
    df["v_achat"] = df["v"] * rng.uniform(0.4, 0.6, n)
    from indicateurs import ema, rsi, atr
    df["ema20"], df["ema50"], df["rsi"], df["atr"] = ema(df["c"], 20), ema(df["c"], 50), rsi(df["c"]), atr(df)
    df["vol_moy"] = df["v"].rolling(20).mean()
    df["t_ferme"] = df["t"] + 900000
    for col in ("sup1", "sup2", "btc_ok", "nasdaq_ok", "spx_ok"):
        df[col] = (rng.random(n) > 0.4).astype(float)
    for col, (a, b) in {"funding": (0, 0.0008), "oi": (1e6, 2e6), "oi_3h": (1e6, 2e6), "ls_foule": (0.8, 3),
                        "ls_gros": (0.8, 3), "fng": (5, 95), "liq_7j": (-1, 1), "attention": (0.5, 3.5)}.items():
        df[col] = rng.uniform(a, b, n)
    df["dxy_stress"] = (rng.random(n) > 0.8).astype(float)
    df["vix_stress"] = (rng.random(n) > 0.9).astype(float)
    return EV.caracteristiques(df, "15m")


def test_meme_decision_en_backtest_et_en_reel():
    random.seed(1)
    P = _caracteristiques_synthetiques()
    F = P["F"]
    for e in S.ESPECES:
        for _ in range(3):
            g = S.aleatoire(e)
            g["seuil_vote"] = 0.3
            sig, score = S.decider(g, F, "15m")
            for i in range(300, 3000, 97):
                Fi = {k: v[i] for k, v in F.items()}
                sig_i, score_i = S.decider(g, Fi, "15m")
                assert bool(sig_i) == bool(sig[i])
                assert float(score_i) == pytest.approx(float(score[i]))


def test_stop_structure_borne():
    P = _caracteristiques_synthetiques()
    g = S.genome_defaut()
    g["type_stop"] = "STRUCTURE"
    d = S.distance_stop(g, P["F"])
    assert np.nanmin(d) >= 0.5 and np.nanmax(d) <= 4.0
