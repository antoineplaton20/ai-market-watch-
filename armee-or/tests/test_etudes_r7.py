"""R7 : le moteur des études (etudes/moteur_r7.py) ne triche pas : exécution à l'ouverture suivante, stop d'abord,
trous de cotation, ordres doubles, aucune donnée du futur dans les règles du catalogue."""
import sys
from pathlib import Path

import numpy as np
import pytest

ETUDES = Path(__file__).resolve().parent.parent / "etudes"
sys.path.insert(0, str(ETUDES))
import catalogue_r7 as C  # noqa: E402
import moteur_r7 as M     # noqa: E402


def serie(n=400, graine=1):
    rng = np.random.default_rng(graine)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.001, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.003, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.003, n)))
    ts = (np.arange(n) * 86_400_000 + 1_600_000_000_000).astype(np.int64)
    return {"ts": ts, "o": o, "h": h, "l": l, "c": c, "v": np.ones(n), "vb": np.full(n, 0.5)}


def test_execution_a_l_ouverture_suivante_et_frais():
    d = serie()
    s = np.zeros(400)
    s[100] = 1
    rend, tr = M.backtest(d["o"], d["h"], d["l"], d["c"], {"sens": s, "duree": 5}, 0.001)
    (ie, i_s, sens, _, net), = tr
    assert ie == 101 and i_s == 106 and sens == 1                     # décidé à la clôture 100, acheté à l'ouverture 101
    v = M._vol_glissante(d["c"], 252)[100]
    w = min(M.VOL_CIBLE / v, M.LEVIER_MAX)
    attendu = w * (d["c"][101] / d["o"][101] - 1 + sum(d["c"][j] / d["c"][j - 1] - 1 for j in range(102, 106))
                   + d["o"][106] / d["c"][105] - 1) - w * 0.001
    assert net == pytest.approx(attendu) and rend.sum() == pytest.approx(net)


def test_stop_d_abord_et_trou_de_cotation():
    o = np.array([100, 100, 100, 95, 95.0])
    h = np.array([101, 101, 104, 96, 96.0])
    l = np.array([99, 99, 97, 90, 94.0])
    c = np.array([100, 100, 100, 95, 95.0])
    s = np.array([1, 0, 0, 0, 0.0])
    regle = {"sens": s, "stop": np.full(5, 98.0), "cible": np.full(5, 103.0)}
    _, tr = M.backtest(o, h, l, c, regle, 0.0)
    assert tr[0][1] == 2 and tr[0][3] == pytest.approx(-1.0)          # stop ET objectif dans la bougie 2 : le stop
    _, tr = M.backtest(o, h, l, c, regle, 0.0, chemin="ohlc")
    assert tr[0][3] == pytest.approx(-1.0)                            # bougie 2 neutre (c = o) : bas d'abord
    regle["cible"] = np.full(5, 110.0)
    regle["stop"] = np.full(5, 96.0)
    _, tr = M.backtest(o, h, l, c, regle, 0.0)
    assert tr[0][1] == 3 and tr[0][3] == pytest.approx((95 - 100) / 4)  # trou sous le stop : exécuté à l'ouverture (95)


def test_ordre_double_le_premier_touche_annule_l_autre():
    o = np.array([100, 100, 100, 100.0])
    h = np.array([100.5, 100.5, 102, 103.0])
    l = np.array([99.5, 99.5, 99.8, 101.0])
    c = np.array([100, 100, 101.5, 102.5])
    regle = {"sens": np.array([0, 2, 0, 0.0]), "entree_l": np.full(4, 101.0), "entree_c": np.full(4, 99.0),
             "stop_l": np.full(4, 99.0), "stop_c": np.full(4, 101.0), "validite": 2}
    _, tr = M.backtest(o, h, l, c, regle, 0.0)
    assert len(tr) == 1 and tr[0][2] == 1 and tr[0][0] == 2           # cassure haute en bougie 2 : achat seulement


def test_les_regles_du_catalogue_n_utilisent_pas_le_futur():
    """Couper la série après la bougie k ne change aucune décision jusqu'à k (sens, niveaux)."""
    d = serie(700, graine=3)
    d["ts"] = (np.arange(700) * 900_000 + 1_600_000_000_000).astype(np.int64)   # bougies de 15 minutes
    k = 520
    court = {x: v[:k + 1] for x, v in d.items()}
    for nom, f in {**C.INTRADAY, **C.JOURNALIER}.items():
        if nom.startswith("H21"):                                    # trou du lundi : entrée au 1er cours, signalée
            continue
        long_, cr = f(d), f(court)
        for cle in ("sens", "stop", "stop_l", "stop_c", "cible_l", "cible_c", "entree_l", "entree_c", "sortie"):
            if cle in cr:
                a, b = np.asarray(long_[cle], float)[:k + 1], np.asarray(cr[cle], float)
                assert np.allclose(a, b, equal_nan=True), (nom, cle, np.flatnonzero(~np.isclose(a, b, equal_nan=True))[:5])


def test_sharpe_degonfle():
    p, seuil = M.sharpe_degonfle(0.63, 3, 252 / 9000, 9000)
    assert p > 0.99 and 0 < seuil < 0.3
    p2, seuil2 = M.sharpe_degonfle(0.63, 250, 252 / 9000, 9000)
    assert seuil2 > seuil and p2 < p                                  # plus d'essais : seuil plus haut
