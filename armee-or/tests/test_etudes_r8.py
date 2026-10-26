"""R8 : les règles du catalogue R8 (etudes/catalogue_r8.py) n'utilisent pas le futur, et le lecteur des bougies
Dukascopy (etudes/donnees_r7.py) décode exactement le format .bi5."""
import calendar
import lzma
import struct
import sys
from pathlib import Path

import numpy as np

ETUDES = Path(__file__).resolve().parent.parent / "etudes"
sys.path.insert(0, str(ETUDES))
import catalogue_r8 as C8  # noqa: E402
import donnees_r7 as D     # noqa: E402


def serie(n, graine, pas_ms):
    rng = np.random.default_rng(graine)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.001, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.003, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.003, n)))
    ts = (np.arange(n) * pas_ms + 1_600_041_600_000).astype(np.int64)   # minuit UTC
    return {"ts": ts, "o": o, "h": h, "l": l, "c": c, "v": rng.uniform(1, 2, n), "vb": np.full(n, 0.5)}


def test_les_regles_r8_n_utilisent_pas_le_futur():
    """Couper la série après la bougie k ne change aucune décision jusqu'à k. N04 (journalier) pose ses ordres d'après
    l'ouverture du jour : exemptée et signalée ; N04b la joue dans la journée."""
    for pas_ms, n, k, unites in ((900_000, 2600, 2399, ("15m", "1h")), (900_000, 2600, 2400, ("15m", "1h")),
                                 (86_400_000, 2600, 2300, ("1j",))):     # 2399 : dernière bougie d'un jour
        d = serie(n, 3, pas_ms)
        court = {x: v[:k + 1] for x, v in d.items()}
        for nom, (f, u) in C8.REGLES.items():
            if nom.startswith("N04 ") or not set(u) & set(unites):
                continue
            long_, cr = f(d), f(court)
            for cle in ("sens", "stop", "stop_l", "stop_c", "cible_l", "cible_c", "entree_l", "entree_c", "sortie",
                        "suivi_l", "suivi_c"):
                if cle in cr:
                    a, b = np.asarray(long_[cle], float)[:k + 1], np.asarray(cr[cle], float)
                    assert np.allclose(a, b, equal_nan=True), (nom, pas_ms, cle,
                                                               np.flatnonzero(~np.isclose(a, b, equal_nan=True))[:5])


def test_chaque_regle_r8_donne_des_signaux():
    d = serie(2600, 5, 900_000)
    for nom, (f, _) in C8.REGLES.items():
        assert np.count_nonzero(f(d)["sens"]) > 0, nom


def test_lecteur_dukascopy(tmp_path):
    rep = tmp_path / "XAUUSD"
    rep.mkdir()
    lignes = [(0, 2000_000, 2001_500, 1999_000, 2002_000, 3.5),          # t, o, c, l, h (entiers), volume
              (3600, 2001_500, 2001_500, 2001_500, 2001_500, 0.0),      # heure sans cotation : écartée
              (7200, 2001_500, 1998_000, 1997_000, 2003_000, 1.25)]
    brut = b"".join(struct.pack(">5if", *x) for x in lignes)
    (rep / "2024_03.bi5").write_bytes(lzma.compress(brut, format=lzma.FORMAT_ALONE))
    (rep / "2024_04.bi5").write_bytes(b"")                                # mois absent (404)
    t0 = calendar.timegm((2024, 3, 1, 0, 0, 0)) * 1000
    ref = {"ts": np.array([t0, t0 + 86_400_000]), "c": np.array([2000.0, 2001.0])}
    d = D.charger_dukascopy(str(tmp_path), "XAUUSD", ref)
    assert d["ts"].tolist() == [t0, t0 + 7_200_000]
    assert np.allclose(d["o"], [2000.0, 2001.5]) and np.allclose(d["h"], [2002.0, 2003.0])
    assert np.allclose(d["l"], [1999.0, 1997.0]) and np.allclose(d["c"], [2001.5, 1998.0])
    assert np.allclose(d["v"], [3.5, 1.25])
    assert D.charger_dukascopy(str(tmp_path), "ABSENT") is None
