"""Simulation bougie par bougie — la MÊME fonction sert au backtest et au test en direct (papier).

Règles (prudentes, identiques au Pine Script généré) :
- signal calculé à la CLÔTURE d'une bougie, achat à l'OUVERTURE de la suivante (jamais sur un prix déjà vu) ;
- stop = clôture du signal − stop_atr × ATR ; objectif = clôture + rr × stop_atr × ATR ;
- ouverture déjà sous le stop (trou de cotation) : pas d'achat ; déjà au-dessus de l'objectif : pas d'achat ;
- stop et objectif touchés dans la même bougie : on compte le STOP (pire cas) ;
- trou de cotation sous le stop : sortie au prix d'ouverture (pire que le stop) ;
- sortie de tendance (option) : décidée à la clôture, exécutée à l'ouverture suivante ;
- frais 0,1 % par côté + glissement 0,05 % par côté ; une seule position à la fois, achat seulement ;
- taille : 1 % du capital risqué par trade (plafonnée à 100 % du capital, jamais de levier).
"""
from __future__ import annotations

import math

import numpy as np

from .strategie import conditions

FRAIS = 0.001
GLISSEMENT = 0.0005
RISQUE = 0.01


def _resultat(entree, sortie, stop, frais, glissement):
    x = sortie * (1 - glissement)
    net = x * (1 - frais) / (entree * (1 + frais)) - 1
    risque = (entree - stop) / entree
    part = min(RISQUE / risque, 1.0) if risque > 0 else 0.0
    return net, (net / risque if risque > 0 else 0.0), part * net


def simuler(barres, spec, *, frais=FRAIS, glissement=GLISSEMENT, etat=None, signaux=None):
    """Parcourt les bougies FERMÉES de `barres` après etat['dernier_ts'].

    -> (trades terminés, événements, état). L'état (position ouverte, dernière bougie traitée) permet de reprendre
    exactement où l'on s'était arrêté : c'est ce qu'utilise le test en direct.
    """
    ts, o, h, l, c = (barres[k] for k in ("ts", "o", "h", "l", "c"))
    entree, tendance, atr = signaux or conditions(barres, spec)
    etat = dict(etat or {"position": None, "dernier_ts": None})
    pos = etat.get("position")
    trades, evenements = [], []
    k, rr = spec["stop_atr"], spec["rr"]
    dernier = etat.get("dernier_ts")
    debut = 1
    if dernier is not None:
        idx = np.searchsorted(ts, dernier, side="right")
        debut = max(1, int(idx))

    def sortir(i, prix, motif):
        nonlocal pos
        net, r, rc = _resultat(pos["prix_entree"], prix, pos["stop"], frais, glissement)
        t = {**pos, "sortie_ts": int(ts[i]), "prix_sortie": float(prix), "motif": motif,
             "rendement": net, "R": r, "r_capital": rc}
        trades.append(t)
        evenements.append({"type": "sortie", **t})
        pos = None

    for i in range(debut, len(ts)):
        j = i - 1                                          # bougie dont la clôture a produit la décision
        if pos is not None and spec.get("sortie_tendance") and not tendance[j]:
            sortir(i, o[i], "tendance")
        if pos is None and entree[j] and not math.isnan(atr[j]):
            stop = c[j] - k * atr[j]
            objectif = c[j] + rr * k * atr[j]
            prix = o[i] * (1 + glissement)
            if stop < prix < objectif and stop > 0:
                pos = {"entree_ts": int(ts[i]), "prix_entree": float(prix), "stop": float(stop),
                       "objectif": float(objectif)}
                evenements.append({"type": "entree", **pos})
        if pos is not None:
            if o[i] <= pos["stop"] and pos["entree_ts"] != int(ts[i]):
                sortir(i, o[i], "stop (trou)")
            elif l[i] <= pos["stop"]:
                sortir(i, pos["stop"], "stop")
            elif h[i] >= pos["objectif"]:
                prix = o[i] if o[i] >= pos["objectif"] and pos["entree_ts"] != int(ts[i]) else pos["objectif"]
                sortir(i, prix, "objectif")
        etat["dernier_ts"] = int(ts[i])
    etat["position"] = pos
    return trades, evenements, etat


def statistiques(trades):
    """Indicateurs d'un ensemble de trades (capital composé, 1 % risqué par trade)."""
    n = len(trades)
    if not n:
        return {"trades": 0, "gain_pct": 0.0, "facteur_profit": 0.0, "taux_gain": 0.0, "baisse_max_pct": 0.0,
                "R_moyen": 0.0}
    rc = np.array([t["r_capital"] for t in sorted(trades, key=lambda t: t["sortie_ts"])])
    courbe = np.cumprod(1 + rc)
    sommet = np.maximum.accumulate(np.concatenate(([1.0], courbe)))[1:]
    gains, pertes = rc[rc > 0].sum(), -rc[rc < 0].sum()
    return {"trades": n, "gain_pct": float((courbe[-1] - 1) * 100),
            "facteur_profit": float(gains / pertes) if pertes > 0 else (99.0 if gains > 0 else 0.0),
            "taux_gain": float((rc > 0).mean() * 100),
            "baisse_max_pct": float(((sommet - courbe) / sommet).max() * 100),
            "R_moyen": float(np.mean([t["R"] for t in trades]))}
