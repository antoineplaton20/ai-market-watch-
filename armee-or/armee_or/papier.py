"""PORTEFEUILLES PAPIER — la même décision exécutée en parallèle avec chaque profil de levier.

Rien n'est envoyé à une plateforme. La simulation est volontairement défavorable dans le doute :
entrée à l'ouverture qui suit la décision (jamais au prix déjà vu), frais + glissement aux deux bouts,
financement toutes les heures, et si la liquidation, le stop et l'objectif sont atteignables dans la même
bougie, c'est le pire qui est retenu. Un compte liquidé perd sa marge ; un compte vidé est déclaré « ruiné ».
"""
from __future__ import annotations

import numpy as np

from . import levier as L

REGLES = {"stop_atr": 3.0, "rr": None, "duree": 4}   # stop de sécurité ; sortie à l'horizon du pronostic
RUINE = 0.05                 # compte sous 5 % du départ : ruiné


def compte_neuf(capital):
    return {"capital": float(capital), "depart": float(capital), "pic": float(capital), "baisse_max": 0.0,
            "position": None, "ruine": False, "liquidations": 0, "trades": 0, "gagnants": 0,
            "frais": 0.0, "financement": 0.0}


def _fermer(compte, prix, ts, motif, trades):
    pos = compte["position"]
    s = pos["sens"]
    prix_net = prix * (1 - s * L.GLISSEMENT)
    brut = s * (prix_net - pos["entree"]) / pos["entree"] * pos["notionnel"]
    frais = pos["notionnel"] * L.FRAIS
    if motif == "liquidation":
        pnl = -compte["capital"]           # marge perdue (le reliquat part en frais de liquidation) ; jamais sous 0
        frais = 0.0
    else:
        pnl = brut - frais
    compte["capital"] = max(0.0, compte["capital"] + pnl)
    compte["frais"] += frais
    compte["trades"] += 1
    compte["gagnants"] += int(pnl > 0)
    compte["liquidations"] += int(motif == "liquidation")
    compte["pic"] = max(compte["pic"], compte["capital"])
    compte["baisse_max"] = max(compte["baisse_max"], 1 - compte["capital"] / compte["pic"])
    if compte["capital"] < compte["depart"] * RUINE:
        compte["ruine"] = True
    trades.append({**pos, "sortie_ts": int(ts), "prix_sortie": float(prix_net), "motif": motif, "pnl": float(pnl),
                   "capital_apres": compte["capital"]})
    compte["position"] = None


def pas(compte, profil, i, b, atr, sens_decision, trades, regles=None):
    """Traite la bougie i (ouverture, extrêmes, clôture) pour un compte. sens_decision : décision prise à la
    CLÔTURE de la bougie i-1 (+1 achat, -1 vente, 0 rien). Règles : stop de sécurité en ATR, objectif en
    multiple du risque (None = aucun), durée maximale en bougies (horizon du pronostic)."""
    regles = regles or REGLES
    heures_barre = (b["ts"][1] - b["ts"][0]) / 3_600_000 if len(b["ts"]) > 1 else 1.0
    o, h, l, c, ts = b["o"][i], b["h"][i], b["l"][i], b["c"][i], b["ts"][i]
    if compte["ruine"]:
        return
    if compte["position"] is None and sens_decision and not np.isnan(atr[i - 1]):
        s = sens_decision
        entree = o * (1 + s * L.GLISSEMENT)
        stop = entree - s * regles["stop_atr"] * atr[i - 1]
        objectif = (entree + s * regles["rr"] * regles["stop_atr"] * atr[i - 1]) if regles["rr"] else None
        notionnel, lev = L.taille(profil, compte["capital"], entree, stop)
        if notionnel > 0:
            compte["capital"] -= notionnel * L.FRAIS
            compte["frais"] += notionnel * L.FRAIS
            compte["position"] = {"profil": profil, "sens": s, "entree_ts": int(ts), "entree": float(entree),
                                  "notionnel": float(notionnel), "levier": float(lev), "stop": float(stop),
                                  "objectif": float(objectif) if objectif else None, "barres": 0,
                                  "liquidation": float(L.prix_liquidation(entree, s, compte["capital"], notionnel))}
    pos = compte["position"]
    if pos is None:
        return
    s, liq, stop, obj = pos["sens"], pos["liquidation"], pos["stop"], pos["objectif"]
    defav, fav = (l, h) if s > 0 else (h, l)
    touche = (lambda niveau: defav <= niveau) if s > 0 else (lambda niveau: defav >= niveau)
    atteint = (lambda niveau: fav >= niveau) if s > 0 else (lambda niveau: fav <= niveau)
    ouverture_pire = (o <= liq) if s > 0 else (o >= liq)
    liq_avant_stop = (liq >= stop) if s > 0 else (liq <= stop)
    if ouverture_pire or (touche(liq) and (liq_avant_stop or not touche(stop))):
        _fermer(compte, liq, ts, "liquidation", trades)
    elif touche(stop):
        prix = min(o, stop) if s > 0 else max(o, stop)            # trou de cotation : pire que le stop
        _fermer(compte, prix, ts, "stop", trades)
    elif obj is not None and atteint(obj):
        _fermer(compte, obj, ts, "objectif", trades)
    else:
        pos["barres"] += 1
        cout = pos["notionnel"] * L.FINANCEMENT_8H / 8 * heures_barre * s   # payé par les acheteurs si taux positif
        compte["capital"] -= cout
        compte["financement"] += cout
        if pos["barres"] >= regles["duree"]:
            _fermer(compte, c, ts, "durée", trades)


def backtest(b, decisions, atr, capital=1000.0, profils=None, regles=None):
    """Rejoue l'historique : decisions[i] = décision prise à la clôture de la bougie i."""
    profils = profils or list(L.PROFILS)
    comptes = {p: compte_neuf(capital) for p in profils}
    trades = {p: [] for p in profils}
    courbes = {p: [] for p in profils}
    for i in range(1, len(b["c"])):
        for p in profils:
            pas(comptes[p], p, i, b, atr, int(decisions[i - 1]), trades[p], regles)
            if i % 24 == 0:
                courbes[p].append([int(b["ts"][i] // 1000), round(comptes[p]["capital"], 2)])
    return comptes, trades, courbes
