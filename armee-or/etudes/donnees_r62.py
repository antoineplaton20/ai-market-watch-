"""R6.2 (25/10/2026) : contrôle de qualité des données qui servent aux preuves, avec les MÊMES contrôles que
l'armée applique désormais à l'historique du courtier (armee_or/qualite.py).

1. Chaque marché Yahoo (34 + 10) : lignes rejetées, trous, prix figés, sauts aberrants, ouvertures recopiées.
2. L'or vu par trois sources sur la même période : COMEX (Yahoo GC=F), PAXG et XAUUSDT (Binance, livrés).

Usage : python etudes/donnees_r62.py DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA RACINE_ARMEE
"""
import datetime as dt
import glob
import json
import os
import sys
import zipfile

import numpy as np

sys.path.insert(0, sys.argv[3])
from armee_or import qualite as Q   # noqa: E402


def lire_yahoo(chemin):
    r = json.load(open(chemin))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    brut = [(t, o, h, l, c) for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"])]
    return brut


def jour(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).date()


print("1) Qualité de chaque historique journalier (Yahoo 2000-2026)")
print("marché     | lignes | rejetées | trous > 7 j | figés ≥ 5 j | sauts aberrants | ouvertures recopiées | verdict")
bilan = {"bon": 0, "réserve": 0, "écarté": 0}
for dossier in (sys.argv[1], sys.argv[2]):
    for f in sorted(glob.glob(os.path.join(dossier, "*.json"))):
        nom = os.path.basename(f)[:-5]
        brut = lire_yahoo(f)
        rapport = Q.controler([(t * 1000, o, h, l, c) for t, o, h, l, c in brut], famille="crypto" if "-USD" in nom else "")
        bilan[rapport["verdict"]] += 1
        print(f"{nom:10} | {rapport['lignes']:6} | {rapport['rejetees']:8} | {rapport['trous']:11} | {rapport['figes']:11} | "
              f"{rapport['sauts']:15} | {rapport['ouvertures_recopiees'] * 100:19.0f} % | {rapport['verdict']}"
              + (f" ({'; '.join(rapport['raisons'])})" if rapport["raisons"] else ""))
print(f"   bilan : {bilan}")

print("2) L'or par trois sources, rendements journaliers sur la période commune")
gc = {jour(t): c for t, o, h, l, c in lire_yahoo(os.path.join(sys.argv[1], "GCF.json")) if c}
binance = os.path.join(sys.argv[3], "donnees_initiales", "binance")
autres = {}
for sym in ("PAXGUSDT", "XAUUSDT"):
    clot = {}
    for z in sorted(glob.glob(os.path.join(binance, f"{sym}-15m-*.zip"))):
        zz = zipfile.ZipFile(z)
        for ligne in zz.read(zz.namelist()[0]).decode().splitlines():
            p = ligne.split(",")
            if p[0].isdigit():
                t = int(p[0])
                t = (t // 1000 if t > 1e14 else t) // 1000
                if (t % 86400) // 3600 < 21:                        # clôture COMEX ≈ 18 h 30 UTC : dernière avant 21 h
                    clot[jour(t)] = float(p[4])
    autres[sym] = clot
for sym, clot in autres.items():
    jours = sorted(set(gc) & set(clot))
    a = np.array([gc[j] for j in jours])
    b = np.array([clot[j] for j in jours])
    ra, rb = np.diff(np.log(a)), np.diff(np.log(b))
    ecart = np.median(np.abs(b / a - 1))
    print(f"   COMEX contre {sym} : {len(jours)} jours ({jours[0]} → {jours[-1]}), corrélation des rendements "
          f"{np.corrcoef(ra, rb)[0, 1]:.2f}, écart médian de prix {ecart * 100:.2f} %, pire écart "
          f"{np.max(np.abs(b / a - 1)) * 100:.1f} %")
