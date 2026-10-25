"""Or : séance asiatique contre séance de New York (constat cité par le World Gold Council, 1er semestre 2026),
mesuré sur PAXGUSDT 15 min 2021-2026 livré avec l'armée. Rendement moyen par heure UTC, puis deux règles fixes :
acheteur pendant l'Asie seulement (0 h-7 h UTC), acheteur hors de New York (sauf 13 h 30-20 h UTC), vendeur pendant New York. Écart payé :
0,30 $ par once et par aller-retour, une fois par jour. Deux moitiés.
Usage : python etudes/or_seances.py DOSSIER_BINANCE"""
import datetime as dt
import glob
import os
import sys
import zipfile

import numpy as np

lignes = []
for f in sorted(glob.glob(os.path.join(sys.argv[1], "PAXGUSDT-15m-*.zip"))):
    z = zipfile.ZipFile(f)
    for l in z.read(z.namelist()[0]).decode().splitlines():
        p = l.split(",")
        if p[0].isdigit():
            t = int(p[0])
            lignes.append(((t // 1000 if t > 1e14 else t) // 1000, float(p[1]), float(p[4])))
b = np.array(lignes)
b = b[b[:, 0] >= dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp()]
t, o, c = b.T
r = np.concatenate(([0.0], np.log(c[1:] / c[:-1])))         # clôture à clôture : jamais o→c (rebond achat/vente)
r[np.concatenate(([True], np.diff(t) != 900))] = 0.0        # trou dans les données : pas de rendement inventé
heure = ((t % 86400) // 3600).astype(int)
minute = ((t % 3600) // 60).astype(int)
jour = (t // 86400).astype(int)
moitie = jour >= np.median(jour)
print("Rendement moyen par heure UTC (en $ pour une once à 2 500 $, par jour) :")
for hh in range(24):
    k = heure == hh
    print(f"  {hh:02d} h : {r[k & ~moitie].sum() / len(set(jour[~moitie])) * 2500:+.3f} $ (1re moitié) · "
          f"{r[k & moitie].sum() / len(set(jour[moitie])) * 2500:+.3f} $ (2e moitié)")


def regle(masque, nom, sens=1):
    prix = c.mean()
    for m, lib in ((~moitie, "1re moitié"), (moitie, "2e moitié")):
        jours = sorted(set(jour[m & masque]))
        brut = sens * np.array([r[(jour == j) & masque].sum() for j in jours])
        net = brut - 0.30 / prix
        print(f"  {nom} · {lib} : {len(jours)} jours, {(net > 0).mean()*100:.0f} % de jours gagnants, "
              f"{net.mean() * 2500:+.3f} $/once/jour, Sharpe {net.mean() / net.std() * np.sqrt(252):+.2f}")


asie = (heure >= 0) & (heure < 7)
new_york = ((heure == 13) & (minute >= 30)) | ((heure >= 14) & (heure < 20))
semaine = np.array([dt.datetime.fromtimestamp(x, dt.timezone.utc).weekday() < 5 for x in t])
regle(asie & semaine, "acheteur pendant l'Asie (0 h-7 h UTC)")
regle(~new_york & semaine, "acheteur hors de New York")
regle(semaine, "acheteur toute la journée (naïf, même écart payé chaque jour)")
regle(new_york & semaine, "VENDEUR pendant New York (13 h 30-20 h UTC)", sens=-1)
