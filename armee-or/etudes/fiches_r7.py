"""R7 (25/10/2026) : les fiches H01 à H21 testées TELLES QU'ELLES ONT ÉTÉ ÉCRITES en R3 (armee_or/hypotheses.json),
réglages manquants fixés ici une fois pour toutes (« parametres_a_formaliser »), avant les tests.

Or journalier : fonds GLD (2004-2026, données « bonnes » au contrôleur), argent : SLV ; or intraday : PAXGUSDT
(jours ouvrés) ; euro-dollar intraday : EURUSDT ; taux réel 10 ans (DFII10), dollar large (DTWEXBGS) : FRED, connus
le lendemain (30 h pour le taux réel : le Trésor publie après la clôture) ; COT : CFTC, connu le lundi suivant.
Questions « le rendement suivant est-il différent ? » : moyenne, statistique t, seuil de Bonferroni pour la famille.

Usage : python etudes/fiches_r7.py BINANCE YAHOO YAHOO_EXTRA MACRO RACINE_ARMEE
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
import donnees_r7 as D        # noqa: E402
import moteur_r7 as M         # noqa: E402
import speciales_r7 as SP     # noqa: E402
from armee_or import marches as MM   # noqa: E402
from charger import charger          # noqa: E402

FRAIS_OR = 0.0003
JOUR = 86_400_000


def yahoo_brut(dossier, nom, famille):
    r = json.load(open(os.path.join(dossier, nom + ".json")))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    rows = [(t, o, h, l, c) for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"])
            if None not in (o, h, l, c) and min(o, h, l, c) > 0 and l <= min(o, c) and h >= max(o, c)]
    a = np.array(rows, dtype=float)
    return {"ts": (a[:, 0] * 1000).astype(np.int64), "o": a[:, 1], "h": a[:, 2], "l": a[:, 3], "c": a[:, 4],
            "v": np.zeros(len(a)), "vb": np.zeros(len(a)), "famille": famille,
            "cout": MM.couts({}, famille, a[-1, 4])}


def jours_de(d):
    return d["ts"] // JOUR


def date_de(j):
    return dt.date(1970, 1, 1) + dt.timedelta(days=int(j))


def ligne(nom, rend, jours, naif=None, trades=None, note=""):
    s1, s2, coupe = M.moities(jours, rend)
    txt = f"{nom:60} | {s1:+.2f} / {s2:+.2f}"
    ok = s1 > 0 and s2 > 0
    if naif is not None:
        n1, n2 = M.sharpe(naif[jours < coupe]), M.sharpe(naif[jours >= coupe])
        txt += f" | naïf {n1:+.2f} / {n2:+.2f}"
        ok = ok and s1 > n1 and s2 > n2
    if trades is not None:
        txt += f" | {trades} trades"
        ok = ok and trades >= 2 * M.MIN_TRADES
    print(txt + f" | {'✅ PERMIS' if ok else '✖'} {note}", flush=True)
    return {"regle": nom, "sharpe": [round(s1, 3), round(s2, 3)], "permis": bool(ok)}


def question(nom, valeurs, n_tests, note=""):
    """Moyenne d'un rendement conditionnel, t de Student, seuil de Bonferroni pour n_tests tests (5 %)."""
    from statistics import NormalDist
    x = np.asarray([v for v in valeurs if np.isfinite(v)])
    if len(x) < 10:
        print(f"{nom:60} | {len(x)} cas : trop peu")
        return {"regle": nom, "cas": int(len(x))}
    t = x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))
    seuil = NormalDist().inv_cdf(1 - 0.025 / n_tests)
    print(f"{nom:60} | {len(x)} cas, moyenne {x.mean() * 100:+.3f} %, t = {t:+.2f} (seuil {seuil:.2f}) "
          f"{'✅ significatif' if abs(t) >= seuil else '✖ rien'} {note}", flush=True)
    return {"regle": nom, "cas": int(len(x)), "moyenne": float(x.mean()), "t": float(t), "seuil": float(seuil)}


def naif_or(d):
    return SP.rendement_position(d, SP.taille_vol(d), FRAIS_OR)


# ============================================================================ H01 : Turtles avec le filtre
def turtles_s1_filtre(d, cout, entree=20, sortie_n=10, secours=55, bougies_jour=1, filtre=True, stop_niveau=False,
                      achat_seul=False):
    """Système 1 : cassure de 20 jours, SAUTÉE si la cassure précédente (prise ou non) aurait gagné ; la cassure de
    55 jours est toujours prise (règle de secours) ; stop 2 N (ATR 20) ; sortie à la cassure opposée de 10 jours.
    Entrée au niveau de cassure (au pire à l'ouverture), risque 0,5 % du capital à 2 N."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 20)
    n = len(c)
    jours = jours_de(d)
    hh, ll = C.fen_max(h, entree), C.fen_min(l, entree)
    h55 = C.fen_max(h, secours) if secours else np.full(n, np.inf)
    l55 = C.fen_min(l, secours) if secours else np.full(n, -np.inf)
    hs, ls = C.fen_max(h, sortie_n), C.fen_min(l, sortie_n)
    rend = np.zeros(n)
    trades = 0
    dernier_gagnant = False
    fictif = None                                                 # cassure sautée suivie « pour voir »
    pos = None                                                    # (sens, entrée, stop, taille, réf)
    for i in range(max(entree, sortie_n, secours or 0) + 1, n):
        N = a[i - 1]
        if not np.isfinite(N) or N <= 0:
            continue
        if fictif is not None:                                    # résultat de la cassure sautée
            s, e, st = fictif
            if (s > 0 and (l[i] <= st or l[i] <= ls[i - 1])) or (s < 0 and (h[i] >= st or h[i] >= hs[i - 1])):
                px = st if (s > 0 and l[i] <= st) or (s < 0 and h[i] >= st) else (ls[i - 1] if s > 0 else hs[i - 1])
                dernier_gagnant = s * (px - e) > 0
                fictif = None
        if pos is not None:
            s, e, st, w, ref = pos
            sortie = None
            if s > 0 and l[i] <= max(st, ls[i - 1]):
                sortie = min(o[i], max(st, ls[i - 1]))
            elif s < 0 and h[i] >= min(st, hs[i - 1]):
                sortie = max(o[i], min(st, hs[i - 1]))
            if sortie is not None:
                rend[i] += w * s * (sortie / ref - 1) - w * cout / 2
                dernier_gagnant = s * (sortie - e) > 0
                pos = None
            else:
                r_ = w * s * (c[i] / ref - 1)
                if i + 1 < n and jours[i + 1] != jours[i]:            # financement jour calendaire (week-ends compris)
                    r_ -= w * M.FINANCEMENT / 365 * (jours[i + 1] - jours[i])
                rend[i] += r_
                pos = (s, e, st, w, c[i])
            continue
        haut, bas = h[i] >= hh[i - 1], l[i] <= ll[i - 1] and not achat_seul
        if not (haut or bas):
            continue
        s = 1 if haut and (not bas or hh[i - 1] - o[i] <= o[i] - ll[i - 1]) else -1
        e = max(o[i], hh[i - 1]) if s > 0 else min(o[i], ll[i - 1])
        base_stop = (hh[i - 1] if s > 0 else ll[i - 1]) if stop_niveau else e   # 2 N depuis l'entrée (règle) ou
        st = base_stop - 2 * N if s > 0 else base_stop + 2 * N                 # depuis le niveau de cassure
        cas_55 = (s > 0 and h[i] >= h55[i - 1]) or (s < 0 and l[i] <= l55[i - 1])
        if fictif is not None and not cas_55:                     # cassure sautée encore en cours : seule la
            continue                                              # cassure de 55 jours (secours) est prise
        if filtre and dernier_gagnant and not cas_55:
            fictif = (s, e, st)
            dernier_gagnant = False
            continue
        w = min(M.RISQUE / (2 * N / e), M.LEVIER_MAX)
        trades += 1
        if (s > 0 and l[i] <= st) or (s < 0 and h[i] >= st):           # stop touché le jour même (prudent)
            rend[i] += w * s * (st / e - 1) - w * cout
            dernier_gagnant = False
            continue
        rend[i] += w * s * (c[i] / e - 1) - w * cout / 2
        if i + 1 < n and jours[i + 1] != jours[i]:
            rend[i] -= w * M.FINANCEMENT / 365 * (jours[i + 1] - jours[i])
        pos = (s, e, st, w, c[i])
    return rend, trades


def turtles_cloture(d, cout, entree=20, sortie_n=10, secours=55, filtre=True):
    """Système 1 ACHETEUR, exécutable par l'équipe telle qu'elle trade : décision à la CLÔTURE (clôture au-dessus du
    plus haut des 20 jours précédents), achat à l'ouverture suivante ; stop 2 N posé chez le courtier (touché dans la
    journée) ; sortie à l'ouverture qui suit une clôture sous le plus bas des 10 jours précédents ; filtre « sauter
    après un gain » (sauf cassure de 55 jours), la cassure sautée étant suivie pour savoir si elle aurait gagné."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 20)
    n = len(c)
    jours = jours_de(d)
    ph, pb = M.plus_haut(h, entree), M.plus_bas(l, sortie_n)
    p55 = M.plus_haut(h, secours) if secours else np.full(n, np.inf)
    rend = np.zeros(n)
    trades, gagnant, fictif, pos = 0, False, None, None
    for i in range(max(entree, sortie_n, secours or 0) + 1, n - 1):
        if fictif is not None:                                    # cassure sautée : aurait-elle gagné ?
            e_f, st_f = fictif
            if l[i] <= st_f:
                gagnant, fictif = st_f > e_f, None
            elif c[i] < pb[i]:
                gagnant, fictif = o[i + 1] > e_f, None
        if pos is not None:
            e, st, w, ref = pos
            if l[i] <= st:                                        # stop chez le courtier
                px = min(o[i], st)
                rend[i] += w * (px / ref - 1) - w * cout / 2
                gagnant, pos = px > e, None
                continue
            r_ = w * (c[i] / ref - 1)
            if jours[i + 1] != jours[i]:
                r_ -= w * M.FINANCEMENT / 365 * (jours[i + 1] - jours[i])
            rend[i] += r_
            if c[i] < pb[i]:                                      # sortie à l'ouverture suivante
                rend[i + 1] += w * (o[i + 1] / c[i] - 1) - w * cout / 2
                gagnant, pos = o[i + 1] > e, None
            else:
                pos = (e, st, w, c[i])
            continue
        N = a[i]
        if not (np.isfinite(N) and N > 0 and np.isfinite(ph[i]) and c[i] > ph[i]):
            continue
        e = o[i + 1]
        st = e - 2 * N
        if fictif is not None and not c[i] > p55[i]:
            continue
        if filtre and gagnant and not c[i] > p55[i]:
            fictif, gagnant = (e, st), False
            continue
        w = min(M.RISQUE / (2 * N / e), M.LEVIER_MAX)
        trades += 1
        rend[i + 1] -= w * cout / 2
        pos = (e, st, w, e)
    return rend, trades


# ============================================================================ H02, H07, H14 : règles écrites
def h02_livermore_ecrite(d, k=20, x=4.0):
    """Consolidation de 20 bougies d'amplitude < 4 ATR, puis clôture au-dessus (nouveau plus haut de 52 semaines),
    confirmée par la clôture suivante → achat ; stop sous la consolidation ; sortie au plus bas de 20 jours."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    n = len(c)
    s, sl = np.zeros(n), np.full(n, np.nan)
    ph, pb = M.plus_haut(h, k), M.plus_bas(l, k)
    h52 = M.plus_haut(h, 252)
    for i in range(253, n - 1):
        if not np.isfinite(a[i - 1]):
            continue
        if ph[i] - pb[i] < x * a[i - 1] and c[i] > ph[i] and c[i] >= h52[i]:
            if c[i + 1] > ph[i]:                                  # confirmée par la clôture suivante
                s[i + 1], sl[i + 1] = 1, pb[i]
    return {"sens": s, "stop": sl, "sortie": np.where(c < M.plus_bas(l, 20), 1, 0)}


def h07_wyckoff_ecrite(d):
    """Fausse cassure du bas d'un range (40 bougies d'amplitude ≤ 6 ATR), réintégrée en 1 ou 2 bougies → achat ;
    stop sous la mèche ; objectif le haut du range. Upthrust : symétrique."""
    h, l, c = d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    n = len(c)
    ph, pb = M.plus_haut(h, 40), M.plus_bas(l, 40)
    s, sl, sc, cl, cc = np.zeros(n), np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    for i in range(41, n - 2):
        if not np.isfinite(a[i]) or ph[i] - pb[i] > 6 * a[i]:
            continue
        if l[i] < pb[i]:
            for j in (i, i + 1):
                if c[j] > pb[i]:
                    s[j], sl[j], cl[j] = 1, min(l[i:j + 1]), ph[i]
                    break
        elif h[i] > ph[i]:
            for j in (i, i + 1):
                if c[j] < ph[i]:
                    s[j], sc[j], cc[j] = -1, max(h[i:j + 1]), pb[i]
                    break
    return {"sens": s, "stop_l": sl, "stop_c": sc, "cible_l": cl, "cible_c": cc}


def h14_range_ecrite(d):
    """ADX < 20 : vendre la bande haute, acheter la bande basse, sortie à la moyenne (sans stop, comme écrit)."""
    h, l, c = d["h"], d["l"], d["c"]
    x, _, _ = M.adx(h, l, c, 14)
    m, haut, bas = M.bollinger(c, 20, 2.0)
    achat, vente = (x < 20) & (c < bas), (x < 20) & (c > haut)
    return {"sens": np.where(achat, 1, np.where(vente, -1, 0)), "cible_l": m, "cible_c": m}


def h19_londres_nr4(d):
    """Fourchette de la 1re heure de Londres (7 h-8 h UTC) ; ordres à la sortie (le premier touché), stop au bord
    opposé, sortie à 16 h UTC ; seulement les jours qui suivent une journée NR4 (la plus étroite des 4 dernières)."""
    hh, ll, m = C._plage(d, 420, 480)
    _, j = C.minutes_utc(d["ts"])
    debut = np.flatnonzero(np.r_[True, j[1:] != j[:-1]])
    fin = np.r_[debut[1:], len(j)]
    amp = np.array([d["h"][a:b].max() - d["l"][a:b].min() for a, b in zip(debut, fin)])
    nr4 = np.zeros(len(j), bool)
    for k in range(4, len(debut)):
        nr4[debut[k]:fin[k]] = amp[k - 1] <= amp[k - 4:k].min()
    fen = (m >= 480) & (m < 960) & nr4
    premier = fen & np.isfinite(hh) & np.r_[True, ~fen[:-1] | (j[1:] != j[:-1])]
    return {"sens": np.where(premier, 2, 0), "entree_l": hh, "entree_c": ll, "stop_l": ll, "stop_c": hh,
            "validite": 32, "sortie": np.where(m >= 960, 2, 0)}


def motifs_haussiers(d):
    """Les cinq motifs haussiers, BRUTS (sans le filtre de tendance des règles V34 à V38) : mêmes définitions."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    a = M.atr(h, l, c, 14)
    po, pc = np.r_[np.nan, o[:-1]], np.r_[np.nan, c[:-1]]
    corps = np.abs(c - o) + 1e-12
    o2, c2 = np.r_[np.nan, np.nan, o[:-2]], np.r_[np.nan, np.nan, c[:-2]]
    doji = np.abs(c - o) <= 0.1 * (h - l + 1e-12)
    hb = (c > o) & (h - c <= 0.3 * (h - l + 1e-12)) & np.r_[False, c[1:] > c[:-1]]
    return {"avalement": (pc < po) & (c > o) & (c >= po) & (o <= pc),
            "marteau": (np.minimum(o, c) - l >= 2 * corps) & (h - np.maximum(o, c) <= corps),
            "étoile du matin": (np.abs(c2 - o2) > 0.6 * a) & (c2 < o2) & (np.abs(pc - po) < 0.3 * a) &
                               (np.abs(c - o) > 0.6 * a) & (c > o) & (c > (o2 + c2) / 2),
            "doji confirmé": np.r_[False, doji[:-1]] & (c > np.r_[np.nan, h[:-1]]),
            "trois soldats": hb & np.r_[False, hb[:-1]] & np.r_[False, False, hb[:-2]]}


def moteur(d, regle, cout, par_an=252):
    rend, tr = M.backtest(d["o"], d["h"], d["l"], d["c"], regle, cout, jours=jours_de(d), bougies_par_an=par_an)
    j, p = M.par_jour(d["ts"], rend)
    return j, p, len(tr)


def portefeuille(series):
    return M.portefeuille(series)


if __name__ == "__main__":
    tous = charger(YAHOO, MM)
    gld = yahoo_brut(EXTRA, "GLD", "métaux")
    slv = yahoo_brut(EXTRA, "SLV", "métaux")
    paxg5 = D.charger_binance(BINANCE, "PAXGUSDT", "5m")
    eur5 = D.charger_binance(BINANCE, "EURUSDT", "5m")
    for x in (paxg5, eur5):
        g = D.jour_semaine(x["ts"]) < 5
        for k in list(x):
            x[k] = x[k][g]
    import recherche_r7 as R
    R.BINANCE, R.YAHOO, R.MACRO = BINANCE, YAHOO, MACRO
    propres = R.yahoo()
    jg = jours_de(gld)
    ng = naif_or(gld)
    out = []

    print("H01 Turtles, telles qu'écrites (filtre « sauter après un gain », secours 55 jours), 25 marchés journaliers")
    eq = MM.banc(propres, strategies=("momentum_12m", "toujours_acheter"), sorties=MM.SORTIES, serie=True)
    je, pe = map(np.asarray, eq["momentum_12m"]["serie"])
    jn, pn = map(np.asarray, eq["toujours_acheter"]["serie"])
    noms = sorted(propres)

    def batterie(nom_v, fonction, complet=True):
        """Permis, frais, paniers, périodes, corrélation, Sharpe dégonflé : la batterie complète d'une version."""
        frais = {s: MM.FRAIS_DEFAUT.get(d["famille"], 0.0005) for s, d in propres.items()}
        res = {s: fonction(d, frais[s]) for s, d in propres.items()}
        ser = {s: (jours_de(d), res[s][0], d["famille"]) for s, d in propres.items()}
        jv, pv = portefeuille(ser)
        ct = jv[len(jv) // 2]
        sh = lambda j_, p_: (M.sharpe(p_[j_ < ct]), M.sharpe(p_[j_ >= ct]))
        v, nv_, ev = sh(jv, pv), sh(jn, pn), sh(je, pe)
        permis = v[0] > max(0, nv_[0]) and v[1] > max(0, nv_[1])
        bat_e = v[0] > ev[0] and v[1] > ev[1]
        print(f"   {nom_v:52} {v[0]:+.2f} / {v[1]:+.2f} (naïf {nv_[0]:+.2f} / {nv_[1]:+.2f} ; équipe {ev[0]:+.2f} / "
              f"{ev[1]:+.2f}) ; {sum(r[1] for r in res.values())} trades ; {'✅ PERMIS' if permis else '✖'}"
              f"{' · bat l’équipe' if bat_e else ''}", flush=True)
        ligne_ = {"regle": "H01 " + nom_v, "sharpe": [round(v[0], 3), round(v[1], 3)], "permis": bool(permis),
                  "bat_equipe": bool(bat_e)}
        if not complet:
            return ligne_
        for f_ in (2.0, 3.0):
            jf_, pf_ = portefeuille({s: (jours_de(d), fonction(d, frais[s] * f_)[0], d["famille"])
                                     for s, d in propres.items()})
            x = sh(jf_, pf_)
            print(f"      frais × {f_:g} : {x[0]:+.2f} / {x[1]:+.2f}")
        sans = [s for s in noms if propres[s]["famille"] != "crypto"]
        js_, ps_ = portefeuille({s: ser[s] for s in sans})
        b_s = MM.banc({s: propres[s] for s in sans}, strategies=("momentum_12m", "toujours_acheter"),
                      sorties=MM.SORTIES, serie=True)
        x, y, z = sh(js_, ps_), sh(*map(np.asarray, b_s["momentum_12m"]["serie"])), \
            sh(*map(np.asarray, b_s["toujours_acheter"]["serie"]))
        print(f"      sans cryptos : {x[0]:+.2f} / {x[1]:+.2f} (équipe {y[0]:+.2f} / {y[1]:+.2f} ; naïf "
              f"{z[0]:+.2f} / {z[1]:+.2f})")
        rng = np.random.default_rng(13)
        bn = be = 0
        for _ in range(200):
            choix = list(rng.choice(noms, size=len(noms) // 2, replace=False))
            a_, b_ = portefeuille({s: ser[s] for s in choix})
            r_ = MM.banc({s: propres[s] for s in choix}, strategies=("momentum_12m", "toujours_acheter"),
                         sorties=MM.SORTIES, serie=True)
            jn_, pn_ = map(np.asarray, r_["toujours_acheter"]["serie"])
            je_, pe_ = map(np.asarray, r_["momentum_12m"]["serie"])
            c_ = a_[len(a_) // 2]
            t1, t2 = M.sharpe(b_[a_ < c_]), M.sharpe(b_[a_ >= c_])
            bn += t1 > M.sharpe(pn_[jn_ < c_]) and t2 > M.sharpe(pn_[jn_ >= c_])
            be += t1 > M.sharpe(pe_[je_ < c_]) and t2 > M.sharpe(pe_[je_ >= c_])
        print(f"      200 sous-paniers : bat le naïf {bn}/200, bat l'équipe {be}/200")
        txt = "      périodes de 5 ans (version / équipe / naïf) :"
        for debut_ in range(2001, 2026, 5):
            a0 = (dt.date(debut_, 1, 1) - dt.date(1970, 1, 1)).days
            b0 = (dt.date(debut_ + 5, 1, 1) - dt.date(1970, 1, 1)).days
            per = lambda j_, p_: M.sharpe(p_[(j_ >= a0) & (j_ < b0)])
            txt += f" {debut_}-{debut_ + 4} {per(jv, pv):+.2f} / {per(je, pe):+.2f} / {per(jn, pn):+.2f} ;"
        print(txt)
        commun = np.intersect1d(jv, je)
        x_, y_ = pv[np.searchsorted(jv, commun)], pe[np.searchsorted(je, commun)]
        mix = 0.5 * x_ / x_.std() + 0.5 * y_ / y_.std()
        print(f"      corrélation avec l'équipe {np.corrcoef(x_, y_)[0, 1]:+.2f} ; moitié + moitié équipe (même risque) "
              f"{M.sharpe(mix[commun < ct]):+.2f} / {M.sharpe(mix[commun >= ct]):+.2f} ; pire baisse à 10 %/an "
              f"{M.pire_baisse(pv) / (pv.std() * 252 ** 0.5) * 10:.1f} % (équipe "
              f"{M.pire_baisse(pe) / (pe.std() * 252 ** 0.5) * 10:.1f} %)")
        t_ = M.sharpe(pv) * (len(pv) / 252) ** 0.5
        txt = f"      Sharpe total {M.sharpe(pv):+.2f} (équipe {M.sharpe(pe):+.2f}), t = {t_:.2f} ; Sharpe dégonflé :"
        for n_e in (22, 251):
            prob, sr0 = M.sharpe_degonfle(M.sharpe(pv), n_e, 252 / len(pv), len(pv), R._moment(pv, 3),
                                          R._moment(pv, 4))
            txt += f" {n_e} essais → {prob * 100:.0f} %"
        print(txt)
        ligne_.update(trades=int(sum(r[1] for r in res.values())))
        return ligne_

    out.append(batterie("système 1, dans la journée, achat et vente, avec filtre", turtles_s1_filtre))
    out.append(batterie("système 1, dans la journée, achat et vente, sans filtre",
                        lambda d, k: turtles_s1_filtre(d, k, filtre=False, secours=None), complet=False))
    out.append(batterie("système 2 (55 / 20), dans la journée, achat et vente",
                        lambda d, k: turtles_s1_filtre(d, k, entree=55, sortie_n=20, filtre=False, secours=None),
                        complet=False))
    out.append(batterie("système 1, dans la journée, ACHAT SEUL, avec filtre",
                        lambda d, k: turtles_s1_filtre(d, k, achat_seul=True)))
    out.append(batterie("système 1, à la CLÔTURE, achat seul, avec filtre", turtles_cloture))
    out.append(batterie("système 1, à la clôture, achat seul, sans filtre",
                        lambda d, k: turtles_cloture(d, k, filtre=False, secours=None), complet=False))
    out.append(batterie("système 1, dans la journée, achat et vente, stop compté depuis la cassure",
                        lambda d, k: turtles_s1_filtre(d, k, stop_niveau=True), complet=False))
    from armee_or import qualite as Q
    fiables = {}
    for s, d in propres.items():
        q = Q.controler(list(zip(d["ts"], d["o"], d["h"], d["l"], d["c"])), famille=d["famille"])
        if q["ouvertures_recopiees"] < 0.10:
            fiables[s] = d
    ef = MM.banc(fiables, strategies=("momentum_12m", "toujours_acheter"), sorties=MM.SORTIES, serie=True)
    jfe, pfe = map(np.asarray, ef["momentum_12m"]["serie"])
    jfn, pfn = map(np.asarray, ef["toujours_acheter"]["serie"])
    print(f"   ouvertures fiables seulement (moins de 10 % recopiées) : {len(fiables)} marchés ; sans "
          f"{', '.join(sorted(set(propres) - set(fiables)))}")
    for nom_v, f_v in (("dans la journée, achat seul, filtre", lambda d, k: turtles_s1_filtre(d, k, achat_seul=True)),
                       ("à la clôture, achat seul, filtre", turtles_cloture)):
        jv, pv = portefeuille({s: (jours_de(d), f_v(d, MM.FRAIS_DEFAUT.get(d["famille"], 0.0005))[0], d["famille"])
                               for s, d in fiables.items()})
        ct = jv[len(jv) // 2]
        print(f"      {nom_v} : {M.sharpe(pv[jv < ct]):+.2f} / {M.sharpe(pv[jv >= ct]):+.2f} (naïf "
              f"{M.sharpe(pfn[jfn < ct]):+.2f} / {M.sharpe(pfn[jfn >= ct]):+.2f} ; équipe "
              f"{M.sharpe(pfe[jfe < ct]):+.2f} / {M.sharpe(pfe[jfe >= ct]):+.2f})")
    series4, tot4 = {}, 0
    for sym, fam in (("PAXGUSDT", "métaux"), ("EURUSDT", "forex"), ("BTCUSDT", "crypto"), ("ETHUSDT", "crypto")):
        d1 = D.charger_binance(BINANCE, sym, "1h")
        if sym in ("PAXGUSDT", "EURUSDT"):
            g = D.jour_semaine(d1["ts"]) < 5
            d1 = {k: v[g] for k, v in d1.items()}
        d4 = D.regrouper(d1, 240)
        cout = {"PAXGUSDT": 0.30 / float(np.median(d4["c"])), "EURUSDT": 0.00012 / float(np.median(d4["c"])),
                "BTCUSDT": 0.0006, "ETHUSDT": 0.0008}[sym]
        r, n = turtles_s1_filtre(d4, cout, bougies_jour=6)
        j, p = M.par_jour(d4["ts"], r)
        series4[sym] = (j, p, fam)
        tot4 += n
    jp4, pp4 = portefeuille(series4)
    nv = R.naif("1h")
    s1, s2, coupe = M.moities(jp4, pp4)
    print(f"{'H01 système 1 avec filtre, 4 h (or, euro, bitcoin, ether)':60} | {s1:+.2f} / {s2:+.2f} | naïf "
          f"{nv['sharpe'][0]:+.2f} / {nv['sharpe'][1]:+.2f} | {tot4} trades | "
          f"{'✅ PERMIS' if s1 > max(0, nv['sharpe'][0]) and s2 > max(0, nv['sharpe'][1]) else '✖'}")
    for nom, regle in (("H01 système 2 (55 / 20), 4 h", C.h01b_turtles_s2),):
        ser = {}
        n_t = 0
        for sym, fam in (("PAXGUSDT", "métaux"), ("EURUSDT", "forex"), ("BTCUSDT", "crypto"), ("ETHUSDT", "crypto")):
            d1 = D.charger_binance(BINANCE, sym, "1h")
            if sym in ("PAXGUSDT", "EURUSDT"):
                g = D.jour_semaine(d1["ts"]) < 5
                d1 = {k: v[g] for k, v in d1.items()}
            d4 = D.regrouper(d1, 240)
            cout = {"PAXGUSDT": 0.30 / float(np.median(d4["c"])), "EURUSDT": 0.00012 / float(np.median(d4["c"])),
                    "BTCUSDT": 0.0006, "ETHUSDT": 0.0008}[sym]
            j, p, n = moteur(d4, regle(d4), cout, par_an=252 * 6)
            ser[sym] = (j, p, fam)
            n_t += n
        jj, ppp = portefeuille(ser)
        a1, a2, _ = M.moities(jj, ppp)
        print(f"{nom:60} | {a1:+.2f} / {a2:+.2f} | naïf {nv['sharpe'][0]:+.2f} / {nv['sharpe'][1]:+.2f} | "
              f"{n_t} trades | {'✅ PERMIS' if a1 > nv['sharpe'][0] and a2 > nv['sharpe'][1] and min(a1, a2) > 0 else '✖'}")

    print("\nH02, H03, H07, H14 telles qu'écrites, or (GLD) et 25 marchés, journalier")
    for nom, f in (("H02 Livermore : consolidation < 4 ATR, nouveau plus haut confirmé", h02_livermore_ecrite),
                   ("H03 Darvas (boîte de 3 jours)", C.h03_darvas),
                   ("H07 Wyckoff : fausse cassure réintégrée en 1 ou 2 bougies", h07_wyckoff_ecrite),
                   ("H14 range : bandes de Bollinger si ADX < 20, sans stop", h14_range_ecrite)):
        series, n_t = {}, 0
        for s, d in propres.items():
            j, p, n = moteur(d, f(d), MM.FRAIS_DEFAUT.get(d["famille"], 0.0005))
            series[s] = (j, p, d["famille"])
            n_t += n
        jp, pp = portefeuille(series)
        pn_al = np.zeros(len(jp))
        pn_al[np.searchsorted(jp, jn)] = pn
        out.append(ligne(nom + ", 25 marchés", pp, jp, pn_al, n_t))
        j, p, n = moteur(gld, f(gld), FRAIS_OR)
        out.append(ligne(nom + ", or GLD", p, j, ng[np.searchsorted(jg, j)], n))

    print("\nH06 règle des 10 mois de Faber (clôture mensuelle > moyenne de 10 mois), acheteur ou neutre")
    series = {}
    for s, d in {**propres, "GLD": gld}.items():
        jd = jours_de(d)
        mois = np.array([date_de(x).year * 12 + date_de(x).month for x in jd])
        fin_mois = np.r_[mois[1:] != mois[:-1], True]
        cl = d["c"][fin_mois]
        m10 = M.sma(cl, 10)
        w = np.zeros(len(jd))
        etat = 0.0
        k = 0
        for i in range(len(jd)):
            if fin_mois[i]:
                etat = 1.0 if np.isfinite(m10[k]) and cl[k] > m10[k] else 0.0
                k += 1
            w[i] = etat
        series[s] = (jd, SP.rendement_position(d, w * SP.taille_vol(d), MM.FRAIS_DEFAUT.get(d["famille"], 0.0005)),
                     d["famille"])
    gser = series.pop("GLD")
    jp, pp = portefeuille(series)
    pn_al = np.zeros(len(jp))
    pn_al[np.searchsorted(jp, jn)] = pn
    out.append(ligne("H06 10 mois, 25 marchés", pp, jp, pn_al))
    out.append(ligne("H06 10 mois, or GLD", gser[1], gser[0], ng))

    print("\nH08 COT, tel qu'écrit : rendement des 4 semaines après un excès (or GLD et marchés du COT)")
    from autres_r7 import COT
    cas_long, cas_court = [], []
    for s, f in {**COT}.items():
        d = gld if s == "GCF" else tous[s]
        pos = SP.cot(d, os.path.join(MACRO, f))                    # repère les franchissements du 90e / 10e centile
        entrees = np.flatnonzero(np.diff(np.r_[0, pos]) != 0)
        for i in entrees:
            if pos[i] == 0 or i + 21 >= len(d["c"]):
                continue
            r4 = d["c"][i + 21] / d["o"][i + 1] - 1
            (cas_long if pos[i] > 0 else cas_court).append(r4)
    out.append(question("H08 après un excès de VENTES (sous le 10e centile) : 4 semaines", cas_long, 2,
                        "(attendu : positif)"))
    out.append(question("H08 après un excès d'ACHATS (au-dessus du 90e) : 4 semaines", cas_court, 2,
                        "(attendu : négatif)"))

    print("\nH09 réflexivité, réduite au prix et au COT (les avoirs des ETF restent introuvables gratuitement)")
    lignes = json.load(open(os.path.join(MACRO, "cot_or.json")))
    jr = np.array([(dt.date.fromisoformat(r["report_date_as_yyyy_mm_dd"][:10]) - dt.date(1970, 1, 1)).days + 6
                   for r in lignes])
    net = np.array([float(r["m_money_positions_long_all"]) - float(r["m_money_positions_short_all"]) for r in lignes])
    netj = SP.aligner(jg, jr, net)
    chg_cot = np.r_[np.full(28, np.nan), netj[28:] - netj[:-28]]
    chg_px = np.r_[np.full(60, np.nan), gld["c"][60:] / gld["c"][:-60] - 1]
    w = np.where(np.isfinite(chg_cot) & np.isfinite(chg_px) & (chg_cot > 0) & (chg_px > 0), 1.0, 0.0)
    out.append(ligne("H09 or GLD : prix 12 semaines ET COT 4 semaines en hausse", SP.rendement_position(
        gld, w * SP.taille_vol(gld), FRAIS_OR), jg, ng))

    print("\nH10 quadrants de Dalio et Druckenmiller : taux réel 10 ans × dollar (20 jours), or la semaine suivante")
    jr, vr = SP.lire_fred(os.path.join(MACRO, "DFII10.csv"), 2)
    jd_, vd = SP.lire_fred(os.path.join(MACRO, "DTWEXBGS.csv"), 1)
    tr_, do_ = SP.aligner(jg, jr, vr), SP.aligner(jg, jd_, vd)
    d20r = np.r_[np.full(20, np.nan), tr_[20:] - tr_[:-20]]
    d20d = np.r_[np.full(20, np.nan), do_[20:] / do_[:-20] - 1]
    lundi = np.array([date_de(x).weekday() == 0 for x in jg])
    w, etat = np.zeros(len(jg)), 0.0
    for i in range(len(jg)):
        if lundi[i] and np.isfinite(d20r[i]) and np.isfinite(d20d[i]):
            etat = 1.0 if (d20r[i] < 0 and d20d[i] < 0) else (-1.0 if (d20r[i] > 0 and d20d[i] > 0) else 0.0)
        w[i] = etat
    out.append(ligne("H10 or : acheté si taux réel ET dollar baissent, vendu s'ils montent", SP.rendement_position(
        gld, w * SP.taille_vol(gld), FRAIS_OR), jg, ng))

    print("\nH12 saisonnalités de l'or (GLD), 4 effets, seuil de Bonferroni")
    r = np.r_[0.0, gld["c"][1:] / gld["c"][:-1] - 1]
    dates = [date_de(x) for x in jg]
    coupe = jg[len(jg) // 2]
    dow = np.array([x.weekday() for x in dates])
    moy = {k: r[(jg < coupe) & (dow == k)].mean() for k in range(5)}
    meilleur = max(moy, key=moy.get)
    out.append(question(f"H12 jour de la semaine : le meilleur de la 1re moitié ({'lun mar mer jeu ven'.split()[meilleur]}), "
                        "joué sur la 2e", r[(jg >= coupe) & (dow == meilleur)], 4))
    mois = np.array([x.year * 12 + x.month for x in dates])
    debut_mois = np.r_[True, mois[1:] != mois[:-1]]
    tom = np.zeros(len(jg), bool)
    for i in np.flatnonzero(debut_mois):
        tom[max(0, i - 1):i + 3] = True
    out.append(question("H12 tournant du mois (dernier jour + 3 premiers)", r[tom], 4))
    automne = np.array([x.month in (9, 10, 11) for x in dates])
    out.append(question("H12 mois d'automne (septembre à novembre) contre le reste", r[automne] - r[~automne].mean(), 4))
    feries = []
    for an in range(2004, 2027):
        def nieme(mois_, jour_sem, k):
            x = dt.date(an, mois_, 1)
            x += dt.timedelta(days=(jour_sem - x.weekday()) % 7)
            return x + dt.timedelta(weeks=k - 1)
        def dernier(mois_, jour_sem):
            x = dt.date(an, mois_ + 1, 1) - dt.timedelta(days=1)
            return x - dt.timedelta(days=(x.weekday() - jour_sem) % 7)
        a_ = an % 19
        b_, c_ = divmod(an, 100)
        d_, e_ = divmod(b_, 4)
        g_ = (8 * b_ + 13) // 25
        h_ = (19 * a_ + b_ - d_ - g_ + 15) % 30
        i_, k_ = divmod(c_, 4)
        l_ = (32 + 2 * e_ + 2 * i_ - h_ - k_) % 7
        m_ = (a_ + 11 * h_ + 22 * l_) // 451
        mm_, jj_ = divmod(h_ + l_ - 7 * m_ + 114, 31)
        paques = dt.date(an, mm_, jj_ + 1)
        feries += [dt.date(an, 1, 1), nieme(1, 0, 3), nieme(2, 0, 3), paques - dt.timedelta(days=2), dernier(5, 0),
                   dt.date(an, 7, 4), nieme(9, 0, 1), nieme(11, 3, 4), dt.date(an, 12, 25)]
        if an >= 2022:
            feries.append(dt.date(an, 6, 19))
    veilles = set()
    for f in feries:
        x = f - dt.timedelta(days=1)
        while x.weekday() >= 5:
            x -= dt.timedelta(days=1)
        veilles.add(x)
    veille = np.array([x in veilles for x in dates])
    out.append(question("H12 veille de jour férié américain", r[veille], 4,
                        "(fêtes indiennes et chinoises : pas de calendrier fiable hors ligne, non testées)"))
    out.append(question("   … sur la 1re moitié seulement", r[veille & (jg < coupe)], 1))
    out.append(question("   … sur la 2e moitié seulement", r[veille & (jg >= coupe)], 1))
    out.append(question("   … nette de 0,03 % de frais (achat à la clôture d'avant-veille, vente à celle de la veille)",
                        r[veille] - 0.0003, 1))

    print("\nH13 emploi américain : la direction des 15 premières minutes se prolonge-t-elle jusqu'à 4 h après ?")
    for nom_m, d5 in (("or", paxg5), ("euro-dollar", eur5)):
        m, jny = C.minutes_ny(d5["ts"])
        vals = []
        for jour_ in np.unique(jny):
            x = date_de(jour_)
            if x.weekday() != 4 or x.day > 7:
                continue
            sel = np.flatnonzero(jny == jour_)
            i0 = sel[m[sel] == 510]
            i15 = sel[m[sel] == 525]
            i4 = sel[m[sel] == 750]
            if len(i0) and len(i15) and len(i4):
                sens = np.sign(d5["o"][i15[0]] - d5["o"][i0[0]])
                vals.append(sens * (d5["o"][i4[0]] / d5["o"][i15[0]] - 1))
        out.append(question(f"H13 {nom_m} (5 min), NFP", vals, 2))

    print("\nH15 chandeliers en contexte : motif sur un plus bas récent APRÈS une baisse, contre le même contexte sans "
          "motif (5 bougies suivantes, en ATR)")
    for nom_u, d in (("or 1 h", D.regrouper(paxg5, 60)), ("or journalier (GLD)", gld)):
        h, l, c = d["h"], d["l"], d["c"]
        a = M.atr(h, l, c, 14)
        contexte = (C.fen_min(l, 3) <= M.plus_bas(l, 20) + 0.5 * a) & (c < np.r_[np.full(10, np.nan), c[:-10]] - a)
        fut = np.r_[(c[5:] - c[:-5]) / a[:-5], np.full(5, np.nan)]
        base = fut[contexte & np.isfinite(fut)].mean()
        for nom_mo, haussier in motifs_haussiers(d).items():
            sel = haussier & contexte & np.isfinite(fut)
            out.append(question(f"H15 {nom_mo}, {nom_u} : avance sur le contexte seul", (fut[sel] - base) / 100, 10,
                                "(moyenne en ATR, pas en %)"))

    print("\nH16 ratio or / argent (GLD / SLV), score z sur un an : l'or SEUL en profite-t-il ?")
    j_s = jours_de(slv)
    commun = np.intersect1d(jg, j_s)
    ig, is_ = np.searchsorted(jg, commun), np.searchsorted(j_s, commun)
    x = np.log(gld["c"][ig] / slv["c"][is_])
    z = np.full(len(x), np.nan)
    for i in range(252, len(x)):
        f_ = x[i - 251:i + 1]
        z[i] = (x[i] - f_.mean()) / f_.std()
    w, etat = np.zeros(len(jg)), 0.0
    for k_, i in enumerate(ig):
        if np.isfinite(z[k_]):
            if etat == 0 and z[k_] > 2:
                etat = -1.0
            elif etat == 0 and z[k_] < -2:
                etat = 1.0
            elif (etat < 0 and z[k_] < 0) or (etat > 0 and z[k_] > 0):
                etat = 0.0
        w[i] = etat
    out.append(ligne("H16 or vendu si le ratio est cher (z > 2), acheté s'il est bon marché", SP.rendement_position(
        gld, w * SP.taille_vol(gld), FRAIS_OR), jg, ng))

    print("\nH17 chocs de taux réels (variation d'un jour > 2 écarts-types) : l'or prolonge-t-il ou revient-il ?")
    jr, vr = SP.lire_fred(os.path.join(MACRO, "DFII10.csv"), 0)
    tr_ = SP.aligner(jg, jr, vr)
    dtr = np.r_[np.nan, np.diff(tr_)]
    rg = np.r_[0.0, gld["c"][1:] / gld["c"][:-1] - 1]
    vals = []
    for i in range(253, len(jg) - 2):
        e_ = np.nanstd(dtr[i - 252:i])
        if np.isfinite(dtr[i]) and e_ > 0 and abs(dtr[i]) > 2 * e_:
            vals.append(np.sign(rg[i]) * (gld["c"][i + 2] / gld["o"][i + 2] - 1))   # connu 30 h après : jour i+2
    out.append(question("H17 or : même sens que le jour du choc, 2 jours après (positif = prolonge)", vals, 1))

    print("\nH18 profil horaire de l'or (PAXG, 1 h), appris sur les 2 années précédentes, joué l'année suivante")
    d1 = D.regrouper(paxg5, 60)
    hr = (d1["ts"] // 3_600_000) % 24
    an = np.array([date_de(x).year for x in jours_de(d1)])
    r1 = d1["c"] / d1["o"] - 1
    rend = np.zeros(len(r1))
    cout = 0.30 / float(np.median(d1["c"]))
    n_t = 0
    for a_ in range(int(an.min()) + 2, int(an.max()) + 1):
        app = (an >= a_ - 2) & (an < a_)
        for hh_ in range(24):
            x_ = r1[app & (hr == hh_)]
            if len(x_) < 50:
                continue
            t_ = x_.mean() / (x_.std(ddof=1) / math.sqrt(len(x_)))
            if abs(t_) >= 2:
                sel = (an == a_) & (hr == hh_)
                v = np.array([r1[max(0, i - 120):i].std() for i in np.flatnonzero(sel)]) * math.sqrt(252 * 24)
                w_ = np.minimum(0.10 / np.where(v > 0, v, 1), 5.0)
                rend[sel] = np.sign(t_) * w_ * r1[sel] - w_ * cout
                n_t += int(sel.sum())
    j, p = M.par_jour(d1["ts"], rend)
    nv = R.naif("1h")
    s1, s2, _ = M.moities(j, p)
    print(f"{'H18 heures choisies sur les 2 années précédentes':60} | {s1:+.2f} / {s2:+.2f} | {n_t} trades | "
          f"{'✅' if s1 > 0 and s2 > 0 else '✖'}")
    out.append({"regle": "H18 profil horaire", "sharpe": [round(s1, 3), round(s2, 3)], "trades": n_t})
    m_l, _ = C.minutes_utc(d1["ts"])
    out.append(question("H18 dérive vers le fixing de 15 h (Londres) : de 10 h à 15 h, heure de Londres",
                        [d1["c"][i + 4] / d1["o"][i] - 1 for i in range(len(d1["c"]) - 5)
                         if m_l[i] == 600 - 60 * (1 if C.decalage_ny(d1["ts"][i:i + 1])[0] == -4 else 0)], 1,
                        "(10 h Londres = 9 h UTC en été, 10 h UTC en hiver)"))

    print("\nH19 cassure de la 1re heure de Londres (7 h-8 h UTC), jours NR4 seulement, or et euro-dollar, 15 min")
    ser, n_t = {}, 0
    for sym, d5, fam in (("PAXGUSDT", paxg5, "métaux"), ("EURUSDT", eur5, "forex")):
        d15 = D.regrouper(d5, 15)
        cout = (0.30 if sym == "PAXGUSDT" else 0.00012) / float(np.median(d15["c"]))
        j, p, n = moteur(d15, h19_londres_nr4(d15), cout, par_an=252 * 96)
        ser[sym] = (j, p, fam)
        n_t += n
    jj, pp = portefeuille(ser)
    s1, s2, _ = M.moities(jj, pp)
    print(f"{'H19 Londres 7 h-8 h, jours NR4':60} | {s1:+.2f} / {s2:+.2f} | {n_t} trades | "
          f"{'✅' if s1 > 0 and s2 > 0 else '✖'}")
    out.append({"regle": "H19 Londres NR4", "sharpe": [round(s1, 3), round(s2, 3)], "trades": n_t})

    print("\nH21 trou du week-end (vendredi soir → lundi) : se comble-t-il le lundi, ou se prolonge-t-il ?")
    spy = yahoo_brut(EXTRA, "SPY", "indices")
    for nom_m, d in (("or (GLD)", gld), ("S&P 500 (indice)", tous["GSPC"]), ("S&P 500 (fonds SPY)", spy),
                     ("euro-dollar", tous["EURUSDX"])):
        jd = jours_de(d)
        comble, prolonge = [], []
        for i in range(1, len(jd)):
            if jd[i] - jd[i - 1] >= 3 and date_de(jd[i]).weekday() == 0:
                g = d["o"][i] / d["c"][i - 1] - 1
                if abs(g) < 0.001:
                    continue
                atteint = (d["l"][i] <= d["c"][i - 1]) if g > 0 else (d["h"][i] >= d["c"][i - 1])
                comble.append(float(atteint))
                prolonge.append(np.sign(g) * (d["c"][i] / d["o"][i] - 1))
        print(f"   {nom_m:12} : {len(comble)} lundis à trou, comblé dans la journée {np.mean(comble) * 100:.0f} %")
        out.append(question(f"H21 {nom_m} : le lundi prolonge le trou (ouverture → clôture)", prolonge, 4))
