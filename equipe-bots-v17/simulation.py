"""Moteur de sortie partagé : BACKTESTEUR, ÉVOLUTION et AUDITEUR (fantômes, ombres) simulent
exactement les mêmes règles que le GARDIEN en réel."""
import numpy as np
import config

try:                                   # numba accélère l'évolution ~50x ; sans lui tout marche, en plus lent
    from numba import njit
except Exception:                      # pragma: no cover
    def njit(*a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]


def _defauts():
    return {"stop_atr": config.STOP_ATR, "secu_r": config.SECURISATION_R, "trailing_atr": config.TRAILING_ATR,
            "objectif_atr": config.OBJECTIF_ATR, "part_frac": 0.0, "part_r": 1.0}


def simuler_sortie(bougies, entree, atr, duree_max_bougies=None, params=None):
    """bougies : liste de (ouverture, haut, bas, clôture) à partir de la bougie d'entrée.
    Renvoie (multiple de R, pnl %, raison, nb de bougies tenues)."""
    p = {**_defauts(), **(params or {})}
    duree = duree_max_bougies or p.get("horizon_bougies") or \
        int(config.DUREE_MAX_H * 60 / config.MINUTES[config.UNITE_BOUGIE])
    o = np.array([b[0] for b in bougies], dtype=float)
    h = np.array([b[1] for b in bougies], dtype=float)
    l = np.array([b[2] for b in bougies], dtype=float)
    c = np.array([b[3] for b in bougies], dtype=float)
    if len(o) == 0:
        return 0.0, -config.FRAIS_ALLER_RETOUR_PCT, "fin des données", 0
    r, pnl, code, n = _sortie(o, h, l, c, 0, entree, atr, p["stop_atr"], p["secu_r"], p["trailing_atr"],
                              p["objectif_atr"], p["part_frac"], p["part_r"], duree,
                              config.GLISSEMENT_PCT / 100, config.FRAIS_ALLER_RETOUR_PCT,
                              config.GLISSEMENT_STOP_PCT / 100)
    return r, pnl, RAISONS[code], n


RAISONS = ["fin des données", "stop (gap)", "stop-loss", "stop sécurisé", "objectif", "durée max"]


@njit(cache=True)
def _sortie(o, h, l, c, debut, entree, atr, stop_atr, secu_r, trailing_atr, objectif_atr, part_frac, part_r,
            duree, g, frais, g_stop=-1.0):
    gs = g if g_stop < 0 else g_stop                # glissement propre aux sorties par stop (stop-limite)
    stop = entree - stop_atr * atr
    risque = entree - stop
    objectif = entree + objectif_atr * atr
    plus_haut = entree
    securise = False
    partiel = False
    gain_partiel = 0.0
    sortie = -1.0
    code = 0
    n = 0
    fin = len(o)
    for k in range(debut, fin):
        n = k - debut + 1
        if k > debut and o[k] <= stop:
            sortie, code = o[k] * (1 - gs), 1
            break
        if l[k] <= stop:
            sortie = stop * (1 - gs)
            code = 3 if securise else 2
            break
        if h[k] >= objectif:
            sortie, code = objectif * (1 - g), 4
            break
        if part_frac > 0 and (not partiel) and h[k] >= entree + part_r * risque:
            partiel = True                        # on encaisse une partie, le reste court avec le stop suiveur
            gain_partiel = ((entree + part_r * risque) * (1 - g) / entree - 1) * 100
        if h[k] > plus_haut:
            plus_haut = h[k]
        if (not securise) and plus_haut >= entree + secu_r * risque:
            stop = entree * (1 + frais / 100 + gs + 0.0005)     # couvre frais + glissement du stop
            securise = True
        if securise:
            t = plus_haut - trailing_atr * atr
            if t > stop:
                stop = t
        if n >= duree:
            sortie, code = c[k] * (1 - g), 5
            break
    if sortie < 0:
        sortie = c[fin - 1] * (1 - g)
    pnl_reste = (sortie / entree - 1) * 100
    pnl = (part_frac * gain_partiel + (1 - part_frac) * pnl_reste if partiel else pnl_reste) - frais
    r = pnl / (risque / entree * 100)
    return r, pnl, code, n


@njit(cache=True)
def simuler_serie(o, h, l, c, atr, signal, stop_atr, secu_r, trailing_atr, objectif_atr, part_frac, part_r,
                  duree, g, frais, g_stop=-1.0):
    """stop_atr : tableau (distance du stop en ATR, bougie par bougie : fixe ou structurelle)."""
    """Parcourt toute une série : à chaque signal, achat à l'ouverture suivante, une position à la fois.
    Renvoie (indices d'entrée, indices de sortie, R)."""
    n = len(o)
    entrees = np.empty(n, dtype=np.int64)
    sorties = np.empty(n, dtype=np.int64)
    rs = np.empty(n, dtype=np.float64)
    m = 0
    i = 0
    while i < n - 2:
        if signal[i] and atr[i] > 0:
            entree = o[i + 1] * (1 + g)
            fin = min(n, i + 2 + duree)
            r, pnl, code, tenu = _sortie(o[:fin], h[:fin], l[:fin], c[:fin], i + 1, entree, atr[i],
                                         stop_atr[i], secu_r, trailing_atr, objectif_atr, part_frac, part_r,
                                         duree, g, frais, g_stop)
            entrees[m] = i + 1
            sorties[m] = i + tenu
            rs[m] = r
            m += 1
            i = i + tenu + 1
        else:
            i += 1
    return entrees[:m], sorties[:m], rs[:m]


def note_sur_10(ecart_r):
    """Note d'un bot = de combien il améliore l'espérance, en R par trade.
    5 = aucun effet (hasard) | 8 = +0,3 R | 10 = +0,5 R ou plus | < 5 = il fait perdre."""
    return max(0.0, min(10.0, 5 + 10 * ecart_r))
