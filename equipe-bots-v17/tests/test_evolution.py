"""ÉVOLUTION : refuse le hasard, reconnaît un vrai motif."""
import random
import numpy as np
import pandas as pd
import pytest
import config
import backtest as B
import evolution as EV

Q = 15 * 60 * 1000


def _synth(n, rng, cycle):
    k = np.arange(n)
    r = rng.normal(0, 0.004, n) + 0.00002 + cycle * np.sin(k / 300) * 0.002
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    v = rng.uniform(500, 1500, n)
    return pd.DataFrame({"t": 1_700_000_000_000 + k * Q, "o": o, "h": np.maximum(o, c) * 1.002,
                         "l": np.minimum(o, c) * 0.998, "c": c, "v": v, "v_achat": v * rng.uniform(0.4, 0.6, n)})


def _charger(cycle):
    def charger(jours, nb, univers="actuel"):
        rng = np.random.default_rng(7)
        n = 96 * 240
        btc = _synth(n, rng, 0)
        t = btc["t"].values[::96]
        ext = {"btc": B.regime(btc, "1h"), "fundings": {}, "positions": {},
               "fng": pd.DataFrame({"t_g": t, "fng": rng.integers(5, 95, len(t))}),
               "stables": pd.DataFrame({"t_l": t, "liq_7j": rng.normal(0, 1, len(t))}),
               "macro": pd.DataFrame({"t_x": t, "nasdaq_ok": (rng.random(len(t)) > 0.4) * 1.0,
                                      "dxy_stress": (rng.random(len(t)) > 0.8) * 1.0}),
               "monde": pd.DataFrame({"t_w": t, "spx_ok": (rng.random(len(t)) > 0.3) * 1.0,
                                      "vix_stress": (rng.random(len(t)) > 0.9) * 1.0}),
               "attention": pd.DataFrame({"t_a": t, "attention": rng.uniform(0.5, 3.5, len(t))})}
        return {f"X{k}/USDT": _synth(n, rng, cycle) for k in range(5)}, ext
    return charger


@pytest.fixture
def evolution_rapide(monkeypatch):
    monkeypatch.setattr(config, "EVO_GENERATIONS", 5)
    monkeypatch.setattr(config, "EVO_TRADES_MIN", 40)
    monkeypatch.setattr(config, "EVO_UNITE", "15m")
    monkeypatch.setattr("sys.argv", ["evolution.py"])
    random.seed(3)
    np.random.seed(3)


def test_le_hasard_est_refuse(monkeypatch, evolution_rapide):
    monkeypatch.setattr(B, "charger", _charger(0.0))
    EV.main()
    import strategie as S
    assert S.challenger() is None


def test_un_vrai_motif_est_trouve(monkeypatch, evolution_rapide):
    monkeypatch.setattr(B, "charger", _charger(1.0))
    EV.main()
    import strategie as S
    assert S.challenger() is not None
