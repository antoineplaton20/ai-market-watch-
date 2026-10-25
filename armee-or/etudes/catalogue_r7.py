"""R7 (25/10/2026) : chaque famille de stratégies trouvée dans les vidéos de trading les plus vues (inventaire YouTube,
etudes/LISEZMOI.md) et chaque fiche restée sans test (H01 à H22), écrite en règles FIXES avant le moindre test.

YouTube refuse les sous-titres aux serveurs : les réglages sont ceux de la version écrite la plus répandue de chaque
méthode (sites et livres des auteurs, définitions classiques) ; quand une vidéo donne un réglage précis (86 % de
gagnants, 1:1,5, 9 et 15 EMA…), c'est lui. Aucun réglage n'est ajusté après coup : une seule version par méthode.

Chaque règle reçoit d = {"ts","o","h","l","c","v","vb"} (bougies closes) et rend un dict pour moteur_r7.backtest :
sens (+1 achat / −1 vente, décidé à la clôture), stop/cible (par sens : *_l, *_c), entree (ordre stop), sortie, duree.
"""
from __future__ import annotations

import numpy as np

import moteur_r7 as M

NAN = np.nan


# ============================================================================ outils
def _nan(n):
    return np.full(n, NAN)


def fen_min(x, n):
    """Plus bas des n dernières bougies, bougie du jour COMPRISE."""
    out = _nan(len(x))
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1:i + 1].min()
    return out


def fen_max(x, n):
    out = _nan(len(x))
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1:i + 1].max()
    return out


def croise_haut(a, b):
    a, b = np.asarray(a, float), np.broadcast_to(np.asarray(b, float), np.shape(a))
    out = np.zeros(len(a), bool)
    out[1:] = (a[1:] > b[1:]) & (a[:-1] <= b[:-1])
    return out & np.isfinite(a) & np.isfinite(b)


def croise_bas(a, b):
    a, b = np.asarray(a, float), np.broadcast_to(np.asarray(b, float), np.shape(a))
    out = np.zeros(len(a), bool)
    out[1:] = (a[1:] < b[1:]) & (a[:-1] >= b[:-1])
    return out & np.isfinite(a) & np.isfinite(b)


def avec_rr(d, achat, vente, stop_l, stop_c, rr):
    """Signal + stop de chaque côté ; objectif à rr fois le risque, mesuré depuis la clôture de décision."""
    c = d["c"]
    s = np.where(achat, 1, np.where(vente, -1, 0))
    cible_l = c + rr * (c - stop_l)
    cible_c = c - rr * (stop_c - c)
    return {"sens": s, "stop_l": stop_l, "stop_c": stop_c, "cible_l": cible_l, "cible_c": cible_c}


def swing(d, n=10, marge=0.0):
    a = M.atr(d["h"], d["l"], d["c"], 14)
    return fen_min(d["l"], n) - marge * a, fen_max(d["h"], n) + marge * a


def decalage_ny(ts_ms):
    """Heure de New York = UTC − 4 h en heure d'été (2e dimanche de mars → 1er dimanche de novembre), sinon − 5 h."""
    ts = np.asarray(ts_ms, dtype=np.int64)
    annees = 1970 + (ts // 86_400_000 // 365.2425).astype(int)
    out = np.full(len(ts), -5)
    for a in np.unique(annees):
        import datetime as dt
        mars = dt.datetime(int(a), 3, 8, tzinfo=dt.timezone.utc)
        debut = mars + dt.timedelta(days=(6 - mars.weekday()) % 7, hours=7)
        nov = dt.datetime(int(a), 11, 1, tzinfo=dt.timezone.utc)
        fin = nov + dt.timedelta(days=(6 - nov.weekday()) % 7, hours=6)
        sel = annees == a
        ete = (ts >= debut.timestamp() * 1000) & (ts < fin.timestamp() * 1000)
        out[sel & ete] = -4
    return out


def minutes_ny(ts_ms):
    """Minute du jour à New York (0 à 1439) et jour de New York."""
    t = np.asarray(ts_ms, dtype=np.int64) + decalage_ny(ts_ms).astype(np.int64) * 3_600_000
    return (t // 60_000) % 1440, t // 86_400_000


def minutes_utc(ts_ms):
    t = np.asarray(ts_ms, dtype=np.int64)
    return (t // 60_000) % 1440, t // 86_400_000


def niveaux_veille(d):
    """Plus haut, plus bas, clôture de la VEILLE (jour UTC), connus dès minuit."""
    _, j = minutes_utc(d["ts"])
    ph, pb, pc = _nan(len(j)), _nan(len(j)), _nan(len(j))
    debut = np.flatnonzero(np.r_[True, j[1:] != j[:-1]])
    fin = np.r_[debut[1:], len(j)]
    for k in range(1, len(debut)):
        a, b = debut[k - 1], fin[k - 1]
        ph[debut[k]:fin[k]] = d["h"][a:b].max()
        pb[debut[k]:fin[k]] = d["l"][a:b].min()
        pc[debut[k]:fin[k]] = d["c"][b - 1]
    return ph, pb, pc


def vwap_jour(d):
    _, j = minutes_utc(d["ts"])
    tp = (d["h"] + d["l"] + d["c"]) / 3
    v = np.where(d["v"] > 0, d["v"], 1e-12)
    out = np.empty(len(tp))
    debut = np.flatnonzero(np.r_[True, j[1:] != j[:-1]])
    fin = np.r_[debut[1:], len(j)]
    for a, b in zip(debut, fin):
        out[a:b] = np.cumsum(tp[a:b] * v[a:b]) / np.cumsum(v[a:b])
    return out


def psar(h, l, pas=0.02, maxi=0.2):
    n = len(h)
    sar, sens = np.empty(n), np.empty(n)
    haussier, af, ep, sar[0], sens[0] = True, pas, h[0], l[0], 1
    for i in range(1, n):
        s = sar[i - 1] + af * (ep - sar[i - 1])
        if haussier:
            s = min(s, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < s:
                haussier, s, ep, af = False, ep, l[i], pas
            elif h[i] > ep:
                ep, af = h[i], min(af + pas, maxi)
        else:
            s = max(s, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > s:
                haussier, s, ep, af = True, ep, h[i], pas
            elif l[i] < ep:
                ep, af = l[i], min(af + pas, maxi)
        sar[i], sens[i] = s, 1 if haussier else -1
    return sar, sens


def pivots_connus(d, g=5, dr=5):
    """Tableaux des derniers sommets / creux CONFIRMÉS à chaque bougie (prix et indice), plus les listes."""
    sommets, creux = M.pivots(d["h"], d["l"], g, dr)
    return sommets, creux


# ============================================================================ indicateurs (vidéos)
def v01_macd_200ema(d):
    """TradingLab, « BEST MACD Trading Strategy [86% Win Rate] » : au-dessus de l'EMA 200, croisement haussier du MACD
    SOUS zéro → achat ; stop au dernier creux (10 bougies) ; objectif 1,5 fois le risque. Vente : symétrique."""
    c = d["c"]
    e200 = M.ema(c, 200)
    m, s = M.macd(c)
    achat = (c > e200) & croise_haut(m, s) & (m < 0)
    vente = (c < e200) & croise_bas(m, s) & (m > 0)
    sl, sc = swing(d, 10)
    return avec_rr(d, achat, vente, sl, sc, 1.5)


def v02_ema_9_15(d):
    """The Trade Room, « 9 and 15 EMA strategy » (scalping) : croisement EMA 9 / EMA 15 et clôture du bon côté des deux ;
    stop au dernier creux (5 bougies), objectif 2 fois le risque."""
    c = d["c"]
    a, b = M.ema(c, 9), M.ema(c, 15)
    achat = croise_haut(a, b) & (c > np.fmax(a, b))
    vente = croise_bas(a, b) & (c < np.fmin(a, b))
    sl, sc = swing(d, 5)
    return avec_rr(d, achat, vente, sl, sc, 2.0)


def v03_ema5(d):
    """Power of Stocks (S. Pani), « 5 EMA » : bougie d'alerte entièrement au-dessus de l'EMA 5 → vente si la bougie
    suivante casse son plus bas, stop à son plus haut, objectif 3 fois le risque ; achat symétrique (alerte entièrement
    sous l'EMA 5, cassure de son plus haut)."""
    c, h, l = d["c"], d["h"], d["l"]
    e = M.ema(c, 5)
    alerte_v, alerte_a = l > e, h < e
    s = np.where(alerte_a, 1, np.where(alerte_v, -1, 0))
    return {"sens": s, "entree_l": h, "entree_c": l, "stop_l": l, "stop_c": h,
            "cible_l": h + 3 * (h - l), "cible_c": l - 3 * (h - l), "validite": 1}


def v04_ema_9_21(d):
    """Croisement EMA 9 / EMA 21, toujours en position (retournement à chaque croisement)."""
    c = d["c"]
    a, b = M.ema(c, 9), M.ema(c, 21)
    return {"sens": np.where(croise_haut(a, b), 1, np.where(croise_bas(a, b), -1, 0))}


def v05_croix_or_50_200(d):
    """« Golden cross » : EMA 50 au-dessus de l'EMA 200 → achat ; « death cross » → vente. Toujours en position."""
    c = d["c"]
    a, b = M.ema(c, 50), M.ema(c, 200)
    return {"sens": np.where(croise_haut(a, b), 1, np.where(croise_bas(a, b), -1, 0))}


def v06_rebond_ema50(d):
    """Rayner Teo / Wysetrade, rebond sur la moyenne : tendance (clôture > EMA 200 et EMA 50 > EMA 200), la bougie touche
    l'EMA 50 et clôture au-dessus → achat ; stop EMA 50 − 1 ATR ; objectif 2 fois le risque. Vente symétrique."""
    c, h, l = d["c"], d["h"], d["l"]
    e50, e200 = M.ema(c, 50), M.ema(c, 200)
    a = M.atr(h, l, c, 14)
    achat = (c > e200) & (e50 > e200) & (l <= e50) & (c > e50)
    vente = (c < e200) & (e50 < e200) & (h >= e50) & (c < e50)
    return avec_rr(d, achat, vente, e50 - a, e50 + a, 2.0)


def v07_rsi_30_70(d):
    """RSI 14 : remonte au-dessus de 30 → achat, repasse sous 70 → vente ; stop 1,5 ATR ; sortie quand le RSI franchit 50."""
    c, h, l = d["c"], d["h"], d["l"]
    r = M.rsi(c, 14)
    a = M.atr(h, l, c, 14)
    s = np.where(croise_haut(r, 30), 1, np.where(croise_bas(r, 70), -1, 0))
    sortie = np.where(croise_haut(r, 50), 1, np.where(croise_bas(r, 50), -1, 0))
    return {"sens": s, "stop_l": c - 1.5 * a, "stop_c": c + 1.5 * a, "sortie": sortie}


def v08_divergence_rsi(d):
    """Divergence RSI : nouveau creux de prix (pivot 5/5) plus bas que le précédent (moins de 60 bougies avant), RSI plus
    haut, RSI < 40 → achat à la confirmation du pivot ; stop sous le creux − 0,2 ATR ; objectif 2 fois le risque."""
    c, h, l = d["c"], d["h"], d["l"]
    r = M.rsi(c, 14)
    a = M.atr(h, l, c, 14)
    n = len(c)
    s, sl, sc = np.zeros(n), _nan(n), _nan(n)
    sommets, creux = M.pivots(h, l, 5, 5)
    for liste, signe in ((creux, 1), (sommets, -1)):
        for (k1, i1, p1), (k2, i2, p2) in zip(liste, liste[1:]):
            if i2 - i1 > 60 or k2 >= n or not np.isfinite(r[i2]) or not np.isfinite(a[k2]):
                continue
            if signe > 0 and p2 < p1 and r[i2] > r[i1] and r[i2] < 40:
                s[k2], sl[k2] = 1, p2 - 0.2 * a[k2]
            if signe < 0 and p2 > p1 and r[i2] < r[i1] and r[i2] > 60:
                s[k2], sc[k2] = -1, p2 + 0.2 * a[k2]
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": c + 2 * (c - sl), "cible_c": c - 2 * (sc - c)}


def v09_bollinger_rsi(d):
    """TradingLab, « Bollinger Band + RSI » : la veille clôture sous la bande basse (20, 2) avec RSI < 30, aujourd'hui
    clôture revenue au-dessus → achat ; stop sous les 2 derniers plus bas − 0,2 ATR ; objectif : la moyenne 20."""
    c, h, l = d["c"], d["h"], d["l"]
    m, haut, bas = M.bollinger(c, 20, 2.0)
    r = M.rsi(c, 14)
    a = M.atr(h, l, c, 14)
    achat = np.r_[False, (c[:-1] < bas[:-1]) & (r[:-1] < 30)] & (c > bas)
    vente = np.r_[False, (c[:-1] > haut[:-1]) & (r[:-1] > 70)] & (c < haut)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "stop_l": fen_min(l, 2) - 0.2 * a,
            "stop_c": fen_max(h, 2) + 0.2 * a, "cible_l": m, "cible_c": m}


def v10_compression_bollinger(d):
    """Compression (« squeeze ») : largeur des bandes au plus bas de 120 bougies dans les 5 dernières, clôture hors
    bande → entrée dans ce sens ; stop à la bande opposée ; sortie au retour sur la moyenne 20."""
    c = d["c"]
    m, haut, bas = M.bollinger(c, 20, 2.0)
    larg = (haut - bas) / m
    mini = fen_min(np.nan_to_num(larg, nan=np.inf), 120)
    serre = fen_min((larg <= mini * 1.0001).astype(float) * -1, 5) < 0
    achat, vente = serre & (c > haut), serre & (c < bas)
    sortie = np.where(croise_bas(c, m), 1, np.where(croise_haut(c, m), -1, 0))
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "stop_l": bas, "stop_c": haut, "sortie": sortie}


def v11_stochastique_tendance(d):
    """Scalping 5 minutes (Data Trader, The Moving Average) : EMA 50 > EMA 200 et stochastique (14, 3, 3) qui croise à la
    hausse sous 20 → achat ; stop au dernier creux (10 bougies) ; objectif 1,5 fois le risque. Vente symétrique."""
    c, h, l = d["c"], d["h"], d["l"]
    e50, e200 = M.ema(c, 50), M.ema(c, 200)
    k, dd = M.stochastique(h, l, c, 14, 3, 3)
    achat = (e50 > e200) & croise_haut(k, dd) & (k < 20)
    vente = (e50 < e200) & croise_bas(k, dd) & (k > 80)
    sl, sc = swing(d, 10)
    return avec_rr(d, achat, vente, sl, sc, 1.5)


def v12_supertrend(d):
    """SuperTrend (10, 3) : toujours en position, retournement à chaque changement de couleur."""
    s, _, _ = M.supertrend(d["h"], d["l"], d["c"], 10, 3.0)
    chg = np.r_[0, np.where(s[1:] != s[:-1], s[1:], 0)]
    return {"sens": chg}


def v13_ichimoku(d):
    """Ichimoku (9, 26, 52) : prix au-dessus du nuage et Tenkan croise Kijun à la hausse → achat ; sortie sous la Kijun.
    Vente symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    tenkan = (fen_max(h, 9) + fen_min(l, 9)) / 2
    kijun = (fen_max(h, 26) + fen_min(l, 26)) / 2
    a = np.r_[_nan(26), ((tenkan + kijun) / 2)[:-26]]
    b = np.r_[_nan(26), ((fen_max(h, 52) + fen_min(l, 52)) / 2)[:-26]]
    achat = (c > np.fmax(a, b)) & croise_haut(tenkan, kijun)
    vente = (c < np.fmin(a, b)) & croise_bas(tenkan, kijun)
    sortie = np.where(c < kijun, 1, np.where(c > kijun, -1, 0))
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "sortie": sortie}


def v14_heikin_ashi_ema(d):
    """Trader DNA, « EMA-Heiken Ashi » : bougie Heikin Ashi verte sans mèche basse et clôture > EMA 50 → achat ; sortie
    à la première bougie Heikin Ashi rouge. Vente symétrique."""
    ho, hh, hl, hc = M.heikin_ashi(d["o"], d["h"], d["l"], d["c"])
    e50 = M.ema(d["c"], 50)
    verte, rouge = hc > ho, hc < ho
    sans_bas = np.isclose(hl, np.minimum(ho, hc), rtol=0, atol=1e-12) | (hl >= np.minimum(ho, hc))
    sans_haut = np.isclose(hh, np.maximum(ho, hc), rtol=0, atol=1e-12) | (hh <= np.maximum(ho, hc))
    achat = verte & sans_bas & (d["c"] > e50) & np.r_[True, ~(verte[:-1] & sans_bas[:-1])]
    vente = rouge & sans_haut & (d["c"] < e50) & np.r_[True, ~(rouge[:-1] & sans_haut[:-1])]
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "sortie": np.where(rouge, 1, np.where(verte, -1, 0))}


def v15_sar_ema200(d):
    """SAR parabolique (0,02 ; 0,2) filtré par l'EMA 200 : passage du SAR sous le prix au-dessus de l'EMA 200 → achat ;
    sortie au retournement du SAR. Vente symétrique."""
    _, sens = psar(d["h"], d["l"])
    e200 = M.ema(d["c"], 200)
    chg = np.r_[0, np.where(sens[1:] != sens[:-1], sens[1:], 0)]
    achat, vente = (chg > 0) & (d["c"] > e200), (chg < 0) & (d["c"] < e200)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "sortie": np.where(chg < 0, 1, np.where(chg > 0, -1, 0))}


def v16_adx_di(d):
    """ADX (14) > 25 et DI+ croise DI− à la hausse → achat ; sortie au croisement inverse. Vente symétrique."""
    x, p, m = M.adx(d["h"], d["l"], d["c"], 14)
    achat, vente = (x > 25) & croise_haut(p, m), (x > 25) & croise_bas(p, m)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)),
            "sortie": np.where(croise_bas(p, m), 1, np.where(croise_haut(p, m), -1, 0))}


def v17_vwap(d):
    """VWAP du jour : clôture qui repasse au-dessus du VWAP avec EMA 20 > EMA 50 → achat ; sortie sous le VWAP. Vente
    symétrique. (Intraday seulement.)"""
    c = d["c"]
    w = vwap_jour(d)
    e20, e50 = M.ema(c, 20), M.ema(c, 50)
    achat, vente = croise_haut(c, w) & (e20 > e50), croise_bas(c, w) & (e20 < e50)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)),
            "sortie": np.where(croise_bas(c, w), 1, np.where(croise_haut(c, w), -1, 0))}


def v18_keltner(d):
    """Canal de Keltner (EMA 20 ± 2 ATR) : clôture au-dessus → achat ; sortie sous l'EMA 20. Vente symétrique."""
    c = d["c"]
    e = M.ema(c, 20)
    a = M.atr(d["h"], d["l"], c, 20)
    achat, vente = croise_haut(c, e + 2 * a), croise_bas(c, e - 2 * a)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)),
            "sortie": np.where(c < e, 1, np.where(c > e, -1, 0)), "stop_l": e - 2 * a, "stop_c": e + 2 * a}


def v19_cci(d):
    """CCI (20) qui franchit +100 → achat, −100 → vente ; sortie au retour à 0."""
    h, l, c = d["h"], d["l"], d["c"]
    tp = (h + l + c) / 3
    m = M.sma(tp, 20)
    dev = _nan(len(tp))
    for i in range(19, len(tp)):
        dev[i] = np.abs(tp[i - 19:i + 1] - m[i]).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        cci = (tp - m) / (0.015 * dev)
    return {"sens": np.where(croise_haut(cci, 100), 1, np.where(croise_bas(cci, -100), -1, 0)),
            "sortie": np.where(croise_bas(cci, 0), 1, np.where(croise_haut(cci, 0), -1, 0))}


def v20_williams(d):
    """Williams %R (14) qui remonte au-dessus de −80 avec clôture > EMA 200 → achat ; sortie au-dessus de −20.
    Vente symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    hh, ll = fen_max(h, 14), fen_min(l, 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        wr = -100 * (hh - c) / (hh - ll)
    e200 = M.ema(c, 200)
    achat, vente = croise_haut(wr, -80) & (c > e200), croise_bas(wr, -20) & (c < e200)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)),
            "sortie": np.where(wr > -20, 1, np.where(wr < -80, -1, 0))}


def v21_mfi(d):
    """Money Flow Index (14) : remonte au-dessus de 20 → achat ; sortie au-dessus de 80. Vente symétrique."""
    h, l, c, v = d["h"], d["l"], d["c"], d["v"]
    tp = (h + l + c) / 3
    flux = tp * v
    hausse = np.r_[False, tp[1:] > tp[:-1]]
    pos, neg = np.where(hausse, flux, 0.0), np.where(~hausse, flux, 0.0)
    sp, sn = M.sma(pos, 14) * 14, M.sma(neg, 14) * 14
    with np.errstate(divide="ignore", invalid="ignore"):
        mfi = 100 - 100 / (1 + sp / sn)
    return {"sens": np.where(croise_haut(mfi, 20), 1, np.where(croise_bas(mfi, 80), -1, 0)),
            "sortie": np.where(mfi > 80, 1, np.where(mfi < 20, -1, 0))}


def v22_obv(d):
    """OBV au plus haut de 20 bougies → ordre d'achat au-dessus du plus haut de 20 bougies ; stop au plus bas de 10.
    Vente symétrique."""
    c, v = d["c"], d["v"]
    obv = np.cumsum(np.sign(np.diff(c, prepend=c[0])) * v)
    haut_obv, bas_obv = obv >= fen_max(obv, 20), obv <= fen_min(obv, 20)
    hh, ll = fen_max(d["h"], 20), fen_min(d["l"], 20)
    return {"sens": np.where(haut_obv, 1, np.where(bas_obv, -1, 0)), "entree_l": hh, "entree_c": ll,
            "stop_l": fen_min(d["l"], 10), "stop_c": fen_max(d["h"], 10), "validite": 1,
            "sortie": np.where(c < M.plus_bas(d["l"], 10), 1, np.where(c > M.plus_haut(d["h"], 10), -1, 0))}


def v23_points_pivots(d):
    """Points pivots de la veille (P, S1, S2, R1, R2) : la bougie touche S1 et clôture au-dessus → achat, objectif P,
    stop S2 ; vente symétrique sur R1. (Intraday.)"""
    ph, pb, pc = niveaux_veille(d)
    p = (ph + pb + pc) / 3
    s1, r1, s2, r2 = 2 * p - ph, 2 * p - pb, p - (ph - pb), p + (ph - pb)
    achat = (d["l"] <= s1) & (d["c"] > s1)
    vente = (d["h"] >= r1) & (d["c"] < r1)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "stop_l": s2, "stop_c": r2, "cible_l": p, "cible_c": p}


# ============================================================================ Fibonacci, Elliott, harmoniques
def v24_fibonacci_poche(d):
    """Retracement de Fibonacci, « poche dorée » (61,8 à 65 %) : tendance (EMA 50 > EMA 200), dernier mouvement creux →
    sommet confirmés (pivots 5/5) ; la bougie touche 61,8 % et clôture au-dessus de 65 % → achat ; stop sous 78,6 % ;
    objectif le sommet. Vente symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    e50, e200 = M.ema(c, 50), M.ema(c, 200)
    n = len(c)
    sommets, creux = M.pivots(h, l, 5, 5)
    evts = sorted([(k, i, p, 1) for k, i, p in sommets] + [(k, i, p, -1) for k, i, p in creux])
    s, sl, sc, cl, cc = np.zeros(n), _nan(n), _nan(n), _nan(n), _nan(n)
    dernier = {1: None, -1: None}
    for idx, (k, i, p, t) in enumerate(evts):
        dernier[t] = (i, p)
        fin = evts[idx + 1][0] if idx + 1 < len(evts) else n
        if dernier[1] is None or dernier[-1] is None:
            continue
        (i_h, ph), (i_b, pb) = dernier[1], dernier[-1]
        amp = ph - pb
        if amp <= 0:
            continue
        for j in range(k, min(fin, n)):
            if t == 1 and i_b < i_h and e50[j] > e200[j]:                 # impulsion haussière : retracement
                n618, n65, n786 = ph - 0.618 * amp, ph - 0.65 * amp, ph - 0.786 * amp
                if l[j] <= n618 and c[j] > n65 and l[j] > n786:
                    s[j], sl[j], cl[j] = 1, n786, ph
                    break
            if t == -1 and i_h < i_b and e50[j] < e200[j]:
                n618, n65, n786 = pb + 0.618 * amp, pb + 0.65 * amp, pb + 0.786 * amp
                if h[j] >= n618 and c[j] < n65 and h[j] < n786:
                    s[j], sc[j], cc[j] = -1, n786, pb
                    break
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc}


def _zigzag(d, g=5, dr=5):
    """Pivots alternés (sommet, creux, sommet…) confirmés : (k_connu, i, prix, +1 sommet / −1 creux)."""
    sommets, creux = M.pivots(d["h"], d["l"], g, dr)
    evts = sorted([(i, k, p, 1) for k, i, p in sommets] + [(i, k, p, -1) for k, i, p in creux])
    zz = []
    for i, k, p, t in evts:
        if zz and zz[-1][3] == t:
            if (t == 1 and p > zz[-1][2]) or (t == -1 and p < zz[-1][2]):
                zz[-1] = (k, i, p, t)
            continue
        zz.append((k, i, p, t))
    return zz


def v25_elliott_vague3(d):
    """Elliott, entrée en vague 3 : vague 1 (creux A → sommet B), vague 2 qui retrace 50 à 78,6 % sans casser A
    (creux C) → achat à la confirmation de C ; stop sous A ; objectif C + 1,618 × (B − A). Vente symétrique."""
    c = d["c"]
    n = len(c)
    zz = _zigzag(d)
    s, sl, sc, cl, cc = np.zeros(n), _nan(n), _nan(n), _nan(n), _nan(n)
    for (_, _, pa, ta), (_, _, pb, _), (kc, _, pc, _) in zip(zz, zz[1:], zz[2:]):
        if kc >= n:
            continue
        amp = abs(pb - pa)
        if amp == 0:
            continue
        retr = abs(pb - pc) / amp
        if ta == -1 and pc > pa and 0.5 <= retr <= 0.786:
            s[kc], sl[kc], cl[kc] = 1, pa, pc + 1.618 * amp
        if ta == 1 and pc < pa and 0.5 <= retr <= 0.786:
            s[kc], sc[kc], cc[kc] = -1, pa, pc - 1.618 * amp
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc}


def v26_gartley(d):
    """Harmonique de Gartley (X, A, B, C, D alternés) : AB = 0,55-0,68 XA, BC = 0,382-0,886 AB, CD = 1,13-1,618 BC,
    AD = 0,74-0,83 XA → retournement à la confirmation de D ; stop au-delà de X ; objectif D + 0,618 × (A − D)."""
    c = d["c"]
    n = len(c)
    zz = _zigzag(d)
    s, sl, sc, cl, cc = np.zeros(n), _nan(n), _nan(n), _nan(n), _nan(n)
    for x, a, b, cpt, dd in zip(zz, zz[1:], zz[2:], zz[3:], zz[4:]):
        px, pa, pb, pc, pd = x[2], a[2], b[2], cpt[2], dd[2]
        xa, ab, bc, cd = abs(pa - px), abs(pb - pa), abs(pc - pb), abs(pd - pc)
        if min(xa, ab, bc) == 0 or dd[0] >= n:
            continue
        if 0.55 <= ab / xa <= 0.68 and 0.382 <= bc / ab <= 0.886 and 1.13 <= cd / bc <= 1.618 \
                and 0.74 <= abs(pa - pd) / xa <= 0.83:
            k = dd[0]
            if x[3] == -1:                                          # X creux : D creux, achat
                s[k], sl[k], cl[k] = 1, px, pd + 0.618 * (pa - pd)
            else:
                s[k], sc[k], cc[k] = -1, px, pd - 0.618 * (pd - pa)
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc}


# ============================================================================ figures chartistes, supports, lignes
def v27_double_creux_sommet(d):
    """Double creux : deux creux (pivots 5/5) à moins de 0,5 ATR l'un de l'autre, 10 bougies d'écart au moins ; clôture
    au-dessus du sommet intermédiaire (ligne de cou) → achat ; stop sous le plus bas ; objectif la hauteur reportée.
    Double sommet : symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    n = len(c)
    zz = _zigzag(d)
    s, sl, sc, cl, cc = np.zeros(n), _nan(n), _nan(n), _nan(n), _nan(n)
    for p1, cou, p2 in zip(zz, zz[1:], zz[2:]):
        k = p2[0]
        if k >= n or not np.isfinite(a[k]) or p2[1] - p1[1] < 10 or abs(p2[2] - p1[2]) > 0.5 * a[k]:
            continue
        haut = abs(cou[2] - min(p1[2], p2[2]) if p1[3] == -1 else max(p1[2], p2[2]) - cou[2])
        for j in range(k, min(n, k + 30)):
            if p1[3] == -1 and c[j] > cou[2]:
                s[j], sl[j], cl[j] = 1, min(p1[2], p2[2]), cou[2] + haut
                break
            if p1[3] == 1 and c[j] < cou[2]:
                s[j], sc[j], cc[j] = -1, max(p1[2], p2[2]), cou[2] - haut
                break
            if (p1[3] == -1 and l[j] < min(p1[2], p2[2])) or (p1[3] == 1 and h[j] > max(p1[2], p2[2])):
                break
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc}


def v28_tete_epaules(d):
    """Tête et épaules : trois sommets (épaule, tête plus haute, épaule à moins de 1 ATR de la première), ligne de cou =
    moyenne des deux creux ; clôture sous la ligne de cou → vente ; stop au-dessus de l'épaule droite ; objectif la
    hauteur reportée. Tête et épaules inversée : achat symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    n = len(c)
    zz = _zigzag(d)
    s, sl, sc, cl, cc = np.zeros(n), _nan(n), _nan(n), _nan(n), _nan(n)
    for e1, c1, t, c2, e2 in zip(zz, zz[1:], zz[2:], zz[3:], zz[4:]):
        k = e2[0]
        if k >= n or not np.isfinite(a[k]) or abs(e1[2] - e2[2]) > a[k]:
            continue
        cou = (c1[2] + c2[2]) / 2
        if e1[3] == 1 and t[2] > max(e1[2], e2[2]):
            for j in range(k, min(n, k + 30)):
                if c[j] < cou:
                    s[j], sc[j], cc[j] = -1, e2[2], cou - (t[2] - cou)
                    break
                if h[j] > e2[2]:
                    break
        if e1[3] == -1 and t[2] < min(e1[2], e2[2]):
            for j in range(k, min(n, k + 30)):
                if c[j] > cou:
                    s[j], sl[j], cl[j] = 1, e2[2], cou + (cou - t[2])
                    break
                if l[j] < e2[2]:
                    break
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc}


def v29_triangle(d):
    """Triangle : deux derniers sommets descendants et deux derniers creux montants (en 60 bougies) ; clôture au-dessus
    de la droite des sommets → achat (stop au dernier creux), sous la droite des creux → vente ; objectif la hauteur
    du triangle à son début."""
    h, l, c = d["h"], d["l"], d["c"]
    n = len(c)
    sommets, creux = M.pivots(h, l, 5, 5)
    s, sl, sc, cl, cc = np.zeros(n), _nan(n), _nan(n), _nan(n), _nan(n)
    ks, kc = 0, 0
    sh, sb = [], []
    evts = sorted([(k, i, p, 1) for k, i, p in sommets] + [(k, i, p, -1) for k, i, p in creux])
    e = 0
    for j in range(n):
        while e < len(evts) and evts[e][0] <= j:
            (sh if evts[e][3] == 1 else sb).append(evts[e][1:3])
            e += 1
        if len(sh) < 2 or len(sb) < 2:
            continue
        (i1, p1), (i2, p2) = sh[-2], sh[-1]
        (j1, q1), (j2, q2) = sb[-2], sb[-1]
        if not (p2 < p1 and q2 > q1 and j - min(i1, j1) <= 60):
            continue
        haut = p1 + (p2 - p1) / (i2 - i1) * (j - i1)
        bas = q1 + (q2 - q1) / (j2 - j1) * (j - j1)
        if haut <= bas:
            continue
        hauteur = p1 - q1
        if c[j] > haut and c[j - 1] <= p1 + (p2 - p1) / (i2 - i1) * (j - 1 - i1):
            s[j], sl[j], cl[j] = 1, q2, c[j] + hauteur
        elif c[j] < bas and c[j - 1] >= q1 + (q2 - q1) / (j2 - j1) * (j - 1 - j1):
            s[j], sc[j], cc[j] = -1, p2, c[j] - hauteur
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc}


def v30_drapeau(d):
    """Drapeau : impulsion d'au moins 4 ATR en 10 bougies au plus, puis 5 à 15 bougies serrées (amplitude ≤ 50 % de
    l'impulsion, sans retracer plus de 50 %) ; clôture au-dessus du drapeau → achat ; stop sous le drapeau ; objectif
    la longueur de l'impulsion. Symétrique à la baisse."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    n = len(c)
    s, sl, sc, cl, cc = np.zeros(n), _nan(n), _nan(n), _nan(n), _nan(n)
    for j in range(30, n):
        if not np.isfinite(a[j]):
            continue
        for long_d in (5, 10, 15):
            f0 = j - long_d
            fh, fl = h[f0:j].max(), l[f0:j].min()
            imp_debut = f0 - 10
            if imp_debut < 0:
                continue
            bas_imp, haut_imp = l[imp_debut:f0].min(), h[imp_debut:f0].max()
            imp = haut_imp - bas_imp
            if imp < 4 * a[j]:
                continue
            if fh - fl <= 0.5 * imp:
                hausse = np.argmax(h[imp_debut:f0]) > np.argmin(l[imp_debut:f0])
                if hausse and fl > haut_imp - 0.5 * imp and c[j] > fh and c[j - 1] <= fh:
                    s[j], sl[j], cl[j] = 1, fl, c[j] + imp
                    break
                if not hausse and fh < bas_imp + 0.5 * imp and c[j] < fl and c[j - 1] >= fl:
                    s[j], sc[j], cc[j] = -1, fh, c[j] - imp
                    break
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc}


def v31_cassure_retest(d):
    """Cassure puis retest : clôture au-dessus du dernier sommet confirmé ; dans les 10 bougies, retour à 0,25 ATR du
    niveau et clôture au-dessus → achat ; stop niveau − 1 ATR ; objectif 2 fois le risque. Symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    n = len(c)
    sommets, creux = M.pivots(h, l, 5, 5)
    s, sl, sc = np.zeros(n), _nan(n), _nan(n)
    for liste, t in ((sommets, 1), (creux, -1)):
        for idx, (k, i, p) in enumerate(liste):
            fin = liste[idx + 1][0] if idx + 1 < len(liste) else n
            casse = None
            for j in range(k, min(fin, n)):
                if casse is None:
                    if (t == 1 and c[j] > p) or (t == -1 and c[j] < p):
                        casse = j
                    continue
                if j - casse > 10 or not np.isfinite(a[j]):
                    break
                if t == 1 and l[j] <= p + 0.25 * a[j] and c[j] > p:
                    s[j], sl[j] = 1, p - a[j]
                    break
                if t == -1 and h[j] >= p - 0.25 * a[j] and c[j] < p:
                    s[j], sc[j] = -1, p + a[j]
                    break
    c_ = d["c"]
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": c_ + 2 * (c_ - sl), "cible_c": c_ - 2 * (sc - c_)}


def v32_fausse_cassure(d):
    """Fausse cassure (TradingLab ; « turtle soup » de Connors et Raschke ; « liquidity sweep » ICT ; « spring » de
    Wyckoff) : plus bas sous le plus bas des 20 bougies précédentes, clôture revenue au-dessus → achat ; stop sous le
    plus bas − 0,2 ATR ; objectif 2 fois le risque. Symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    pb, ph = M.plus_bas(l, 20), M.plus_haut(h, 20)
    achat, vente = (l < pb) & (c > pb), (h > ph) & (c < ph)
    return avec_rr(d, achat, vente, l - 0.2 * a, h + 0.2 * a, 2.0)


def v33_ligne_tendance(d):
    """Ligne de tendance : droite des deux derniers sommets descendants ; clôture qui la franchit → achat ; stop au
    dernier creux ; objectif 2 fois le risque. Symétrique avec la droite des creux montants."""
    h, l, c = d["h"], d["l"], d["c"]
    n = len(c)
    sommets, creux = M.pivots(h, l, 5, 5)
    evts = sorted([(k, i, p, 1) for k, i, p in sommets] + [(k, i, p, -1) for k, i, p in creux])
    s, sl, sc = np.zeros(n), _nan(n), _nan(n)
    sh, sb, e = [], [], 0
    utilise = set()
    for j in range(1, n):
        while e < len(evts) and evts[e][0] <= j:
            (sh if evts[e][3] == 1 else sb).append(evts[e][1:3])
            e += 1
        if len(sh) >= 2 and sb and ("h", sh[-1][0]) not in utilise:
            (i1, p1), (i2, p2) = sh[-2], sh[-1]
            if p2 < p1:
                ligne = p1 + (p2 - p1) / (i2 - i1) * (j - i1)
                avant = p1 + (p2 - p1) / (i2 - i1) * (j - 1 - i1)
                if c[j] > ligne and c[j - 1] <= avant:
                    s[j], sl[j] = 1, sb[-1][1]
                    utilise.add(("h", sh[-1][0]))
        if len(sb) >= 2 and sh and ("b", sb[-1][0]) not in utilise:
            (i1, q1), (i2, q2) = sb[-2], sb[-1]
            if q2 > q1:
                ligne = q1 + (q2 - q1) / (i2 - i1) * (j - i1)
                avant = q1 + (q2 - q1) / (i2 - i1) * (j - 1 - i1)
                if c[j] < ligne and c[j - 1] >= avant:
                    s[j], sc[j] = -1, sh[-1][1]
                    utilise.add(("b", sb[-1][0]))
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": c + 2 * (c - sl), "cible_c": c - 2 * (sc - c)}


# ============================================================================ chandeliers en contexte (H15)
def _contexte(d):
    """Contexte commun : tendance (EMA 200) et proximité d'un support / d'une résistance de 20 bougies (0,5 ATR)."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    e200 = M.ema(c, 200)
    pres_support = fen_min(l, 3) <= M.plus_bas(l, 20) + 0.5 * a
    pres_resist = fen_max(h, 3) >= M.plus_haut(h, 20) - 0.5 * a
    return a, e200, pres_support, pres_resist


def _bougie(d, haussier, baissier):
    """Entrée au-dessus du plus haut de la bougie signal (achat) ; stop sous son plus bas − 0,1 ATR ; objectif 2 R."""
    h, l, c = d["h"], d["l"], d["c"]
    a, e200, sup, res = _contexte(d)
    achat = haussier & sup & (c > e200)
    vente = baissier & res & (c < e200)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)),
            "stop_l": fen_min(l, 2) - 0.1 * a, "stop_c": fen_max(h, 2) + 0.1 * a,
            "cible_l": c + 2 * (c - (fen_min(l, 2) - 0.1 * a)), "cible_c": c - 2 * ((fen_max(h, 2) + 0.1 * a) - c)}


def v34_avalement(d):
    """Avalement (engulfing) haussier près d'un support dans une tendance haussière ; baissier symétrique."""
    o, c = d["o"], d["c"]
    po, pc = np.r_[NAN, o[:-1]], np.r_[NAN, c[:-1]]
    hauss = (pc < po) & (c > o) & (c >= po) & (o <= pc)
    baiss = (pc > po) & (c < o) & (c <= po) & (o >= pc)
    return _bougie(d, hauss, baiss)


def v35_marteau(d):
    """Marteau / « pin bar » : mèche basse ≥ 2 fois le corps, mèche haute ≤ le corps ; étoile filante symétrique."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    corps = np.abs(c - o) + 1e-12
    bas, haut = np.minimum(o, c) - l, h - np.maximum(o, c)
    return _bougie(d, (bas >= 2 * corps) & (haut <= corps), (haut >= 2 * corps) & (bas <= corps))


def v36_etoile_matin(d):
    """Étoile du matin : grande bougie baissière, petite bougie, grande haussière qui clôture au-delà du milieu de la
    première ; étoile du soir symétrique."""
    o, c = d["o"], d["c"]
    a = M.atr(d["h"], d["l"], c, 14)
    o2, c2, o1, c1 = np.r_[NAN, NAN, o[:-2]], np.r_[NAN, NAN, c[:-2]], np.r_[NAN, o[:-1]], np.r_[NAN, c[:-1]]
    grand2, petit1, grand0 = np.abs(c2 - o2) > 0.6 * a, np.abs(c1 - o1) < 0.3 * a, np.abs(c - o) > 0.6 * a
    hauss = grand2 & (c2 < o2) & petit1 & grand0 & (c > o) & (c > (o2 + c2) / 2)
    baiss = grand2 & (c2 > o2) & petit1 & grand0 & (c < o) & (c < (o2 + c2) / 2)
    return _bougie(d, hauss, baiss)


def v37_doji(d):
    """Doji (corps ≤ 10 % de l'amplitude) près d'un support, confirmé par une clôture au-dessus de son plus haut le
    lendemain ; symétrique près d'une résistance."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    doji = np.abs(c - o) <= 0.1 * (h - l + 1e-12)
    pd_, ph_, pl_ = np.r_[False, doji[:-1]], np.r_[NAN, h[:-1]], np.r_[NAN, l[:-1]]
    return _bougie(d, pd_ & (c > ph_), pd_ & (c < pl_))


def v38_trois_soldats(d):
    """Trois soldats blancs : trois bougies haussières de plus en plus hautes, clôtures près du plus haut ; trois
    corbeaux symétriques."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    hb = (c > o) & (h - c <= 0.3 * (h - l + 1e-12))
    bb = (c < o) & (c - l <= 0.3 * (h - l + 1e-12))
    up = np.r_[False, c[1:] > c[:-1]]
    dn = np.r_[False, c[1:] < c[:-1]]
    trois = lambda x: x & np.r_[False, x[:-1]] & np.r_[False, False, x[:-2]]
    return _bougie(d, trois(hb & up), trois(bb & dn))


def v39_barre_interieure(d):
    """Barre intérieure (inside bar) dans le sens de la tendance (EMA 50) : ordre au-dessus de la bougie mère (achat) ou
    au-dessous (vente), stop de l'autre côté, objectif 2 fois le risque."""
    h, l, c = d["h"], d["l"], d["c"]
    mh, ml = np.r_[NAN, h[:-1]], np.r_[NAN, l[:-1]]
    inside = (h < mh) & (l > ml)
    e50 = M.ema(c, 50)
    s = np.where(inside & (c > e50), 1, np.where(inside & (c < e50), -1, 0))
    r = mh - ml
    return {"sens": s, "entree_l": mh, "entree_c": ml, "stop_l": ml, "stop_c": mh,
            "cible_l": mh + 2 * r, "cible_c": ml - 2 * r, "validite": 2}


def v40_trois_lignes(d):
    """« Three line strike » : trois bougies baissières puis une haussière qui avale les trois → achat (dans la tendance
    EMA 200) ; symétrique."""
    o, c = d["o"], d["c"]
    b = c < o
    trois_b = np.r_[False, b[:-1]] & np.r_[False, False, b[:-2]] & np.r_[False, False, False, b[:-3]]
    trois_h = np.r_[False, ~b[:-1]] & np.r_[False, False, ~b[:-2]] & np.r_[False, False, False, ~b[:-3]]
    o3 = np.r_[NAN, NAN, NAN, o[:-3]]
    hauss = trois_b & (c > o) & (c > o3)
    baiss = trois_h & (c < o) & (c < o3)
    a, e200, _, _ = _contexte(d)
    h, l = d["h"], d["l"]
    achat, vente = hauss & (c > e200), baiss & (c < e200)
    sl, sc = fen_min(l, 4) - 0.1 * a, fen_max(h, 4) + 0.1 * a
    return avec_rr(d, achat, vente, sl, sc, 2.0)


# ============================================================================ « smart money » / ICT
def v41_bloc_ordres(d):
    """Bloc d'ordres : cassure de structure (clôture au-dessus du dernier sommet confirmé), bloc = dernière bougie
    baissière avant l'impulsion (10 bougies au plus) ; retour dans le bloc en 20 bougies et clôture au-dessus de son bas
    → achat ; stop sous le bloc − 0,1 ATR ; objectif 2 fois le risque. Symétrique."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    n = len(c)
    sommets, creux = M.pivots(h, l, 5, 5)
    s, sl, sc = np.zeros(n), _nan(n), _nan(n)
    for liste, t in ((sommets, 1), (creux, -1)):
        for idx, (k, i, p) in enumerate(liste):
            fin = liste[idx + 1][0] if idx + 1 < len(liste) else n
            bos = next((j for j in range(k, min(fin, n)) if (t == 1 and c[j] > p) or (t == -1 and c[j] < p)), None)
            if bos is None:
                continue
            bloc = next((m for m in range(bos - 1, max(bos - 11, 0), -1) if (t == 1 and c[m] < o[m]) or
                         (t == -1 and c[m] > o[m])), None)
            if bloc is None:
                continue
            bh, bb = h[bloc], l[bloc]
            for j in range(bos + 1, min(n, bos + 21)):
                if not np.isfinite(a[j]):
                    break
                if t == 1 and l[j] <= bh and c[j] > bb:
                    s[j], sl[j] = 1, bb - 0.1 * a[j]
                    break
                if t == -1 and h[j] >= bb and c[j] < bh:
                    s[j], sc[j] = -1, bh + 0.1 * a[j]
                    break
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": c + 2 * (c - sl), "cible_c": c - 2 * (sc - c)}


def _fvg(d):
    """Écarts de juste valeur (« fair value gaps ») : bas(i) > haut(i−2) avec une bougie i−1 haussière d'au moins 1 ATR."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    h2, l2 = np.r_[NAN, NAN, h[:-2]], np.r_[NAN, NAN, l[:-2]]
    o1, c1, a1 = np.r_[NAN, o[:-1]], np.r_[NAN, c[:-1]], np.r_[NAN, a[:-1]]
    haussier = (l > h2) & (c1 - o1 > a1)
    baissier = (h < l2) & (o1 - c1 > a1)
    return haussier, baissier, h2, l2, a


def v42_fvg(d):
    """Écart de juste valeur : après un écart haussier, retour dans l'écart en 20 bougies et clôture au-dessus de son
    bas → achat ; stop sous l'écart − 0,5 ATR ; objectif 2 fois le risque. Symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    hs, bs, h2, l2, a = _fvg(d)
    n = len(c)
    s, sl, sc = np.zeros(n), _nan(n), _nan(n)
    for i in np.flatnonzero(hs):
        bas, haut = h2[i], l[i]
        for j in range(i + 1, min(n, i + 21)):
            if l[j] <= haut and c[j] > bas:
                s[j], sl[j] = 1, bas - 0.5 * a[j]
                break
            if c[j] < bas:
                break
    for i in np.flatnonzero(bs):
        haut, bas = l2[i], h[i]
        for j in range(i + 1, min(n, i + 21)):
            if h[j] >= bas and c[j] < haut:
                s[j], sc[j] = -1, haut + 0.5 * a[j]
                break
            if c[j] > haut:
                break
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": c + 2 * (c - sl), "cible_c": c - 2 * (sc - c)}


def v43_balayage_veille(d):
    """ICT, balayage de liquidité : le prix dépasse le plus haut de la VEILLE puis clôture en dessous → vente ; stop au
    plus haut atteint + 0,1 ATR ; objectif 2 fois le risque. Symétrique sur le plus bas de la veille. (Intraday.)"""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    ph, pb, _ = niveaux_veille(d)
    _, j = minutes_utc(d["ts"])
    debut = np.r_[True, j[1:] != j[:-1]]
    haut_jour = np.empty(len(c))
    bas_jour = np.empty(len(c))
    for k in range(len(c)):
        haut_jour[k] = h[k] if debut[k] else max(haut_jour[k - 1], h[k])
        bas_jour[k] = l[k] if debut[k] else min(bas_jour[k - 1], l[k])
    vente = (h > ph) & (c < ph)
    achat = (l < pb) & (c > pb)
    return avec_rr(d, achat, vente, bas_jour - 0.1 * a, haut_jour + 0.1 * a, 2.0)


def v44_changement_caractere(d):
    """Changement de caractère (« CHoCH ») : après deux sommets et deux creux descendants, clôture au-dessus du dernier
    sommet → achat ; stop au dernier creux ; objectif 2 fois le risque. Symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    n = len(c)
    sommets, creux = M.pivots(h, l, 5, 5)
    evts = sorted([(k, i, p, 1) for k, i, p in sommets] + [(k, i, p, -1) for k, i, p in creux])
    s, sl, sc = np.zeros(n), _nan(n), _nan(n)
    sh, sb, e, fait = [], [], 0, set()
    for j in range(n):
        while e < len(evts) and evts[e][0] <= j:
            (sh if evts[e][3] == 1 else sb).append(evts[e][2])
            e += 1
        if len(sh) >= 2 and len(sb) >= 2:
            if sh[-1] < sh[-2] and sb[-1] < sb[-2] and c[j] > sh[-1] and ("h", len(sh)) not in fait:
                s[j], sl[j] = 1, sb[-1]
                fait.add(("h", len(sh)))
            elif sh[-1] > sh[-2] and sb[-1] > sb[-2] and c[j] < sb[-1] and ("b", len(sb)) not in fait:
                s[j], sc[j] = -1, sh[-1]
                fait.add(("b", len(sb)))
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": c + 2 * (c - sl), "cible_c": c - 2 * (sc - c)}


def v45_silver_bullet(d):
    """ICT « Silver Bullet » : de 10 h à 11 h (New York), premier écart de juste valeur ; entrée au retour dans l'écart
    avant 11 h ; stop sous l'écart − 0,5 ATR ; objectif 2 fois le risque ; sortie à 12 h au plus tard. (Intraday.)"""
    h, l, c = d["h"], d["l"], d["c"]
    m, jny = minutes_ny(d["ts"])
    hs, bs, h2, l2, a = _fvg(d)
    n = len(c)
    s, sl, sc, sortie = np.zeros(n), _nan(n), _nan(n), np.zeros(n)
    fenetre = (m >= 600) & (m < 660)
    sortie[(m >= 715)] = 2
    vu = set()
    for i in np.flatnonzero((hs | bs) & fenetre):
        if jny[i] in vu:
            continue
        vu.add(jny[i])
        for j in range(i + 1, n):
            if not fenetre[j] or jny[j] != jny[i]:
                break
            if hs[i] and l[j] <= l[i] and c[j] > h2[i]:
                s[j], sl[j] = 1, h2[i] - 0.5 * a[j]
                break
            if bs[i] and h[j] >= h[i] and c[j] < l2[i]:
                s[j], sc[j] = -1, l2[i] + 0.5 * a[j]
                break
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": c + 2 * (c - sl), "cible_c": c - 2 * (sc - c),
            "sortie": sortie}


def _plage(d, debut_min, fin_min, base="utc"):
    """Plus haut / plus bas d'une plage horaire du jour, connus à la fin de la plage (sinon nan)."""
    m, j = minutes_utc(d["ts"]) if base == "utc" else minutes_ny(d["ts"])
    n = len(m)
    hh, ll = _nan(n), _nan(n)
    cur_j, mh, ml = None, -np.inf, np.inf
    for k in range(n):
        if j[k] != cur_j:
            cur_j, mh, ml = j[k], -np.inf, np.inf
        if debut_min <= m[k] < fin_min:
            mh, ml = max(mh, d["h"][k]), min(ml, d["l"][k])
        elif m[k] >= fin_min and np.isfinite(mh):
            hh[k], ll[k] = mh, ml
    return hh, ll, m


def v46_judas_londres(d):
    """ICT « Judas swing » / « power of 3 » : plage asiatique 0 h-7 h UTC ; entre 7 h et 10 h UTC, le prix dépasse le haut
    de la plage puis clôture dedans → vente, objectif le bas de la plage, stop au plus haut atteint ; symétrique. Sortie
    à 16 h UTC. (Intraday.)"""
    h, l, c = d["h"], d["l"], d["c"]
    hh, ll, m = _plage(d, 0, 420)
    a = M.atr(h, l, c, 14)
    fen = (m >= 420) & (m < 600)
    vente = fen & (h > hh) & (c < hh) & (c > ll)
    achat = fen & (l < ll) & (c > ll) & (c < hh)
    sortie = np.where(m >= 945, 2, 0)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "stop_l": fen_min(l, 12) - 0.1 * a,
            "stop_c": fen_max(h, 12) + 0.1 * a, "cible_l": hh, "cible_c": ll, "sortie": sortie}


# ============================================================================ séances (H18, H19), annonces, lundi
def v47_cassure_londres(d):
    """Cassure de Londres : plage asiatique 0 h-7 h UTC ; de 7 h à 12 h UTC, ordre au-dessus du haut (achat) et au-dessous
    du bas (vente), le premier touché ; stop de l'autre côté ; objectif 1 fois la plage ; sortie à 16 h UTC."""
    hh, ll, m = _plage(d, 0, 420)
    _, j = minutes_utc(d["ts"])
    fen = (m >= 420) & (m < 720)
    n = len(m)
    s = np.zeros(n)
    premier = fen & np.isfinite(hh) & np.r_[True, ~fen[:-1] | (j[1:] != j[:-1])]
    s[premier] = 2
    r = hh - ll
    return {"sens": s, "entree_l": hh, "entree_c": ll, "stop_l": ll, "stop_c": hh, "cible_l": hh + r, "cible_c": ll - r,
            "validite": 60, "sortie": np.where(m >= 945, 2, 0)}


def v48_ouverture_ny(d):
    """Cassure de la fourchette d'ouverture (Crabel, H19) : 30 premières minutes après 9 h 30 (New York) ; ordre au-dessus
    et au-dessous jusqu'à 12 h ; stop de l'autre côté ; objectif 2 fois la fourchette ; sortie à 15 h 55. (Intraday.)"""
    hh, ll, m = _plage(d, 570, 600, base="ny")
    _, j = minutes_ny(d["ts"])
    fen = (m >= 600) & (m < 720)
    premier = fen & np.isfinite(hh) & np.r_[True, ~fen[:-1] | (j[1:] != j[:-1])]
    s = np.where(premier, 2, 0)
    r = hh - ll
    sortie = np.where(m >= 955, 2, 0)
    return {"sens": s, "entree_l": hh, "entree_c": ll, "stop_l": ll, "stop_c": hh, "cible_l": hh + 2 * r,
            "cible_c": ll - 2 * r, "validite": 30, "sortie": sortie}


def v49_nfp(d):
    """Emploi américain (NFP, 1er vendredi du mois, 8 h 30 New York) : fourchette 8 h-8 h 30 ; ordres 0,5 ATR au-delà
    jusqu'à 10 h ; stop de l'autre côté ; objectif 2 fois le risque ; sortie à 15 h 55. (Intraday.)"""
    import datetime as dt
    hh, ll, m = _plage(d, 480, 510, base="ny")
    _, jny = minutes_ny(d["ts"])
    a = M.atr(d["h"], d["l"], d["c"], 14)
    jours = np.array([dt.date(1970, 1, 1) + dt.timedelta(days=int(x)) for x in jny])
    nfp = np.array([x.weekday() == 4 and x.day <= 7 for x in jours])
    fen = nfp & (m >= 510) & (m < 600)
    premier = fen & np.isfinite(hh) & np.r_[True, ~fen[:-1]]
    s = np.where(premier, 2, 0)
    hl, lc = hh + 0.5 * a, ll - 0.5 * a
    sortie = np.where(m >= 955, 2, 0)
    return {"sens": s, "entree_l": hl, "entree_c": lc, "stop_l": ll, "stop_c": hh, "cible_l": hl + 2 * (hl - ll),
            "cible_c": lc - 2 * (hh - lc), "validite": 18, "sortie": sortie}


def v50_trou_lundi(d):
    """Trou du lundi (H21), en journalier : écart d'ouverture de plus de 0,3 % contre la clôture du vendredi → on joue
    sa fermeture le jour même (objectif : la clôture du vendredi ; stop : 1 écart au-delà ; sortie à la clôture)."""
    import datetime as dt
    o, c = d["o"], d["c"]
    jours = d["ts"] // 86_400_000
    lundi = np.array([(dt.date(1970, 1, 1) + dt.timedelta(days=int(x))).weekday() == 0 for x in jours])
    n = len(c)
    s, sl, sc, cl, cc = np.zeros(n), _nan(n), _nan(n), _nan(n), _nan(n)
    # le trou n'est connu qu'à l'OUVERTURE du lundi : entrée au premier cours du lundi (un peu optimiste, signalé)
    gap = np.r_[o[1:] / c[:-1] - 1, 0.0]
    for i in range(n - 1):
        if lundi[i + 1] and abs(gap[i]) > 0.003:
            g = o[i + 1] - c[i]
            if g > 0:
                s[i], sc[i], cc[i] = -1, o[i + 1] + g, c[i]
            else:
                s[i], sl[i], cl[i] = 1, o[i + 1] + g, c[i]
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc, "duree": 1, "_regarde_ouverture": True}


# ============================================================================ autres familles
def v51_renko(d):
    """Renko (briques de 1 ATR 14, fixé chaque jour sur l'ATR de la veille) : deux briques haussières après une brique
    baissière → achat ; sortie à la première brique contraire. Symétrique."""
    c = d["c"]
    a = M.atr(d["h"], d["l"], c, 14)
    n = len(c)
    s, sortie = np.zeros(n), np.zeros(n)
    briques = []
    base = c[0]
    for i in range(1, n):
        taille = a[i - 1]
        if not np.isfinite(taille) or taille <= 0:
            continue
        while c[i] >= base + taille:
            base += taille
            briques.append(1)
            if len(briques) >= 3 and briques[-3:] == [-1, 1, 1]:
                s[i] = 1
            sortie[i] = -1
        while c[i] <= base - taille:
            base -= taille
            briques.append(-1)
            if len(briques) >= 3 and briques[-3:] == [1, -1, -1]:
                s[i] = -1
            sortie[i] = 1
    return {"sens": s, "sortie": sortie}


def v52_multi_unites(d):
    """Analyse multi-unités : biais du jour = EMA 50 journalière montante (journée close la veille) ; dans ce sens,
    croisement EMA 9 / EMA 21 sur l'unité testée → entrée ; stop au dernier creux (10 bougies) ; objectif 2 R."""
    c = d["c"]
    _, j = minutes_utc(d["ts"])
    debut = np.flatnonzero(np.r_[True, j[1:] != j[:-1]])
    fin = np.r_[debut[1:], len(j)]
    cl_j = np.array([c[b - 1] for b in fin])
    e50 = M.ema(cl_j, 50)
    pente = np.r_[NAN, e50[1:] - e50[:-1]]
    biais = np.zeros(len(c))
    for k in range(1, len(debut)):
        biais[debut[k]:fin[k]] = np.sign(pente[k - 1]) if np.isfinite(pente[k - 1]) else 0
    a9, a21 = M.ema(c, 9), M.ema(c, 21)
    sl, sc = swing(d, 10)
    return avec_rr(d, croise_haut(a9, a21) & (biais > 0), croise_bas(a9, a21) & (biais < 0), sl, sc, 2.0)


def v53_scalping_1min(d):
    """Scalping 1 minute (Jdub Trades et autres) : clôture > VWAP et EMA 9 > EMA 20, repli qui touche l'EMA 20 et clôture
    au-dessus de l'EMA 9 → achat ; stop sous la bougie − 0,1 ATR ; objectif 1,5 R. Symétrique. (1 minute.)"""
    c, h, l = d["c"], d["h"], d["l"]
    w = vwap_jour(d)
    e9, e20 = M.ema(c, 9), M.ema(c, 20)
    a = M.atr(h, l, c, 14)
    achat = (c > w) & (e9 > e20) & (l <= e20) & (c > e9)
    vente = (c < w) & (e9 < e20) & (h >= e20) & (c < e9)
    return avec_rr(d, achat, vente, l - 0.1 * a, h + 0.1 * a, 1.5)


def v54_flux_ordres(d):
    """Flux d'ordres (volume acheteur des preneurs, Binance) : delta cumulé de 20 bougies positif et cassure du plus
    haut de 20 bougies → achat ; stop 1,5 ATR ; objectif 2 R. Symétrique."""
    c, h, l = d["c"], d["h"], d["l"]
    delta = 2 * d["vb"] - d["v"]
    cvd20 = M.sma(delta, 20) * 20
    a = M.atr(h, l, c, 14)
    ph, pb = M.plus_haut(h, 20), M.plus_bas(l, 20)
    achat = (cvd20 > 0) & (c > ph)
    vente = (cvd20 < 0) & (c < pb)
    return avec_rr(d, achat, vente, c - 1.5 * a, c + 1.5 * a, 2.0)


def v55_profil_volume(d):
    """Profil de volume, règle des 80 % (Dalton) : zone de valeur de la veille (70 % du volume autour du prix le plus
    échangé) ; ouverture hors de la zone puis deux bougies closes dedans → objectif l'autre bord de la zone ; stop au
    plus extrême du jour. (Intraday.)"""
    h, l, c, v = d["h"], d["l"], d["c"], d["v"]
    _, j = minutes_utc(d["ts"])
    debut = np.flatnonzero(np.r_[True, j[1:] != j[:-1]])
    fin = np.r_[debut[1:], len(j)]
    n = len(c)
    s, sl, sc, cl, cc = np.zeros(n), _nan(n), _nan(n), _nan(n), _nan(n)
    for k in range(1, len(debut)):
        a, b = debut[k - 1], fin[k - 1]
        tp = (h[a:b] + l[a:b] + c[a:b]) / 3
        vol = v[a:b]
        if vol.sum() <= 0:
            continue
        ordre = np.argsort(tp)
        tps, vols = tp[ordre], vol[ordre]
        poc = np.argmax(vols)
        lo_i, hi_i, tot = poc, poc, vols[poc]
        while tot < 0.7 * vols.sum():
            g = vols[lo_i - 1] if lo_i > 0 else -1
            dr = vols[hi_i + 1] if hi_i + 1 < len(vols) else -1
            if dr >= g:
                hi_i += 1
                tot += dr
            else:
                lo_i -= 1
                tot += g
        val, vah = tps[lo_i], tps[hi_i]
        a2, b2 = debut[k], fin[k]
        ouv = d["o"][a2]
        dedans = 0
        for i in range(a2, b2):
            if val < c[i] < vah:
                dedans += 1
            else:
                dedans = 0
            if dedans == 2:
                if ouv < val:
                    s[i], sl[i], cl[i] = 1, l[a2:i + 1].min(), vah
                elif ouv > vah:
                    s[i], sc[i], cc[i] = -1, h[a2:i + 1].max(), val
                break
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc, "sortie": np.r_[np.where(j[1:] != j[:-1], 2, 0), 0]}


# ============================================================================ fiches H01 à H22 (journalier)
def h01_turtles_s1(d):
    """Turtles, système 1 (Faith, « Way of the Turtle ») : ordre à la cassure du plus haut de 20 jours (achat) ou du plus
    bas (vente), le premier touché ; stop à 2 N (ATR 20) ; sortie dès que le prix touche le plus bas de 10 jours
    (achat) / le plus haut de 10 jours (vente). Sans le filtre « sauter après un gain » (voir etudes/fiches_r7.py)."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 20)
    ph, pb = fen_max(h, 20), fen_min(l, 20)
    s = np.where(np.isfinite(ph) & np.isfinite(a), 2, 0)
    return {"sens": s, "entree_l": ph, "entree_c": pb, "stop_l": ph - 2 * a, "stop_c": pb + 2 * a, "validite": 1,
            "suivi_l": fen_min(l, 10), "suivi_c": fen_max(h, 10)}


def h01b_turtles_s2(d):
    """Turtles, système 2 : cassure du plus haut (bas) de 55 jours, stop 2 N, sortie dès que le prix touche le plus bas
    (haut) de 20 jours."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 20)
    ph, pb = fen_max(h, 55), fen_min(l, 55)
    s = np.where(np.isfinite(ph) & np.isfinite(a), 2, 0)
    return {"sens": s, "entree_l": ph, "entree_c": pb, "stop_l": ph - 2 * a, "stop_c": pb + 2 * a, "validite": 1,
            "suivi_l": fen_min(l, 20), "suivi_c": fen_max(h, 20)}


def h02_pivot_livermore(d):
    """Pivot de Livermore : après un repli d'au moins 3 ATR, ordre au-dessus du dernier sommet confirmé (pivots 10/10)
    quand il est aussi le plus haut de 52 semaines ; stop au dernier creux ; sortie au plus bas de 20 jours."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 20)
    n = len(c)
    sommets, creux = M.pivots(h, l, 10, 10)
    s, en, sl = np.zeros(n), _nan(n), _nan(n)
    dernier_creux = None
    evts = sorted([(k, i, p, 1) for k, i, p in sommets] + [(k, i, p, -1) for k, i, p in creux])
    for k, i, p, t in evts:
        if t == -1:
            dernier_creux = p
            continue
        if k >= n or dernier_creux is None or i < 252:
            continue
        if p >= h[i - 252:i + 1].max() and p - l[i:k + 1].min() >= 3 * a[k]:
            s[k], en[k], sl[k] = 1, p, l[i:k + 1].min()
    return {"sens": s, "entree_l": en, "stop_l": sl, "validite": 20, "sortie": np.where(c < M.plus_bas(l, 20), 1, 0)}


def h03_darvas(d):
    """Boîte de Darvas : nouveau plus haut de 52 semaines ; haut de boîte = plus haut non dépassé 3 jours ; bas de
    boîte = plus bas non cassé 3 jours ensuite ; ordre au-dessus du haut ; stop au bas de la boîte."""
    h, l, c = d["h"], d["l"], d["c"]
    n = len(c)
    s, en, sl = np.zeros(n), _nan(n), _nan(n)
    i = 252
    while i < n - 6:
        if h[i] >= h[i - 252:i].max():
            haut = h[i]
            if h[i + 1:i + 4].max() <= haut:
                bas = l[i + 1:i + 4].min()
                if l[i + 4:i + 7].min() >= bas:
                    k = i + 6
                    s[k], en[k], sl[k] = 1, haut, bas
                    i = k + 1
                    continue
        i += 1
    return {"sens": s, "entree_l": en, "stop_l": sl, "validite": 10, "sortie": np.where(c < M.plus_bas(l, 20), 1, 0)}


def h04_h06_moyennes(d):
    """Règle des 10 mois (Faber, H06) : clôture au-dessus de la moyenne de 210 jours → achat ; en dessous → vente à
    découvert (version longue / courte de la règle des 200 jours de l'équipe, H04)."""
    c = d["c"]
    m = M.sma(c, 210)
    return {"sens": np.where(croise_haut(c, m), 1, np.where(croise_bas(c, m), -1, 0))}


def h05_momentum_1_12(d):
    """Momentum de 1 à 12 mois, long / court : signe de la moyenne des rendements 1, 3, 6 et 12 mois ; revu chaque
    mois (21 jours)."""
    c = d["c"]
    n = len(c)
    s = np.zeros(n)
    cur = 0
    for i in range(252, n):
        if i % 21:
            continue
        sig = np.sign(np.mean([c[i] / c[i - k] - 1 for k in (21, 63, 126, 252)]))
        if sig != cur and sig != 0:
            s[i], cur = sig, sig
    return {"sens": s}


def h07_wyckoff(d):
    """Spring / upthrust de Wyckoff : plage de 40 bougies d'amplitude ≤ 6 ATR ; plus bas sous la plage et clôture dedans,
    volume ≥ 1,5 fois sa moyenne de 20 (si connu) → achat ; stop sous le plus bas − 0,2 ATR ; objectif le haut de la
    plage. Upthrust : symétrique."""
    h, l, c, v = d["h"], d["l"], d["c"], d.get("v")
    a = M.atr(h, l, c, 14)
    ph, pb = M.plus_haut(h, 40), M.plus_bas(l, 40)
    plage = (ph - pb) <= 6 * a
    if v is not None and np.nanmax(v) > 0:
        fort = v >= 1.5 * M.sma(v, 20)
    else:
        fort = np.ones(len(c), bool)
    achat = plage & (l < pb) & (c > pb) & fort
    vente = plage & (h > ph) & (c < ph) & fort
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "stop_l": l - 0.2 * a, "stop_c": h + 0.2 * a,
            "cible_l": ph, "cible_c": pb}


def h09_reflexivite(d):
    """Réflexivité (Soros), formalisée en tendance qui S'ACCÉLÈRE : rendement 12 mois > 0 et rendement 3 mois > le quart
    du rendement 12 mois → achat ; sinon à plat. Revu chaque mois."""
    c = d["c"]
    n = len(c)
    s, sortie = np.zeros(n), np.zeros(n)
    for i in range(252, n):
        if i % 21:
            continue
        r12, r3 = c[i] / c[i - 252] - 1, c[i] / c[i - 63] - 1
        if r12 > 0 and r3 > r12 / 4:
            s[i] = 1
        else:
            sortie[i] = 1
    return {"sens": s, "sortie": sortie}


def h14_range(d):
    """Retour à la moyenne en marché sans tendance : ADX (14) < 20, clôture sous la bande basse de Bollinger (20, 2) →
    achat, objectif la moyenne 20, stop 1,5 ATR ; symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    x, _, _ = M.adx(h, l, c, 14)
    m, haut, bas = M.bollinger(c, 20, 2.0)
    a = M.atr(h, l, c, 14)
    achat, vente = (x < 20) & (c < bas), (x < 20) & (c > haut)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "stop_l": c - 1.5 * a, "stop_c": c + 1.5 * a,
            "cible_l": m, "cible_c": m}


def h11_meta_etiquetage(d):
    """Méta-étiquetage (López de Prado, H11) : marqueur pour l'étude ; la règle est appliquée dans recherche_r7.py
    (filtre appris sur la 1re moitié, jugé sur la 2e seulement)."""
    return {"sens": np.zeros(len(d["c"]))}


# ============================================================================ registre
INTRADAY = {
    "V01 MACD + EMA 200 (TradingLab, « 86 % »)": v01_macd_200ema,
    "V02 EMA 9 / 15 (The Trade Room)": v02_ema_9_15,
    "V03 5 EMA (Power of Stocks)": v03_ema5,
    "V04 croisement EMA 9 / 21": v04_ema_9_21,
    "V05 croix d'or EMA 50 / 200": v05_croix_or_50_200,
    "V06 rebond sur l'EMA 50": v06_rebond_ema50,
    "V07 RSI 30 / 70": v07_rsi_30_70,
    "V08 divergence RSI": v08_divergence_rsi,
    "V09 Bollinger + RSI (TradingLab)": v09_bollinger_rsi,
    "V10 compression de Bollinger": v10_compression_bollinger,
    "V11 stochastique dans la tendance": v11_stochastique_tendance,
    "V12 SuperTrend 10 / 3": v12_supertrend,
    "V13 Ichimoku": v13_ichimoku,
    "V14 Heikin Ashi + EMA (Trader DNA)": v14_heikin_ashi_ema,
    "V15 SAR parabolique + EMA 200": v15_sar_ema200,
    "V16 ADX / DI": v16_adx_di,
    "V17 VWAP": v17_vwap,
    "V18 Keltner": v18_keltner,
    "V19 CCI ±100": v19_cci,
    "V20 Williams %R": v20_williams,
    "V21 MFI": v21_mfi,
    "V22 OBV + cassure": v22_obv,
    "V23 points pivots": v23_points_pivots,
    "V24 Fibonacci, poche dorée": v24_fibonacci_poche,
    "V25 Elliott, vague 3": v25_elliott_vague3,
    "V26 Gartley (harmonique)": v26_gartley,
    "V27 double creux / sommet": v27_double_creux_sommet,
    "V28 tête et épaules": v28_tete_epaules,
    "V29 triangle": v29_triangle,
    "V30 drapeau": v30_drapeau,
    "V31 cassure + retest": v31_cassure_retest,
    "V32 fausse cassure (turtle soup, balayage)": v32_fausse_cassure,
    "V33 ligne de tendance": v33_ligne_tendance,
    "V34 avalement (H15)": v34_avalement,
    "V35 marteau / pin bar (H15)": v35_marteau,
    "V36 étoile du matin / du soir (H15)": v36_etoile_matin,
    "V37 doji confirmé (H15)": v37_doji,
    "V38 trois soldats / corbeaux (H15)": v38_trois_soldats,
    "V39 barre intérieure": v39_barre_interieure,
    "V40 three line strike": v40_trois_lignes,
    "V41 bloc d'ordres (SMC)": v41_bloc_ordres,
    "V42 écart de juste valeur (FVG)": v42_fvg,
    "V43 balayage de la veille (ICT)": v43_balayage_veille,
    "V44 changement de caractère (CHoCH)": v44_changement_caractere,
    "V45 Silver Bullet (ICT)": v45_silver_bullet,
    "V46 Judas swing / power of 3 (ICT)": v46_judas_londres,
    "V47 cassure de Londres (H18)": v47_cassure_londres,
    "V48 cassure d'ouverture New York (H19)": v48_ouverture_ny,
    "V49 emploi américain NFP": v49_nfp,
    "V51 Renko": v51_renko,
    "V52 multi-unités de temps": v52_multi_unites,
    "V54 flux d'ordres (delta)": v54_flux_ordres,
    "V55 profil de volume, règle des 80 %": v55_profil_volume,
    "H07 spring / upthrust de Wyckoff": h07_wyckoff,
    "H14 retour à la moyenne sans tendance": h14_range,
}
SEULEMENT_INTRADAY = {"V17 VWAP", "V23 points pivots", "V43 balayage de la veille (ICT)", "V45 Silver Bullet (ICT)",
                      "V46 Judas swing / power of 3 (ICT)", "V47 cassure de Londres (H18)",
                      "V48 cassure d'ouverture New York (H19)", "V49 emploi américain NFP",
                      "V52 multi-unités de temps", "V54 flux d'ordres (delta)", "V55 profil de volume, règle des 80 %"}
SCALPING = {"V02 EMA 9 / 15 (The Trade Room)", "V03 5 EMA (Power of Stocks)", "V11 stochastique dans la tendance",
            "V01 MACD + EMA 200 (TradingLab, « 86 % »)"}
JOURNALIER = {
    "H01 Turtles, système 1 (20 / 10)": h01_turtles_s1,
    "H01 Turtles, système 2 (55 / 20)": h01b_turtles_s2,
    "H02 pivot de Livermore": h02_pivot_livermore,
    "H03 boîte de Darvas": h03_darvas,
    "H04/H06 règle des 10 mois, long / court": h04_h06_moyennes,
    "H05 momentum 1-12 mois, long / court": h05_momentum_1_12,
    "H09 réflexivité (tendance qui accélère)": h09_reflexivite,
    "H21 trou du lundi": v50_trou_lundi,
}
