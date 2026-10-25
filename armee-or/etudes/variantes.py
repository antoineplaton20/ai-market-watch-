"""Étude : peut-on rendre CHAQUE trade gagnant sans perdre au total ? Variantes de la règle des 200 jours, mêmes
données (34 marchés Yahoo 2000-2026), mêmes coûts, exécution à l'ouverture suivante, taille à 10 % de volatilité.
- tp : prise de gain dès +k ATR (ATR à l'entrée), rachat possible le lendemain si le signal tient ;
- gain_seul : on ne sort JAMAIS à perte (sortie de règle seulement si le trade est gagnant), pas de stop ;
- stop : stop de catastrophe (ATR), None = aucun."""
import math, sys
import numpy as np
sys.path.insert(0, sys.argv[2]); sys.path.insert(0, sys.argv[3])
from armee_or import marches as M, indicateurs as I
from charger import charger


def simuler(d, tp=None, gain_seul=False, stop_atr=5.0):
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    ecart, swap = d["cout"]["ecart"], d["cout"]["swap_long"]
    n = len(c); sig = M.signal(c, "sma200"); atr = I.atr(h, l, c, 20)
    net = np.zeros(n); trades = []; w = 0.0; ordre = None; taille = 0.0; entree = stop = cible = 0.0; res = 0.0
    bloque = False; debut = 0; dures = []
    for i in range(1, n):
        if ordre == "sortir" and w:
            r = w * (o[i] / c[i - 1] - 1) - w * ecart; net[i] += r; trades.append(res + r); dures.append(i - debut); w = 0.0
        elif ordre == "entrer":
            w, entree, debut = taille, o[i], i
            stop = entree - stop_atr * atr[i - 1] if stop_atr else -1.0
            cible = entree + tp * atr[i - 1] if tp else math.inf
            res = -w * ecart; net[i] -= w * ecart
            if l[i] <= stop:
                r = w * (stop / entree - 1) - w * ecart; net[i] += r; trades.append(res + r); dures.append(0); w = 0.0; bloque = True
            elif h[i] >= cible:
                r = w * (cible / entree - 1) - w * ecart; net[i] += r; trades.append(res + r); dures.append(0); w = 0.0
            else:
                r = w * (c[i] / entree - 1) + w * swap; net[i] += r; res += r
        elif w:
            if l[i] <= stop:
                r = w * (min(o[i], stop) / c[i - 1] - 1) - w * ecart; net[i] += r; trades.append(res + r); dures.append(i - debut); w = 0.0; bloque = True
            elif h[i] >= cible:
                px = max(o[i], cible)
                r = w * (px / c[i - 1] - 1) - w * ecart; net[i] += r; trades.append(res + r); dures.append(i - debut); w = 0.0
            else:
                r = w * (c[i] / c[i - 1] - 1) + w * swap; net[i] += r; res += r
        ordre = None
        if sig[i] == 0:
            bloque = False
            if w and (not gain_seul or res + w * (c[i] / c[i] - 1) - w * ecart > 0):
                ordre = "sortir"
        elif not w and not bloque and i >= 60 and i + 1 < n:
            vol = M.volatilite(c, i)
            if vol > 0 and np.isfinite(atr[i]):
                ordre, taille = "entrer", min(M.LEVIER_MAX, M.VOL_BANC / vol)
    ouvert = res if w else None
    return net, trades, ouvert, dures


def portefeuille(marches, **v):
    jours = np.array(sorted({int(t) // 86_400_000 for d in marches.values() for t in d["ts"]}))
    pos = {j: k for k, j in enumerate(jours)}; coupe = jours[len(jours) // 2]
    somme, nb = np.zeros(len(jours)), np.zeros(len(jours)); tous, ouverts, dures = [], [], []
    for d in marches.values():
        net, tr, ouv, du = simuler(d, **v)
        idx = np.array([pos[int(t) // 86_400_000] for t in d["ts"]])
        somme[idx] += net; nb[idx] += 1; tous += tr; dures += du
        if ouv is not None: ouverts.append(ouv)
    ok = nb > 0; p, j = somme[ok] / nb[ok], jours[ok]
    st = [M.statistiques(p[j < coupe]), M.statistiques(p[j >= coupe]), M.statistiques(p)]
    r = np.array(tous)
    return st, r, ouverts, dures


marches = charger(sys.argv[1], M)
print("variante                         | Sharpe moitiés | %/an  | pire baisse | trades | gagnants | gain moy | perte moy | pire trade | ouverts à la fin (pire)")
for nom, v in [("200 j, stop 5 ATR (l'équipe)", {}),
               ("+ prise de gain 0,5 ATR", {"tp": 0.5}), ("+ prise de gain 1 ATR", {"tp": 1.0}),
               ("+ prise de gain 2 ATR", {"tp": 2.0}), ("+ prise de gain 3 ATR", {"tp": 3.0}),
               ("+ prise de gain 1 ATR, stop 10 ATR", {"tp": 1.0, "stop_atr": 10.0}),
               ("jamais de sortie à perte, sans stop", {"gain_seul": True, "stop_atr": None}),
               ("jamais à perte + prise de gain 1 ATR", {"gain_seul": True, "stop_atr": None, "tp": 1.0})]:
    st, r, ouv, du = portefeuille(marches, **v)
    print(f"{nom:33}| {st[0]['sharpe']:+.2f} / {st[1]['sharpe']:+.2f}  | {st[2]['rendement']*100:+.1f} | {st[2]['pire_baisse']*100:6.0f} %    | {len(r):6} | "
          f"{(r > 0).mean()*100:6.1f} % | {r[r > 0].mean()*100 if (r > 0).any() else 0:+.2f} % | {r[r <= 0].mean()*100 if (r <= 0).any() else 0:+.2f} %  | "
          f"{r.min()*100:+.1f} %   | {len(ouv)} ({min(ouv)*100 if ouv else 0:+.1f} %) · durée moy {np.mean(du):.0f} j, max {max(du)} j")
