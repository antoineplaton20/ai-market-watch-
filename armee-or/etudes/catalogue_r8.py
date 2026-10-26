"""R8 (26/10/2026) : les méthodes trouvées dans le corpus R8 (podcasts, vidéos Odysee, forums, recherche, discours)
qui n'avaient encore jamais été testées, écrites en règles FIXES avant les tests (même format que catalogue_r7)."""
from __future__ import annotations

import math

import numpy as np

import catalogue_r7 as C
import moteur_r7 as M

NAN = np.nan


def _pas_min(d):
    ts = np.asarray(d["ts"], np.int64)
    return int(np.median(np.diff(ts[:1000])) // 60_000) if len(ts) > 1 else 60


def fin_du_jour(d, fin=1440, fuseau="utc"):
    """Dernière bougie du jour (ou de la séance qui finit à la minute `fin`), connue par son HEURE : la bougie se
    termine à minuit (ou à `fin`) ou après. Pas besoin de voir la bougie suivante."""
    mn, _ = (C.minutes_ny if fuseau == "ny" else C.minutes_utc)(d["ts"])
    return (mn < fin) & (mn + _pas_min(d) >= fin)


def n01_gann_carre_9(d):
    """Carré de 9 de Gann : niveaux (√(ouverture du jour) ± k × 0,25)² ; cassure du premier niveau au-dessus de
    l'ouverture du jour → achat, stop au niveau au-dessous, objectif le niveau suivant ; vente symétrique. Sortie en
    fin de journée (UTC). Intraday."""
    _, j = C.minutes_utc(d["ts"])
    n = len(j)
    debut = np.flatnonzero(np.r_[True, j[1:] != j[:-1]])
    fin = np.r_[debut[1:], n]
    ouv = np.empty(n)
    for a, b in zip(debut, fin):
        ouv[a:b] = d["o"][a]
    echelle = 10_000.0 if np.median(ouv) < 10 else 1.0           # devises : en points de base, comme les praticiens
    r = np.sqrt(ouv * echelle)
    n1h, n2h = (r + 0.25) ** 2 / echelle, (r + 0.5) ** 2 / echelle
    n1b, n2b = (r - 0.25) ** 2 / echelle, (r - 0.5) ** 2 / echelle
    premier = np.zeros(n, bool)
    premier[debut] = True
    s = np.where(premier, 2, 0)
    return {"sens": s, "entree_l": n1h, "entree_c": n1b, "stop_l": ouv, "stop_c": ouv, "cible_l": n2h,
            "cible_c": n2b, "validite": int(np.max(fin - debut)), "sortie": np.where(fin_du_jour(d), 2, 0)}


def n02_camarilla(d):
    """Pivots Camarilla de la veille (H3/L3 : retour à la moyenne ; H4/L4 : cassure) : la bougie touche L3 et clôture
    au-dessus → achat, objectif le pivot, stop L4 ; clôture au-dessus de H4 → achat, objectif H4 + (H4 − H3) × 2,
    stop H3 ; symétrique. Intraday."""
    ph, pb, pc = C.niveaux_veille(d)
    r = ph - pb
    h3, l3, h4, l4 = pc + r * 1.1 / 4, pc - r * 1.1 / 4, pc + r * 1.1 / 2, pc - r * 1.1 / 2
    p = (ph + pb + pc) / 3
    c, h, l = d["c"], d["h"], d["l"]
    retour_a, retour_v = (l <= l3) & (c > l3), (h >= h3) & (c < h3)
    cass_a, cass_v = C.croise_haut(c, h4), C.croise_bas(c, l4)
    s = np.where(retour_a | cass_a, 1, np.where(retour_v | cass_v, -1, 0))
    return {"sens": s, "stop_l": np.where(cass_a, h3, l4), "stop_c": np.where(cass_v, l3, h4),
            "cible_l": np.where(cass_a, h4 + 2 * (h4 - h3), p), "cible_c": np.where(cass_v, l4 - 2 * (l3 - l4), p)}


def n03_ttm_squeeze(d):
    """TTM Squeeze (Carter) : Bollinger (20, 2) à l'intérieur de Keltner (20, 1,5 ATR) puis sortie de la compression ;
    sens donné par la régression du prix sur 20 bougies (pente) ; sortie quand la pente change de signe."""
    c, h, l = d["c"], d["h"], d["l"]
    m, bh, bb = M.bollinger(c, 20, 2.0)
    e, a = M.ema(c, 20), M.atr(h, l, c, 20)
    serre = (bh < e + 1.5 * a) & (bb > e - 1.5 * a)
    libere = np.r_[False, serre[:-1] & ~serre[1:]]
    x = np.arange(20) - 9.5
    pente = np.full(len(c), NAN)
    for i in range(19, len(c)):
        pente[i] = (x * (c[i - 19:i + 1] - c[i - 19:i + 1].mean())).sum()
    s = np.where(libere & (pente > 0), 1, np.where(libere & (pente < 0), -1, 0))
    chg = np.r_[0, np.sign(pente[1:]) != np.sign(pente[:-1])]
    return {"sens": s, "sortie": np.where(chg & (pente < 0), 1, np.where(chg & (pente > 0), -1, 0)),
            "stop_l": c - 2 * a, "stop_c": c + 2 * a}


def n04_cassure_williams(d):
    """Cassure de volatilité de Larry Williams : ordre d'achat à l'ouverture + 0,6 × l'amplitude de la veille, de vente
    à l'ouverture − 0,6 × l'amplitude ; le premier touché ; stop à l'ordre opposé ; sortie à l'ouverture suivante.
    Journalier (ordres posés à l'ouverture du jour, d'après elle : signalé dans le test « pas de futur »)."""
    o, h, l = d["o"], d["h"], d["l"]
    amp = h - l
    n = len(o)
    s = np.zeros(n)
    s[:-1] = 2
    haut = np.r_[o[1:] + 0.6 * amp[:-1], NAN]
    bas = np.r_[o[1:] - 0.6 * amp[:-1], NAN]
    return {"sens": s, "entree_l": haut, "entree_c": bas, "stop_l": bas, "stop_c": haut, "duree": 1, "validite": 1}


def n04b_williams_intraday(d):
    """Même cassure de Williams jouée DANS LA JOURNÉE (l'ordre des prix est connu) : à la 1re bougie du jour UTC,
    ordres à l'ouverture du jour ± 0,6 × l'amplitude de la veille ; stop à l'ordre opposé ; sortie en fin de jour."""
    ph, pb, _ = C.niveaux_veille(d)
    _, j = C.minutes_utc(d["ts"])
    n = len(j)
    debut = np.flatnonzero(np.r_[True, j[1:] != j[:-1]])
    fin = np.r_[debut[1:], n]
    ouv = np.full(n, NAN)
    for a_, b_ in zip(debut, fin):
        ouv[a_:b_] = d["o"][a_]
    haut, bas = ouv + 0.6 * (ph - pb), ouv - 0.6 * (ph - pb)
    s = np.zeros(n)
    s[debut] = 2                                                  # décidé à la clôture de la 1re bougie du jour
    return {"sens": s, "entree_l": haut, "entree_c": bas, "stop_l": bas, "stop_c": haut,
            "validite": int(np.max(fin - debut)), "sortie": np.where(fin_du_jour(d), 2, 0)}


def hma(x, n):
    def wma(y, k):
        w = np.arange(1, k + 1)
        out = np.full(len(y), NAN)
        for i in range(k - 1, len(y)):
            out[i] = (y[i - k + 1:i + 1] * w).sum() / w.sum()
        return out
    a = 2 * wma(x, n // 2) - wma(x, n)
    a = np.nan_to_num(a, nan=x[0])
    out = wma(a, int(math.sqrt(n)))
    out[:n] = NAN
    return out


def n05_hull(d):
    """Moyenne de Hull (55) : le prix la franchit → entrée dans ce sens ; toujours en position."""
    c = d["c"]
    m = hma(c, 55)
    return {"sens": np.where(C.croise_haut(c, m), 1, np.where(C.croise_bas(c, m), -1, 0))}


def kama(c, n=10, rapide=2, lent=30):
    out = np.full(len(c), NAN)
    out[n] = c[n]
    fr, le = 2 / (rapide + 1), 2 / (lent + 1)
    for i in range(n + 1, len(c)):
        bruit = np.abs(np.diff(c[i - n:i + 1])).sum()
        er = abs(c[i] - c[i - n]) / bruit if bruit > 0 else 0
        sc = (er * (fr - le) + le) ** 2
        out[i] = out[i - 1] + sc * (c[i] - out[i - 1])
    return out


def n06_kama(d):
    """Moyenne adaptative de Kaufman (10, 2, 30) : pente qui change de signe → entrée dans ce sens ; toujours en
    position."""
    k = kama(d["c"])
    p = np.r_[NAN, np.diff(k)]
    return {"sens": np.where(C.croise_haut(p, 0), 1, np.where(C.croise_bas(p, 0), -1, 0))}


def n07_aroon(d):
    """Aroon (25) : Aroon haut croise Aroon bas → entrée dans ce sens ; toujours en position."""
    h, l = d["h"], d["l"]
    n = 25
    up, dn = np.full(len(h), NAN), np.full(len(h), NAN)
    for i in range(n, len(h)):
        up[i] = 100 * np.argmax(h[i - n:i + 1]) / n                # 100 × (n − bougies depuis le plus haut) / n
        dn[i] = 100 * (np.argmin(l[i - n:i + 1])) / n
    return {"sens": np.where(C.croise_haut(up, dn), 1, np.where(C.croise_bas(up, dn), -1, 0))}


def n08_vortex(d):
    """Vortex (14) : VI+ croise VI− → entrée dans ce sens ; toujours en position."""
    h, l, c = d["h"], d["l"], d["c"]
    vp = np.abs(h - np.r_[l[0], l[:-1]])
    vm = np.abs(l - np.r_[h[0], h[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[c[0], c[:-1]]), np.abs(l - np.r_[c[0], c[:-1]])))
    sp, sm, st = M.sma(vp, 14) * 14, M.sma(vm, 14) * 14, M.sma(tr, 14) * 14
    with np.errstate(divide="ignore", invalid="ignore"):
        vip, vim = sp / st, sm / st
    return {"sens": np.where(C.croise_haut(vip, vim), 1, np.where(C.croise_bas(vip, vim), -1, 0))}


def n09_biseau(d):
    """Biseau (« wedge ») : deux sommets et deux creux tous descendants (biseau descendant) dont les droites se
    rapprochent ; clôture au-dessus de la droite des sommets → achat (stop au dernier creux, objectif 2 R).
    Biseau montant : symétrique à la vente."""
    h, l, c = d["h"], d["l"], d["c"]
    n = len(c)
    sommets, creux = M.pivots(h, l, 5, 5)
    evts = sorted([(k, i, p, 1) for k, i, p in sommets] + [(k, i, p, -1) for k, i, p in creux])
    s, sl, sc = np.zeros(n), np.full(n, NAN), np.full(n, NAN)
    sh, sb, e = [], [], 0
    for j in range(1, n):
        while e < len(evts) and evts[e][0] <= j:
            (sh if evts[e][3] == 1 else sb).append(evts[e][1:3])
            e += 1
        if len(sh) < 2 or len(sb) < 2:
            continue
        (i1, p1), (i2, p2) = sh[-2], sh[-1]
        (k1, q1), (k2, q2) = sb[-2], sb[-1]
        if j - min(i1, k1) > 80:
            continue
        ph_, pb_ = (p2 - p1) / (i2 - i1), (q2 - q1) / (k2 - k1)
        haut = p1 + ph_ * (j - i1)
        bas = q1 + pb_ * (j - k1)
        if haut <= bas:
            continue
        if ph_ < 0 and pb_ < 0 and ph_ < pb_ and c[j] > haut and c[j - 1] <= p1 + ph_ * (j - 1 - i1):
            s[j], sl[j] = 1, q2
        elif ph_ > 0 and pb_ > 0 and pb_ > ph_ and c[j] < bas and c[j - 1] >= q1 + pb_ * (j - 1 - k1):
            s[j], sc[j] = -1, p2
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": c + 2 * (c - sl), "cible_c": c - 2 * (sc - c)}


def n10_achat_du_creux(d):
    """« Buy the dip » : au-dessus de la moyenne de 200 jours, repli d'au moins 2 ATR (20) sous le plus haut des
    20 bougies → achat ; sortie au retour sur ce plus haut ou après 20 bougies ; stop de catastrophe à 5 ATR."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 20)
    m200 = M.sma(c, 200)
    ph = M.plus_haut(h, 20)
    achat = (c > m200) & (ph - c >= 2 * a)
    debut = achat & ~np.r_[False, achat[:-1]]
    return {"sens": np.where(debut, 1, 0), "stop": c - 5 * a, "cible_l": ph, "duree": 20}


def n12_plus_haut_52_semaines(d):
    """Achat au nouveau plus haut de 52 semaines (clôture au-dessus du plus haut des 252 bougies précédentes) ; sortie
    à la clôture sous le plus bas des 20 bougies précédentes ; stop 2 ATR (20). Acheteur seulement."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 20)
    nouveau = c > M.plus_haut(h, 252)
    return {"sens": np.where(nouveau, 1, 0), "stop": c - 2 * a, "sortie": np.where(c < M.plus_bas(l, 20), 1, 0)}



# ============================================================================ R8, 2e passage : Trading Rush, TradingView
# Trading Rush (chaîne YouTube qui teste chaque méthode 100 à 200 fois, textes de ses vidéos sur tradingrush.net) :
# même gabarit que ses essais : filtre EMA 200 (achat au-dessus, vente au-dessous), stop au dernier creux / sommet
# (10 bougies), objectif 1,5 fois le risque. TradingView : les scripts publics les plus suivis (« j'aime »), écrits
# comme leur code publié, avec les réglages par défaut.
def _ema(x, n):
    """EMA qui démarre à la première valeur connue (les NaN de tête ne contaminent pas la suite)."""
    x = np.asarray(x, float)
    out = np.full(len(x), NAN)
    ok = np.flatnonzero(np.isfinite(x))
    if len(ok) and len(x) - ok[0] >= n:
        y = x[ok[0]:].copy()
        for i in range(1, len(y)):
            if not np.isfinite(y[i]):
                y[i] = y[i - 1]
        out[ok[0]:] = M.ema(y, n)
    return out


def _sma(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), NAN)
    ok = np.flatnonzero(np.isfinite(x))
    if len(ok):
        out[ok[0]:] = M.sma(np.nan_to_num(x[ok[0]:], nan=0.0), n)
    return out


def wma(x, n):
    x = np.asarray(x, float)
    w = np.arange(1, n + 1, dtype=float)
    out = np.full(len(x), NAN)
    if len(x) >= n:
        out[n - 1:] = np.convolve(x, w[::-1], "valid") / w.sum()
    return out


def _gabarit_tr(d, achat, vente):
    c = d["c"]
    e = M.ema(c, 200)
    sl, sc = C.swing(d, 10)
    return C.avec_rr(d, achat & (c > e), vente & (c < e), sl, sc, 1.5)


def _premier(x):
    x = np.asarray(x, bool)
    return x & ~np.r_[False, x[:-1]]


def _toujours(achat, vente):
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0))}


def n13_connors_rsi(d):
    """Connors RSI (Connors et Alvarez) : moyenne de RSI(3), RSI(2) de la série des hausses / baisses consécutives
    et rang centile (100) de la variation du jour. Au-dessus de la SMA 200, CRSI < 10 → achat, sortie CRSI > 70 ;
    au-dessous, CRSI > 90 → vente, sortie CRSI < 30."""
    c = d["c"]
    n = len(c)
    serie = np.zeros(n)
    for i in range(1, n):
        if c[i] > c[i - 1]:
            serie[i] = serie[i - 1] + 1 if serie[i - 1] > 0 else 1
        elif c[i] < c[i - 1]:
            serie[i] = serie[i - 1] - 1 if serie[i - 1] < 0 else -1
    var = np.r_[NAN, c[1:] / c[:-1] - 1]
    rang = np.full(n, NAN)
    for i in range(101, n):
        rang[i] = 100 * (var[i - 100:i] < var[i]).mean()
    crsi = (M.rsi(c, 3) + M.rsi(serie - serie.min() + 1, 2) + rang) / 3
    m200 = M.sma(c, 200)
    achat, vente = (c > m200) & (crsi < 10), (c < m200) & (crsi > 90)
    return {"sens": np.where(_premier(achat), 1, np.where(_premier(vente), -1, 0)),
            "sortie": np.where(crsi > 70, 1, np.where(crsi < 30, -1, 0))}


def n14_fisher(d):
    """Transformée de Fisher (Ehlers, 9, version TradingView) : croisement haussier de Fisher au-dessus de sa valeur
    d'avant, sous zéro → achat (gabarit Trading Rush) ; vente symétrique."""
    hl2 = (d["h"] + d["l"]) / 2
    n = len(hl2)
    hh, ll = C.fen_max(hl2, 9), C.fen_min(hl2, 9)
    v, f = np.zeros(n), np.zeros(n)
    for i in range(1, n):
        if not np.isfinite(hh[i]):
            continue
        v[i] = 0.66 * ((hl2[i] - ll[i]) / max(hh[i] - ll[i], 1e-12) - 0.5) + 0.67 * v[i - 1]
        v[i] = min(max(v[i], -0.999), 0.999)
        f[i] = 0.5 * math.log((1 + v[i]) / (1 - v[i])) + 0.5 * f[i - 1]
    f[:9] = NAN
    g = np.r_[NAN, f[:-1]]
    return _gabarit_tr(d, C.croise_haut(f, g) & (f < 0), C.croise_bas(f, g) & (f > 0))


def n15_rvi(d):
    """Indice de vigueur relative (RVI, 10) : RVI croise sa ligne de signal par le haut sous zéro → achat ;
    symétrique (gabarit Trading Rush)."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    co, hl = c - o, h - l
    def sym(x):
        return (x + 2 * np.r_[NAN, x[:-1]] + 2 * np.r_[NAN, NAN, x[:-2]] + np.r_[NAN, NAN, NAN, x[:-3]]) / 6
    num, den = _sma(sym(co), 10), _sma(sym(hl), 10)
    with np.errstate(divide="ignore", invalid="ignore"):
        rvi = np.where(den != 0, num / den, NAN)
    sig = sym(rvi)
    return _gabarit_tr(d, C.croise_haut(rvi, sig) & (rvi < 0), C.croise_bas(rvi, sig) & (rvi > 0))


def n16_trix(d):
    """TRIX (15, signal 9) : croise son signal par le haut sous zéro → achat ; symétrique (gabarit Trading Rush)."""
    e3 = _ema(_ema(_ema(np.log(d["c"]), 15), 15), 15)
    trix = 10_000 * np.r_[NAN, np.diff(e3)]
    sig = _ema(trix, 9)
    return _gabarit_tr(d, C.croise_haut(trix, sig) & (trix < 0), C.croise_bas(trix, sig) & (trix > 0))


def n17_cmo(d):
    """Oscillateur de Chande (CMO, 9) : remonte au-dessus de −50 → achat ; repasse sous +50 → vente (gabarit)."""
    dc = np.diff(d["c"], prepend=d["c"][0])
    su, sd = _sma(np.maximum(dc, 0), 9), _sma(np.maximum(-dc, 0), 9)
    with np.errstate(divide="ignore", invalid="ignore"):
        cmo = 100 * (su - sd) / (su + sd)
    return _gabarit_tr(d, C.croise_haut(cmo, -50), C.croise_bas(cmo, 50))


def n18_tema(d):
    """Croisement TEMA 9 / TEMA 21 (moyennes triples) dans le sens de l'EMA 200 (gabarit Trading Rush)."""
    def tema(x, n):
        e1 = _ema(x, n)
        e2 = _ema(e1, n)
        return 3 * e1 - 3 * e2 + _ema(e2, n)
    a, b = tema(d["c"], 9), tema(d["c"], 21)
    return _gabarit_tr(d, C.croise_haut(a, b), C.croise_bas(a, b))


def mcginley(c, n):
    out = np.full(len(c), NAN)
    e = M.ema(c, n)
    for i in range(len(c)):
        if not np.isfinite(out[i - 1] if i else NAN):
            out[i] = e[i]
        else:
            out[i] = out[i - 1] + (c[i] - out[i - 1]) / (n * (c[i] / out[i - 1]) ** 4)
    return out


def n19_mcginley(d):
    """McGinley Dynamic 9 croise McGinley Dynamic 21 (version Trading Rush), dans le sens de l'EMA 200."""
    a, b = mcginley(d["c"], 9), mcginley(d["c"], 21)
    return _gabarit_tr(d, C.croise_haut(a, b), C.croise_bas(a, b))


def schaff(c, cycle=10, rapide=23, lent=50, f=0.5):
    m = M.ema(c, rapide) - M.ema(c, lent)
    n = len(c)
    f1, pf, f2, stc = np.full(n, NAN), np.full(n, NAN), np.full(n, NAN), np.full(n, NAN)
    v1, v2 = C.fen_min(m, cycle), C.fen_max(m, cycle)
    for i in range(n):
        if not np.isfinite(v1[i]):
            continue
        f1[i] = (m[i] - v1[i]) / (v2[i] - v1[i]) * 100 if v2[i] > v1[i] else (f1[i - 1] if i else 0)
        pf[i] = f1[i] if not np.isfinite(pf[i - 1]) else pf[i - 1] + f * (f1[i] - pf[i - 1])
        a = pf[max(0, i - cycle + 1):i + 1]
        a = a[np.isfinite(a)]
        f2[i] = (pf[i] - a.min()) / (a.max() - a.min()) * 100 if a.max() > a.min() else (
            f2[i - 1] if np.isfinite(f2[i - 1]) else 0)
        stc[i] = f2[i] if not np.isfinite(stc[i - 1]) else stc[i - 1] + f * (f2[i] - stc[i - 1])
    return stc


def n20_schaff(d):
    """Schaff Trend Cycle (10, 23, 50) : remonte au-dessus de 25 → achat ; repasse sous 75 → vente (gabarit)."""
    s = schaff(d["c"])
    return _gabarit_tr(d, C.croise_haut(s, 25), C.croise_bas(s, 75))


def n21_chaikin(d):
    """Chaikin Money Flow (20) : passe au-dessus de zéro → achat ; au-dessous → vente (gabarit). Il faut un volume."""
    h, l, c, v = d["h"], d["l"], d["c"], d["v"]
    with np.errstate(divide="ignore", invalid="ignore"):
        mfm = np.where(h > l, ((c - l) - (h - c)) / (h - l), 0.0)
        cmf = _sma(mfm * v, 20) / _sma(v, 20)
    cmf[~np.isfinite(cmf)] = NAN
    return _gabarit_tr(d, C.croise_haut(cmf, 0), C.croise_bas(cmf, 0))


def n22_awesome(d):
    """Awesome Oscillator (Bill Williams, SMA 5 − SMA 34 du milieu de bougie) : au-dessus de zéro, il repart à la
    hausse (« soucoupe ») → achat ; symétrique (gabarit Trading Rush, qui retient l'entrée au-dessus de zéro)."""
    hl2 = (d["h"] + d["l"]) / 2
    ao = M.sma(hl2, 5) - M.sma(hl2, 34)
    a1, a2 = np.r_[NAN, ao[:-1]], np.r_[NAN, NAN, ao[:-2]]
    return _gabarit_tr(d, (ao > 0) & (ao > a1) & (a1 <= a2), (ao < 0) & (ao < a1) & (a1 >= a2))


def _decale(x, k):
    return np.r_[np.full(k, NAN), x[:-k]]


def n23_alligator_macd(d):
    """Alligator de Bill Williams (lèvres SMMA 5 décalée de 3, dents 8 / 5, mâchoire 13 / 8) dans l'ordre lèvres >
    dents > mâchoire et croisement haussier du MACD → achat ; symétrique (version Trading Rush)."""
    hl2 = (d["h"] + d["l"]) / 2
    levres, dents, machoire = _decale(M.rma(hl2, 5), 3), _decale(M.rma(hl2, 8), 5), _decale(M.rma(hl2, 13), 8)
    m, s = M.macd(d["c"])
    haut = (levres > dents) & (dents > machoire)
    bas = (levres < dents) & (dents < machoire)
    return _gabarit_tr(d, haut & C.croise_haut(m, s), bas & C.croise_bas(m, s))


def fractales(h, l):
    """Dernière fractale haute / basse de Bill Williams (5 bougies), connue 2 bougies après."""
    n = len(h)
    fh, fb = np.full(n, NAN), np.full(n, NAN)
    dh = db = NAN
    for i in range(4, n):
        k = i - 2
        if h[k] == h[k - 2:k + 3].max() and (h[k - 2:k + 3] == h[k]).sum() == 1:
            dh = h[k]
        if l[k] == l[k - 2:k + 3].min() and (l[k - 2:k + 3] == l[k]).sum() == 1:
            db = l[k]
        fh[i], fb[i] = dh, db
    return fh, fb


def n24_fractale(d):
    """Cassure de fractale : clôture au-dessus de la dernière fractale haute → achat (gabarit Trading Rush)."""
    fh, fb = fractales(d["h"], d["l"])
    return _gabarit_tr(d, C.croise_haut(d["c"], fh), C.croise_bas(d["c"], fb))


def choppiness(h, l, c, n=14):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[c[0], c[:-1]]), np.abs(l - np.r_[c[0], c[:-1]])))
    s = M.sma(tr, n) * n
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100 * np.log10(s / (C.fen_max(h, n) - C.fen_min(l, n))) / math.log10(n)


def n25_cassure_sans_chop(d):
    """Cassure de 20 bougies prise seulement si l'indice de « choppiness » (14) de la bougie d'avant est sous 50
    (marché qui tend, le filtre que Trading Rush recommande) ; sortie à la cassure contraire de 10 bougies."""
    h, l, c = d["h"], d["l"], d["c"]
    ch = np.r_[NAN, choppiness(h, l, c)[:-1]]
    achat = (c > M.plus_haut(h, 20)) & (ch < 50)
    vente = (c < M.plus_bas(l, 20)) & (ch < 50)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)),
            "sortie": np.where(c < M.plus_bas(l, 10), 1, np.where(c > M.plus_haut(h, 10), -1, 0))}


def n26_beep_boop(d):
    """« Beep Boop » de Trading Rush (formule exacte réservée à ses abonnés : version décrite dans la vidéo) :
    barre verte = histogramme du MACD positif et en hausse avec le prix au-dessus de l'EMA 50 ; rouge = l'inverse ;
    blanche sinon. Première verte au-dessus de l'EMA 200 → achat ; sortie à la première blanche ; stop au dernier
    creux, objectif 1,5 R."""
    c = d["c"]
    m, s = M.macd(c)
    hist = m - s
    h1 = np.r_[NAN, hist[:-1]]
    e50 = M.ema(c, 50)
    verte = (hist > 0) & (hist > h1) & (c > e50)
    rouge = (hist < 0) & (hist < h1) & (c < e50)
    r = _gabarit_tr(d, _premier(verte), _premier(rouge))
    blanche = ~verte & ~rouge
    r["sortie"] = np.where(blanche, 2, 0)
    return r


def n27_chiffres_ronds(d):
    """Niveaux psychologiques (chiffres ronds à deux chiffres significatifs : 2 000, 2 010… pour l'or ; 1,10, 1,11
    pour l'euro-dollar) : la bougie descend sous le niveau et clôture au-dessus, ouverte au-dessus → achat, stop
    à 0,5 ATR sous le niveau, objectif 1,5 R ; symétrique ; dans le sens de l'EMA 200."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    pas = 10.0 ** (np.floor(np.log10(c)) - 1)
    niv_b = np.ceil(l / pas) * pas                                # premier chiffre rond au-dessus du plus bas
    niv_h = np.floor(h / pas) * pas
    a = M.atr(h, l, c, 14)
    achat = (o > niv_b) & (c > niv_b) & (l < niv_b)
    vente = (o < niv_h) & (c < niv_h) & (h > niv_h)
    e = M.ema(c, 200)
    achat, vente = achat & (c > e), vente & (c < e)
    sl, sc = niv_b - 0.5 * a, niv_h + 0.5 * a
    return C.avec_rr(d, achat, vente, sl, sc, 1.5)


def wavetrend(d, n1=10, n2=21):
    ap = (d["h"] + d["l"] + d["c"]) / 3
    esa = M.ema(ap, n1)
    dd = _ema(np.abs(ap - esa), n1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ci = (ap - esa) / (0.015 * dd)
    ci[~np.isfinite(ci)] = NAN
    wt1 = _ema(ci, n2)
    return wt1, _sma(wt1, 4)


def n28_wavetrend(d):
    """WaveTrend de LazyBear (10, 21) : wt1 croise wt2 par le haut sous −60 → achat ; par le bas au-dessus de 60 →
    vente ; toujours en position (le signal contraire retourne)."""
    w1, w2 = wavetrend(d)
    return _toujours(C.croise_haut(w1, w2) & (w1 < -60), C.croise_bas(w1, w2) & (w1 > 60))


def n29_ut_bot(d):
    """« UT Bot Alerts » (clé 1, ATR 10) : stop suiveur ATR ; clôture qui le franchit → entrée dans ce sens."""
    c = d["c"]
    a = M.atr(d["h"], d["l"], c, 10)
    n = len(c)
    ts = np.full(n, NAN)
    for i in range(1, n):
        if not np.isfinite(a[i]):
            continue
        p = ts[i - 1] if np.isfinite(ts[i - 1]) else c[i]
        if c[i] > p and c[i - 1] > p:
            ts[i] = max(p, c[i] - a[i])
        elif c[i] < p and c[i - 1] < p:
            ts[i] = min(p, c[i] + a[i])
        elif c[i] > p:
            ts[i] = c[i] - a[i]
        else:
            ts[i] = c[i] + a[i]
    return _toujours(C.croise_haut(c, ts), C.croise_bas(c, ts))


def n30_chandelier(d):
    """« Chandelier Exit » (22, 3 ATR, script le plus suivi de TradingView) : stop acheteur = plus haut 22 − 3 ATR
    (qui ne fait que monter), stop vendeur = plus bas 22 + 3 ATR ; la clôture franchit le stop opposé → retournement."""
    h, l, c = d["h"], d["l"], d["c"]
    a = 3 * M.atr(h, l, c, 22)
    n = len(c)
    ls, ss = C.fen_max(c, 22) - a, C.fen_min(c, 22) + a
    sens = np.zeros(n)
    for i in range(1, n):
        if np.isfinite(ls[i - 1]) and c[i - 1] > ls[i - 1]:
            ls[i] = max(ls[i], ls[i - 1])
        if np.isfinite(ss[i - 1]) and c[i - 1] < ss[i - 1]:
            ss[i] = min(ss[i], ss[i - 1])
        sens[i] = 1 if c[i] > ss[i - 1] else (-1 if c[i] < ls[i - 1] else sens[i - 1])
    chg = np.r_[False, sens[1:] != sens[:-1]]
    return _toujours(chg & (sens == 1), chg & (sens == -1))


def n31_filtre_amplitude(d):
    """« Range Filter » (guikroth, période 100, multiple 3) : filtre qui ne bouge que de plus d'une amplitude
    lissée ; prix au-dessus du filtre montant → achat (au changement d'état) ; symétrique."""
    c = d["c"]
    n = len(c)
    amp = _ema(_ema(np.abs(np.r_[NAN, np.diff(c)]), 100), 199) * 3
    f = np.full(n, NAN)
    haut = np.zeros(n)
    bas = np.zeros(n)
    etat = np.zeros(n)
    for i in range(1, n):
        if not np.isfinite(amp[i]):
            continue
        p = f[i - 1] if np.isfinite(f[i - 1]) else c[i]
        f[i] = (p if c[i] - amp[i] < p else c[i] - amp[i]) if c[i] > p else (p if c[i] + amp[i] > p else c[i] + amp[i])
        haut[i] = haut[i - 1] + 1 if f[i] > p else (0 if f[i] < p else haut[i - 1])
        bas[i] = bas[i - 1] + 1 if f[i] < p else (0 if f[i] > p else bas[i - 1])
        lc, sc = (c[i] > f[i]) and haut[i] > 0, (c[i] < f[i]) and bas[i] > 0
        etat[i] = 1 if lc else (-1 if sc else etat[i - 1])
    chg = np.r_[False, etat[1:] != etat[:-1]]
    return _toujours(chg & (etat == 1), chg & (etat == -1))


def n32_qqe(d):
    """QQE (RSI 14 lissé 5, facteur 4,236) : le RSI lissé franchit sa ligne suiveuse → entrée dans ce sens."""
    r = _ema(M.rsi(d["c"], 14), 5)
    dar = _ema(_ema(np.abs(np.r_[NAN, np.diff(r)]), 27), 27) * 4.236
    n = len(r)
    lb, sb, tl = np.full(n, NAN), np.full(n, NAN), np.full(n, NAN)
    tendance = 1
    for i in range(1, n):
        if not (np.isfinite(r[i]) and np.isfinite(dar[i])):
            continue
        nl, ns = r[i] - dar[i], r[i] + dar[i]
        lb[i] = max(lb[i - 1], nl) if np.isfinite(lb[i - 1]) and r[i - 1] > lb[i - 1] and r[i] > lb[i - 1] else nl
        sb[i] = min(sb[i - 1], ns) if np.isfinite(sb[i - 1]) and r[i - 1] < sb[i - 1] and r[i] < sb[i - 1] else ns
        if np.isfinite(sb[i - 1]) and (r[i] - sb[i - 1]) * (r[i - 1] - sb[i - 1]) < 0 and r[i] > sb[i - 1]:
            tendance = 1
        elif np.isfinite(lb[i - 1]) and (r[i] - lb[i - 1]) * (r[i - 1] - lb[i - 1]) < 0 and r[i] < lb[i - 1]:
            tendance = -1
        tl[i] = lb[i] if tendance == 1 else sb[i]
    return _toujours(C.croise_haut(r, tl), C.croise_bas(r, tl))


def n33_ssl(d):
    """Canal SSL (10) : clôture au-dessus de la moyenne des plus hauts → haussier, sous celle des plus bas →
    baissier ; changement d'état → entrée dans ce sens."""
    c = d["c"]
    mh, mb = M.sma(d["h"], 10), M.sma(d["l"], 10)
    n = len(c)
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = 1 if c[i] > mh[i] else (-1 if c[i] < mb[i] else e[i - 1])
    chg = np.r_[False, e[1:] != e[:-1]]
    return _toujours(chg & (e == 1), chg & (e == -1))


def n34_halftrend(d):
    """HalfTrend (everget, amplitude 2) : changement de demi-tendance → entrée dans ce sens ; toujours en position."""
    h, l, c = d["h"], d["l"], d["c"]
    n = len(c)
    amp = 2
    hp, lp = C.fen_max(h, amp), C.fen_min(l, amp)
    hma_, lma_ = M.sma(h, amp), M.sma(l, amp)
    tendance = np.zeros(n)
    t, prochain = 0, 0
    max_bas, min_haut = l[0], h[0]
    for i in range(1, n):
        if not np.isfinite(hp[i]):
            tendance[i] = t
            continue
        if prochain == 1:
            max_bas = max(lp[i], max_bas)
            if hma_[i] < max_bas and c[i] < l[i - 1]:
                t, prochain, min_haut = 1, 0, hp[i]
        else:
            min_haut = min(hp[i], min_haut)
            if lma_[i] > min_haut and c[i] > h[i - 1]:
                t, prochain, max_bas = 0, 1, lp[i]
        tendance[i] = t
    t0 = np.r_[0, tendance[:-1]]
    return _toujours((tendance == 0) & (t0 == 1), (tendance == 1) & (t0 == 0))


def nadaraya_watson(c, h=8.0, fenetre=500):
    w = np.exp(-np.arange(fenetre) ** 2 / (2 * h * h))
    out = np.full(len(c), NAN)
    if len(c) >= fenetre:
        out[fenetre - 1:] = np.convolve(c, w, "valid") / w.sum()
    return out


def n35_nadaraya_watson(d):
    """Enveloppe de Nadaraya-Watson (LuxAlgo, version sans repeinte : estimation au dernier point, noyau gaussien
    h = 8, enveloppe ± 3 × écart absolu moyen) : la clôture passe sous l'enveloppe basse → achat (retour à la
    moyenne), objectif la ligne centrale, stop 2 ATR ; symétrique."""
    c = d["c"]
    est = nadaraya_watson(c)
    mae = _sma(np.abs(c - est), 499) * 3
    haut, bas = est + mae, est - mae
    a = M.atr(d["h"], d["l"], c, 14)
    s = np.where(C.croise_bas(c, bas), 1, np.where(C.croise_haut(c, haut), -1, 0))
    return {"sens": s, "stop_l": c - 2 * a, "stop_c": c + 2 * a, "cible_l": est, "cible_c": est}


def _normalise_cumul(x):
    """(x − plus bas connu) / (plus haut connu − plus bas connu), sur tout le passé (comme le script)."""
    lo = np.fmin.accumulate(np.where(np.isfinite(x), x, np.inf))
    hi = np.fmax.accumulate(np.where(np.isfinite(x), x, -np.inf))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(hi > lo, (x - lo) / (hi - lo), NAN)


def cci(h, l, c, n=20):
    tp = (h + l + c) / 3
    m = M.sma(tp, n)
    dm = np.full(len(c), NAN)
    for i in range(n - 1, len(c)):
        dm[i] = np.abs(tp[i - n + 1:i + 1] - m[i]).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        return (tp - m) / (0.015 * dm)


def n36_lorentzienne(d):
    """« Machine Learning: Lorentzian Classification » (jdehorty), le principe sans les bizarreries du script :
    5 caractéristiques (RSI 14, WaveTrend 10/11, CCI 20, ADX 20, RSI 9, normalisées), 8 plus proches voisins par la
    distance de Lorentz Σ log(1 + |écart|) parmi les 2 000 bougies passées (une sur quatre), étiquette = sens des
    4 bougies suivantes (connue 4 bougies après) ; filtres par défaut du script (volatilité, régime, noyau
    quadratique rationnel) ; entrée au changement de signal, sortie après 4 bougies."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    n = len(c)
    w1, w2 = wavetrend(d, 10, 11)
    f = np.vstack([M.rsi(c, 14) / 100, _normalise_cumul(w1 - w2), _normalise_cumul(cci(h, l, c, 20)),
                   M.adx(h, l, c, 20)[0] / 100, M.rsi(c, 9) / 100]).T
    etiq = np.full(n, NAN)
    etiq[:-4] = np.sign(c[4:] - c[:-4])
    pred = np.zeros(n)
    for i in range(2000, n):
        j = np.arange(i - 1999, i - 3, 4)                          # étiquettes connues à la clôture i
        fi = f[i]
        if not np.all(np.isfinite(fi)):
            continue
        fj = f[j]
        ok = np.all(np.isfinite(fj), axis=1)
        if ok.sum() < 8:
            continue
        dist = np.log1p(np.abs(fj[ok] - fi)).sum(axis=1)
        proches = np.argpartition(dist, 8)[:8]
        pred[i] = etiq[j[ok][proches]].sum()
    volat = M.atr(h, l, c, 1) > M.atr(h, l, c, 10)
    src = (o + h + l + c) / 4
    v1, v2, klmf = np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(1, n):
        v1[i] = 0.2 * (src[i] - src[i - 1]) + 0.8 * v1[i - 1]
        v2[i] = 0.1 * (h[i] - l[i]) + 0.8 * v2[i - 1]
        om = abs(v1[i] / v2[i]) if v2[i] else 0.0
        al = (-om ** 2 + math.sqrt(om ** 4 + 16 * om ** 2)) / 8
        klmf[i] = al * src[i] + (1 - al) * klmf[i - 1]
    pente = np.abs(np.r_[0, np.diff(klmf)])
    moy = M.ema(pente, 200)
    with np.errstate(divide="ignore", invalid="ignore"):
        regime = (pente - moy) / moy >= -0.1
    poids = (1 + np.arange(27) ** 2 / (2 * 64 * 8)) ** -8.0
    noyau = np.full(n, NAN)
    noyau[26:] = np.convolve(c, poids, "valid") / poids.sum()
    hausse, baisse = noyau > np.r_[NAN, noyau[:-1]], noyau < np.r_[NAN, noyau[:-1]]
    signal = np.zeros(n)
    filtre = volat & regime
    for i in range(1, n):
        signal[i] = 1 if (pred[i] > 0 and filtre[i]) else (-1 if (pred[i] < 0 and filtre[i]) else signal[i - 1])
    nouveau = np.r_[False, signal[1:] != signal[:-1]]
    return {"sens": np.where(nouveau & (signal == 1) & hausse, 1, np.where(nouveau & (signal == -1) & baisse, -1, 0)),
            "duree": 4}


def n37_vix_fix(d):
    """« Williams Vix Fix » (Larry Williams, script CM) : (plus haute clôture 22 − plus bas) / plus haute clôture ;
    au-dessus de sa Bollinger haute (20, 2) ou de 85 % de son plus haut de 50 bougies → creux de peur : achat,
    sortie après 10 bougies, stop de catastrophe 3 ATR. Acheteur seulement."""
    c, l = d["c"], d["l"]
    hc = C.fen_max(c, 22)
    wvf = (hc - l) / hc * 100
    m = _sma(wvf, 20)
    sd = np.full(len(c), NAN)
    for i in range(41, len(c)):
        sd[i] = wvf[i - 19:i + 1].std()
    sig = (wvf >= m + 2 * sd) | (wvf >= 0.85 * C.fen_max(wvf, 50))
    a = M.atr(d["h"], l, c, 14)
    return {"sens": np.where(_premier(sig), 1, 0), "stop": c - 3 * a, "duree": 10}


def n38_bande_de_bruit(d, fuseau="utc", fin_jour=1440):
    """Bande de bruit (Zarattini, Aziz et Barbon 2024, « Beat the Market », momentum dans la journée) : bruit à
    chaque heure = moyenne sur 14 jours de |cours / ouverture du jour − 1| à la même heure ; bande haute =
    max(ouverture, clôture de la veille) × (1 + bruit), basse symétrique. Aux points de contrôle (chaque demi-heure),
    clôture au-dessus de la bande haute → achat, sous la basse → vente ; sortie quand la clôture repasse sous
    max(bande, VWAP) (au-dessus de min(bande, VWAP) pour une vente), et en fin de journée.
    fuseau « ny » et fin_jour (minute de New York) : séance d'actions seulement, données filtrées avant."""
    mn, j = (C.minutes_ny if fuseau == "ny" else C.minutes_utc)(d["ts"])
    c, o = d["c"], d["o"]
    n = len(c)
    debut = np.flatnonzero(np.r_[True, j[1:] != j[:-1]])
    fin = np.r_[debut[1:], n]
    ouv, veille = np.full(n, NAN), np.full(n, NAN)
    for k, (a_, b_) in enumerate(zip(debut, fin)):
        ouv[a_:b_] = o[a_]
        if k:
            veille[a_:b_] = c[debut[k] - 1]
    mouv = np.abs(c / ouv - 1)
    bruit = np.full(n, NAN)
    hist = {}
    for k, (a_, b_) in enumerate(zip(debut, fin)):
        for i in range(a_, b_):
            passe = hist.get(mn[i], [])
            if len(passe) >= 14:
                bruit[i] = np.mean(passe[-14:])
        for i in range(a_, b_):
            hist.setdefault(mn[i], []).append(mouv[i])
    haut = np.fmax(ouv, veille) * (1 + bruit)
    bas = np.fmin(ouv, veille) * (1 - bruit)
    tp = (d["h"] + d["l"] + c) / 3
    v = np.where(d["v"] > 0, d["v"], 1e-12)
    vw = np.empty(n)
    for a_, b_ in zip(debut, fin):
        vw[a_:b_] = np.cumsum(tp[a_:b_] * v[a_:b_]) / np.cumsum(v[a_:b_])
    pas = _pas_min(d)
    controle = (mn + pas) // 30 > mn // 30                        # la bougie se ferme sur une heure ou une demie
    dernier = fin_du_jour(d, fin_jour, fuseau)
    achat = controle & (c > haut) & ~dernier
    vente = controle & (c < bas) & ~dernier
    sortie = np.where(dernier, 2, np.where(controle & (c < np.fmax(haut, vw)), 1,
                                           np.where(controle & (c > np.fmin(bas, vw)), -1, 0)))
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "sortie": sortie}


def n39_stoch_rsi(d):
    """RSI stochastique (14, 14, 3, 3) : %K croise %D par le haut sous 20 → achat ; par le bas au-dessus de 80 →
    vente (gabarit Trading Rush)."""
    r = M.rsi(d["c"], 14)
    lo, hi = C.fen_min(r, 14), C.fen_max(r, 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        st = np.where(hi > lo, 100 * (r - lo) / (hi - lo), NAN)
    k = _sma(st, 3)
    dd = _sma(k, 3)
    return _gabarit_tr(d, C.croise_haut(k, dd) & (k < 20), C.croise_bas(k, dd) & (k > 80))


def n40_canal_moyennes(d):
    """Canal de moyennes (SMA 20 des plus hauts et des plus bas, Trading Rush, 73 % de gagnants annoncés en marché
    très porteur) : première bougie ouverte ET clôturée au-dessus du canal → achat ; symétrique (gabarit)."""
    o, c = d["o"], d["c"]
    mh, mb = M.sma(d["h"], 20), M.sma(d["l"], 20)
    return _gabarit_tr(d, _premier((o > mh) & (c > mh)), _premier((o < mb) & (c < mb)))


def _suivi_moyenne(m, ecart):
    """Stop suiveur autour d'une moyenne (OTT, PMax) : sens qui change quand la moyenne franchit le stop d'avant."""
    n = len(m)
    ls, ss, sens, out = np.full(n, NAN), np.full(n, NAN), np.ones(n), np.full(n, NAN)
    for i in range(n):
        if not (np.isfinite(m[i]) and np.isfinite(ecart[i])):
            continue
        l0, s0 = m[i] - ecart[i], m[i] + ecart[i]
        lp = ls[i - 1] if i and np.isfinite(ls[i - 1]) else l0
        sp = ss[i - 1] if i and np.isfinite(ss[i - 1]) else s0
        ls[i] = max(l0, lp) if m[i] > lp else l0
        ss[i] = min(s0, sp) if m[i] < sp else s0
        s = sens[i - 1] if i else 1
        sens[i] = 1 if (s == -1 and m[i] > sp) else (-1 if (s == 1 and m[i] < lp) else s)
        out[i] = ls[i] if sens[i] == 1 else ss[i]
    return out


def n41_ott(d):
    """Optimized Trend Tracker (Anıl Özekşi, script de KivancOzbilgic : moyenne VAR 2 de Chande, 1,4 %) : la moyenne
    franchit l'OTT d'il y a 2 bougies → entrée dans ce sens ; toujours en position."""
    c = d["c"]
    dc = np.r_[0.0, np.diff(c)]
    su, sd = _sma(np.maximum(dc, 0), 9) * 9, _sma(np.maximum(-dc, 0), 9) * 9
    with np.errstate(divide="ignore", invalid="ignore"):
        cmo = np.nan_to_num((su - sd) / (su + sd))
    a = 2 / 3
    var = np.zeros(len(c))
    for i in range(1, len(c)):
        var[i] = a * abs(cmo[i]) * c[i] + (1 - a * abs(cmo[i])) * var[i - 1]
    var[:30] = NAN
    mt = _suivi_moyenne(var, var * 0.014)
    ott = np.where(var > mt, mt * (200 + 1.4) / 200, mt * (200 - 1.4) / 200)
    o2 = _decale(ott, 2)
    return _toujours(C.croise_haut(var, o2), C.croise_bas(var, o2))


def n42_pmax(d):
    """Profit Maximizer (PMax, KivancOzbilgic : EMA 10, 3 ATR 10) : l'EMA franchit le PMax → entrée dans ce sens."""
    c = d["c"]
    m = M.ema(c, 10)
    pm = _suivi_moyenne(m, 3 * M.atr(d["h"], d["l"], c, 10))
    return _toujours(C.croise_haut(m, pm), C.croise_bas(m, pm))


def n43_supertrend_ia(d):
    """« SuperTrend AI (Clustering) » de LuxAlgo : 9 SuperTrend (facteurs 1 à 5, ATR 10) notés par leur performance
    lissée ; k-moyennes en 3 groupes sur ces notes ; le facteur moyen du meilleur groupe donne le SuperTrend suivi ;
    changement de sens → entrée dans ce sens. Calculé à chaque bougie avec le seul passé."""
    h, l, c = d["h"], d["l"], d["c"]
    n = len(c)
    hl2 = (h + l) / 2
    a = M.atr(h, l, c, 10)
    fac = np.arange(1.0, 5.01, 0.5)
    k = len(fac)
    haut, bas, tend, sortie, perf = (np.full(k, NAN), np.full(k, NAN), np.zeros(k), np.full(k, NAN), np.zeros(k))
    alpha = 2 / 11
    cible = np.full(n, NAN)
    for i in range(1, n):
        if not np.isfinite(a[i]):
            continue
        up, dn = hl2[i] + a[i] * fac, hl2[i] - a[i] * fac
        tend = np.where(c[i] > haut, 1, np.where(c[i] < bas, 0, tend))
        haut = np.where(np.isfinite(haut) & (c[i - 1] < haut), np.fmin(up, haut), up)
        bas = np.where(np.isfinite(bas) & (c[i - 1] > bas), np.fmax(dn, bas), dn)
        diff = np.nan_to_num(np.sign(c[i - 1] - sortie))
        perf += alpha * ((c[i] - c[i - 1]) * diff - perf)
        sortie = np.where(tend == 1, bas, haut)
        cen = np.percentile(perf, [25, 50, 75])
        for _ in range(100):
            g = np.argmin(np.abs(perf[:, None] - cen[None, :]), axis=1)
            nouv = np.array([perf[g == j].mean() if (g == j).any() else cen[j] for j in range(3)])
            if np.allclose(nouv, cen):
                break
            cen = nouv
        meilleur = np.argmax(cen)
        cible[i] = fac[g == meilleur].mean() if (g == meilleur).any() else fac.mean()
    up, dn = hl2 + a * cible, hl2 - a * cible
    hh, bb, os_ = np.full(n, NAN), np.full(n, NAN), np.zeros(n)
    for i in range(1, n):
        if not np.isfinite(up[i]):
            continue
        hh[i] = min(up[i], hh[i - 1]) if np.isfinite(hh[i - 1]) and c[i - 1] < hh[i - 1] else up[i]
        bb[i] = max(dn[i], bb[i - 1]) if np.isfinite(bb[i - 1]) and c[i - 1] > bb[i - 1] else dn[i]
        os_[i] = 1 if c[i] > hh[i] else (0 if c[i] < bb[i] else os_[i - 1])
    o1 = np.r_[0, os_[:-1]]
    return _toujours(os_ > o1, os_ < o1)


def n44_raschke_3_10(d):
    """Oscillateur 3-10 de Linda Raschke (SMA 3 − SMA 10, ligne lente = SMA 16 de l'oscillateur) : la ligne rapide
    recroise la lente par le haut alors que la lente monte → achat ; symétrique ; stop au dernier creux / sommet
    (10 bougies) ; sortie après 5 bougies (ses trades durent quelques jours)."""
    c = d["c"]
    rapide = M.sma(c, 3) - M.sma(c, 10)
    lente = _sma(rapide, 16)
    l1 = np.r_[NAN, lente[:-1]]
    sl, sc = C.swing(d, 10)
    s = np.where(C.croise_haut(rapide, lente) & (lente > l1), 1,
                 np.where(C.croise_bas(rapide, lente) & (lente < l1), -1, 0))
    return {"sens": s, "stop_l": sl, "stop_c": sc, "duree": 5}


def n45_raschke_holy_grail(d):
    """« Holy Grail » de Linda Raschke (Connors et Raschke, Street Smarts, 1995) : ADX (14) au-dessus de 30 et en
    hausse, +DI au-dessus de −DI ; le plus bas touche l'EMA 20 → ordre d'achat au-dessus du plus haut de cette bougie
    (valable 1 bougie), stop sous son plus bas, objectif le plus haut des 20 bougies précédentes (à défaut 2 R) ;
    symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    a, pdi, ndi = M.adx(h, l, c, 14)
    fort = (a > 30) & (a > np.r_[NAN, a[:-1]])
    e = M.ema(c, 20)
    achat = fort & (pdi > ndi) & (l <= e) & (h > e)
    vente = fort & (ndi > pdi) & (h >= e) & (l < e)
    ph, pb = M.plus_haut(h, 20), M.plus_bas(l, 20)
    cible_l = np.where(ph > h, ph, h + 2 * (h - l))
    cible_c = np.where(pb < l, pb, l - 2 * (h - l))
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "entree_l": h, "entree_c": l, "stop_l": l,
            "stop_c": h, "cible_l": cible_l, "cible_c": cible_c, "validite": 1}


REGLES = {
    "N01 carré de 9 de Gann": (n01_gann_carre_9, ("15m", "1h")),
    "N02 pivots Camarilla": (n02_camarilla, ("15m", "1h")),
    "N03 TTM Squeeze": (n03_ttm_squeeze, ("15m", "1h", "1j")),
    "N04 cassure de volatilité de Larry Williams": (n04_cassure_williams, ("1j",)),
    "N04b cassure de Williams dans la journée": (n04b_williams_intraday, ("15m", "1h")),
    "N05 moyenne de Hull 55": (n05_hull, ("15m", "1h", "1j")),
    "N06 moyenne adaptative de Kaufman": (n06_kama, ("15m", "1h", "1j")),
    "N07 Aroon 25": (n07_aroon, ("15m", "1h", "1j")),
    "N08 Vortex 14": (n08_vortex, ("15m", "1h", "1j")),
    "N09 biseau (wedge)": (n09_biseau, ("15m", "1h", "1j")),
    "N10 achat du creux (buy the dip)": (n10_achat_du_creux, ("1h", "1j")),
    "N12 nouveau plus haut de 52 semaines": (n12_plus_haut_52_semaines, ("1j",)),
    "N13 Connors RSI": (n13_connors_rsi, ("1h", "1j")),
    "N14 transformée de Fisher": (n14_fisher, ("15m", "1h", "1j")),
    "N15 RVI (vigueur relative)": (n15_rvi, ("15m", "1h", "1j")),
    "N16 TRIX": (n16_trix, ("15m", "1h", "1j")),
    "N17 oscillateur de Chande (CMO)": (n17_cmo, ("15m", "1h", "1j")),
    "N18 croisement TEMA 9 / 21": (n18_tema, ("15m", "1h", "1j")),
    "N19 McGinley Dynamic 9 / 21": (n19_mcginley, ("15m", "1h", "1j")),
    "N20 Schaff Trend Cycle": (n20_schaff, ("15m", "1h", "1j")),
    "N21 Chaikin Money Flow": (n21_chaikin, ("15m", "1h", "1j")),
    "N22 Awesome Oscillator (soucoupe)": (n22_awesome, ("15m", "1h", "1j")),
    "N23 Alligator + MACD": (n23_alligator_macd, ("15m", "1h", "1j")),
    "N24 cassure de fractale": (n24_fractale, ("15m", "1h", "1j")),
    "N25 cassure filtrée par la choppiness": (n25_cassure_sans_chop, ("15m", "1h", "1j")),
    "N26 Beep Boop (Trading Rush)": (n26_beep_boop, ("15m", "1h", "1j")),
    "N27 chiffres ronds (niveaux psychologiques)": (n27_chiffres_ronds, ("15m", "1h", "1j")),
    "N28 WaveTrend (LazyBear)": (n28_wavetrend, ("15m", "1h", "1j")),
    "N29 UT Bot": (n29_ut_bot, ("15m", "1h", "1j")),
    "N30 Chandelier Exit": (n30_chandelier, ("15m", "1h", "1j")),
    "N31 Range Filter": (n31_filtre_amplitude, ("15m", "1h", "1j")),
    "N32 QQE": (n32_qqe, ("15m", "1h", "1j")),
    "N33 canal SSL": (n33_ssl, ("15m", "1h", "1j")),
    "N34 HalfTrend": (n34_halftrend, ("15m", "1h", "1j")),
    "N35 enveloppe de Nadaraya-Watson": (n35_nadaraya_watson, ("15m", "1h", "1j")),
    "N36 classification lorentzienne (k plus proches voisins)": (n36_lorentzienne, ("1h", "1j")),
    "N37 Williams Vix Fix": (n37_vix_fix, ("1h", "1j")),
    "N38 bande de bruit (Zarattini)": (n38_bande_de_bruit, ("15m", "1h")),
    "N39 RSI stochastique": (n39_stoch_rsi, ("15m", "1h", "1j")),
    "N40 canal de moyennes (Trading Rush)": (n40_canal_moyennes, ("15m", "1h", "1j")),
    "N41 Optimized Trend Tracker (OTT)": (n41_ott, ("15m", "1h", "1j")),
    "N42 Profit Maximizer (PMax)": (n42_pmax, ("15m", "1h", "1j")),
    "N43 SuperTrend IA (k-moyennes, LuxAlgo)": (n43_supertrend_ia, ("1h", "1j")),
    "N44 oscillateur 3-10 de Raschke": (n44_raschke_3_10, ("15m", "1h", "1j")),
    "N45 Holy Grail de Raschke": (n45_raschke_holy_grail, ("15m", "1h", "1j")),
}
