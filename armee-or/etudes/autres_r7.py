"""R7 (25/10/2026), 2e partie : portage (H37), paires (H16), COT (H08), taux réels (H17), régimes (H10), saisonnalité
(H12), momentum relatif, écarts d'ouverture, apprentissage automatique et méta-étiquetage (H11), martingale et grille
(H39). Mêmes conventions et même jugement que recherche_r7.py ; données externes décalées de leur publication.

Usage : python etudes/autres_r7.py BINANCE YAHOO MACRO RACINE_ARMEE SORTIE.json
"""
import json
import os
import sys

import numpy as np

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
BINANCE, YAHOO, MACRO, RACINE, SORTIE = sys.argv[1:6]
sys.path.insert(0, RACINE)

import donnees_r7 as D        # noqa: E402
import moteur_r7 as M         # noqa: E402
import speciales_r7 as SP     # noqa: E402
from armee_or import marches as MM, qualite as Q   # noqa: E402
from charger import charger   # noqa: E402

COT = {"SIF": "cot_SIF.json", "CLF": "cot_CLF.json", "HGF": "cot_HGF.json", "NGF": "cot_NGF.json",
       "ZCF": "cot_ZCF.json", "ZWF": "cot_ZWF.json", "KCF": "cot_KCF.json", "SBF": "cot_SBF.json",
       "CCF": "cot_CCF.json", "PLF": "cot_PLF.json", "GCF": "cot_or.json"}
ESSAIS = []


def verdicts():
    tous = charger(YAHOO, MM)
    v = {}
    for nom, d in tous.items():
        r = json.load(open(os.path.join(YAHOO, nom + ".json")))["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        v[nom] = Q.controler([(t * 1000, *x) for t, *x in zip(r["timestamp"], q["open"], q["high"], q["low"],
                                                                 q["close"])], famille=d["famille"])["verdict"]
    return tous, v


def bilan(nom, series, naif_series=None, note="", trades=None):
    """series : {marché: (jours, rendements, famille)} -> ligne du tableau + essai compté."""
    jp, pp = M.portefeuille(series)
    s1, s2, coupe = M.moities(jp, pp)
    ligne = {"regle": nom, "sharpe": [round(s1, 3), round(s2, 3)], "sharpe_total": round(M.sharpe(pp), 3),
             "pire_baisse": round(M.pire_baisse(pp), 4), "jours": int(len(jp)), "note": note,
             "annees": round(float(jp[-1] - jp[0]) / 365.25, 2),
             "asym": SPmoment(pp, 3), "aplat": SPmoment(pp, 4)}
    if naif_series is not None:
        jn, pn = M.portefeuille(naif_series)
        n1, n2 = M.sharpe(pn[jn < coupe]), M.sharpe(pn[jn >= coupe])
        ligne["naif"] = [round(n1, 3), round(n2, 3)]
        ligne["bat_naif"] = bool(s1 > n1 and s2 > n2)
    if trades is not None:
        ligne["trades"] = trades
    ligne["permis"] = bool(s1 > 0 and s2 > 0 and ligne.get("bat_naif", False) and
                           (trades is None or min(trades) >= M.MIN_TRADES))
    ESSAIS.append(ligne)
    nv = ligne.get("naif")
    print(f"{nom:58} | {s1:+.2f} / {s2:+.2f}" + (f" | naïf {nv[0]:+.2f} / {nv[1]:+.2f}" if nv else "") +
          f" | pire baisse {ligne['pire_baisse'] * 100:5.1f} % | {'✅ PERMIS' if ligne['permis'] else '✖'} {note}",
          flush=True)
    return ligne


def SPmoment(x, k):
    x = np.asarray(x)
    s = x.std()
    return float(((x - x.mean()) ** k).mean() / s ** k) if s > 0 else 0.0


def naif_de(marches):
    out = {}
    for s, d in marches.items():
        net, _ = MM.simuler_marche(d["o"], d["h"], d["l"], d["c"], "toujours_acheter", d["cout"])
        out[s] = (D.jour(d["ts"]), net, d["famille"])
    return out


def frais(d):
    return MM.FRAIS_DEFAUT.get(d["famille"], 0.0005)


if __name__ == "__main__":
    tous, verdict = verdicts()
    propres = {s: d for s, d in tous.items() if verdict[s] != "écarté"}
    print(f"marchés propres : {len(propres)} sur {len(tous)} ; écartés : "
          f"{', '.join(sorted(s for s in tous if verdict[s] == 'écarté'))}")

    print("\n1) Portage des devises (H37), 12 paires, taux 3 mois OCDE (connus 2 mois plus tard)")
    fx = {s: d for s, d in tous.items() if s in SP.PAIRES_DEVISES and verdict[s] != "écarté"}
    bilan("portage des devises", SP.portage(fx, MACRO, MM.FRAIS_DEFAUT["forex"]), naif_de(fx))

    print("\n2) Paires (H16) : écart en score z, |z| > 2")
    for a, b, note in (("EURUSDX", "GBPUSDX", ""), ("GSPC", "NDX", ""), ("GDAXI", "FCHI", ""),
                       ("GCF", "SIF", "indicatif : historique de l'or COMEX écarté")):
        da, db = tous[a], tous[b]
        j, r, n = SP.paire(da, db, cout=frais(da))
        bilan(f"paire {a} / {b}", {"paire": (j, r, "paire")}, naif_de({a: da, b: db}),
              note=f"{n} trades " + note)

    print("\n3) Extrêmes du COT (H08), gérants de fonds, rang sur 3 ans")
    ser_c, ser_i = {}, {}
    for s, f in COT.items():
        d = tous[s]
        pos = SP.cot(d, os.path.join(MACRO, f))
        w = pos * SP.taille_vol(d)
        serie = (D.jour(d["ts"]), SP.rendement_position(d, w, frais(d)), d["famille"])
        ser_i[s] = serie
        if verdict[s] != "écarté":
            ser_c[s] = serie
    bilan("COT à contre-courant, marchés propres", ser_c, naif_de({s: tous[s] for s in ser_c}),
          note=f"({', '.join(ser_c)})")
    bilan("COT à contre-courant, 11 marchés (indicatif)", ser_i, naif_de({s: tous[s] for s in ser_i}),
          note="7 historiques écartés inclus")

    print("\n4) Or et taux réels (H17) ; régimes d'inflation et de liquidité (H10)")
    paxg = D.regrouper(D.charger_binance(BINANCE, "PAXGUSDT", "1h"), 1440)
    paxg["famille"] = "métaux"
    for nom_or, dor, note in (("PAXG 2020-2026", paxg, ""), ("or COMEX 2003-2026", tous["GCF"], "indicatif : écarté")):
        pos = SP.taux_reels_or(dor, MACRO)
        ser = {"or": (D.jour(dor["ts"]), SP.rendement_position(dor, pos * SP.taille_vol(dor), 0.0003), "métaux")}
        nv = {"or": (D.jour(dor["ts"]), SP.rendement_position(dor, SP.taille_vol(dor), 0.0003), "métaux")}
        bilan(f"or acheté quand le taux réel baisse ({nom_or})", ser, nv, note=note)
    infl = {s: d for s, d in propres.items() if d["famille"] in ("métaux", "énergie", "agricoles")}
    ser = {s: (D.jour(d["ts"]), SP.rendement_position(d, SP.regime_inflation(d, MACRO) * SP.taille_vol(d), frais(d)),
               d["famille"]) for s, d in infl.items()}
    bilan("matières premières en régime d'inflation montante", ser, naif_de(infl))
    ind = {s: d for s, d in propres.items() if d["famille"] == "indices"}
    ser = {s: (D.jour(d["ts"]), SP.rendement_position(d, SP.regime_liquidite(d, MACRO) * SP.taille_vol(d), frais(d)),
               d["famille"]) for s, d in ind.items()}
    bilan("indices quand le bilan de la Fed grossit", ser, naif_de(ind))

    print("\n5) Saisonnalité (H12) : mois appris sur la 1re moitié, joués sur la 2e")
    jp, _ = M.portefeuille(naif_de(propres))
    coupe = jp[len(jp) // 2]
    ser = {s: (D.jour(d["ts"]), SP.rendement_position(d, SP.saisonnalite(d, coupe) * SP.taille_vol(d), frais(d)),
               d["famille"]) for s, d in propres.items()}
    jj, pp = M.portefeuille(ser)
    nj, npn = M.portefeuille(naif_de(propres))
    s2, n2 = M.sharpe(pp[jj >= coupe]), M.sharpe(npn[nj >= coupe])
    ESSAIS.append({"regle": "saisonnalité (2e moitié seulement)", "sharpe": [None, round(s2, 3)],
                   "sharpe_total": round(s2, 3), "naif": [None, round(n2, 3)], "permis": False,
                   "asym": SPmoment(pp[jj >= coupe], 3), "aplat": SPmoment(pp[jj >= coupe], 4),
                   "jours": int((jj >= coupe).sum())})
    print(f"{'saisonnalité des mois (2e moitié)':58} | 2e moitié {s2:+.2f} | naïf {n2:+.2f} | "
          f"{'mieux' if s2 > n2 else '✖ pas mieux'}")

    print("\n6) Momentum relatif : le tiers des marchés le plus fort sur 12 mois")
    couts = {s: frais(d) for s, d in propres.items()}
    bilan("momentum relatif (tiers le plus fort)", SP.momentum_relatif(propres, couts), naif_de(propres))

    print("\n7) Écarts d'ouverture (« gap fill », « gap and go »), marchés propres")
    for suivre, chemin, nom in ((False, "prudent", "fermeture de l'écart (gap fill)"),
                                (False, "ohlc", "fermeture de l'écart, ordre probable de la bougie"),
                                (True, "prudent", "écart suivi (gap and go)"),
                                (True, "ohlc", "écart suivi, ordre probable de la bougie")):
        ser, nt = {}, [0, 0]
        for s, d in propres.items():
            r, tr = SP.ecarts_ouverture(d, frais(d), suivre=suivre, chemin=chemin)
            ser[s] = (D.jour(d["ts"]), r, d["famille"])
            for t in tr:
                nt[int(D.jour(d["ts"][t[0]]) >= coupe)] += 1
        bilan(nom, ser, naif_de(propres), note="entrée au premier cours (optimiste)", trades=nt)

    print("\n8) Apprentissage automatique (H11) : régression logistique réentraînée chaque année")
    bilan("prévision du lendemain (logistique, 9 indicateurs)", SP.apprentissage(propres, couts), naif_de(propres))

    print("\n9) Méta-étiquetage (López de Prado) du momentum 12 mois de l'équipe")
    import catalogue_r7 as C
    base_ser, filt_ser, garde_tot, tot = {}, {}, 0, 0
    X_app, y_app, entrees = [], [], {}
    for s, d in propres.items():
        sig = MM.signal(d["c"], "momentum_12m")
        a20 = M.atr(d["h"], d["l"], d["c"], 20)
        on = np.r_[False, (sig[1:] == 1) & (sig[:-1] != 1)]
        regle = {"sens": np.where(on, 1, 0), "sortie": np.where(sig == 0, 1, 0), "stop": d["c"] - 5 * a20}
        rend, tr = M.backtest(d["o"], d["h"], d["l"], d["c"], regle, frais(d), jours=D.jour(d["ts"]))
        base_ser[s] = (D.jour(d["ts"]), rend, d["famille"])
        X = SP._caracteristiques(d["c"])
        entrees[s] = (regle, tr, X)
        for t in tr:
            i = t[0] - 1
            if D.jour(d["ts"][t[1]]) < coupe and np.all(np.isfinite(X[i])):
                X_app.append(X[i])
                y_app.append(float(t[4] > 0))
    w = SP.logistique(np.array(X_app), np.array(y_app))
    seuil = float(np.mean(y_app))                               # garder les trades jugés meilleurs que la moyenne
    for s, d in propres.items():
        regle, tr, X = entrees[s]
        garde = []
        for t in tr:
            i = t[0] - 1
            if D.jour(d["ts"][t[0]]) < coupe:
                continue
            tot += 1
            p = 1 / (1 + np.exp(-(np.r_[1.0, np.nan_to_num(X[i])] @ w)))
            if p > seuil:
                garde.append((i, 1))
        garde_tot += len(garde)
        rend, _ = M.backtest(d["o"], d["h"], d["l"], d["c"], regle, frais(d), jours=D.jour(d["ts"]),
                             entrees_imposees=garde)
        filt_ser[s] = (D.jour(d["ts"]), rend, d["famille"])
    jb, pb = M.portefeuille(base_ser)
    jf, pf = M.portefeuille(filt_ser)
    sb, sf = M.sharpe(pb[jb >= coupe]), M.sharpe(pf[jf >= coupe])
    ESSAIS.append({"regle": "méta-étiquetage du momentum (2e moitié)", "sharpe": [None, round(sf, 3)],
                   "sharpe_total": round(sf, 3), "permis": False, "asym": SPmoment(pf[jf >= coupe], 3),
                   "aplat": SPmoment(pf[jf >= coupe], 4), "jours": int((jf >= coupe).sum())})
    print(f"{'momentum 12 mois, 2e moitié, sans filtre':58} | {sb:+.2f} ({tot} trades)")
    print(f"{'momentum 12 mois, 2e moitié, filtré (appris sur la 1re)':58} | {sf:+.2f} ({garde_tot} trades gardés, "
          f"seuil {seuil * 100:.0f} % = part de gagnants de la 1re moitié)")

    print("\n10) Martingale et grille (H39) sur l'or (1 h), compte de 3 000, 200 départs au hasard sur 1 an")
    paxg_h = D.charger_binance(BINANCE, "PAXGUSDT", "1h")
    garde = D.jour_semaine(paxg_h["ts"]) < 5
    paxg_h = {k: v[garde] for k, v in paxg_h.items()}
    res = SP.martingale_grille(paxg_h, 0.30 / float(np.median(paxg_h["c"])))
    for nom, lst in res.items():
        ruines = sum(1 for r in lst if r[0])
        eqs = np.array([r[1] for r in lst])
        gains = np.array([r[2] for r in lst])
        print(f"{nom:12} : ruinés {ruines}/{len(lst)} ; compte final médian {np.median(eqs):.0f} ; "
              f"gains encaissés médians {np.median(gains):.0f} ; pire compte {eqs.min():.0f}")
        ESSAIS.append({"regle": nom, "ruines": ruines, "departs": len(lst), "compte_median": float(np.median(eqs)),
                       "permis": False})
    json.dump(ESSAIS, open(SORTIE, "w"), ensure_ascii=False, indent=0)
