"""R8 (26/10/2026) : contre-épreuves en bougies d'une heure, pour savoir si un résultat journalier tient quand on suit
le vrai chemin des prix dans la journée.
- Turtles système 1 ACHETEUR avec filtre (fiche H01, candidate R7) : niveaux journaliers (20 j, 10 j, N = ATR 20 j)
  appliqués heure par heure, comparé au même système en journalier (même source) et sur Yahoo ;
- cassure de volatilité de Larry Williams (N04) : journalier contre la même règle jouée dans la journée (N04b) ;
- bande de bruit de Zarattini (N38) sur le S&P 500, séance de New York seulement.
Sources : Binance (or PAXG, euro, bitcoin, ether) et Dukascopy (S&P 500, or, argent, pétrole, DAX ; fichiers
mensuels .bi5, enregistrements de 24 octets : secondes depuis le début du mois, ouverture, clôture, bas, haut en
entiers, volume ; échelle des prix trouvée en comparant au niveau Yahoo du même marché).

Usage : python etudes/validation_r8.py BINANCE YAHOO YAHOO_EXTRA MACRO RACINE_ARMEE DUKASCOPY
"""
import os
import sys

import numpy as np

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
BINANCE, YAHOO, _, _, RACINE, DUKA = sys.argv[1:7]   # même ordre que fiches_r7 (lu à l'import)
sys.path.insert(0, RACINE)

import catalogue_r7 as C      # noqa: E402
import catalogue_r8 as C8     # noqa: E402
import donnees_r7 as D        # noqa: E402
import fiches_r7 as F         # noqa: E402
import moteur_r7 as M         # noqa: E402

DUKAS = {"USA500IDXUSD": ("GSPC", "indices", "S&P 500"), "XAUUSD": ("GCF", "métaux", "or"),
         "XAGUSD": ("SIF", "métaux", "argent"), "LIGHTCMDUSD": ("CLF", "énergie", "pétrole"),
         "DEUIDXEUR": ("GDAXI", "indices", "DAX")}
FRAIS = {"indices": 0.0002, "métaux": 0.0003, "énergie": 0.0005}       # armee_or.marches.FRAIS_DEFAUT


def turtles_horaire(d1, cout):
    """Turtles S1 acheteur avec filtre, niveaux journaliers (20 j, 10 j, N = ATR 20 j) appliqués heure par heure."""
    dj = D.regrouper(d1, 1440)
    jd = D.jour(dj["ts"])
    a = M.atr(dj["h"], dj["l"], dj["c"], 20)
    hh, ls = C.fen_max(dj["h"], 20), C.fen_min(dj["l"], 10)
    h55 = C.fen_max(dj["h"], 55)
    jh = D.jour(d1["ts"])
    idx = np.searchsorted(jd, jh) - 1                             # niveaux connus : ceux de la VEILLE
    o, h, l, c = d1["o"], d1["h"], d1["l"], d1["c"]
    rend = np.zeros(len(c))
    gagnant, fictif, pos, n = False, None, None, 0
    for i in range(1, len(c)):
        k = idx[i]
        if k < 56 or not np.isfinite(a[k]):
            continue
        N, haut, sortie, h5 = a[k], hh[k], ls[k], h55[k]
        if fictif is not None:
            e_f, st_f = fictif
            if l[i] <= max(st_f, sortie):
                gagnant, fictif = max(st_f, sortie) > e_f, None
        if pos is not None:
            e, st, w, ref = pos
            niv = max(st, sortie)
            if l[i] <= niv:
                px = min(o[i], niv)
                rend[i] += w * (px / ref - 1) - w * cout / 2
                gagnant, pos = px > e, None
                continue
            r_ = w * (c[i] / ref - 1)
            if i + 1 < len(c) and jh[i + 1] != jh[i]:
                r_ -= w * M.FINANCEMENT / 365 * (jh[i + 1] - jh[i])
            rend[i] += r_
            pos = (e, st, w, c[i])
            continue
        if h[i] < haut:
            continue
        e = max(o[i], haut)
        st = e - 2 * N
        cas55 = h[i] >= h5
        if fictif is not None and not cas55:
            continue
        if gagnant and not cas55:
            fictif, gagnant = (e, st), False
            continue
        w = min(M.RISQUE / (2 * N / e), M.LEVIER_MAX)
        n += 1
        if l[i] <= st:
            rend[i] += w * (st / e - 1) - w * cout
            continue
        rend[i] += w * (c[i] / e - 1) - w * cout / 2
        pos = (e, st, w, c[i])
    return rend, n


def moities(j, p):
    coupe = j[len(j) // 2]
    return M.sharpe(p[j < coupe]), M.sharpe(p[j >= coupe])


def williams_seance(d):
    """N04b avec la sortie à la dernière bougie de chaque jour de cotation, d'après le calendrier du marché (le S&P
    de Dukascopy ferme à 21 h UTC le vendredi : la fin repérée par l'heure, minuit, ne suffit pas)."""
    r = C8.n04b_williams_intraday(d)
    j = D.jour(d["ts"])
    r["sortie"] = np.where(np.r_[j[1:] != j[:-1], True], 2, 0)
    return r


def regle(d, f, cout, par_an):
    r, tr = M.backtest(d["o"], d["h"], d["l"], d["c"], f(d), cout, jours=D.jour(d["ts"]), bougies_par_an=par_an)
    return M.par_jour(d["ts"], r) + (len(tr),)


if __name__ == "__main__":
    marches = []
    for sym, fam in (("PAXGUSDT", "métaux"), ("EURUSDT", "forex"), ("BTCUSDT", "crypto"), ("ETHUSDT", "crypto")):
        d1 = D.charger_binance(BINANCE, sym, "1h")
        if sym in ("PAXGUSDT", "EURUSDT"):
            g = D.jour_semaine(d1["ts"]) < 5
            d1 = {k: v[g] for k, v in d1.items()}
        cout = {"BTCUSDT": 0.0006, "ETHUSDT": 0.0008, "PAXGUSDT": 0.30 / np.median(d1["c"]),
                "EURUSDT": 0.00012 / np.median(d1["c"])}[sym]
        marches.append((f"Binance {sym}", d1, cout, None))
    for sym, (nom_y, fam, nom) in DUKAS.items():
        ref = F.yahoo_brut(YAHOO, nom_y, fam)
        d1 = D.charger_dukascopy(DUKA, sym, ref)
        if d1 is None or len(d1["c"]) < 24 * 400:
            print(f"Dukascopy {sym} : données insuffisantes ({0 if d1 is None else len(d1['c'])} heures)")
            continue
        marches.append((f"Dukascopy {nom} ({sym})", d1, FRAIS[fam], ref))
    for nom, d1, _, _ in marches:
        j = D.jour(d1["ts"])
        print(f"   {nom:34} {len(d1['c'])} heures, du {F.date_de(int(j[0]))} au {F.date_de(int(j[-1]))}")
    print("1) Turtles système 1 acheteur avec filtre (H01) : heure par heure contre journalier (Sharpe ; moitiés)")
    for nom, d1, cout, ref in marches:
        r1, n1 = turtles_horaire(d1, cout)
        j1, p1 = M.par_jour(d1["ts"], r1)
        dj = D.regrouper(d1, 1440)
        r2, n2 = F.turtles_s1_filtre(dj, cout, achat_seul=True)
        j2, p2 = M.par_jour(dj["ts"], r2)
        a1, b1 = moities(j1, p1)
        a2, b2 = moities(j2, p2)
        txt = (f"   {nom:34} heure par heure {M.sharpe(p1):+.2f} ({a1:+.2f} / {b1:+.2f}, {n1} trades) | journalier même "
               f"source {M.sharpe(p2):+.2f} ({a2:+.2f} / {b2:+.2f}, {n2})")
        if ref is not None:
            sel = (ref["ts"] >= dj["ts"][0]) & (ref["ts"] <= dj["ts"][-1])
            dy = {k: (v[sel] if hasattr(v, "__len__") and len(v) == len(sel) else v) for k, v in ref.items()}
            r3, n3 = F.turtles_s1_filtre(dy, cout, achat_seul=True)
            j3, p3 = M.par_jour(dy["ts"], r3)
            txt += f" | Yahoo {M.sharpe(p3):+.2f} ({n3})"
        print(txt, flush=True)
    print("\n2) Cassure de volatilité de Larry Williams : journalier (N04) contre dans la journée (N04b, sortie en fin de "
          "séance), mêmes données")
    for nom, d1, cout, _ in marches:
        dj = D.regrouper(d1, 1440)
        jj, pj, nj = regle(dj, C8.n04_cassure_williams, cout, 252)
        jh, ph, nh = regle(d1, williams_seance, cout, 252 * 24)
        a1, b1 = moities(jj, pj)
        a2, b2 = moities(jh, ph)
        print(f"   {nom:34} journalier {a1:+.2f} / {b1:+.2f} ({nj} trades) | dans la journée {a2:+.2f} / {b2:+.2f} "
              f"({nh} trades)", flush=True)
    print("\n3) Bande de bruit de Zarattini sur le S&P 500, séance de New York (10 h – 16 h), contrôles chaque heure")
    for nom, d1, cout, _ in marches:
        if "S&P" not in nom:
            continue
        mn, _ = C.minutes_ny(d1["ts"])
        seance = (mn >= 600) & (mn < 960)
        ds = {k: v[seance] for k, v in d1.items()}
        js, ps, ns = regle(ds, lambda d: C8.n38_bande_de_bruit(d, fuseau="ny", fin_jour=960), cout, 252 * 6)
        a1, b1 = moities(js, ps)
        dj = D.regrouper(d1, 1440)
        rn = np.r_[0.0, dj["c"][1:] / dj["c"][:-1] - 1]
        jn = D.jour(dj["ts"])
        n1, n2 = moities(jn, rn)
        print(f"   {nom:34} {a1:+.2f} / {b1:+.2f} ({ns} trades) | S&P acheté et gardé {n1:+.2f} / {n2:+.2f}", flush=True)
    print("\n4) Williams dans la journée sur bitcoin et ether SEULS (choix fait APRÈS avoir vu le point 2 : essai compté)")
    ser, nv = {}, {}
    for nom, d1, cout, _ in marches:
        if not any(x in nom for x in ("BTCUSDT", "ETHUSDT")):
            continue
        j, p, _ = regle(d1, williams_seance, cout, 252 * 24)
        ser[nom] = (j, p, "crypto")
        dj = D.regrouper(d1, 1440)
        r = np.r_[0.0, dj["c"][1:] / dj["c"][:-1] - 1]
        taille = np.nan_to_num(np.minimum(M.VOL_CIBLE / M._vol_glissante(dj["c"], 365), M.LEVIER_MAX))
        nv[nom] = (D.jour(dj["ts"]), np.r_[0.0, taille[:-1]] * r, "crypto")
    j, p = M.portefeuille(ser)
    jn, pn = M.portefeuille(nv)
    a1, b1 = moities(j, p)
    coupe = j[len(j) // 2]
    n1, n2 = M.sharpe(pn[jn < coupe]), M.sharpe(pn[jn >= coupe])
    ok = a1 > max(0, n1) and b1 > max(0, n2)
    print(f"   bitcoin + ether {a1:+.2f} / {b1:+.2f} | naïf (achat gardé, 10 % de volatilité) {n1:+.2f} / {n2:+.2f} | "
          f"{'✅ PERMIS' if ok else '✖ ne bat pas le naïf sur les deux moitiés'}")
