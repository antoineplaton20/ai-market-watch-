"""R7 : les méthodes qui ne tiennent pas dans « une règle sur un marché » : portage, paires, COT, taux réels, régimes,
saisonnalité, momentum relatif, écarts d'ouverture, apprentissage automatique, méta-étiquetage, grille et martingale.
Mêmes conventions que moteur_r7 (décision à la clôture, exécution le lendemain, frais, financement) ; chaque donnée
externe est décalée de son délai de publication (aucune donnée du futur)."""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os

import numpy as np

import moteur_r7 as M

JOUR = 86_400_000


def _jour(ts):
    return np.asarray(ts, dtype=np.int64) // JOUR


def lire_fred(chemin, decalage_jours=1):
    """Série FRED (date, valeur) -> (jours connus, valeurs) : valeur connue `decalage_jours` après sa date."""
    j, v = [], []
    for ligne in csv.DictReader(open(chemin)):
        cle = [k for k in ligne if k.lower() != "observation_date" and k.upper() != "DATE"][0]
        date = ligne.get("observation_date") or ligne.get("DATE")
        try:
            x = float(ligne[cle])
        except ValueError:
            continue
        j.append((dt.date.fromisoformat(date) - dt.date(1970, 1, 1)).days + decalage_jours)
        v.append(x)
    return np.array(j), np.array(v)


def aligner(jours_cible, jours_src, valeurs):
    """Dernière valeur connue à chaque jour cible (nan avant la première)."""
    idx = np.searchsorted(jours_src, jours_cible, side="right") - 1
    out = np.where(idx >= 0, valeurs[np.clip(idx, 0, None)], np.nan)
    return out


def rendement_position(d, poids, cout, financement=M.FINANCEMENT):
    """Position décidée à la clôture i (poids en notionnel, signé), exécutée à l'OUVERTURE i+1 : le jour i+1 rapporte
    l'ancienne position de la clôture i à l'ouverture, la nouvelle de l'ouverture à la clôture ; frais à chaque
    changement de poids, financement chaque jour. -> rendements quotidiens."""
    o, c = d["o"], d["c"]
    nuit = np.r_[0.0, o[1:] / c[:-1] - 1]
    jour = c / o - 1
    neuf = np.r_[0.0, poids[:-1]]
    ancien = np.r_[0.0, 0.0, poids[:-2]][:len(c)]
    return ancien * nuit + neuf * jour - np.abs(neuf - ancien) * cout / 2 - np.abs(neuf) * financement / 252


def taille_vol(d, cible=M.VOL_CIBLE, n=60, levier=M.LEVIER_MAX):
    c = d["c"]
    r = np.r_[0.0, np.diff(np.log(c))]
    v = np.full(len(c), np.nan)
    for i in range(n, len(c)):
        v[i] = r[i - n + 1:i + 1].std() * math.sqrt(252)
    return np.where(np.isfinite(v) & (v > 0), np.minimum(cible / np.where(v > 0, v, 1), levier), 0.0)


# ============================================================================ portage (H37)
PAIRES_DEVISES = {"EURUSDX": ("EUR", "USD"), "GBPUSDX": ("GBP", "USD"), "JPYX": ("USD", "JPY"), "CHFX": ("USD", "CHF"),
                  "AUDUSDX": ("AUD", "USD"), "CADX": ("USD", "CAD"), "NZDUSDX": ("NZD", "USD"),
                  "EURGBPX": ("EUR", "GBP"), "EURJPYX": ("EUR", "JPY"), "GBPJPYX": ("GBP", "JPY"),
                  "EURCHFX": ("EUR", "CHF"), "AUDJPYX": ("AUD", "JPY")}
TAUX = {"USD": "IR3TIB01USM156N", "EUR": "IR3TIB01EZM156N", "JPY": "IR3TIB01JPM156N", "GBP": "IR3TIB01GBM156N",
        "CHF": "IR3TIB01CHM156N", "AUD": "IR3TIB01AUM156N", "CAD": "IR3TIB01CAM156N", "NZD": "IR3TIB01NZM156N"}


def portage(marches, macro, cout_fx):
    """Portage (Koijen et al.) : chaque mois, acheter la devise au taux 3 mois le plus élevé de chaque paire (taux
    mensuels de l'OCDE, connus 2 mois après le mois) ; le portage (différentiel / 365 par jour) est encaissé."""
    taux = {k: lire_fred(os.path.join(macro, f + ".csv"), decalage_jours=61) for k, f in TAUX.items()}
    out = {}
    for nom, (base, cot) in PAIRES_DEVISES.items():
        if nom not in marches:
            continue
        d = marches[nom]
        j = _jour(d["ts"])
        diff = aligner(j, *taux[base]) - aligner(j, *taux[cot])
        sens = np.zeros(len(j))
        courant = 0.0
        for i in range(len(j)):
            if np.isfinite(diff[i]) and (i == 0 or (j[i] // 30) != (j[i - 1] // 30)):
                courant = float(np.sign(diff[i]))
            sens[i] = courant
        w = sens * taille_vol(d)
        rend = rendement_position(d, w, cout_fx, financement=0.0)
        rend += np.r_[0.0, (w * np.nan_to_num(diff) / 100 / 365 * 7 / 5)[:-1]]   # portage encaissé, week-ends compris
        out[nom] = (j, rend, "forex")
    return out


# ============================================================================ paires (H16)
def paire(da, db, n=60, entree=2.0, sortie=0.0, arret=4.0, cout=0.0003):
    """Écart log(A/B) en score z sur 60 jours : |z| > 2 → vendre le cher, acheter le bon marché (même risque) ;
    sortie à z = 0 ; arrêt à |z| > 4."""
    ja, jb = _jour(da["ts"]), _jour(db["ts"])
    commun = np.intersect1d(ja, jb)
    ia, ib = np.searchsorted(ja, commun), np.searchsorted(jb, commun)
    a, b = da["c"][ia], db["c"][ib]
    x = np.log(a / b)
    z = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        f = x[i - n + 1:i + 1]
        z[i] = (x[i] - f.mean()) / (f.std() or np.nan)
    pos = np.zeros(len(x))
    p = 0
    for i in range(len(x)):
        if not np.isfinite(z[i]):
            pos[i] = p
            continue
        if p == 0 and z[i] > entree:
            p = -1
        elif p == 0 and z[i] < -entree:
            p = 1
        elif p != 0 and (abs(z[i]) > arret or (p == -1 and z[i] < sortie) or (p == 1 and z[i] > -sortie)):
            p = 0
        pos[i] = p
    ra, rb = np.r_[0.0, a[1:] / a[:-1] - 1], np.r_[0.0, b[1:] / b[:-1] - 1]
    va = np.array([ra[max(0, i - 59):i + 1].std() for i in range(len(ra))]) * math.sqrt(252)
    vb = np.array([rb[max(0, i - 59):i + 1].std() for i in range(len(rb))]) * math.sqrt(252)
    wa = np.where(va > 0, 0.05 / np.where(va > 0, va, 1), 0)
    wb = np.where(vb > 0, 0.05 / np.where(vb > 0, vb, 1), 0)
    jambe_a = {"o": da["o"][ia], "c": a}
    jambe_b = {"o": db["o"][ib], "c": b}
    rend = rendement_position(jambe_a, pos * wa, cout) + rendement_position(jambe_b, -pos * wb, cout)
    return commun, rend, int((np.abs(np.diff(np.r_[0.0, pos])) > 0).sum() // 2)


# ============================================================================ COT (H08)
def cot(d, chemin, centile=156):
    """Extrêmes du COT (gérants de fonds, « managed money ») : position nette / intérêt ouvert, rang sur 3 ans ; au-dessus
    du 90e centile → vente (foule trop acheteuse), sous le 10e → achat ; sortie au retour au 50e. Rapport du mardi,
    publié le vendredi : connu le lundi suivant (décalage de 6 jours)."""
    lignes = json.load(open(chemin))
    jr, val = [], []
    for r in lignes:
        try:
            net = (float(r["m_money_positions_long_all"]) - float(r["m_money_positions_short_all"])) / \
                  float(r["open_interest_all"])
        except (KeyError, ValueError, ZeroDivisionError):
            continue
        jr.append((dt.date.fromisoformat(r["report_date_as_yyyy_mm_dd"][:10]) - dt.date(1970, 1, 1)).days + 6)
        val.append(net)
    jr, val = np.array(jr), np.array(val)
    rang = np.full(len(val), np.nan)
    for i in range(centile, len(val)):
        f = val[i - centile:i + 1]
        rang[i] = (f < val[i]).mean()
    j = _jour(d["ts"])
    rg = aligner(j, jr, rang)
    pos, p = np.zeros(len(j)), 0
    for i in range(len(j)):
        if np.isfinite(rg[i]):
            if p == 0 and rg[i] > 0.9:
                p = -1
            elif p == 0 and rg[i] < 0.1:
                p = 1
            elif (p == -1 and rg[i] < 0.5) or (p == 1 and rg[i] > 0.5):
                p = 0
        pos[i] = p
    return pos


# ============================================================================ taux réels (H17), régimes (H10)
def taux_reels_or(d, macro):
    """Chocs de taux réels : taux réel 10 ans (TIPS, DFII10, connu le lendemain) en baisse sur 20 jours → or acheté ;
    sinon à plat."""
    jr, v = lire_fred(os.path.join(macro, "DFII10.csv"), 1)
    j = _jour(d["ts"])
    x = aligner(j, jr, v)
    chg = np.r_[np.full(20, np.nan), x[20:] - x[:-20]]
    return np.where(np.isfinite(chg) & (chg < 0), 1.0, 0.0)


def regime_inflation(d, macro):
    """Régime d'inflation (Dalio) : point mort d'inflation 10 ans (T10YIE) en hausse sur 3 mois → acheté ; sinon à plat."""
    jr, v = lire_fred(os.path.join(macro, "T10YIE.csv"), 1)
    j = _jour(d["ts"])
    x = aligner(j, jr, v)
    chg = np.r_[np.full(63, np.nan), x[63:] - x[:-63]]
    return np.where(np.isfinite(chg) & (chg > 0), 1.0, 0.0)


def regime_liquidite(d, macro):
    """Liquidité (Druckenmiller) : bilan de la Fed (WALCL, publié le jeudi) en hausse sur 13 semaines → indices achetés."""
    jr, v = lire_fred(os.path.join(macro, "WALCL.csv"), 2)
    j = _jour(d["ts"])
    x = aligner(j, jr, v)
    chg = np.r_[np.full(91, np.nan), x[91:] / x[:-91] - 1]
    return np.where(np.isfinite(chg) & (chg > 0), 1.0, 0.0)


# ============================================================================ saisonnalité (H12)
def saisonnalite(d, coupe_jour):
    """Mois de l'année : moyenne du rendement de chaque mois sur la 1re moitié SEULEMENT ; sur la 2e moitié, achat
    pendant les mois à moyenne positive, vente pendant les autres."""
    j = _jour(d["ts"])
    mois = np.array([(dt.date(1970, 1, 1) + dt.timedelta(days=int(x))).month for x in j])
    r = np.r_[0.0, d["c"][1:] / d["c"][:-1] - 1]
    avant = j < coupe_jour
    moy = {m: r[avant & (mois == m)].mean() if (avant & (mois == m)).any() else 0.0 for m in range(1, 13)}
    return np.where(avant, 0.0, np.array([np.sign(moy[m]) for m in mois]))


# ============================================================================ momentum relatif
def momentum_relatif(marches, cout_par_marche, tiers=1 / 3):
    """Momentum relatif (Jegadeesh et Titman ; Asness, Moskowitz et Pedersen) : chaque mois, acheter le tiers des
    marchés au meilleur rendement 12 mois (hors dernier mois), à risque égal ; tenue un mois."""
    jours = np.array(sorted({int(x) for d in marches.values() for x in _jour(d["ts"])}))
    idx = {s: (np.searchsorted(jours, _jour(d["ts"])), d) for s, d in marches.items()}
    prix = {}
    for s, (ix, d) in idx.items():
        p = np.full(len(jours), np.nan)
        p[ix] = d["c"]
        for i in range(1, len(p)):                                  # dernier cours connu
            if not np.isfinite(p[i]):
                p[i] = p[i - 1]
        prix[s] = p
    noms = list(prix)
    P = np.array([prix[s] for s in noms])
    poids = np.zeros_like(P)
    choix = np.zeros(len(noms))
    for i in range(273, len(jours)):
        if (jours[i] // 30) != (jours[i - 1] // 30):
            score = P[:, i - 21] / P[:, i - 273] - 1
            ok = np.isfinite(score)
            choix = np.zeros(len(noms))
            if ok.sum() >= 6:
                k = max(1, int(round(ok.sum() * tiers)))
                meilleurs = np.argsort(np.where(ok, -score, np.inf))[:k]
                choix[meilleurs] = 1
        poids[:, i] = choix
    out = {}
    for k_, s in enumerate(noms):
        ix, d = idx[s]
        w = poids[k_, ix] * taille_vol(d)
        out[s] = (_jour(d["ts"]), rendement_position(d, w, cout_par_marche[s]), d.get("famille", "?"))
    return out


# ============================================================================ écarts d'ouverture
def ecarts_ouverture(d, cout, suivre=False, seuil=0.005, chemin="prudent"):
    """Écart d'ouverture de plus de 0,5 % contre la veille : on joue sa FERMETURE (vers la clôture de la veille) ou on
    le SUIT (« gap and go »), entrée au premier cours, sortie à la clôture du jour, stop à 1 écart. Entrée au premier
    cours : un peu optimiste (signalé)."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    rend = np.zeros(len(c))
    trades = []
    for i in range(1, len(c)):
        g = o[i] / c[i - 1] - 1
        if abs(g) < seuil:
            continue
        s = -np.sign(g) if not suivre else np.sign(g)
        e = o[i]
        ecart = abs(o[i] - c[i - 1])
        stop = e + ecart if s < 0 else e - ecart
        cible = c[i - 1] if not suivre else (e + 2 * ecart * s)
        w = min(M.RISQUE / (ecart / e), M.LEVIER_MAX)
        t_sl = l[i] <= stop if s > 0 else h[i] >= stop
        t_tp = h[i] >= cible if s > 0 else l[i] <= cible
        if t_sl and t_tp and chemin == "ohlc":                  # ordre probable de la bougie
            if (s > 0) == (c[i] >= o[i]):
                t_tp = False
            else:
                t_sl = False
        sortie = stop if t_sl else (cible if t_tp else c[i])
        r = w * s * (sortie / e - 1) - w * cout
        rend[i] += r
        trades.append((i, i, int(s), s * (sortie - e) / ecart, r))
    return rend, trades


# ============================================================================ apprentissage automatique (H11)
def _caracteristiques(c):
    r = np.r_[0.0, np.diff(np.log(c))]
    def ret(k):
        return np.r_[np.full(k, np.nan), np.log(c[k:] / c[:-k])]
    vol = np.array([r[max(0, i - 59):i + 1].std() for i in range(len(r))]) + 1e-12
    rs = M.rsi(c, 14)
    m50, m200 = M.sma(c, 50), M.sma(c, 200)
    X = np.column_stack([ret(1) / vol, ret(5) / vol / math.sqrt(5), ret(20) / vol / math.sqrt(20),
                         ret(60) / vol / math.sqrt(60), ret(252) / vol / math.sqrt(252), (rs - 50) / 50,
                         np.log(c / m50) / vol / 7, np.log(c / m200) / vol / 14,
                         vol / (np.array([r[max(0, i - 251):i + 1].std() for i in range(len(r))]) + 1e-12) - 1])
    return X


def logistique(X, y, l2=1.0, iterations=300):
    """Régression logistique (descente de Newton, pénalité L2), sans dépendance."""
    X1 = np.column_stack([np.ones(len(X)), X])
    w = np.zeros(X1.shape[1])
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-X1 @ w))
        g = X1.T @ (p - y) + l2 * np.r_[0, w[1:]]
        H = X1.T @ (X1 * (p * (1 - p))[:, None]) + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        pas = np.linalg.solve(H + 1e-9 * np.eye(len(w)), g)
        w -= pas
        if np.abs(pas).max() < 1e-8:
            break
    return w


def apprentissage(marches, cout_par_marche, seuil=0.52):
    """Prévision du sens du lendemain par régression logistique (9 indicateurs de prix), réentraînée chaque année sur
    tout le passé de tous les marchés (fenêtre croissante, jamais l'année prédite) ; position dans le sens prévu quand
    la probabilité dépasse 52 %, taille à 10 % de volatilité."""
    feats = {s: _caracteristiques(d["c"]) for s, d in marches.items()}
    cibles = {s: np.r_[(d["c"][1:] > d["c"][:-1]).astype(float), np.nan] for s, d in marches.items()}
    annees = {s: np.array([(dt.date(1970, 1, 1) + dt.timedelta(days=int(x))).year for x in _jour(d["ts"])])
              for s, d in marches.items()}
    an_min, an_max = min(a.min() for a in annees.values()), max(a.max() for a in annees.values())
    pos = {s: np.zeros(len(d["c"])) for s, d in marches.items()}
    for an in range(an_min + 3, an_max + 1):
        X, y = [], []
        for s in marches:
            sel = (annees[s] < an) & np.all(np.isfinite(feats[s]), axis=1) & np.isfinite(cibles[s])
            X.append(feats[s][sel])
            y.append(cibles[s][sel])
        X, y = np.vstack(X), np.concatenate(y)
        if len(y) < 2000:
            continue
        w = logistique(X, y)
        for s in marches:
            sel = (annees[s] == an) & np.all(np.isfinite(feats[s]), axis=1)
            p = 1 / (1 + np.exp(-(np.column_stack([np.ones(sel.sum()), feats[s][sel]]) @ w)))
            pos[s][sel] = np.where(p > seuil, 1, np.where(p < 1 - seuil, -1, 0))
    out = {}
    for s, d in marches.items():
        w_ = pos[s] * taille_vol(d)
        out[s] = (_jour(d["ts"]), rendement_position(d, w_, cout_par_marche[s]), d.get("famille", "?"))
    return out


# ============================================================================ grille et martingale (H39)
def martingale_grille(d, cout, capital=3000.0, graines=200, levier_max=30.0):
    """Ruine des méthodes « 100 % gagnantes » sur l'or (1 h) : (1) martingale : sens au hasard, objectif et stop à
    1 ATR, mise doublée après chaque perte, revenue à la base après un gain ; (2) grille : achat tous les 1 ATR de
    baisse, revente de chaque lot à +1 ATR, sans stop. Compte de 3 000, mise de base 0,5 % ; ruine = compte ≤ 0 ou
    levier au-delà de 30 fois (appel de marge). Départs tirés au hasard sur tout l'historique, un an chacun."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    res = {"martingale": [], "grille": []}
    for g in range(graines):
        rng = np.random.default_rng(g)
        eq, mise, gains, ruine = capital, 1.0, 0, False
        i = int(rng.integers(200, len(c) - 24 * 252 - 2))
        fin = min(len(c) - 2, i + 24 * 252)
        base = capital * 0.005
        while i < fin and not ruine:
            s = 1 if rng.random() < 0.5 else -1
            e, pas = o[i + 1], a[i]
            if not np.isfinite(pas) or pas <= 0:
                i += 1
                continue
            unite = base / pas                                          # risque 1 ATR = mise de base
            q = unite * mise
            if q * e / max(eq, 1e-9) > levier_max:
                ruine = True
                break
            j = i + 1
            while j < len(c) - 1:
                if (s > 0 and l[j] <= e - pas) or (s < 0 and h[j] >= e + pas):
                    eq -= q * pas + q * e * cout
                    mise *= 2
                    break
                if (s > 0 and h[j] >= e + pas) or (s < 0 and l[j] <= e - pas):
                    eq += q * pas - q * e * cout
                    mise, gains = 1.0, gains + 1
                    break
                j += 1
            i = j
            if eq <= 0:
                ruine = True
        res["martingale"].append((ruine, eq, gains))
        # grille
        eq, i = capital, int(rng.integers(200, len(c) - 24 * 252 - 2))
        fin = min(len(c) - 1, i + 24 * 252)
        lots, niveau, ruine, gains = [], c[i], False, 0
        unite = capital * 0.005 / (a[i] if np.isfinite(a[i]) else c[i] * 0.005)
        pire = 0.0
        while i < fin:
            i += 1
            pas = a[i - 1] if np.isfinite(a[i - 1]) else c[i] * 0.005
            for k in range(len(lots) - 1, -1, -1):                 # revente : lots achetés AVANT cette bougie
                x, quand = lots[k]
                if quand < i and h[i] >= x + pas:
                    eq += unite * pas - unite * x * cout
                    gains += 1
                    lots.pop(k)
            while l[i] <= niveau - pas:                             # achat de chaque niveau traversé
                niveau -= pas
                lots.append((niveau, i))
            if not lots:
                niveau = c[i]
            latent = sum(unite * (c[i] - x) for x, _ in lots)
            pire = min(pire, eq + latent - capital)
            expo = unite * c[i] * len(lots) / max(eq + latent, 1e-9)
            if eq + latent <= 0 or expo > levier_max:
                ruine = True
                break
        res["grille"].append((ruine, eq + (sum(unite * (c[i] - x) for x, _ in lots) if lots else 0.0), gains))
    return res
