"""Recherche R6 (25/10/2026) : les idées publiées les plus sérieuses, testées à l'identique sur 34 marchés Yahoo
2000-2026. Paramètres FIXÉS par les sources (aucun réglage sur nos données). Mêmes règles pour toutes :
- décision à la clôture du jour i, ordre exécuté à l'OUVERTURE du jour i+1 (sauf « nuit », qui exige d'acheter à la
  clôture : à faire en direct par une équipe minutée) ;
- taille de chaque marché à 10 % de volatilité annuelle (60 jours), levier 5 au plus ;
- frais : écart par famille à chaque changement de position, financement −3 %/an pour chaque nuit tenue ;
- portefeuille à risque égal ; jugé sur CHAQUE moitié et contre « toujours acheter » le MÊME panier.

Usage : python etudes/recherche_r6.py DOSSIER_YAHOO RACINE_ARMEE DOSSIER_ETUDES
"""
import datetime as dt
import math
import sys

import numpy as np

sys.path.insert(0, sys.argv[2])
sys.path.insert(0, sys.argv[3])
from armee_or import indicateurs as I, marches as M   # noqa: E402
from charger import charger                            # noqa: E402

INDICES = {"GSPC", "NDX", "DJI", "GDAXI", "FCHI", "FTSE", "N225", "STOXX50E"}


def taille(c, i):
    vol = M.volatilite(c, i)
    return min(M.LEVIER_MAX, M.VOL_BANC / vol) if vol > 0 else 0.0


def executer(d, cible, nuit_seulement=False):
    """cible[i] : fraction de la taille voulue à partir de l'ouverture i+1 (décidée à la clôture i).
    -> (rendement net quotidien, trades [résultat en part du capital])."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    ecart, swap = d["cout"]["ecart"], d["cout"]["swap_long"]
    n = len(c)
    net, trades = np.zeros(n), []
    w, poids, encours = 0.0, 0.0, None
    for i in range(1, n):
        if nuit_seulement:                                  # acheté à la clôture i-1, vendu à l'ouverture i
            if cible[i - 1] > 0:
                p = cible[i - 1] * taille(c, i - 1)
                r = p * (o[i] / c[i - 1] - 1) - 2 * p * ecart + p * swap
                net[i] = r
                trades.append(r)
            continue
        nouveau = cible[i - 1] * poids if cible[i - 1] > 0 and w > 0 else 0.0
        if cible[i - 1] > 0 and w == 0:
            poids = taille(c, i - 1)
            nouveau = cible[i - 1] * poids
        r = w * (o[i] / c[i - 1] - 1) + nouveau * (c[i] / o[i] - 1) - abs(nouveau - w) * ecart
        if nouveau > 0:
            r += nouveau * swap
        net[i] = r
        if w == 0 and nouveau > 0:
            encours = 0.0
        if encours is not None:
            encours += r
        if w > 0 and nouveau == 0:
            trades.append(encours)
            encours = None
        w = nouveau
    return net, trades


# ------------------------------------------------------------------------------------------------ les règles (cibles)
def dates(d):
    return [dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date() for t in d["ts"]]


def naif(d):
    c = d["c"]
    x = np.ones(len(c))
    x[:200] = 0
    return x


def tsmom12(d):
    c = d["c"]
    x = np.zeros(len(c))
    x[252:] = (c[252:] / c[:-252] - 1) > 0
    return x


def tsmom_1_3_12(d):
    c = d["c"]
    x = np.zeros(len(c))
    for k in (21, 63, 252):
        s = np.zeros(len(c))
        s[k:] = (c[k:] / c[:-k] - 1) > 0
        x += s / 3
    x[:252] = 0
    return x


def moyennes_50_100_200(d):
    c = d["c"]
    x = sum(np.where(np.isfinite(m := I.sma(c, k)) & (c > m), 1.0, 0.0) for k in (50, 100, 200)) / 3
    x[:200] = 0
    return x


def rsi2(d):
    """Connors et Alvarez (2008) : au-dessus de la moyenne 200 j, RSI(2) < 10 → achat ; sortie au-dessus de la
    moyenne 5 j."""
    c = d["c"]
    r, m5, m200 = I.rsi(c, 2), I.sma(c, 5), I.sma(c, 200)
    x, dedans = np.zeros(len(c)), False
    for i in range(len(c)):
        if not dedans and np.isfinite(m200[i]) and c[i] > m200[i] and r[i] < 10:
            dedans = True
        elif dedans and c[i] > m5[i]:
            dedans = False
        x[i] = dedans
    return x


def ibs(d):
    """Force de clôture (IBS) : achat si la clôture est dans le bas 20 % de la journée, sortie au-dessus de 80 %."""
    h, l, c = d["h"], d["l"], d["c"]
    v = np.where(h > l, (c - l) / np.where(h > l, h - l, 1), 0.5)
    x, dedans = np.zeros(len(c)), False
    for i in range(len(c)):
        if not dedans and v[i] < 0.2:
            dedans = True
        elif dedans and v[i] > 0.8:
            dedans = False
        x[i] = dedans
    return x


def tournant_du_mois(d):
    """Lakonishok et Smidt (1988) : du dernier jour de bourse du mois au 3e du mois suivant (ici : achat à
    l'ouverture du dernier jour, vente à l'ouverture du 4e)."""
    j = dates(d)
    n = len(j)
    x = np.zeros(n)
    for i in range(n - 2):
        if j[i + 1].month != j[i + 2].month:               # demain = dernier jour du mois : acheter à son ouverture
            for k in range(i, min(n, i + 4)):               # tenu du dernier jour au 3e jour inclus
                x[k] = 1
    return x


def halloween(d):
    """Bouman et Jacobsen (2002) : investi de novembre à avril, dehors de mai à octobre."""
    j = dates(d)
    x = np.array([1.0 if (j[i + 1] if i + 1 < len(j) else j[i]).month in (11, 12, 1, 2, 3, 4) else 0.0
                  for i in range(len(j))])
    x[:200] = 0
    return x


def nuit(d):
    """Cliff, Cooper et Gulen (2008) : acheté à la clôture, vendu à l'ouverture suivante, chaque jour."""
    x = np.ones(len(d["c"]))
    x[:200] = 0
    return x


REGLES = [("toujours acheter (naïf)", naif, "tous"), ("200 jours, stop 5 ATR (l'équipe)", None, "tous"),
          ("momentum 12 mois (MOP 2012)", tsmom12, "tous"), ("momentum 1/3/12 mois (AQR)", tsmom_1_3_12, "tous"),
          ("moyennes 50/100/200 combinées", moyennes_50_100_200, "tous"),
          ("indices : toujours acheter (naïf)", naif, "indices"), ("indices : RSI(2) Connors", rsi2, "indices"),
          ("indices : IBS < 0,2", ibs, "indices"), ("indices : tournant du mois", tournant_du_mois, "indices"),
          ("indices : Halloween (nov.-avr.)", halloween, "indices"), ("indices : nuit (clôture → ouverture)", nuit,
                                                                     "indices")]


def portefeuille(marches, fonction, nuit_seulement=False):
    jours = np.array(sorted({int(t) // 86_400_000 for d in marches.values() for t in d["ts"]}))
    pos = {j: k for k, j in enumerate(jours)}
    coupe = jours[len(jours) // 2]
    somme, nb, tous = np.zeros(len(jours)), np.zeros(len(jours)), []
    for d in marches.values():
        if fonction is None:
            journal = []
            net, _ = M.simuler_marche(d["o"], d["h"], d["l"], d["c"], "sma200", d["cout"], journal=journal)
            tr = [t[2] for t in journal if t[1] is not None]
        else:
            net, tr = executer(d, fonction(d), nuit_seulement)
        idx = np.array([pos[int(t) // 86_400_000] for t in d["ts"]])
        somme[idx] += net
        nb[idx] += 1
        tous += tr
    ok = nb > 0
    p, j = somme[ok] / nb[ok], jours[ok]
    mois = {}
    for v, jj in zip(p, j):
        k = dt.date.fromtimestamp(int(jj) * 86400).strftime("%Y-%m")
        mois[k] = mois.get(k, 0.0) + v
    st = [M.statistiques(p[j < coupe]), M.statistiques(p[j >= coupe]), M.statistiques(p)]
    return st, np.array(tous), np.mean([v > 0 for v in mois.values()])


if __name__ == "__main__":
    tous = charger(sys.argv[1], M)
    print("règle                                | Sharpe moitiés | %/an | pire baisse | mois + | trades | gagnants | gain moy | perte moy")
    for nom, f, panier in REGLES:
        m = tous if panier == "tous" else {s: d for s, d in tous.items() if s in INDICES}
        st, r, mp = portefeuille(m, f, nuit_seulement=(f is nuit))
        g = (r > 0).mean() * 100 if len(r) else 0
        print(f"{nom:37}| {st[0]['sharpe']:+.2f} / {st[1]['sharpe']:+.2f}  | {st[2]['rendement']*100:+4.1f} | "
              f"{st[2]['pire_baisse']*100:6.0f} %    | {mp*100:3.0f} %  | {len(r):6} | {g:5.1f} %  | "
              f"{r[r > 0].mean()*100 if (r > 0).any() else 0:+.2f} % | {r[r <= 0].mean()*100 if (r <= 0).any() else 0:+.2f} %")
