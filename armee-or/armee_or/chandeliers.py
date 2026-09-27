"""ANALYSTE DES CHANDELIERS — 40 motifs classiques (S. Nison, « Japanese Candlestick Charting Techniques », 1991 ;
T. Bulkowski, « Encyclopedia of Candlestick Charts », 2008) détectés sur chaque bougie, puis MESURÉS sur
l'historique de l'or : un motif n'a de valeur que si, sur l'or, il a réellement été suivi plus souvent qu'à
l'ordinaire par un mouvement dans le sens annoncé.

Contexte de tendance : « après baisse » = clôture sous la moyenne mobile exponentielle de 20 bougies,
« après hausse » = au-dessus. Les motifs à trou de cotation (bébé abandonné, kicker) sont rares sur l'or,
coté presque sans interruption : leur nombre d'occurrences le montre.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

from . import indicateurs as I


def _decale(x, k):
    """x[t-k] aligné sur t (NaN au début)."""
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:-k] if k else x
    return out


def detecter(b):
    """-> {nom: (sens, tableau booléen)} ; sens +1 haussier, -1 baissier, 0 indécision."""
    o, h, l, c = b["o"], b["h"], b["l"], b["c"]
    corps = np.abs(c - o)
    etendue = np.maximum(h - l, 1e-12)
    haut_meche = h - np.maximum(o, c)
    bas_meche = np.minimum(o, c) - l
    vert, rouge = c > o, c < o
    atr = I.atr(h, l, c, 14)
    grand = corps > 0.6 * np.nan_to_num(atr, nan=np.inf)
    ema = I.ema(c, 20)
    baisse_avant = c < np.nan_to_num(ema, nan=0) * 1.0
    hausse_avant = c > np.nan_to_num(ema, nan=np.inf)
    o1, c1, h1, l1 = _decale(o, 1), _decale(c, 1), _decale(h, 1), _decale(l, 1)
    o2, c2, h2, l2 = _decale(o, 2), _decale(c, 2), _decale(h, 2), _decale(l, 2)
    o3, c3, h3, l3 = _decale(o, 3), _decale(c, 3), _decale(h, 3), _decale(l, 3)
    o4, c4, h4, l4 = _decale(o, 4), _decale(c, 4), _decale(h, 4), _decale(l, 4)
    corps1, corps2 = np.abs(c1 - o1), np.abs(c2 - o2)
    corps3, corps4 = np.abs(c3 - o3), np.abs(c4 - o4)
    a = np.nan_to_num(atr)
    a1, a2, a4 = _decale(a, 1), _decale(a, 2), _decale(a, 4)
    doji = corps <= 0.1 * etendue
    doji1 = corps1 <= 0.1 * np.maximum(h1 - l1, 1e-12)
    grand1, grand2, grand4 = corps1 > 0.6 * a1, corps2 > 0.6 * a2, corps4 > 0.6 * a4
    with np.errstate(invalid="ignore"):
        m = {
            "marteau": (1, (bas_meche >= 2 * corps) & (haut_meche <= 0.3 * etendue) & baisse_avant & (corps > 0)),
            "etoile_filante": (-1, (haut_meche >= 2 * corps) & (bas_meche <= 0.3 * etendue) & hausse_avant & (corps > 0)),
            "avalement_haussier": (1, vert & (c1 < o1) & (o <= c1) & (c >= o1) & (corps > corps1)),
            "avalement_baissier": (-1, rouge & (c1 > o1) & (o >= c1) & (c <= o1) & (corps > corps1)),
            "harami_haussier": (1, vert & (c1 < o1) & (corps1 > np.nan_to_num(atr) * 0.6) & (o > c1) & (c < o1)),
            "harami_baissier": (-1, rouge & (c1 > o1) & (corps1 > np.nan_to_num(atr) * 0.6) & (o < c1) & (c > o1)),
            "etoile_du_matin": (1, (c2 < o2) & (corps2 > 0.6 * np.nan_to_num(atr)) & (corps1 < 0.3 * corps2)
                                & vert & (c > (o2 + c2) / 2)),
            "etoile_du_soir": (-1, (c2 > o2) & (corps2 > 0.6 * np.nan_to_num(atr)) & (corps1 < 0.3 * corps2)
                               & rouge & (c < (o2 + c2) / 2)),
            "trois_soldats": (1, vert & (c1 > o1) & (c2 > o2) & (c > c1) & (c1 > c2)
                              & (corps > 0.5 * etendue) & (corps1 > 0.5 * (h1 - l1))),
            "trois_corbeaux": (-1, rouge & (c1 < o1) & (c2 < o2) & (c < c1) & (c1 < c2)
                               & (corps > 0.5 * etendue) & (corps1 > 0.5 * (h1 - l1))),
            "penetrante": (1, vert & (c1 < o1) & (o < c1) & (c > (o1 + c1) / 2) & (c < o1)),
            "couverture_nuageuse": (-1, rouge & (c1 > o1) & (o > c1) & (c < (o1 + c1) / 2) & (c > o1)),
            "marubozu_haussier": (1, vert & grand & (haut_meche <= 0.05 * etendue) & (bas_meche <= 0.05 * etendue)),
            "marubozu_baissier": (-1, rouge & grand & (haut_meche <= 0.05 * etendue) & (bas_meche <= 0.05 * etendue)),
            "doji": (0, doji),
            "bougie_interieure": (0, (h < h1) & (l > l1)),
            # --- 24 motifs supplémentaires ---------------------------------------------------------------
            "pendu": (-1, (bas_meche >= 2 * corps) & (haut_meche <= 0.3 * etendue) & hausse_avant & (corps > 0)),
            "marteau_inverse": (1, (haut_meche >= 2 * corps) & (bas_meche <= 0.3 * etendue) & baisse_avant & (corps > 0)),
            "doji_libellule": (1, doji & (haut_meche <= 0.1 * etendue) & (bas_meche >= 0.6 * etendue) & baisse_avant),
            "doji_pierre_tombale": (-1, doji & (bas_meche <= 0.1 * etendue) & (haut_meche >= 0.6 * etendue)
                                    & hausse_avant),
            "pinces_bas": (1, (np.abs(l - l1) <= 0.05 * a) & (c1 < o1) & vert & baisse_avant),
            "pinces_haut": (-1, (np.abs(h - h1) <= 0.05 * a) & (c1 > o1) & rouge & hausse_avant),
            "bebe_abandonne_haussier": (1, (c2 < o2) & grand2 & doji1 & (h1 < l2) & (l > h1) & vert),
            "bebe_abandonne_baissier": (-1, (c2 > o2) & grand2 & doji1 & (l1 > h2) & (h < l1) & rouge),
            "etoile_doji_du_matin": (1, (c2 < o2) & grand2 & doji1 & vert & (c > (o2 + c2) / 2)),
            "etoile_doji_du_soir": (-1, (c2 > o2) & grand2 & doji1 & rouge & (c < (o2 + c2) / 2)),
            "trois_interieurs_haussier": (1, (c2 < o2) & grand2 & (c1 > o1) & (o1 > c2) & (c1 < o2) & vert & (c > o2)),
            "trois_interieurs_baissier": (-1, (c2 > o2) & grand2 & (c1 < o1) & (o1 < c2) & (c1 > o2) & rouge & (c < o2)),
            "trois_exterieurs_haussier": (1, (c2 < o2) & (c1 > o1) & (o1 <= c2) & (c1 >= o2) & (corps1 > corps2)
                                          & vert & (c > c1)),
            "trois_exterieurs_baissier": (-1, (c2 > o2) & (c1 < o1) & (o1 >= c2) & (c1 <= o2) & (corps1 > corps2)
                                          & rouge & (c < c1)),
            "kicker_haussier": (1, (c1 < o1) & grand1 & vert & grand & (o >= o1)),
            "kicker_baissier": (-1, (c1 > o1) & grand1 & rouge & grand & (o <= o1)),
            "ceinture_haussiere": (1, vert & grand & (bas_meche <= 0.02 * etendue) & (haut_meche <= 0.25 * etendue)
                                   & baisse_avant),
            "ceinture_baissiere": (-1, rouge & grand & (haut_meche <= 0.02 * etendue) & (bas_meche <= 0.25 * etendue)
                                   & hausse_avant),
            "trois_methodes_montantes": (1, (c4 > o4) & grand4
                                         & (corps3 < 0.5 * corps4) & (corps2 < 0.5 * corps4) & (corps1 < 0.5 * corps4)
                                         & (np.fmax(np.fmax(h3, h2), h1) <= h4) & (np.fmin(np.fmin(l3, l2), l1) >= l4)
                                         & vert & (c > c4)),
            "trois_methodes_descendantes": (-1, (c4 < o4) & grand4
                                            & (corps3 < 0.5 * corps4) & (corps2 < 0.5 * corps4) & (corps1 < 0.5 * corps4)
                                            & (np.fmax(np.fmax(h3, h2), h1) <= h4) & (np.fmin(np.fmin(l3, l2), l1) >= l4)
                                            & rouge & (c < c4)),
            "harami_croise_haussier": (1, doji & (c1 < o1) & grand1 & (np.maximum(o, c) < o1) & (np.minimum(o, c) > c1)),
            "harami_croise_baissier": (-1, doji & (c1 > o1) & grand1 & (np.maximum(o, c) < c1) & (np.minimum(o, c) > o1)),
            "frappe_trois_lignes_haussiere": (1, (c3 < o3) & (c2 < o2) & (c1 < o1) & (c2 < c3) & (c1 < c2)
                                              & vert & (o <= c1) & (c >= o3)),
            "frappe_trois_lignes_baissiere": (-1, (c3 > o3) & (c2 > o2) & (c1 > o1) & (c2 > c3) & (c1 > c2)
                                              & rouge & (o >= c1) & (c <= o3)),
        }
    return {k: (s, np.nan_to_num(v, nan=0).astype(bool)) for k, (s, v) in m.items()}


def statistiques(b, horizon=4, motifs=None):
    """Pour chaque motif : sur l'historique, que s'est-il passé `horizon` bougies plus tard ?

    -> {motif: {n, reussite (dans le sens annoncé), base (fréquence ordinaire), z (écart significatif si |z| > 2),
                mouvement_atr (mouvement moyen, en ATR, dans le sens annoncé)}}"""
    c = b["c"]
    motifs = motifs or detecter(b)
    atr = I.atr(b["h"], b["l"], c, 14)
    fut = np.full(len(c), np.nan)
    if len(c) > horizon:
        fut[:-horizon] = c[horizon:] - c[:-horizon]
    valide = ~np.isnan(fut) & ~np.isnan(atr)
    hausse = fut > 0
    base_hausse = hausse[valide].mean() if valide.any() else 0.5
    out = {}
    for nom, (sens, masque) in motifs.items():
        sel = masque & valide
        n = int(sel.sum())
        if n == 0:
            out[nom] = {"sens": sens, "n": 0, "reussite": None, "base": None, "z": 0.0, "mouvement_atr": 0.0}
            continue
        s = sens if sens else 1
        base_p = base_hausse if s > 0 else 1 - base_hausse
        reussite = float((hausse[sel] if s > 0 else ~hausse[sel]).mean())
        z = (reussite - base_p) / math.sqrt(max(base_p * (1 - base_p), 1e-9) / n)
        out[nom] = {"sens": sens, "n": n, "reussite": reussite, "base": float(base_p), "z": float(z),
                    "mouvement_atr": float(np.mean(s * fut[sel] / atr[sel]))}
    return out


def seuil_z(nb_motifs, risque=0.05):
    """Écart significatif exigé quand on teste `nb_motifs` motifs à la fois (correction de Bonferroni) : avec 40 motifs
    et le seuil habituel |z| > 2, environ 2 motifs paraîtraient « fiables » par pur hasard."""
    return NormalDist().inv_cdf(1 - risque / (2 * max(1, nb_motifs)))


def derniers_motifs(b, stats=None):
    """Motifs présents sur la DERNIÈRE bougie fermée, avec leur fiabilité historique sur l'or."""
    motifs = detecter(b)
    exige = seuil_z(len(motifs))
    out = []
    for nom, (sens, masque) in motifs.items():
        if len(masque) and masque[-1]:
            st = (stats or {}).get(nom, {})
            out.append({"motif": nom, "sens": sens, "n": st.get("n"), "reussite": st.get("reussite"),
                        "z": st.get("z"), "fiable": bool(st.get("n", 0) >= 30 and abs(st.get("z", 0)) >= exige)})
    return out
