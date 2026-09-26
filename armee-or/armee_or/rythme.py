"""ANALYSTE DU RYTHME — volatilité, séances mondiales, saisonnalité horaire, séries de bougies.

Le rythme des bougies se MESURE ; il ne se commande pas : chercher à influencer les cours (ordres fictifs,
opérations concertées) est de la manipulation de marché, interdite (règlement européen MAR). L'armée observe,
calcule et anticipe, rien de plus.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from . import indicateurs as I

SEANCES = (("Asie (Tokyo, Shanghai)", 0, 7), ("Londres", 7, 13), ("Londres + New York", 13, 16),
           ("New York", 16, 21), ("Calme (fin de journée US)", 21, 24))


def seance(ts_ms):
    heure = dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc).hour
    return next(nom for nom, a, b in SEANCES if a <= heure < b)


def profil_horaire(b):
    """Par heure UTC : amplitude moyenne (en % du prix) et fréquence de hausse, sur tout l'historique fourni."""
    heures = (b["ts"] // 3_600_000) % 24
    amp = (b["h"] - b["l"]) / b["c"] * 100
    ret = np.diff(b["c"], prepend=np.nan) / b["c"]
    out = []
    for hr in range(24):
        sel = (heures == hr) & ~np.isnan(ret)
        out.append({"heure": hr, "amplitude_pct": float(amp[sel].mean()) if sel.any() else 0.0,
                    "hausse": float((ret[sel] > 0).mean()) if sel.any() else 0.5, "n": int(sel.sum())})
    return out


def series(b):
    """Probabilité historique de hausse de la bougie suivante après k bougies consécutives dans le même sens."""
    sens = np.sign(np.diff(b["c"]))
    out = {}
    for k in range(1, 7):
        for s, nom in ((1, "hausses"), (-1, "baisses")):
            idx = [i for i in range(k, len(sens) - 1) if np.all(sens[i - k + 1:i + 1] == s)]
            if len(idx) >= 20:
                suiv = sens[np.array(idx) + 1]
                out[f"{k} {nom}"] = {"n": len(idx), "hausse_suivante": float((suiv > 0).mean())}
    return out


def etat(b):
    """Photographie du rythme actuel (dernière bougie fermée)."""
    atr = I.atr(b["h"], b["l"], b["c"], 14)
    rang = I.percentile_glissant(atr, 500)
    amp = b["h"] - b["l"]
    moy = I.sma(amp, 20)
    sens = np.sign(np.diff(b["c"]))
    serie = 0
    for s in sens[::-1]:
        if serie == 0 or np.sign(serie) == s:
            serie += int(s)
        else:
            break
    dernier = -1
    return {"prix": float(b["c"][dernier]), "atr": float(atr[dernier]), "atr_pct": float(atr[dernier] / b["c"][dernier] * 100),
            "rang_volatilite": float(rang[dernier]) if not np.isnan(rang[dernier]) else None,
            "expansion": float(amp[dernier] / moy[dernier]) if moy[dernier] else None, "serie": serie,
            "seance": seance(int(b["ts"][dernier]) + 3_600_000),
            "regime": ("volatilité extrême" if rang[dernier] >= 0.97 else "volatilité forte" if rang[dernier] >= 0.8
                       else "calme" if rang[dernier] <= 0.2 else "normal") if not np.isnan(rang[dernier]) else "inconnu"}
