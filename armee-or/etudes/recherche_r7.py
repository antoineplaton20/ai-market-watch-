"""R7 (25/10/2026) : toutes les méthodes des vidéos de trading les plus vues et toutes les fiches restées sans test,
jugées comme le permis de l'armée, puis contrôlées (entrées au hasard, frais doublés, Sharpe dégonflé).

Données :
- intraday : or (PAXGUSDT, jours ouvrés seulement, comme l'or chez un courtier MT5), euro-dollar (EURUSDT, idem),
  bitcoin et ether (BTCUSDT, ETHUSDT), Binance 2019-2026, bougies de 1, 5, 15 minutes et 1 heure ;
- journalier : les marchés Yahoo 2000-2026 que le contrôleur de données ne rejette pas (armee_or/qualite.py) ;
- macro (portage, COT, taux réels, régimes) : FRED et CFTC, décalés de leur délai de publication.
Frais aller-retour : or 0,30 $ l'once, euro-dollar 1,2 pip, bitcoin 0,06 %, ether 0,08 % ; journalier : frais par
famille du banc de l'équipe (marches.FRAIS_DEFAUT). Financement : 3 %/an, achat comme vente.

Usage : python etudes/recherche_r7.py BINANCE YAHOO MACRO RACINE_ARMEE SORTIE.json [processus]
"""
import concurrent.futures as cf
import json
import math
import os
import sys
import time

import numpy as np

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
BINANCE, YAHOO, MACRO, RACINE, SORTIE = sys.argv[1:6] if len(sys.argv) > 5 else (None,) * 5
if RACINE:
    sys.path.insert(0, RACINE)

import catalogue_r7 as C     # noqa: E402
import donnees_r7 as D       # noqa: E402
import moteur_r7 as M        # noqa: E402

INTRA = {"PAXGUSDT": ("métaux", 0.30, True), "EURUSDT": ("forex", 0.00012, True),
         "BTCUSDT": ("crypto", None, False), "ETHUSDT": ("crypto", None, False)}
FRAIS_CRYPTO = {"BTCUSDT": 0.0006, "ETHUSDT": 0.0008}
UNITES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
_CACHE = {}


def intraday(sym, unite):
    cle = (sym, unite)
    if cle not in _CACHE:
        brut = D.charger_binance(BINANCE, sym, "1m" if unite == "1m" else ("1h" if unite == "1h" else "5m"))
        d = brut if unite in ("1m", "5m", "1h") else D.regrouper(brut, UNITES[unite])
        if INTRA[sym][2]:                                         # or et euro-dollar : pas de week-end (courtier MT5)
            garde = D.jour_semaine(d["ts"]) < 5
            d = {k: v[garde] for k, v in d.items()}
        _CACHE[cle] = d
    return _CACHE[cle]


def cout_intra(sym, d):
    fam, frais, _ = INTRA[sym]
    if sym in FRAIS_CRYPTO:
        return FRAIS_CRYPTO[sym]
    return frais / float(np.median(d["c"])) if sym == "PAXGUSDT" else frais / float(np.median(d["c"]))


def yahoo():
    if "yahoo" not in _CACHE:
        from armee_or import marches as MM, qualite as Q
        sys.path.insert(0, ICI)
        from charger import FAMILLES, charger
        tous = charger(YAHOO, MM)
        garde = {}
        for nom, d in tous.items():
            r = json.load(open(os.path.join(YAHOO, nom + ".json")))["chart"]["result"][0]
            q = r["indicators"]["quote"][0]
            v = Q.controler([(t * 1000, *x) for t, *x in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"])],
                            famille=d["famille"])
            if v["verdict"] != "écarté":                          # volume aligné sur les lignes gardées par charger
                vol = [x if x else 0.0 for t, o, h, l, c, x in zip(r["timestamp"], q["open"], q["high"], q["low"],
                       q["close"], q.get("volume") or [0] * len(r["timestamp"]))
                       if None not in (o, h, l, c) and min(o, h, l, c) > 0 and l <= min(o, c) and h >= max(o, c)]
                d["v"] = np.array(vol, dtype=float)
                d["vb"] = d["v"] / 2
                garde[nom] = d
        _CACHE["yahoo"] = garde
    return _CACHE["yahoo"]


def frais_yahoo(d):
    from armee_or import marches as MM
    return MM.FRAIS_DEFAUT.get(d["famille"], 0.0005)


# ============================================================================ un essai
def essai(nom, unite, serie=False, facteur_frais=1.0, graine=None, chemin="prudent"):
    """-> dict : Sharpe des deux moitiés, naïf, trades, etc. pour la règle `nom` sur l'unité `unite`."""
    f = C.INTRADAY.get(nom) or C.JOURNALIER.get(nom)
    series, trades_tous, par_marche = {}, [], {}
    if unite == "1j":
        univers = {s: (d, frais_yahoo(d), d["famille"]) for s, d in yahoo().items()}
        par_an = 252
    else:
        syms = ["PAXGUSDT"] if unite == "1m" else list(INTRA)
        univers = {}
        for s in syms:
            d = intraday(s, unite)
            univers[s] = (d, cout_intra(s, d), INTRA[s][0])
        par_an = 252 * (1440 // UNITES[unite])
    for s, (d, cout, fam) in univers.items():
        regle = f(d)
        jours = D.jour(d["ts"])
        ent = None
        if graine is not None:
            _, tr0 = M.backtest(d["o"], d["h"], d["l"], d["c"], regle, cout, jours=jours, bougies_par_an=par_an)
            ent = M.entrees_au_hasard(tr0, len(d["c"]), graine * 1000 + sum(map(ord, s)))
            if regle["sens"].max() == 2:                              # ordres doubles : le hasard garde des ordres doubles
                ent = [(i, 2) for i, _ in ent]
        rend, tr = M.backtest(d["o"], d["h"], d["l"], d["c"], regle, cout * facteur_frais, jours=jours,
                              bougies_par_an=par_an, entrees_imposees=ent, chemin=chemin)
        j, p = M.par_jour(d["ts"], rend)
        series[s] = (j, p, fam)
        trades_tous += [(s, t) for t in tr]
        s1, s2, _ = M.moities(j, p)
        par_marche[s] = (round(s1, 2), round(s2, 2), len(tr))
    jp, pp = M.portefeuille(series)
    s1, s2, coupe = M.moities(jp, pp)
    n1 = sum(1 for s, t in trades_tous if D.jour(univers[s][0]["ts"][t[0]]) < coupe)
    n2 = len(trades_tous) - n1
    b = M.bilan_trades([t for _, t in trades_tous])
    return {"regle": nom, "unite": unite, "sharpe": [round(s1, 3), round(s2, 3)], "sharpe_total": round(M.sharpe(pp), 3),
            "trades": [n1, n2], "gagnants": round(b["gagnants"], 3), "R_moyen": round(b["R_moyen"], 3),
            "pire_baisse": round(M.pire_baisse(pp), 4), "jours": int(len(jp)), "coupe": int(coupe),
            "annees": round(float(jp[-1] - jp[0]) / 365.25, 2),
            "par_marche": par_marche, "asym": float(_moment(pp, 3)), "aplat": float(_moment(pp, 4)),
            "_serie": (jp.tolist(), pp.tolist()) if serie else None}


def _moment(x, k):
    x = np.asarray(x)
    s = x.std()
    return float(((x - x.mean()) ** k).mean() / s ** k) if s > 0 else 0.0


def naif(unite):
    """« Toujours acheter » le même panier, même risque (10 % de volatilité par marché, risque égal par famille)."""
    import speciales_r7 as SP
    series = {}
    if unite == "1j":
        from armee_or import marches as MM
        for s, d in yahoo().items():
            net, _ = MM.simuler_marche(d["o"], d["h"], d["l"], d["c"], "toujours_acheter", d["cout"])
            series[s] = (D.jour(d["ts"]), net, d["famille"])
    else:
        for s in (["PAXGUSDT"] if unite == "1m" else INTRA):
            dj = D.regrouper(intraday(s, unite), 1440)
            w = SP.taille_vol(dj)
            series[s] = (D.jour(dj["ts"]), SP.rendement_position(dj, w, cout_intra(s, dj)), INTRA[s][0])
    jp, pp = M.portefeuille(series)
    s1, s2, coupe = M.moities(jp, pp)
    return {"sharpe": [round(s1, 3), round(s2, 3)], "coupe": int(coupe), "sharpe_total": round(M.sharpe(pp), 3)}


def _tache(args):
    nom, unite = args
    t0 = time.time()
    try:
        r = essai(nom, unite)
    except Exception as ex:                                       # une règle qui plante est notée, pas cachée
        import traceback
        return {"regle": nom, "unite": unite, "erreur": repr(ex), "trace": traceback.format_exc(limit=4)}
    r["secondes"] = round(time.time() - t0, 1)
    return r


def plan():
    taches = []
    for nom in C.INTRADAY:
        for unite in ("15m", "1h"):
            taches.append((nom, unite))
        if nom in C.SCALPING:
            taches.append((nom, "5m"))
        if nom not in C.SEULEMENT_INTRADAY:
            taches.append((nom, "1j"))
    taches.append(("V53 scalping 1 minute (Jdub)", "1m"))
    for nom in C.JOURNALIER:
        taches.append((nom, "1j"))
    return taches


C.INTRADAY["V53 scalping 1 minute (Jdub)"] = C.v53_scalping_1min
C.SEULEMENT_INTRADAY.add("V53 scalping 1 minute (Jdub)")


def juge(r, nv):
    s1, s2 = r["sharpe"]
    n1, n2 = nv["sharpe"]
    raisons = []
    if s1 <= 0 or s2 <= 0:
        raisons.append("perd sur une moitié")
    if s1 <= n1 or s2 <= n2:
        raisons.append("ne bat pas le naïf")
    if min(r["trades"]) < M.MIN_TRADES:
        raisons.append(f"moins de {M.MIN_TRADES} trades sur une moitié")
    return raisons


if __name__ == "__main__":
    t0 = time.time()
    proc = int(sys.argv[6]) if len(sys.argv) > 6 else 4
    taches = plan()
    print(f"{len(taches)} essais prévus (règle × unité de temps), {proc} processus", flush=True)
    with cf.ProcessPoolExecutor(proc) as ex:
        resultats = list(ex.map(_tache, taches))
    naifs = {u: naif(u) for u in ("1m", "5m", "15m", "1h", "1j")}
    json.dump({"essais": resultats, "naifs": naifs}, open(SORTIE, "w"), ensure_ascii=False, indent=0)
    print(f"fini en {time.time() - t0:.0f} s ; naïfs : " +
          " · ".join(f"{u} {v['sharpe'][0]:+.2f} / {v['sharpe'][1]:+.2f}" for u, v in naifs.items()))
