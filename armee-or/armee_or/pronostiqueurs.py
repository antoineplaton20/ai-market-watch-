"""PRONOSTIQUEURS — chacun calcule une PROBABILITÉ que l'or soit plus haut dans `horizon` bougies.

Règles communes (anti-triche) :
- un pronostiqueur ne voit que le passé : à l'instant t, seules les bougies ≤ t sont utilisées ;
- son score brut est transformé en probabilité par calibration GLISSANTE : on regarde, sur les bougies passées
  dont l'issue est déjà connue, à quelle fréquence l'or a monté pour des scores semblables ;
- il est noté en continu (score de Brier) contre le pronostiqueur « naïf » (fréquence habituelle de hausse) ;
  le chef d'orchestre ne l'écoute que s'il fait MIEUX que le naïf.

Idées sources (voir bibliotheque.py) : suivi de tendance et momentum (Moskowitz, Ooi, Pedersen 2012 ;
Hurst, Ooi, Pedersen 2017), retour à la moyenne (Bollinger ; Poterba & Summers 1988), canaux de Donchian
(règles des « Turtles »), chandeliers (Nison 1991), saisonnalité intrajournalière de l'or.
"""
from __future__ import annotations

import numpy as np

from . import chandeliers as C
from . import indicateurs as I

HORIZON = 4                  # en bougies (4 h sur des bougies d'1 h)
FENETRE_CALIB = 3000         # bougies passées servant à la calibration
PAS_CALIB = 250              # recalibration toutes les 250 bougies
MIN_CALIB = 1000
LISSAGE = 20                 # lissage de Laplace vers la fréquence de base


def _cible(c, h):
    y = np.full(len(c), np.nan)
    if len(c) > h:
        y[:-h] = (c[h:] > c[:-h]).astype(float)
    return y


# ---------------------------------------------------------------------------- scores bruts (passé seulement)
def score_tendance(b):
    atr = I.atr(b["h"], b["l"], b["c"], 14)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (I.ema(b["c"], 20) - I.ema(b["c"], 100)) / atr


def score_momentum(b, n=72):
    lc = np.log(b["c"])
    r = np.diff(lc, prepend=np.nan)
    vol = I.ecart_type_glissant(np.nan_to_num(r), n) * np.sqrt(n)
    out = np.full(len(lc), np.nan)
    out[n:] = lc[n:] - lc[:-n]
    with np.errstate(invalid="ignore", divide="ignore"):
        return out / vol


def score_retour_moyenne(b, n=20):
    with np.errstate(invalid="ignore", divide="ignore"):
        return -(b["c"] - I.sma(b["c"], n)) / I.ecart_type_glissant(b["c"], n)


def score_chandeliers(b):
    s = np.zeros(len(b["c"]))
    for sens, masque in C.detecter(b).values():
        s += sens * masque
    return s


def score_canal(b, n=20):
    hi = I.plus_haut_precedent(b["h"], n)
    lo = -I.plus_haut_precedent(-b["l"], n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (b["c"] - lo) / (hi - lo) * 2 - 1


def score_saisonnalite(b, h=HORIZON, memoire=90):
    """Rendement moyen passé à la même heure UTC (issues déjà connues seulement)."""
    heures = (b["ts"] // 3_600_000) % 24
    fut = np.full(len(b["c"]), np.nan)
    if len(b["c"]) > h:
        fut[:-h] = np.log(b["c"][h:] / b["c"][:-h])
    out = np.full(len(b["c"]), np.nan)
    for hr in range(24):
        pos = np.flatnonzero(heures == hr)
        vals = fut[pos]
        # à la position j, on n'utilise que les occurrences précédentes (24 bougies plus tôt au moins > horizon)
        vals_passe = np.concatenate(([np.nan], vals[:-1]))
        ok = ~np.isnan(vals_passe)
        cs = np.cumsum(np.where(ok, vals_passe, 0.0))
        cn = np.cumsum(ok)
        k = memoire
        somme = cs - np.concatenate((np.zeros(k), cs[:-k])) if len(cs) > k else cs
        nb = cn - np.concatenate((np.zeros(k), cn[:-k])) if len(cn) > k else cn
        with np.errstate(invalid="ignore", divide="ignore"):
            out[pos] = np.where(nb >= 20, somme / nb, np.nan)
    return out


def score_volatilite(b):
    """Direction de la dernière cassure quand la volatilité se réveille (compression puis expansion)."""
    atr = I.atr(b["h"], b["l"], b["c"], 14)
    rang = I.percentile_glissant(atr, 200)
    canal = score_canal(b, 20)
    return np.where(rang > 0.6, canal, 0.0)


PRONOSTIQUEURS = {
    "tendance": ("Tendance (EMA 20 contre EMA 100, en ATR)", score_tendance),
    "momentum": ("Momentum sur 72 h rapporté à la volatilité", score_momentum),
    "retour_moyenne": ("Retour à la moyenne (écart à la moyenne 20 en écarts-types)", score_retour_moyenne),
    "chandeliers": ("Somme des motifs de chandeliers de la bougie", score_chandeliers),
    "canal": ("Position dans le canal de Donchian 20", score_canal),
    "saisonnalite": ("Rendement habituel à cette heure de la journée", score_saisonnalite),
    "volatilite": ("Cassure au réveil de la volatilité", score_volatilite),
}


# ---------------------------------------------------------------------------- calibration glissante
def calibrer(score, y, h=HORIZON, fenetre=FENETRE_CALIB, pas=PAS_CALIB, min_calib=MIN_CALIB, bins=10):
    """Score -> probabilité, en n'utilisant que des issues CONNUES au moment de la prévision."""
    n = len(score)
    p = np.full(n, np.nan)
    for debut in range(min_calib + h, n, pas):
        fin_train = debut - h                              # issues connues jusqu'ici seulement
        a = max(0, fin_train - fenetre)
        s_tr, y_tr = score[a:fin_train], y[a:fin_train]
        ok = ~np.isnan(s_tr) & ~np.isnan(y_tr)
        if ok.sum() < min_calib // 2:
            continue
        s_tr, y_tr = s_tr[ok], y_tr[ok]
        base = y_tr.mean()
        bords = np.unique(np.quantile(s_tr, np.linspace(0, 1, bins + 1)[1:-1]))
        idx_tr = np.searchsorted(bords, s_tr, side="right")
        hausses = np.bincount(idx_tr, weights=y_tr, minlength=len(bords) + 1)
        effectifs = np.bincount(idx_tr, minlength=len(bords) + 1)
        table = (hausses + LISSAGE * base) / (effectifs + LISSAGE)
        s_ap = score[debut:debut + pas]
        idx = np.searchsorted(bords, np.nan_to_num(s_ap), side="right")
        p[debut:debut + pas] = np.where(np.isnan(s_ap), np.nan, table[idx])
    return p


def base_glissante(y, h=HORIZON, n=500):
    """Pronostiqueur naïf : fréquence de hausse sur les n dernières issues connues."""
    yy = np.nan_to_num(y)
    ok = (~np.isnan(y)).astype(float)
    cs, cn = np.cumsum(np.r_[0, yy]), np.cumsum(np.r_[0, ok])
    out = np.full(len(y), np.nan)
    for t in range(h + 50, len(y)):
        fin = t - h + 1
        a = max(0, fin - n)
        if cn[fin] - cn[a] >= 50:
            out[t] = (cs[fin] - cs[a]) / (cn[fin] - cn[a])
    return out


def tout_calculer(b, h=HORIZON):
    """-> (probabilités {nom: série}, base, cible). Utilisé pour l'historique ET pour le direct (dernière valeur)."""
    y = _cible(b["c"], h)
    probas = {nom: calibrer(fn(b), y, h) for nom, (_, fn) in PRONOSTIQUEURS.items()}
    return probas, base_glissante(y, h), y


# ---------------------------------------------------------------------------- notation et consensus
def brier(p, y):
    ok = ~np.isnan(p) & ~np.isnan(y)
    return float(np.mean((p[ok] - y[ok]) ** 2)) if ok.any() else np.nan, int(ok.sum())


def competence(p, base, y, a=0, b=None):
    """1 - Brier / Brier du naïf, sur [a, b) : > 0 = meilleur que le naïf ; ≤ 0 = inutile."""
    sl = slice(a, b)
    ok = ~np.isnan(p[sl]) & ~np.isnan(base[sl]) & ~np.isnan(y[sl])
    if ok.sum() < 200:
        return 0.0, int(ok.sum())
    bs = np.mean((p[sl][ok] - y[sl][ok]) ** 2)
    bb = np.mean((base[sl][ok] - y[sl][ok]) ** 2)
    return float(1 - bs / bb) if bb > 0 else 0.0, int(ok.sum())


def consensus(probas, base, y, h=HORIZON, fenetre=2000, pas=PAS_CALIB):
    """Probabilité du chef d'orchestre : écart de chaque pronostiqueur au naïf, pondéré par sa compétence
    RÉCENTE (issues connues uniquement). Un pronostiqueur sans compétence a un poids nul."""
    n = len(base)
    p = np.array(base, dtype=float)
    poids_hist = []
    for debut in range(h + 1, n, pas):
        fin_eval = debut - h
        a = max(0, fin_eval - fenetre)
        poids = {k: max(0.0, competence(v, base, y, a, fin_eval)[0]) for k, v in probas.items()}
        poids_hist.append((debut, poids))
        total = sum(poids.values())
        if total <= 0:
            continue
        sl = slice(debut, min(n, debut + pas))
        ecart = np.zeros(sl.stop - sl.start)
        for k, w in poids.items():
            if w > 0:
                ecart += w * np.nan_to_num(probas[k][sl] - base[sl])
        p[sl] = base[sl] + ecart / total
    return p, poids_hist
