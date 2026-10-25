"""Laboratoire hors ligne. Aucun appel MT5, aucun ordre, aucune activation automatique.

Catalogue TA-Lib et variantes de recherche à paramètres fixes. Les méthodes
portant un nom ne prétendent pas reproduire le système complet de leur auteur.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import numpy as np


def bibliotheque():
    try:
        import talib
    except ImportError as exc:
        raise RuntimeError("Installer requirements-recherche.txt pour le catalogue de chandeliers") from exc
    return talib


def verifier(b, pas_ms):
    n = len(b["c"])
    if n < 300 or any(len(b[k]) != n for k in ("ts", "o", "h", "l", "v")):
        raise ValueError("historique insuffisant ou colonnes incohérentes")
    if any(not np.isfinite(b[k]).all() for k in ("ts", "o", "h", "l", "c", "v")):
        raise ValueError("valeurs manquantes ou non finies")
    if any((b[k] <= 0).any() for k in ("o", "h", "l", "c")) or (b["v"] < 0).any():
        raise ValueError("prix ou volumes invalides")
    if (b["h"] < np.maximum(b["o"], b["c"])).any() or (b["l"] > np.minimum(b["o"], b["c"])).any():
        raise ValueError("OHLC incohérent")
    d = np.diff(b["ts"])
    if (d <= 0).any() or (d % pas_ms != 0).any():
        raise ValueError("horodatages dupliqués, non triés ou non alignés")
    return {"bougies": n, "ruptures": int((d != pas_ms).sum()),
            "debut_utc": date(b["ts"][0]), "fin_utc": date(b["ts"][-1])}


def date(ts):
    return dt.datetime.fromtimestamp(int(ts) / 1000, dt.timezone.utc).isoformat()


def decaler(x):
    return np.r_[np.nan, x[:-1]]


def motifs(b):
    ta = bibliotheque()
    return {nom: getattr(ta, nom)(*[np.asarray(b[k], dtype=float) for k in ("o", "h", "l", "c")])
            for nom in ta.get_function_groups()["Pattern Recognition"]}


def signaux(b, pas_ms=None):
    if pas_ms is not None:
        sorties, figures = {}, {}
        bornes = np.r_[0,np.flatnonzero(np.diff(b['ts']) != pas_ms)+1,len(b['c'])]
        for debut,fin in zip(bornes[:-1],bornes[1:]):
            s,m = signaux({k:v[debut:fin] for k,v in b.items()})
            for cible,partie in ((sorties,s),(figures,m)):
                for nom,v in partie.items():
                    cible.setdefault(nom,np.zeros(len(b['c']),dtype=int))[debut:fin]=v
        return sorties,figures
    ta = bibliotheque()
    o, h, l, c = [np.asarray(b[k], dtype=float) for k in ("o", "h", "l", "c")]
    out = {}
    for rapide, lent in ((20, 50), (50, 200)):
        a, z = ta.EMA(c, rapide), ta.EMA(c, lent)
        out[f"ema_{rapide}_{lent}"] = np.where(a > z, 1, np.where(a < z, -1, 0))
    for n in (20, 55):
        haut, bas = decaler(ta.MAX(h, n)), decaler(ta.MIN(l, n))
        out[f"cassure_donchian_{n}"] = np.where(c > haut, 1, np.where(c < bas, -1, 0))
    rsi = ta.RSI(c, 14)
    out["rsi_retour_30_70"] = np.where((decaler(rsi) < 30) & (rsi >= 30), 1,
                                          np.where((decaler(rsi) > 70) & (rsi <= 70), -1, 0))
    haut, milieu, bas = ta.BBANDS(c, 20, 2, 2)
    out["bollinger_reintegration"] = np.where((decaler(c) < decaler(bas)) & (c >= bas), 1,
                                               np.where((decaler(c) > decaler(haut)) & (c <= haut), -1, 0))
    macd, signal, hist = ta.MACD(c, 12, 26, 9)
    out["macd_croisement"] = np.where((decaler(hist) <= 0) & (hist > 0), 1,
                                        np.where((decaler(hist) >= 0) & (hist < 0), -1, 0))
    adx, plus, moins = ta.ADX(h, l, c, 14), ta.PLUS_DI(h, l, c, 14), ta.MINUS_DI(h, l, c, 14)
    out["adx_directionnel"] = np.where(adx >= 25, np.sign(plus - moins), 0).astype(int)
    k, d = ta.STOCH(h, l, c)
    out["stochastique_croisement"] = np.where((decaler(k) <= decaler(d)) & (k > d) & (k < 20), 1,
                                               np.where((decaler(k) >= decaler(d)) & (k < d) & (k > 80), -1, 0))
    catalogue = motifs(b)
    # Ces figures décrivent surtout une forme/indécision ; pas d'ordre directionnel automatique.
    neutres = {"CDLDOJI", "CDLLONGLEGGEDDOJI", "CDLRICKSHAWMAN", "CDLHIGHWAVE", "CDLSPINNINGTOP",
               "CDLSHORTLINE", "CDLLONGLINE", "CDLMARUBOZU", "CDLCLOSINGMARUBOZU"}
    for nom, valeurs in catalogue.items():
        if nom not in neutres:
            out[nom] = np.sign(valeurs).astype(int)
    return out, catalogue


def simuler(b, sens, debut, fin, pas_ms, cout_cote=0.0007, horizon=20):
    """Sans levier, une position à la fois, signal clôturé puis entrée à l'ouverture suivante.

    Stop 2 ATR / cible 3 ATR / horizon 20 bougies, stop prioritaire si les deux
    sont touchés dans une même bougie. Frais + spread + glissement forfaitaires.
    Aucun trade n'est simulé à travers une rupture temporelle ni une frontière de segment.
    """
    ta = bibliotheque()
    atr = np.full(len(b['c']),np.nan)
    bornes=np.r_[0,np.flatnonzero(np.diff(b['ts']) != pas_ms)+1,len(b['c'])]
    for debut_bloc,fin_bloc in zip(bornes[:-1],bornes[1:]):
        atr[debut_bloc:fin_bloc]=ta.ATR(b['h'][debut_bloc:fin_bloc],b['l'][debut_bloc:fin_bloc],
                                     b['c'][debut_bloc:fin_bloc],14)
    trous = np.r_[0, np.cumsum(np.diff(b["ts"]) != pas_ms)]
    rendement, operations = [], []
    capital, sommet, recul = 1.0, 1.0, 0.0
    i = max(1, debut)
    while i + horizon <= fin:
        signal_i = i - 1
        direction = int(sens[signal_i])
        if not direction or not np.isfinite(atr[signal_i]) or atr[signal_i] <= 0:
            i += 1
            continue
        dernier = i + horizon - 1
        if trous[dernier] != trous[signal_i]:
            i += 1
            continue
        entree = float(b["o"][i])
        stop = entree - direction * 2 * atr[signal_i]
        cible = entree + direction * 3 * atr[signal_i]
        if min(stop, cible) <= 0:
            i += 1
            continue
        sortie, raison, j = float(b["c"][dernier]), "horizon", dernier
        for j in range(i, dernier + 1):
            op, haut, bas = (float(b[k][j]) for k in ("o", "h", "l"))
            stop_touche = bas <= stop if direction > 0 else haut >= stop
            cible_touche = haut >= cible if direction > 0 else bas <= cible
            if stop_touche:
                sortie = min(stop, op) if direction > 0 else max(stop, op)
                raison = "stop"
                break
            if cible_touche:
                sortie, raison = cible, "cible"
                break
        brut = direction * (sortie / entree - 1)
        net = brut - cout_cote * (1 + sortie / entree)
        rendement.append(net)
        capital *= max(0, 1 + net)
        sommet = max(sommet, capital)
        recul = min(recul, capital / sommet - 1)
        operations.append({"signal_ts": int(b["ts"][signal_i]), "entree_ts": int(b["ts"][i]),
                           "sortie_ts": int(b["ts"][j]), "sens": direction, "entree": entree,
                           "sortie": sortie, "motif": raison, "rendement_net": net})
        i = j + 1
        if capital <= 0:
            break
    r = np.asarray(rendement)
    gains = float(r[r > 0].sum())
    pertes = float(-r[r < 0].sum())
    return {"trades": len(r), "rendement_net": capital - 1, "gain_moyen_net": float(r.mean()) if len(r) else 0,
            "taux_gagnant": float((r > 0).mean()) if len(r) else None,
            "profit_factor": gains / pertes if pertes > 0 else None,
            "drawdown_aux_clotures": recul, "operations": operations}


def evaluer(b, pas_ms):
    qualite = verifier(b, pas_ms)
    sign, catalogue = signaux(b,pas_ms)
    n = len(b["c"])
    a, z = int(n * .6), int(n * .8)
    resultats = {}
    # Paramètres fixés à l'avance. Sélection exclusivement sur les 20 % de validation.
    for nom, s in sign.items():
        val = simuler(b, s, a, z, pas_ms)
        stress = simuler(b, s, a, z, pas_ms, cout_cote=.0014)
        resultats[nom] = {"validation": {k:v for k,v in val.items() if k != "operations"},
                          "validation_couts_doubles": {k:v for k,v in stress.items() if k != "operations"}}
    eligibles = [nom for nom, r in resultats.items() if r["validation"]["trades"] >= 30
                 and r["validation"]["gain_moyen_net"] > 0
                 and r["validation_couts_doubles"]["gain_moyen_net"] > 0]
    selection = max(eligibles, key=lambda nom: resultats[nom]["validation"]["gain_moyen_net"]) if eligibles else None
    test = simuler(b, sign[selection], z, n, pas_ms) if selection else None
    return {"version": "2.4-R3-exploratoire", "qualite": qualite,
            "moteur": {"talib": bibliotheque().__version__, "figures": len(catalogue), "candidats": len(sign)},
            "protocole": {"historique_initial": [0, a], "validation": [a,z], "test_final": [z,n],
                          "cout_par_cote": .0007, "stress_cout_par_cote": .0014,
                          "stop_atr": 2, "cible_atr": 3, "horizon_bougies": 20, "levier": 1},
            "occurrences_figures": {k:int(np.count_nonzero(v)) for k,v in catalogue.items()},
            "validation": resultats, "selection_validation": selection, "test_final": test,
            "autorisation_mt5": False,
            "limites": ["Recherche exploratoire : comparaison multiple sans correction statistique.",
                         "Le segment initial sert au contexte des indicateurs ; aucun modèle n'est entraîné.",
                         "Coûts forfaitaires, aucun financement/swap ni contraintes de lot minimum simulés.",
                         "Drawdown mesuré aux clôtures des trades : le recul intratrade peut être supérieur.",
                         "PAXG, futures et CFD MT5 sont des instruments différents.",
                         "Les ruptures sont exclues, ce qui peut biaiser les résultats.",
                         "Un test final positif ne prouve pas la rentabilité future."]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default="PAXGUSDT")
    p.add_argument("--tf", choices=("15m", "1h", "4h", "1d"), default="1h")
    p.add_argument("--sortie", default="runtime/recherche.json")
    args = p.parse_args(argv)
    from . import donnees
    b = donnees.charger(args.source, args.tf)
    from . import registre
    import hashlib
    empreinte=hashlib.sha256(b''.join(np.asarray(b[k]).tobytes() for k in ('ts','o','h','l','c','v'))).hexdigest()
    candidats,_=signaux(b,donnees.MS[args.tf])
    ids={nom:registre.declarer("LABORATOIRE_R2",nom,args.source+":"+empreinte,
         date(b['ts'][0])+" / "+date(b['ts'][-1]),
         "Protocole exploratoire 60/20/20 ; 2 ATR/3 ATR/20 barres ; coûts forfaitaires 0.0007 et 0.0014 par côté",
         "base-f787e40-R3") for nom in candidats}
    try:
        r = evaluer(b, donnees.MS[args.tf])
    except Exception as exc:
        for identifiant in ids.values():
            registre.conclure(identifiant,{"erreur":type(exc).__name__},"erreur")
        raise
    for nom,identifiant in ids.items():
        registre.conclure(identifiant,r['validation'][nom],"exploratoire")
    r.update(source=args.source, unite=args.tf)
    dest = Path(args.sortie)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(r, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Rapport enregistré : {dest}. Sélection validation : {r['selection_validation']}. Aucun ordre activé.")


if __name__ == "__main__":
    main()
