"""R7 (25/10/2026) : moteur général pour tester les règles des vidéos et des fiches restées sans test.

Conventions, fixées AVANT les tests et les mêmes pour toutes les règles :
- décision à la clôture de la bougie i, exécution à l'OUVERTURE de la bougie i+1 (jamais au cours qui a décidé) ;
- achat (+1) ou vente à découvert (−1) ; une position à la fois par marché ;
- stop et objectif en prix, calculés à la décision ; touchés dans une bougie : on prend le STOP d'abord si les deux
  sont possibles (prudent) ; un trou de cotation au-delà d'un niveau est exécuté à l'ouverture ;
- taille : le stop risque `RISQUE` (0,5 %) du capital, notionnel plafonné à `LEVIER_MAX` (5 fois) ; sans stop, la
  taille vise 10 % de volatilité annuelle ;
- frais : écart aller-retour en part du notionnel (moitié à l'entrée, moitié à la sortie) ; financement des positions
  gardées d'un jour à l'autre (3 %/an, achat comme vente : prudent) ;
- résultat : rendement de chaque bougie en part du capital (non composé), regroupé par jour.
Jugement (le permis de l'armée) : Sharpe > 0 sur chaque moitié ET meilleur que « toujours acheter » le même panier
sur chaque moitié ; au moins 30 trades par moitié. Contrôle en plus : la même règle avec des ENTRÉES AU HASARD (mêmes
sorties, même nombre de trades, même sens) ; un signal qui ne fait pas mieux que 95 % des tirages n'apporte rien.
"""
from __future__ import annotations

import math

import numpy as np

RISQUE = 0.005
LEVIER_MAX = 5.0
VOL_CIBLE = 0.10
FINANCEMENT = 0.03
MIN_TRADES = 30
JOUR_MS = 86_400_000


# ============================================================================ indicateurs (sans données du futur)
def ema(x, n):
    x = np.asarray(x, dtype=float)
    out = np.empty(len(x))
    a = 2 / (n + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    out[:n - 1] = np.nan
    return out


def sma(x, n):
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def rma(x, n):                                                # moyenne de Wilder
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    debut = np.argmax(np.isfinite(x))
    if len(x) - debut < n:
        return out
    out[debut + n - 1] = np.nanmean(x[debut:debut + n])
    for i in range(debut + n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def atr(h, l, c, n=14):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    return rma(tr, n)


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    g, p = rma(np.maximum(d, 0), n), rma(np.maximum(-d, 0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100 - 100 / (1 + g / p)


def macd(c, rapide=12, lent=26, signal=9):
    m = ema(c, rapide) - ema(c, lent)
    s = np.full(len(c), np.nan)
    ok = np.isfinite(m)
    if ok.sum() > signal:
        s[ok] = ema(m[ok], signal)
    return m, s


def stochastique(h, l, c, k=14, d=3, lissage=3):
    bas = np.array([l[max(0, i - k + 1):i + 1].min() for i in range(len(c))])
    haut = np.array([h[max(0, i - k + 1):i + 1].max() for i in range(len(c))])
    with np.errstate(divide="ignore", invalid="ignore"):
        brut = 100 * (c - bas) / (haut - bas)
    brut[:k - 1] = np.nan
    kk = sma(np.nan_to_num(brut, nan=50.0), lissage)
    kk[:k + lissage - 2] = np.nan
    return kk, sma(np.nan_to_num(kk, nan=50.0), d)


def plus_haut(x, n):
    """Plus haut des n bougies PRÉCÉDENTES (hors bougie du jour)."""
    out = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        out[i] = x[i - n:i].max()
    return out


def plus_bas(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        out[i] = x[i - n:i].min()
    return out


def bollinger(c, n=20, k=2.0):
    m = sma(c, n)
    s = np.full(len(c), np.nan)
    for i in range(n - 1, len(c)):
        s[i] = c[i - n + 1:i + 1].std()
    return m, m + k * s, m - k * s


def adx(h, l, c, n=14):
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(h, l, c, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi, ndi = 100 * rma(pdm, n) / a, 100 * rma(ndm, n) / a
        dx = 100 * np.abs(pdi - ndi) / (pdi + ndi)
    return rma(np.nan_to_num(dx), n), pdi, ndi


def supertrend(h, l, c, n=10, k=3.0):
    a = atr(h, l, c, n)
    mid = (h + l) / 2
    haut, bas = mid + k * a, mid - k * a
    sens = np.zeros(len(c))
    fh, fb = haut.copy(), bas.copy()
    for i in range(1, len(c)):
        if not np.isfinite(a[i]):
            continue
        fh[i] = haut[i] if (haut[i] < fh[i - 1] or c[i - 1] > fh[i - 1] or not np.isfinite(fh[i - 1])) else fh[i - 1]
        fb[i] = bas[i] if (bas[i] > fb[i - 1] or c[i - 1] < fb[i - 1] or not np.isfinite(fb[i - 1])) else fb[i - 1]
        if sens[i - 1] >= 0:
            sens[i] = -1 if c[i] < fb[i] else 1
        else:
            sens[i] = 1 if c[i] > fh[i] else -1
    return sens, fh, fb


def heikin_ashi(o, h, l, c):
    hc = (o + h + l + c) / 4
    ho = np.empty(len(c))
    ho[0] = (o[0] + c[0]) / 2
    for i in range(1, len(c)):
        ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    return ho, np.maximum(h, np.maximum(ho, hc)), np.minimum(l, np.minimum(ho, hc)), hc


def pivots(h, l, gauche=5, droite=5):
    """Sommets et creux confirmés : connus seulement `droite` bougies APRÈS (pas de futur) -> listes (i_connu, i, prix)."""
    sommets, creux = [], []
    for i in range(gauche, len(h) - droite):
        fen_h, fen_l = h[i - gauche:i + droite + 1], l[i - gauche:i + droite + 1]
        if h[i] == fen_h.max() and (fen_h == h[i]).sum() == 1:
            sommets.append((i + droite, i, h[i]))
        if l[i] == fen_l.min() and (fen_l == l[i]).sum() == 1:
            creux.append((i + droite, i, l[i]))
    return sommets, creux


# ============================================================================ moteur
def _niveau(regle, cle, s, i):
    """Niveau (stop ou cible) pour une entrée de sens s décidée à la clôture i : tableau commun, ou par sens."""
    par_sens = regle.get(cle + ("_l" if s > 0 else "_c"))
    if par_sens is not None:
        return float(par_sens[i])
    commun = regle.get(cle)
    return float(commun[i]) if commun is not None else float("nan")


def backtest(o, h, l, c, regle, cout, jours=None, risque=RISQUE, levier_max=LEVIER_MAX, financement=FINANCEMENT,
             bougies_par_an=252, entrees_imposees=None, chemin="prudent"):
    """regle : dict de tableaux de la longueur des bougies, décidés à la CLÔTURE i :
      sens (+1, −1, 0 ; 2 = deux ordres stop opposés, le premier touché annule l'autre) : ouvrir à l'ouverture i+1 ;
      stop / cible : niveaux de prix (nan = aucun), communs ou par sens (stop_l, stop_c, cible_l, cible_c) ;
      sortie (+1 / −1 / 2, 0) : fermer à l'ouverture i+1 une position achetée (+1), vendue (−1) ou toute position (2) ;
      entree (ou entree_l / entree_c) : ordre stop d'entrée à ce prix, valable `validite` bougies (1 par défaut) ;
      duree : nombre maximal de bougies en position (0 = sans limite) ;
      suivi_l / suivi_c : sortie suiveuse (niveau connu à la clôture j−1, touché pendant la bougie j), qui ne fait
      que resserrer le stop.
    Un signal contraire ferme la position et la retourne. jours : jour (entier) de chaque bougie (financement).
    entrees_imposees : liste (i, sens) qui remplace les entrées de la règle (contrôle au hasard, mêmes sorties).
    chemin : stop ET objectif touchés dans la même bougie : « prudent » = le stop d'abord ; « ohlc » = l'ordre probable
      de la bougie (haussière : ouverture → bas → haut ; baissière : ouverture → haut → bas), pour mesurer l'effet.
    -> (rendements par bougie en part du capital, trades [(i_entree, i_sortie, sens, R, net)])."""
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    n = len(c)
    sens = np.asarray(regle["sens"], dtype=float)
    if entrees_imposees is not None:
        sens = np.zeros(n)
        for i, s in entrees_imposees:
            sens[i] = s
    sortie = regle.get("sortie")
    sortie = np.zeros(n) if sortie is None else np.asarray(sortie, dtype=float)
    duree = int(regle.get("duree", 0) or 0)
    jour = np.asarray(jours) if jours is not None else None
    vol = _vol_glissante(c, bougies_par_an)
    rend = np.zeros(n)
    trades = []
    signaux = np.flatnonzero(sens[:n - 1])
    k = 0                                                         # prochain signal à examiner
    i = 0
    while k < len(signaux):
        d = signaux[k]
        if d < i:
            k += 1
            continue
        s = int(sens[d])
        if s == 2:                                                # deux ordres stop, le premier touché annule l'autre
            haut, bas = _niveau(regle, "entree", 1, d), _niveau(regle, "entree", -1, d)
            ie = None
            for f in range(d + 1, min(n, d + 1 + int(regle.get("validite", 1)))):
                ha, ba = h[f] >= haut, l[f] <= bas
                if ha and ba:                                     # les deux dans la même bougie : le plus proche de
                    s = 1 if haut - o[f] <= o[f] - bas else -1    # l'ouverture est supposé touché le premier
                elif ha or ba:
                    s = 1 if ha else -1
                if ha or ba:
                    ie, e = f, (max(o[f], haut) if s > 0 else min(o[f], bas))
                    break
            if ie is None:
                k += 1
                i = d + 1
                continue
        sl, tp = _niveau(regle, "stop", s, d), _niveau(regle, "cible", s, d)
        niveau = _niveau(regle, "entree", s, d) if int(sens[d]) != 2 else float("nan")
        if int(sens[d]) != 2:
            ie, e = d + 1, o[d + 1]
        if np.isfinite(niveau):
            ie = None
            for f in range(d + 1, min(n, d + 1 + int(regle.get("validite", 1)))):
                if s > 0 and h[f] >= niveau:
                    ie, e = f, max(o[f], niveau)
                elif s < 0 and l[f] <= niveau:
                    ie, e = f, min(o[f], niveau)
                if ie is not None:
                    break
            if ie is None:                                        # pas de cassure : ordre annulé
                k += 1
                i = d + 1
                continue
        mauvais_stop = np.isfinite(sl) and not ((s > 0 and sl < e) or (s < 0 and sl > e))
        mauvaise_cible = np.isfinite(tp) and not ((s > 0 and tp > e) or (s < 0 and tp < e))
        if mauvais_stop or mauvaise_cible:
            k += 1                                                # niveau déjà dépassé à l'ouverture : pas d'ordre
            i = d + 1
            continue
        if np.isfinite(sl):
            risque_px = abs(e - sl)
            w = min(risque / (risque_px / e), levier_max)
        else:
            v = vol[d]
            if not (np.isfinite(v) and v > 0):
                k += 1
                continue
            w = min(VOL_CIBLE / v, levier_max)
            risque_px = e * 2 * v / math.sqrt(bougies_par_an)
        ref, net = e, -w * cout / 2
        rend[ie] -= w * cout / 2
        sortie_px, i_s, retour = None, None, None
        j = ie
        suivi = regle.get("suivi_l" if s > 0 else "suivi_c")         # sortie suiveuse connue à la clôture d'avant
        while j < n:
            if suivi is not None and j > ie and np.isfinite(suivi[j - 1]):
                sl = max(sl, suivi[j - 1]) if s > 0 and np.isfinite(sl) else (
                    min(sl, suivi[j - 1]) if s < 0 and np.isfinite(sl) else suivi[j - 1])
            if s > 0:
                t_sl, t_tp = np.isfinite(sl) and l[j] <= sl, np.isfinite(tp) and h[j] >= tp
            else:
                t_sl, t_tp = np.isfinite(sl) and h[j] >= sl, np.isfinite(tp) and l[j] <= tp
            if t_sl and t_tp and chemin == "ohlc":
                ouv_sl = j > ie and ((s > 0 and o[j] <= sl) or (s < 0 and o[j] >= sl))
                ouv_tp = j > ie and ((s > 0 and o[j] >= tp) or (s < 0 and o[j] <= tp))
                if ouv_sl or ouv_tp:                              # ouverture déjà au-delà d'un niveau : c'est lui
                    t_tp, t_sl = (False, True) if ouv_sl else (True, False)
                elif (s > 0) == (c[j] >= o[j]):                   # bougie haussière : le bas vient d'abord
                    t_tp = False
                else:
                    t_sl = False
            if t_sl:
                sortie_px = (min(o[j], sl) if s > 0 else max(o[j], sl)) if j > ie else sl
            elif t_tp:
                sortie_px = (max(o[j], tp) if s > 0 else min(o[j], tp)) if j > ie else tp
            if sortie_px is not None:
                i_s = j
                break
            r = w * s * (c[j] / ref - 1)
            if jour is not None and j + 1 < n and jour[j + 1] != jour[j]:
                r -= w * financement / 365 * (jour[j + 1] - jour[j])
            rend[j] += r
            net += r
            ref = c[j]
            if j + 1 >= n:
                i_s, sortie_px = j, c[j]
                break
            if sens[j] == -s:                                     # signal contraire : sortie et retournement
                retour = j
            if retour is not None or (duree and j - ie + 1 >= duree) or sortie[j] in (s, 2):
                i_s, sortie_px = j + 1, o[j + 1]
                break
            j += 1
        r = w * s * (sortie_px / ref - 1) - w * cout / 2
        rend[i_s] += r
        net += r
        trades.append((ie, i_s, s, (s * (sortie_px - e) - cout * e) / risque_px if risque_px else 0.0, net))
        i = i_s
        if retour is not None:                                    # le signal contraire devient l'entrée suivante
            k = int(np.searchsorted(signaux, retour))
            i = retour
        else:
            k = int(np.searchsorted(signaux, i_s))
    return rend, trades


def _vol_glissante(c, bougies_par_an, n=None):
    n = n or max(20, bougies_par_an // 12)
    r = np.diff(np.log(c), prepend=np.log(c[0]))
    out = np.full(len(c), np.nan)
    cs, cs2 = np.cumsum(r), np.cumsum(r * r)
    for i in range(n, len(c)):
        s1, s2 = cs[i] - cs[i - n], cs2[i] - cs2[i - n]
        var = max(s2 / n - (s1 / n) ** 2, 0.0)
        out[i] = math.sqrt(var * bougies_par_an)
    return out


# ============================================================================ jugement
def par_jour(ts_ms, rend):
    j = np.asarray(ts_ms, dtype=np.int64) // JOUR_MS
    u, inv = np.unique(j, return_inverse=True)
    out = np.zeros(len(u))
    np.add.at(out, inv, rend)
    return u, out


def sharpe(x, par_an=252):
    x = np.asarray(x, dtype=float)
    if len(x) < 20 or x.std() == 0:
        return 0.0
    return float(x.mean() / x.std() * math.sqrt(par_an))


def bilan_trades(trades):
    if not trades:
        return {"n": 0, "gagnants": 0.0, "R_moyen": 0.0}
    R = np.array([t[3] for t in trades])
    net = np.array([t[4] for t in trades])
    return {"n": len(trades), "gagnants": float((net > 0).mean()), "R_moyen": float(R.mean()),
            "gain_moyen": float(net[net > 0].mean()) if (net > 0).any() else 0.0,
            "perte_moyenne": float(net[net <= 0].mean()) if (net <= 0).any() else 0.0}


def portefeuille(series):
    """series : {nom: (jours, rendements quotidiens, famille)} -> (jours, rendement à risque égal par famille)."""
    tous = np.array(sorted({int(j) for js, _, _ in series.values() for j in js}))
    pos = {j: k for k, j in enumerate(tous)}
    fam = {}
    for js, r, f in series.values():
        s, n = fam.setdefault(f, (np.zeros(len(tous)), np.zeros(len(tous))))
        idx = np.array([pos[int(j)] for j in js])
        s[idx] += r
        n[idx] += 1
    m = np.array([np.where(n > 0, s / np.maximum(n, 1), np.nan) for s, n in fam.values()])
    presentes = np.isfinite(m).sum(axis=0)
    return tous, np.where(presentes > 0, np.nansum(m, axis=0) / np.maximum(presentes, 1), 0.0)


def moities(jours, p, coupe=None):
    coupe = coupe if coupe is not None else jours[len(jours) // 2]
    return sharpe(p[jours < coupe]), sharpe(p[jours >= coupe]), coupe


def pire_baisse(p):
    courbe = np.cumsum(p)
    return float((courbe - np.maximum.accumulate(courbe)).min()) if len(p) else 0.0


def sharpe_degonfle(sr_annuel, n_essais, var_sr_annuel, n_obs, asym=0.0, aplat=3.0, par_an=252):
    """Sharpe dégonflé (Bailey et López de Prado, 2014) : probabilité que le vrai Sharpe dépasse le meilleur
    Sharpe attendu PAR HASARD parmi n_essais essais indépendants (variance des Sharpe des essais : var_sr_annuel)."""
    from statistics import NormalDist
    nd = NormalDist()
    g = 0.5772156649
    sr, var = sr_annuel / math.sqrt(par_an), var_sr_annuel / par_an
    if n_essais <= 1:
        sr0 = 0.0
    else:
        sr0 = math.sqrt(var) * ((1 - g) * nd.inv_cdf(1 - 1 / n_essais) + g * nd.inv_cdf(1 - 1 / (n_essais * math.e)))
    denom = math.sqrt(max(1 - asym * sr + (aplat - 1) / 4 * sr * sr, 1e-12))
    return nd.cdf((sr - sr0) * math.sqrt(n_obs - 1) / denom), sr0 * math.sqrt(par_an)


def entrees_au_hasard(trades, n, graine, marge=1):
    """Mêmes nombres d'achats et de ventes, à des bougies tirées au hasard (contrôle du signal)."""
    rng = np.random.default_rng(graine)
    sens = [t[2] for t in trades]
    if not sens or n < 10:
        return []
    places = np.sort(rng.choice(np.arange(marge, n - 2), size=min(len(sens), n - 3), replace=False))
    rng.shuffle(sens)
    return list(zip(places.tolist(), sens))
