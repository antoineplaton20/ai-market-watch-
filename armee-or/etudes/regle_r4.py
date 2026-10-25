"""Règle de la démo R4 (EMA20/50 en 15 min ET 1 h, stop 3 ATR, objectif 6 ATR, 4 h max, 7-16 h UTC en semaine,
3 entrées/jour, 1 h d'écart) rejouée sur PAXGUSDT 15 min (Binance, livré avec l'armée), avec la fonction signal()
de R4 elle-même. Entrée à l'ouverture de la bougie suivante, écart de 0,30 $ par once payé, stop d'abord si stop et
objectif tombent dans la même bougie. Le calendrier des annonces n'est pas rejoué (optimiste)."""
import datetime as dt, glob, os, sys, zipfile
import numpy as np
sys.path.insert(0, sys.argv[2])
from armee_or import demo_regles as R

lignes = []
for f in sorted(glob.glob(os.path.join(sys.argv[1], "PAXGUSDT-15m-*.zip"))):
    z = zipfile.ZipFile(f)
    for l in z.read(z.namelist()[0]).decode().splitlines():
        p = l.split(",")
        if not p[0].isdigit():
            continue
        t = int(p[0]); t = t // 1000 if t > 1e14 else t
        lignes.append([t // 1000, *map(float, p[1:6])])
b = np.array(lignes)
b = b[b[:, 0] >= dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp()]
t, o, h, l, c, v = b.T
print(f"{len(b)} bougies 15 min, {dt.datetime.fromtimestamp(t[0], dt.timezone.utc):%Y-%m-%d} → {dt.datetime.fromtimestamp(t[-1], dt.timezone.utc):%Y-%m-%d}")
# bougies 1 h construites depuis les 15 min (alignées sur l'heure)
h1 = {}
for row in b:
    k = int(row[0]) // 3600 * 3600
    if k not in h1: h1[k] = [k, row[1], row[2], row[3], row[4], row[5]]
    else:
        x = h1[k]; x[2] = max(x[2], row[2]); x[3] = min(x[3], row[3]); x[4] = row[4]; x[5] += row[5]
H = sorted(h1.values()); th = np.array([x[0] for x in H])
ECART = 0.30
trades, pos, jour, n_jour, derniere = [], None, None, 0, 0
for i in range(400, len(b) - 1):
    now = t[i] + 900 + 5                           # décision 5 s après la clôture de la bougie i
    if pos:                                        # suivi de la position sur la bougie i (déjà ouverte avant)
        sens, entree, sl, tp, debut = pos
        sortie = None
        if (sens > 0 and l[i] <= sl) or (sens < 0 and h[i] >= sl): sortie = sl
        elif (sens > 0 and h[i] >= tp) or (sens < 0 and l[i] <= tp): sortie = tp
        elif now - debut >= R.HORIZON: sortie = c[i]
        elif dt.datetime.fromtimestamp(now, dt.timezone.utc).weekday() == 4 and dt.datetime.fromtimestamp(now, dt.timezone.utc).hour >= 20: sortie = c[i]
        if sortie is not None:
            trades.append(((sortie - entree) * sens - ECART, abs(entree - sl), debut)); pos = None
        continue
    if not R.horaires(now): continue
    d = dt.datetime.fromtimestamp(now, dt.timezone.utc).date()
    if d != jour: jour, n_jour = d, 0
    if n_jour >= R.MAX_ORDRES_JOUR or now - derniere < R.ATTENTE: continue
    m15 = [list(map(float, x)) for x in b[i - 299:i + 1]]
    j = np.searchsorted(th, now - 3600, side="right")   # 1 h closes avant maintenant
    hh = [x for x in H[max(0, j - 300):j] if x[0] + 3600 <= now]
    try:
        s = R.signal(m15, hh, now)
    except ValueError:
        continue
    if not s["sens"]: continue
    entree = o[i + 1]                                     # ouverture suivante
    sl, tp = R.niveaux(entree, s["sens"], s["atr"], 2)
    pos = (s["sens"], entree, sl, tp, t[i + 1]); n_jour += 1; derniere = now
r = np.array([x[0] for x in trades]); risque = np.array([x[1] for x in trades]); R_ = r / risque
annees = np.array([dt.datetime.fromtimestamp(x[2], dt.timezone.utc).year for x in trades])
print(f"{len(r)} trades : {(r > 0).mean()*100:.1f} % gagnants · moyenne {r.mean():+.2f} $/once ({R_.mean():+.3f} R) · "
      f"gain moyen {r[r > 0].mean():+.2f} · perte moyenne {r[r <= 0].mean():+.2f} · total {r.sum():+.0f} $/once")
for a in sorted(set(annees)):
    k = annees == a
    print(f"  {a} : {k.sum():4} trades, {(r[k] > 0).mean()*100:5.1f} % gagnants, {R_[k].mean():+.3f} R par trade, total {r[k].sum():+7.1f} $/once")
moitie = len(r) // 2
print(f"moitiés : {R_[:moitie].mean():+.3f} R / {R_[moitie:].mean():+.3f} R par trade")
