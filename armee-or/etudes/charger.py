"""Charge les 34 marchés Yahoo (2000-2026) au format du banc de marches.py."""
import json, os
import numpy as np
FAMILLES = {
    "forex": ["EURUSDX", "GBPUSDX", "JPYX", "CHFX", "AUDUSDX", "CADX", "NZDUSDX", "EURGBPX", "EURJPYX", "GBPJPYX", "EURCHFX", "AUDJPYX"],
    "métaux": ["GCF", "SIF", "PLF", "HGF"], "énergie": ["CLF", "BZF", "NGF"],
    "agricoles": ["ZCF", "ZWF", "KCF", "SBF", "CCF"],
    "indices": ["GSPC", "NDX", "DJI", "GDAXI", "FCHI", "FTSE", "N225", "STOXX50E"], "crypto": ["BTC-USD", "ETH-USD"]}


def charger(dossier, M):
    marches = {}
    for fam, noms in FAMILLES.items():
        for nom in noms:
            r = json.load(open(os.path.join(dossier, nom + ".json")))["chart"]["result"][0]
            q = r["indicators"]["quote"][0]
            rows = [(t, o, h, l, c) for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"])
                    if None not in (o, h, l, c) and min(o, h, l, c) > 0 and l <= min(o, c) and h >= max(o, c)]
            a = np.array(rows, dtype=float)
            marches[nom] = {"ts": (a[:, 0] * 1000).astype(np.int64), "o": a[:, 1], "h": a[:, 2], "l": a[:, 3],
                            "c": a[:, 4], "cout": M.couts({}, fam, a[-1, 4]), "famille": fam}
    return marches
