"""RÈGLE DE DÉCISION DU CHEF D'ORCHESTRE — n'agir que si l'avantage attendu dépasse nettement les coûts.

avantage attendu (en % du prix) ≈ (2p − 1) × mouvement moyen habituel sur l'horizon
coûts (en % du prix)            = frais + glissement aux deux bouts + financement pendant l'horizon
On n'agit que si avantage > MARGE × coûts ; sinon on reste à l'écart. On ne prend jamais de nouvelle position
quand la volatilité est extrême (rang ≥ 97 %) : c'est là que les stops glissent et que les leviers liquident.
"""
from __future__ import annotations

import numpy as np

from . import indicateurs as I
from . import levier as L

UNITES = {  # unité : (horizon en bougies, heures par bougie)
    "1h": (4, 1), "4h": (6, 4), "1d": (5, 24),
}
MARGE = 1.5


def mouvement_habituel(c, h, n=500):
    """Moyenne passée de |c[t]/c[t-h] − 1| (connue à l'instant t)."""
    m = np.full(len(c), np.nan)
    if len(c) > h:
        m[h:] = np.abs(c[h:] / c[:-h] - 1)
    ok = ~np.isnan(m)
    cs, cn = np.cumsum(np.where(ok, m, 0)), np.cumsum(ok)
    out = np.full(len(c), np.nan)
    if len(c) > n:
        s = cs[n:] - cs[:-n]
        k = cn[n:] - cn[:-n]
        with np.errstate(invalid="ignore", divide="ignore"):
            out[n:] = np.where(k > 50, s / k, np.nan)
    return out


def couts(h, heures_barre):
    return 2 * (L.FRAIS + L.GLISSEMENT) + L.FINANCEMENT_8H * h * heures_barre / 8


def decisions(p, b, unite, marge=MARGE):
    """p : probabilité de hausse (consensus) -> +1 achat, -1 vente, 0 rien, pour chaque bougie."""
    h, hb = UNITES[unite]
    mv = mouvement_habituel(b["c"], h)
    avantage = np.abs(2 * np.nan_to_num(p, nan=0.5) - 1) * np.nan_to_num(mv)
    rang = I.percentile_glissant(I.atr(b["h"], b["l"], b["c"], 14), 500)
    calme_ok = ~(np.nan_to_num(rang) >= 0.97)
    agir = (avantage > marge * couts(h, hb)) & calme_ok & ~np.isnan(p)
    return np.where(agir, np.sign(np.nan_to_num(p) - 0.5), 0).astype(int)
