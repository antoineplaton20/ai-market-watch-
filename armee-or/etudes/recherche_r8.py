"""R8 (26/10/2026) : toutes les méthodes du corpus R8 (podcasts transcrits, vidéos Odysee, textes des vidéos de
Trading Rush, scripts TradingView les plus suivis, forums, recherche, discours de PDG et de gérants) qui n'avaient
jamais été testées, jugées comme en R7 (permis, naïf, frais, deux moitiés) :
- A. règles sur un marché (catalogue_r8.py, N01 à N45) : Gann, Camarilla, TTM, cassure de Williams, Hull, Kaufman,
  Aroon, Vortex, biseau, achat du creux, plus haut de 52 semaines ; indicateurs de Trading Rush (Connors RSI, Fisher,
  RVI, TRIX, CMO, TEMA, McGinley, Schaff, Chaikin, Awesome, Alligator, fractales, choppiness, Beep Boop, chiffres
  ronds, RSI stochastique, canal de moyennes) ; scripts TradingView (WaveTrend, UT Bot, Chandelier, Range Filter,
  QQE, SSL, HalfTrend, Nadaraya-Watson, classification lorentzienne, Vix Fix, OTT, PMax, SuperTrend IA) ; bande de
  bruit de Zarattini ; oscillateur 3-10 et Holy Grail de Linda Raschke ;
- B. EWMAC de Carver ; C. pyramidage des Turtles ;
- D. sélections entre marchés : valeur (5 ans), faible volatilité, faible bêta, proximité du plus haut de 52 semaines,
  inversion d'une semaine, asymétrie, valeur et momentum, saisonnalité croisée ;
- E. événements et calendrier : réunions de la Fed, résultats des 7 géants (Nvidia, Apple, Microsoft, Amazon,
  Alphabet, Meta, Tesla), cycles lunaires, Diwali et Nouvel An chinois, peur (VIX > 30), courbe des taux, crédit ;
- F. stratégies gratuites de Quantpedia applicables à nos marchés ;
- G. grands investisseurs : All Weather de Dalio, parité de risque, 60/40, bulles de Grantham, « craintif quand
  les autres sont avides » (indice peur et avidité du bitcoin).
Les règles d'exposition sur un marché (E, F, G) doivent aussi compter 30 entrées par moitié, comme le permis.

Usage : python etudes/recherche_r8.py BINANCE YAHOO YAHOO_EXTRA MACRO RACINE_ARMEE [SORTIE.json]
"""
import datetime as dt
import json
import math
import os
import sys

import numpy as np

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
BINANCE, YAHOO, EXTRA, MACRO, RACINE = sys.argv[1:6]
sys.path.insert(0, RACINE)

import catalogue_r7 as C      # noqa: E402
import catalogue_r8 as C8     # noqa: E402
import donnees_r7 as D        # noqa: E402
import fiches_r7 as F         # noqa: E402
import moteur_r7 as M         # noqa: E402
import recherche_r7 as R      # noqa: E402
import speciales_r7 as SP     # noqa: E402
from armee_or import marches as MM   # noqa: E402

R.BINANCE, R.YAHOO, R.MACRO = BINANCE, YAHOO, MACRO
ESSAIS = []
SYNODIQUE, NOUVELLE_LUNE_2000 = 29.530588853, dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.timezone.utc).timestamp() / 86400


def note(r):
    ESSAIS.append(r)
    return r


def question(nom, valeurs, n_tests, jours=None, note_=""):
    """Comme fiches_r7.question ; si l'effet passe le seuil, le même calcul sur chaque moitié (jours des cas)."""
    r = F.question(nom, valeurs, n_tests, note_)
    if r.get("t") is not None and abs(r["t"]) >= r["seuil"] and jours is not None:
        v, js = np.asarray(valeurs, float), np.asarray(jours)
        coupe = np.median(js)
        r["moities"] = []
        for nom_m, sel in (("1re moitié", js < coupe), ("2e moitié", js >= coupe)):
            x = v[sel & np.isfinite(v)]
            t_ = x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 2 else float("nan")
            r["moities"].append(round(float(t_), 2))
            print(f"      … {nom_m} : {len(x)} cas, moyenne {x.mean() * 100:+.3f} %, t = {t_:+.2f}")
    return r


# ============================================================================ A. règles sur un marché
def regles():
    print("A) Règles sur un marché (or, euro-dollar, bitcoin, ether en 15 min et 1 h ; 25 marchés en journalier)")
    naifs = {}
    for nom, (f, unites) in C8.REGLES.items():
        C.INTRADAY[nom] = f
        for u in unites:
            r = R.essai(nom, u)
            nv = naifs.setdefault(u, R.naif(u))
            raisons = R.juge(r, nv)
            print(f"   {nom[:44]:44} {u:4} {r['sharpe'][0]:+.2f} / {r['sharpe'][1]:+.2f} (naïf {nv['sharpe'][0]:+.2f} / "
                  f"{nv['sharpe'][1]:+.2f}) ; {sum(r['trades'])} trades, {r['gagnants'] * 100:.0f} % gagnants ; "
                  f"{'✅ PERMIS' if not raisons else '✖ ' + '; '.join(raisons)}", flush=True)
            note({"regle": nom, "unite": u, "sharpe": r["sharpe"], "sharpe_total": r["sharpe_total"], "jours": r["jours"],
                  "permis": not raisons, "asym": r["asym"], "aplat": r["aplat"]})


def ewmac(d, achat_seul=False):
    """EWMAC de Carver : prévision = (EMA rapide − EMA lente) / écart-type des variations de prix (25 jours), pour 4
    vitesses (8/32, 16/64, 32/128, 64/256) ; chaque prévision mise à l'échelle sur sa moyenne absolue PASSÉE (×10),
    plafonnée à ±20 ; position = moyenne des prévisions / 10 × taille à 10 % de volatilité."""
    c = d["c"]
    dp = np.r_[0.0, np.diff(c)]
    sig = np.array([dp[max(0, i - 24):i + 1].std() for i in range(len(c))])
    sig[sig == 0] = np.nan
    prev = []
    for a, b in ((8, 32), (16, 64), (32, 128), (64, 256)):
        brut = (M.ema(c, a) - M.ema(c, b)) / sig
        echelle = np.array([np.nanmean(np.abs(brut[max(0, i - 2519):i + 1])) for i in range(len(c))])
        prev.append(np.clip(10 * brut / np.where(echelle > 0, echelle, np.nan), -20, 20))
    f = np.nanmean(np.array(prev), axis=0)
    f[:300] = np.nan
    f = np.nan_to_num(f)
    if achat_seul:
        f = np.maximum(f, 0)
    return f / 10 * SP.taille_vol(d)


def portefeuille_poids(marches, fonction):
    ser = {s: (F.jours_de(d), SP.rendement_position(d, fonction(d), MM.FRAIS_DEFAUT.get(d["famille"], 0.0005)),
               d["famille"]) for s, d in marches.items()}
    return M.portefeuille(ser)


def juge_serie(nom, j, p, jn, pn, je=None, pe=None, poids=None):
    """Jugé sur la période où la règle peut agir (après ses données de départ), naïf et équipe sur la même période.
    poids (règles d'exposition sur un marché, alignés sur j) : il faut aussi 30 entrées par moitié, comme le permis."""
    actifs = np.flatnonzero(p != 0)
    if len(actifs):
        debut = j[actifs[0]]
        if poids is not None:
            poids = np.asarray(poids)[j >= debut]
        p, j = p[j >= debut], j[j >= debut]
        pn, jn = pn[jn >= debut], jn[jn >= debut]
        if je is not None:
            pe, je = pe[je >= debut], je[je >= debut]
    coupe = j[len(j) // 2]
    s1, s2 = M.sharpe(p[j < coupe]), M.sharpe(p[j >= coupe])
    n1, n2 = M.sharpe(pn[jn < coupe]), M.sharpe(pn[jn >= coupe])
    ok = s1 > max(0, n1) and s2 > max(0, n2)
    txt = f"   {nom[:60]:60} {s1:+.2f} / {s2:+.2f} (naïf {n1:+.2f} / {n2:+.2f}"
    if je is not None:
        e1, e2 = M.sharpe(pe[je < coupe]), M.sharpe(pe[je >= coupe])
        txt += f" ; équipe {e1:+.2f} / {e2:+.2f}"
    if poids is not None:
        entree = (poids > 0) & (np.r_[0.0, poids[:-1]] <= 0)
        d1, d2 = int(entree[j < coupe].sum()), int(entree[j >= coupe].sum())
        txt += f" ; entrées {d1} / {d2}"
        ok = ok and min(d1, d2) >= M.MIN_TRADES
    print(txt + f") {'✅ PERMIS' if ok else '✖'}", flush=True)
    return note({"regle": nom, "sharpe": [round(s1, 3), round(s2, 3)], "sharpe_total": round(M.sharpe(p), 3),
                 "jours": int(len(p)), "permis": bool(ok), "asym": R._moment(p, 3), "aplat": R._moment(p, 4)})


# ============================================================================ C. pyramidage des Turtles
def turtles_pyramide(d, cout, unites_max=4, pas_n=0.5):
    """Turtles système 1 ACHETEUR avec filtre (fiche H01), entrée dans la journée, et PYRAMIDAGE comme dans les règles
    des Turtles : une unité de plus à chaque +½ N depuis la dernière entrée, 4 unités au plus ; le stop de toutes les
    unités remonte à 2 N sous la dernière entrée ; sortie au plus bas de 10 jours."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 20)
    n = len(c)
    jours = F.jours_de(d)
    hh, ls, h55 = C.fen_max(h, 20), C.fen_min(l, 10), C.fen_max(h, 55)
    rend = np.zeros(n)
    gagnant, fictif, pos, trades = False, None, None, 0
    for i in range(56, n):
        N = a[i - 1]
        if not np.isfinite(N) or N <= 0:
            continue
        if fictif is not None:
            e_f, st_f = fictif
            if l[i] <= st_f or l[i] <= ls[i - 1]:
                px = st_f if l[i] <= st_f else ls[i - 1]
                gagnant, fictif = px > e_f, None
        if pos is not None:
            unites, st, ref, derniere, e0 = pos
            sortie_niv = max(st, ls[i - 1])
            if l[i] <= sortie_niv:
                px = min(o[i], sortie_niv)
                for w, e in unites:
                    rend[i] += w * (px / ref - 1) - w * cout / 2
                gagnant, pos = px > e0, None
                continue
            r_ = sum(w for w, _ in unites) * (c[i] / ref - 1)
            while len(unites) < unites_max and h[i] >= derniere + pas_n * N:      # ajout d'une unité
                e = max(o[i], derniere + pas_n * N)
                w = min(M.RISQUE / (2 * N / e), M.LEVIER_MAX)
                r_ += w * (c[i] / e - 1) - w * cout / 2
                unites.append((w, e))
                derniere, st = e, e - 2 * N
                trades += 1
            if i + 1 < n and jours[i + 1] != jours[i]:
                r_ -= sum(w for w, _ in unites) * M.FINANCEMENT / 365 * (jours[i + 1] - jours[i])
            rend[i] += r_
            pos = (unites, st, c[i], derniere, e0)
            continue
        if not (h[i] >= hh[i - 1]):
            continue
        e = max(o[i], hh[i - 1])
        st = e - 2 * N
        cas_55 = h[i] >= h55[i - 1]
        if fictif is not None and not cas_55:
            continue
        if gagnant and not cas_55:
            fictif, gagnant = (e, st), False
            continue
        w = min(M.RISQUE / (2 * N / e), M.LEVIER_MAX)
        trades += 1
        if l[i] <= st:
            rend[i] += w * (st / e - 1) - w * cout
            continue
        rend[i] += w * (c[i] / e - 1) - w * cout / 2
        pos = ([(w, e)], st, c[i], e, e)
    return rend, trades


# ============================================================================ D. sélections entre marchés
def croisee(marches, score, rebal="mois", tiers=1 / 3):
    """Chaque fin de mois (ou de semaine), acheter le tiers des marchés au MEILLEUR score (calculé sur le passé)."""
    jours = np.array(sorted({int(x) for d in marches.values() for x in SP._jour(d["ts"])}))
    noms = list(marches)
    P = np.full((len(noms), len(jours)), np.nan)
    for k, s in enumerate(noms):
        P[k, np.searchsorted(jours, SP._jour(marches[s]["ts"]))] = marches[s]["c"]
        for i in range(1, len(jours)):
            if not np.isfinite(P[k, i]):
                P[k, i] = P[k, i - 1]
    poids = np.zeros_like(P)
    choix = np.zeros(len(noms))
    periode = 30 if rebal == "mois" else 7
    for i in range(1300, len(jours)):
        if (jours[i] // periode) != (jours[i - 1] // periode):
            sc = score(P[:, :i + 1])
            ok = np.isfinite(sc)
            choix = np.zeros(len(noms))
            if ok.sum() >= 6:
                k = max(1, int(round(ok.sum() * tiers)))
                choix[np.argsort(np.where(ok, -sc, np.inf))[:k]] = 1
        poids[:, i] = choix
    ser = {}
    for k, s in enumerate(noms):
        d = marches[s]
        ix = np.searchsorted(jours, SP._jour(d["ts"]))
        ser[s] = (SP._jour(d["ts"]), SP.rendement_position(d, poids[k, ix] * SP.taille_vol(d),
                                                            MM.FRAIS_DEFAUT.get(d["famille"], 0.0005)), d["famille"])
    return M.portefeuille(ser)


def rendements(P, n):
    return np.log(P[:, -1] / P[:, -1 - n]) if P.shape[1] > n else np.full(P.shape[0], np.nan)


def score_valeur(P):                       # valeur : le plus faible rendement sur 5 ans, hors dernière année
    return -(np.log(P[:, -253] / P[:, -1261]))


def score_faible_vol(P):
    r = np.diff(np.log(P[:, -253:]), axis=1)
    return -np.nanstd(r, axis=1)


def score_faible_beta(P):
    r = np.diff(np.log(P[:, -253:]), axis=1)
    m = np.nanmean(r, axis=0)
    cov = np.array([np.nanmean((x - np.nanmean(x)) * (m - np.nanmean(m))) for x in r])
    return -cov / np.nanvar(m)


def score_52s(P):                          # proximité du plus haut de 52 semaines (George et Hwang, 2004)
    return P[:, -1] / np.nanmax(P[:, -252:], axis=1)


def score_inversion(P):                    # inversion d'une semaine : les plus fortes baisses de la semaine
    return -np.log(P[:, -1] / P[:, -6])


def score_asymetrie(P):                    # asymétrie la plus NÉGATIVE sur un an (prime d'asymétrie)
    r = np.diff(np.log(P[:, -253:]), axis=1)
    mu, sd = np.nanmean(r, axis=1, keepdims=True), np.nanstd(r, axis=1, keepdims=True)
    return -np.nanmean(((r - mu) / sd) ** 3, axis=1)


def score_valeur_momentum(P):             # valeur et momentum ensemble (Asness, Moskowitz, Pedersen 2013) : rangs
    v, m = score_valeur(P), np.log(P[:, -22] / P[:, -274])
    rang = lambda x: np.argsort(np.argsort(np.where(np.isfinite(x), x, -np.inf))).astype(float)
    out = rang(v) + rang(m)
    out[~(np.isfinite(v) & np.isfinite(m))] = np.nan
    return out


def score_saison_croisee(P):               # cycle de 12 mois (Heston et Sadka) : rendement moyen du même mois les
    out = np.full(P.shape[0], np.nan)      # années précédentes (mois suivant celui qui se termine)
    n = P.shape[1]
    vals = [np.log(P[:, n - 1 - 252 * k + 21] / P[:, n - 1 - 252 * k]) for k in range(1, 6) if n - 1 - 252 * k >= 0]
    if vals:
        out = np.nanmean(np.array(vals), axis=0)
    return out


# ============================================================================ E. événements et calendrier
def phase_lune(jours):
    return ((np.asarray(jours, float) + 0.5 - NOUVELLE_LUNE_2000) / SYNODIQUE) % 1.0


def nouvelles_lunes(debut, fin):
    k0 = math.floor((debut - NOUVELLE_LUNE_2000) / SYNODIQUE)
    return [NOUVELLE_LUNE_2000 + k * SYNODIQUE for k in range(k0, k0 + int((fin - debut) / SYNODIQUE) + 3)]


def fetes(annees):
    """Diwali ≈ nouvelle lune entre le 13 octobre et le 14 novembre ; Nouvel An chinois ≈ première nouvelle lune à
    partir du 21 janvier (calcul moyen de la lunaison : ± 1 jour, assez pour une fenêtre de 10 jours)."""
    out = {"Diwali": [], "Nouvel An chinois": []}
    for an in annees:
        for nom, (m1, j1, m2, j2) in (("Diwali", (10, 13, 11, 14)), ("Nouvel An chinois", (1, 21, 2, 21))):
            a = (dt.date(an, m1, j1) - dt.date(1970, 1, 1)).days
            b = (dt.date(an, m2, j2) - dt.date(1970, 1, 1)).days
            nl = [x for x in nouvelles_lunes(a - 30, b + 30) if a <= x <= b]
            if nl:
                out[nom].append(int(math.floor(nl[0])))
    return out


def evenements():
    gld = F.yahoo_brut(EXTRA, "GLD", "métaux")
    spy = F.yahoo_brut(EXTRA, "SPY", "indices")
    qqq = F.yahoo_brut(EXTRA, "QQQ", "indices")
    vix = F.yahoo_brut(EXTRA, "VIX", "indices")
    tous = R.yahoo()
    eur = tous["EURUSDX"]
    btc = tous["BTC-USD"]
    print("\nE) Événements et calendrier (question : le rendement est-il différent ? t de Student, Bonferroni)")
    # Fed
    fomc = [(dt.date.fromisoformat(x) - dt.date(1970, 1, 1)).days for x in json.load(open(os.path.join(MACRO, "fomc.json")))]
    print("   réunions de la Fed (jour de la décision, clôture d'avant → clôture) :")
    for nom, d in (("S&P 500 (SPY)", spy), ("Nasdaq (QQQ)", qqq), ("or (GLD)", gld), ("euro-dollar", eur)):
        j = F.jours_de(d)
        r = np.r_[0.0, d["c"][1:] / d["c"][:-1] - 1]
        jour_f = np.isin(j, fomc)
        note(question(f"   E01 Fed, {nom} : jour de décision moins jour ordinaire", r[jour_f] - r[~jour_f].mean(), 4,
                      j[jour_f]))
    j = F.jours_de(spy)
    r = np.r_[0.0, spy["c"][1:] / spy["c"][:-1] - 1]
    w = np.r_[np.isin(j, fomc)[1:], False].astype(float) * SP.taille_vol(spy)      # acheté la veille au soir
    juge_serie("E01b S&P acheté seulement pour les jours de la Fed", j, SP.rendement_position(spy, w, 0.0002), j,
               SP.rendement_position(spy, SP.taille_vol(spy), 0.0002), poids=w)
    # résultats des géants
    dates = json.load(open(os.path.join(MACRO, "resultats_geants.json")))
    print("   résultats des 7 géants (publiés après la clôture : réaction le lendemain) :")
    jq = F.jours_de(qqq)
    rq = np.r_[0.0, qqq["c"][1:] / qqq["c"][:-1] - 1]
    reac_q, avant, apres, jours_q, jours_a = [], [], [], [], []
    for t, ds in dates.items():
        a = F.yahoo_brut(EXTRA, t, "indices")
        ja = F.jours_de(a)
        moy5 = np.mean(a["c"][5:] / a["c"][:-5] - 1)                 # l'action monte en moyenne : on retire sa
        moy20 = np.mean(a["c"][21:] / a["o"][2:-19] - 1)              # dérive propre (biais du survivant)
        for x in ds:
            jx = (dt.date.fromisoformat(x) - dt.date(1970, 1, 1)).days
            i = int(np.searchsorted(ja, jx))                       # jour de publication (ou le suivant ouvré)
            if i < 6 or i + 22 >= len(ja):
                continue
            iq = int(np.searchsorted(jq, ja[i + 1]))
            if iq < len(jq) and jq[iq] == ja[i + 1]:
                reac_q.append(rq[iq])
                jours_q.append(ja[i])
            avant.append(a["c"][i] / a["c"][i - 5] - 1 - moy5)
            reaction = a["c"][i + 1] / a["c"][i] - 1
            apres.append(np.sign(reaction) * (a["c"][i + 21] / a["o"][i + 2] - 1 - moy20))
            jours_a.append(ja[i])
    note(question("   E02 Nasdaq (QQQ) le lendemain des résultats d'un géant", reac_q, 3, jours_q))
    note(question("   E03 l'action dans les 5 jours AVANT ses résultats, moins sa moyenne", avant, 3, jours_a,
                  "(7 géants d'aujourd'hui : biais du survivant)"))
    note(question("   E04 dérive après résultats (20 jours, sens de la réaction), moins sa moyenne", apres, 3, jours_a))
    # lune
    print("   cycles lunaires (Dichev et Janes 2003) : 15 jours autour de la nouvelle lune moins autour de la pleine lune")
    for nom, d in (("S&P 500 (SPY)", spy), ("or (GLD)", gld), ("bitcoin", btc)):
        j = F.jours_de(d)
        r = np.r_[0.0, d["c"][1:] / d["c"][:-1] - 1]
        ph = phase_lune(j)
        nouvelle = (ph < 0.25) | (ph >= 0.75)
        diff = np.r_[r[nouvelle] - r[~nouvelle].mean()]
        note(F.question(f"   E05 lune, {nom}", diff, 3))
    # fêtes
    print("   or avant Diwali et le Nouvel An chinois (10 jours de bourse avant la fête)")
    jg = F.jours_de(gld)
    r10 = np.r_[np.full(10, np.nan), gld["c"][10:] / gld["c"][:-10] - 1]
    moy10 = np.nanmean(r10)
    for nom, js in fetes(range(2005, 2027)).items():
        vals = []
        for x in js:
            i = int(np.searchsorted(jg, x))
            if 10 < i < len(jg):
                vals.append(r10[i - 1] - moy10)
        note(F.question(f"   E06 or (GLD) avant {nom}, moins la moyenne", vals, 2))
    # VIX
    print("   peur : VIX au-dessus de 30 (première clôture après 20 jours en dessous), S&P les 20 jours suivants")
    jv, cv = F.jours_de(vix), vix["c"]
    js = F.jours_de(spy)
    vals, w = [], np.zeros(len(js))
    for i in range(20, len(jv)):
        if cv[i] > 30 and np.all(cv[i - 20:i] <= 30):
            k = int(np.searchsorted(js, jv[i]))
            if k + 21 < len(js) and js[k] == jv[i]:
                vals.append(spy["c"][k + 20] / spy["o"][k + 1] - 1)
                w[k:k + 20] = 1
    base = np.nanmean([spy["c"][k + 20] / spy["o"][k + 1] - 1 for k in range(len(js) - 21)])
    note(F.question("   E07 S&P 20 jours après un VIX > 30, moins la moyenne", np.array(vals) - base, 1))
    juge_serie("E07b S&P acheté 20 jours après chaque VIX > 30", js, SP.rendement_position(spy, w * SP.taille_vol(spy), 0.0002),
               js, SP.rendement_position(spy, SP.taille_vol(spy), 0.0002), poids=w)
    # courbe des taux, crédit
    print("   courbe des taux et écart de crédit (S&P tenu seulement quand le signal est favorable)")
    jr, vr = SP.lire_fred(os.path.join(MACRO, "T10Y2Y.csv"), 1)
    pente = SP.aligner(js, jr, vr)
    w = np.where(np.isfinite(pente) & (pente >= 0), 1.0, 0.0)
    nv = SP.rendement_position(spy, SP.taille_vol(spy), 0.0002)
    juge_serie("E08 S&P seulement si la courbe 10 ans − 2 ans n'est pas inversée", js,
               SP.rendement_position(spy, w * SP.taille_vol(spy), 0.0002), js, nv, poids=w)
    jc, vc = SP.lire_fred(os.path.join(MACRO, "BAA10Y.csv"), 1)
    ec = SP.aligner(js, jc, vc)
    m252 = np.array([np.nanmean(ec[max(0, i - 251):i + 1]) for i in range(len(ec))])
    w = np.where(np.isfinite(ec) & (ec < m252), 1.0, 0.0)
    juge_serie("E09 S&P seulement si l'écart de crédit (BAA − 10 ans) est sous sa moyenne d'un an", js,
               SP.rendement_position(spy, w * SP.taille_vol(spy), 0.0002), js, nv, poids=w)


def quantpedia():
    """Stratégies gratuites de Quantpedia applicables à nos marchés et jamais testées (fiches #0083, #0096, #0100,
    #0102, #0113, #0198, #0419, #0753)."""
    print("\nF) Stratégies de Quantpedia applicables à nos marchés")
    spy = F.yahoo_brut(EXTRA, "SPY", "indices")
    js = F.jours_de(spy)
    dates = [dt.date(1970, 1, 1) + dt.timedelta(days=int(x)) for x in js]
    r = np.r_[0.0, spy["c"][1:] / spy["c"][:-1] - 1]
    nv = SP.rendement_position(spy, SP.taille_vol(spy), 0.0002)
    # veille de jour férié (S&P) : jours ouvrés suivis d'un trou de plus de 3 jours ou d'un jour férié en semaine
    veille = np.zeros(len(js), bool)
    for i in range(len(js) - 1):
        ecart = js[i + 1] - js[i]
        if ecart > 3 or (ecart == 2 and dates[i].weekday() < 4) or (ecart == 4):
            veille[i] = True
    note(question("   F1 S&P la veille d'un jour férié (#0083), moins un jour ordinaire", r[veille] - r[~veille].mean(), 4,
                  js[veille]))
    # semaine d'expiration (3e vendredi)
    def troisieme_vendredi(a, m):
        x = dt.date(a, m, 15)
        return x + dt.timedelta(days=(4 - x.weekday()) % 7)
    opex = np.array([dates[i].isocalendar()[:2] == troisieme_vendredi(dates[i].year, dates[i].month).isocalendar()[:2]
                     for i in range(len(js))])
    note(question("   F2 S&P la semaine d'expiration des options (#0102), moins le reste", r[opex] - r[~opex].mean(), 4,
                  js[opex]))
    # jour de paie : du 1er au 3 et du 15 au 17
    paie = np.array([x.day in (1, 2, 3, 15, 16, 17) for x in dates])
    note(question("   F3 S&P autour des jours de paie (#0419), moins le reste", r[paie] - r[~paie].mean(), 4, js[paie]))
    # baromètre de janvier
    w = np.zeros(len(js))
    for an in sorted({x.year for x in dates}):
        sel_j = [i for i, x in enumerate(dates) if x.year == an and x.month == 1]
        reste = [i for i, x in enumerate(dates) if x.year == an and x.month > 1]
        if sel_j and reste and spy["c"][sel_j[-1]] > spy["c"][sel_j[0] - 1 if sel_j[0] else 0]:
            w[reste[0] - 1:reste[-1]] = 1
    juge_serie("F4 S&P de février à décembre seulement si janvier a monté (#0113)", js,
               SP.rendement_position(spy, w * SP.taille_vol(spy), 0.0002), js, nv, poids=w)
    # pétrole et actions (Driesprong, Jacobsen, Maat 2008) : le mois suivant une hausse du pétrole, pas d'actions
    oil = R.yahoo().get("CLF") or F.yahoo_brut(YAHOO, "CLF", "énergie")
    jo = F.jours_de(oil)
    w = np.zeros(len(js))
    etat = 1.0
    for i in range(1, len(js)):
        if dates[i].month != dates[i - 1].month:
            k = int(np.searchsorted(jo, js[i - 1], side="right")) - 1
            k0 = int(np.searchsorted(jo, js[i - 1] - 30, side="right")) - 1
            if k > 0 and k0 > 0:
                etat = 0.0 if oil["c"][k] > oil["c"][k0] else 1.0
        w[i] = etat
    juge_serie("F5 S&P seulement le mois qui suit une baisse du pétrole (#0096)", js,
               SP.rendement_position(spy, w * SP.taille_vol(spy), 0.0002), js, nv, poids=w)
    # écart WTI / Brent
    tous = R.yahoo()
    if "CLF" in tous and "BZF" in tous:
        j_, r_, n_ = SP.paire(tous["CLF"], tous["BZF"], cout=0.0005)
        ok = np.flatnonzero(r_ != 0)
        print(f"   F6 écart WTI / Brent en score z (#0100) : {n_} trades ; Sharpe moitiés "
              f"{M.sharpe(r_[j_ < j_[len(j_) // 2]]):+.2f} / {M.sharpe(r_[j_ >= j_[len(j_) // 2]]):+.2f}")
        note({"regle": "F6 écart WTI / Brent", "sharpe": [round(M.sharpe(r_[j_ < j_[len(j_) // 2]]), 3),
              round(M.sharpe(r_[j_ >= j_[len(j_) // 2]]), 3)], "sharpe_total": round(M.sharpe(r_), 3),
              "jours": int(len(r_)), "permis": False})
    # structure du VIX : S&P tenu quand le VIX est sous le VIX à 3 mois (marché calme)
    vix, v3 = F.yahoo_brut(EXTRA, "VIX", "indices"), F.yahoo_brut(EXTRA, "VIX3M", "indices")
    a_ = SP.aligner(js, F.jours_de(vix), vix["c"])
    b_ = SP.aligner(js, F.jours_de(v3), v3["c"])
    w = np.where(np.isfinite(a_) & np.isfinite(b_) & (a_ < b_), 1.0, 0.0)
    juge_serie("F7 S&P seulement si VIX < VIX 3 mois (#0198, structure)", js,
               SP.rendement_position(spy, w * SP.taille_vol(spy), 0.0002), js, nv, poids=w)
    # saisonnalité horaire du bitcoin (appris sur 2 ans, joué l'année suivante)
    d1 = D.charger_binance(BINANCE, "BTCUSDT", "1h")
    hr = (d1["ts"] // 3_600_000) % 24
    an = np.array([(dt.date(1970, 1, 1) + dt.timedelta(days=int(x))).year for x in F.jours_de(d1)])
    r1 = d1["c"] / d1["o"] - 1
    rend = np.zeros(len(r1))
    for a in range(int(an.min()) + 2, int(an.max()) + 1):
        app = (an >= a - 2) & (an < a)
        for h_ in range(24):
            x = r1[app & (hr == h_)]
            if len(x) > 50 and abs(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) >= 2:
                sel = (an == a) & (hr == h_)
                rend[sel] = np.sign(x.mean()) * r1[sel] - 0.0006
    j, p = M.par_jour(d1["ts"], rend)
    s1, s2 = M.sharpe(p[j < j[len(j) // 2]]), M.sharpe(p[j >= j[len(j) // 2]])
    print(f"   F8 bitcoin, heures choisies sur les 2 années précédentes (#0753) : {s1:+.2f} / {s2:+.2f} "
          f"{'✅' if s1 > 0 and s2 > 0 else '✖'}")
    note({"regle": "F8 saisonnalité horaire du bitcoin", "sharpe": [round(s1, 3), round(s2, 3)],
          "sharpe_total": round(M.sharpe(p), 3), "jours": int(len(p)), "permis": False})


# ============================================================================ G. idées des grands investisseurs
def _combine(series_poids):
    """Somme pondérée de séries de rendements quotidiens [(jours, rendements, poids)] sur les jours communs."""
    communs = None
    for j, _, _ in series_poids:
        communs = set(j.tolist()) if communs is None else communs & set(j.tolist())
    jours = np.array(sorted(communs))
    p = np.zeros(len(jours))
    for j, r, w in series_poids:
        p += w * r[np.searchsorted(j, jours)]
    return jours, p


def grands_investisseurs():
    """Portefeuille « All Weather » de Dalio (30 % actions, 40 % obligations longues, 15 % moyennes, 7,5 % or,
    7,5 % matières premières), sa version à parité de risque, le 60/40 ; bulles de Grantham (sortie à 2 écarts-types
    au-dessus de la tendance de 10 ans, retour sous la tendance)."""
    print("\nG) Idées des grands investisseurs encore jamais testées")
    spy, gld = F.yahoo_brut(EXTRA, "SPY", "indices"), F.yahoo_brut(EXTRA, "GLD", "métaux")
    zb, zn = F.yahoo_brut(EXTRA, "ZBF", "obligations"), F.yahoo_brut(EXTRA, "ZNF", "obligations")
    oil = R.yahoo().get("CLF") or F.yahoo_brut(YAHOO, "CLF", "énergie")
    js = F.jours_de(spy)
    nv = SP.rendement_position(spy, SP.taille_vol(spy), 0.0002)
    actifs = (spy, zb, zn, gld, oil)
    frais = (0.0002, 0.0002, 0.0002, 0.0004, 0.0005)
    fixe = [(F.jours_de(d), SP.rendement_position(d, np.ones(len(d["c"])), f)) for d, f in zip(actifs, frais)]
    for nom, poids in (("G1 All Weather de Dalio (30/40/15/7,5/7,5)", (0.30, 0.40, 0.15, 0.075, 0.075)),
                       ("G1c 60/40 (actions / obligations à 10 ans), référence", (0.60, 0.0, 0.40, 0.0, 0.0))):
        j, p = _combine([(a, r, w) for (a, r), w in zip(fixe, poids) if w])
        juge_serie(nom, j, p, js, nv)
    vol = [(F.jours_de(d), SP.rendement_position(d, SP.taille_vol(d), f)) for d, f in zip(actifs, frais)]
    j, p = _combine([(a, r, 0.2) for a, r in vol])
    juge_serie("G1b parité de risque sur les mêmes 5 actifs (10 % de vol. chacun)", j, p, js, nv)
    for nom, d, f in (("S&P 500 (SPY)", spy, 0.0002), ("or (GLD)", gld, 0.0004)):
        c = d["c"]
        lc = np.log(c)
        n = len(c)
        w = np.ones(n)
        dedans = True
        x = np.arange(2520, dtype=float)
        for i in range(2520, n):
            y = lc[i - 2519:i + 1]
            a_, b_ = np.polyfit(x, y, 1)
            res = y - (a_ * x + b_)
            z = res[-1] / res.std()
            if dedans and z >= 2:
                dedans = False
            elif not dedans and z <= 0:
                dedans = True
            w[i] = 1.0 if dedans else 0.0
        w[:2520] = 0.0
        j = F.jours_de(d)
        juge_serie(f"G2 bulle de Grantham, {nom} : dehors à +2 écarts-types de la tendance 10 ans", j,
                   SP.rendement_position(d, w * SP.taille_vol(d), f), j, SP.rendement_position(d, SP.taille_vol(d), f),
                   poids=w)
    # « Soyez craintif quand les autres sont avides » (Buffett) : indice peur et avidité du bitcoin (alternative.me,
    # publié chaque jour à 0 h UTC pour la veille ; utilisé à la clôture du jour qu'il porte, joué le lendemain)
    chemin = os.path.join(MACRO, "fng.json")
    if os.path.exists(chemin):
        fng = sorted((int(x["timestamp"]) // 86400, float(x["value"])) for x in json.load(open(chemin))["data"])
        btc = R.yahoo()["BTC-USD"]
        jb = F.jours_de(btc)
        jf, vf = np.array([a for a, _ in fng]), np.array([b for _, b in fng])
        k = np.searchsorted(jf, jb, side="right") - 1
        val = np.where(k >= 0, vf[np.clip(k, 0, None)], np.nan)
        val[jb < jf[0]] = np.nan
        frais_b = MM.FRAIS_DEFAUT["crypto"]
        nv_b = SP.rendement_position(btc, np.where(np.isfinite(val), 1.0, 0.0) * SP.taille_vol(btc), frais_b)
        for nom, entree, sortie in (("G3 bitcoin acheté sous 25 (peur extrême), vendu au-dessus de 75", 25, 75),
                                    ("G3b bitcoin tenu sauf au-dessus de 75 (avidité extrême), repris sous 50", None, 75)):
            w = np.zeros(len(jb))
            dedans = entree is None
            for i in range(len(jb)):
                if not np.isfinite(val[i]):
                    continue
                if not dedans and ((entree is not None and val[i] < entree) or (entree is None and val[i] < 50)):
                    dedans = True
                elif dedans and val[i] > sortie:
                    dedans = False
                w[i] = 1.0 if dedans else 0.0
            juge_serie(nom, jb, SP.rendement_position(btc, w * SP.taille_vol(btc), frais_b), jb, nv_b, poids=w)


if __name__ == "__main__":
    regles()
    propres = R.yahoo()
    eq = MM.banc(propres, strategies=("momentum_12m", "toujours_acheter"), sorties=MM.SORTIES, serie=True)
    je, pe = map(np.asarray, eq["momentum_12m"]["serie"])
    jn, pn = map(np.asarray, eq["toujours_acheter"]["serie"])
    print("\nB) EWMAC de Carver (4 vitesses, prévisions à l'échelle), 25 marchés")
    j, p = portefeuille_poids(propres, ewmac)
    juge_serie("B1 EWMAC achat et vente", j, p, jn, pn, je, pe)
    j, p = portefeuille_poids(propres, lambda d: ewmac(d, achat_seul=True))
    juge_serie("B2 EWMAC achat seul", j, p, jn, pn, je, pe)
    print("\nC) Pyramidage des Turtles (système 1 acheteur avec filtre, fiche H01)")
    for nom, f in (("C1 sans pyramidage (référence R7)", lambda d, k: F.turtles_s1_filtre(d, k, achat_seul=True)),
                   ("C2 avec pyramidage (4 unités, +½ N)", turtles_pyramide)):
        ser = {s: (F.jours_de(d), f(d, MM.FRAIS_DEFAUT.get(d["famille"], 0.0005))[0], d["famille"])
               for s, d in propres.items()}
        j, p = M.portefeuille(ser)
        juge_serie(nom, j, p, jn, pn, je, pe)
    print("\nD) Sélections entre marchés (le tiers au meilleur score, revu chaque mois ; inversion : chaque semaine)")
    for nom, sc, rb in (("D1 valeur (plus faible rendement sur 5 ans)", score_valeur, "mois"),
                        ("D2 faible volatilité", score_faible_vol, "mois"), ("D3 faible bêta", score_faible_beta, "mois"),
                        ("D4 proche du plus haut de 52 semaines", score_52s, "mois"),
                        ("D5 inversion d'une semaine", score_inversion, "semaine"),
                        ("D6 asymétrie la plus négative", score_asymetrie, "mois")):
        j, p = croisee(propres, sc, rb)
        juge_serie(nom, j, p, jn, pn, je, pe)
    for nom, sc, univers in (("D7 valeur et momentum ensemble", score_valeur_momentum, propres),
                             ("D8 saisonnalité croisée (même mois des 5 années passées)", score_saison_croisee, propres),
                             ("D9 valeur des devises seules (5 ans)", score_valeur,
                              {s: d for s, d in propres.items() if d["famille"] == "forex"})):
        j, p = croisee(univers, sc, "mois")
        if univers is propres:
            juge_serie(nom, j, p, jn, pn, je, pe)
        else:
            b_ = MM.banc(univers, strategies=("momentum_12m", "toujours_acheter"), sorties=MM.SORTIES, serie=True)
            juge_serie(nom, j, p, *map(np.asarray, b_["toujours_acheter"]["serie"]),
                       *map(np.asarray, b_["momentum_12m"]["serie"]))
    evenements()
    quantpedia()
    grands_investisseurs()
    print(f"\n{len(ESSAIS)} essais R8 comptés ; permis : "
          + (", ".join(e["regle"] + (" " + e.get("unite", "") if e.get("unite") else "") for e in ESSAIS if e.get("permis")) or "aucun"))
    for e in ESSAIS:
        if e.get("permis") and e.get("sharpe_total") is not None:
            for n_e in (251 + len(ESSAIS),):
                prob, sr0 = M.sharpe_degonfle(e["sharpe_total"], n_e, 252 / e["jours"], e["jours"], e.get("asym", 0.0),
                                              e.get("aplat", 3.0))
                print(f"   {e['regle'][:56]:56} Sharpe {e['sharpe_total']:+.2f} ; dégonflé sur {n_e} essais : {prob * 100:.0f} %")
    if len(sys.argv) > 6:
        json.dump(ESSAIS, open(sys.argv[6], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
