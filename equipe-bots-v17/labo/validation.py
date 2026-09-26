"""Les 7 portes du labo. « 99 % des backtests échouent une fois sur le marché » : ces portes sont là pour
rejeter la plupart des idées AVANT qu'elles ne coûtent quoi que ce soit. Une stratégie qui les passe toutes
n'est PAS prouvée rentable : elle mérite seulement un test en direct, sur papier.

Données : BTC, ETH et SOL (Binance Spot), toute la période des archives vérifiées. Pas d'optimisation de
paramètres ici : la stratégie est jugée telle qu'elle a été décrite.
"""
from __future__ import annotations

import hashlib
import json
import time

import numpy as np

from . import donnees as D
from .moteur import FRAIS, GLISSEMENT, simuler, statistiques
from .strategie import conditions, decrire

SEUILS = {"trades_min": 30, "facteur_profit_min": 1.2, "actifs_gagnants_min": 2, "periodes": 5,
          "periodes_gagnantes_min": 3, "baisse_max_pct": 20.0, "mc_proba_gain_min": 0.90, "mc_baisse95_max_pct": 30.0,
          "mc_tirages": 2000}


def _monte_carlo(rc, graine, tirages):
    """Rééchantillonnage des trades (avec remise) : chances de finir gagnant et pire baisse probable (95 %)."""
    if len(rc) < 2:
        return 0.0, 100.0
    rng = np.random.default_rng(graine)
    echant = rng.choice(rc, size=(tirages, len(rc)), replace=True)
    courbes = np.cumprod(1 + echant, axis=1)
    finale = courbes[:, -1]
    sommets = np.maximum.accumulate(np.concatenate((np.ones((tirages, 1)), courbes), axis=1), axis=1)[:, 1:]
    baisses = ((sommets - courbes) / sommets).max(axis=1)
    return float((finale > 1).mean()), float(np.percentile(baisses, 95) * 100)


def _courbe(trades, points=120):
    if not trades:
        return []
    tri = sorted(trades, key=lambda t: t["sortie_ts"])
    eq = np.cumprod([1 + t["r_capital"] for t in tri])
    pas = max(1, len(tri) // points)
    return [[tri[i]["sortie_ts"] // 1000, round(float(eq[i] - 1) * 100, 2)] for i in range(0, len(tri), pas)] + \
           [[tri[-1]["sortie_ts"] // 1000, round(float(eq[-1] - 1) * 100, 2)]]


def evaluer(spec, symboles=D.SYMBOLES, seuils=SEUILS):
    """Backtest + portes. -> dict sérialisable en JSON (résultat affiché dans l'application)."""
    debut_calcul = time.time()
    base, stress, par_actif = [], [], {}
    bornes = [None, None]
    for sym in symboles:
        barres = D.charger(sym, spec["unite"])
        sig = conditions(barres, spec)
        tb, _, _ = simuler(barres, spec, signaux=sig)
        ts, _, _ = simuler(barres, spec, signaux=sig, frais=FRAIS * 2, glissement=GLISSEMENT * 2)
        base += tb
        stress += ts
        par_actif[sym] = statistiques(tb)
        bornes[0] = min(bornes[0] or barres["ts"][0], barres["ts"][0])
        bornes[1] = max(bornes[1] or barres["ts"][-1], barres["ts"][-1])

    sb, ss = statistiques(base), statistiques(stress)
    # stabilité : la période est coupée en tranches égales ; chaque tranche doit gagner (somme des résultats)
    n_per = seuils["periodes"]
    limites = np.linspace(bornes[0], bornes[1] + 1, n_per + 1)
    periodes = []
    for a, b in zip(limites[:-1], limites[1:]):
        dans = [t for t in base if a <= t["sortie_ts"] < b]
        periodes.append({"debut": int(a // 1000), "fin": int(b // 1000), "trades": len(dans),
                         "gain_pct": round(float((np.prod([1 + t["r_capital"] for t in dans]) - 1) * 100), 2)})
    rc = np.array([t["r_capital"] for t in base])
    graine = int(hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:8], 16)
    proba, baisse95 = _monte_carlo(rc, graine, seuils["mc_tirages"])
    gagnants = sum(1 for s in par_actif.values() if s["trades"] and s["gain_pct"] > 0)
    per_ok = sum(1 for p in periodes if p["gain_pct"] > 0)

    portes = [
        {"nom": "Assez de trades", "ok": sb["trades"] >= seuils["trades_min"],
         "detail": f"{sb['trades']} trades (minimum {seuils['trades_min']})"},
        {"nom": "Rentable après frais", "ok": sb["facteur_profit"] >= seuils["facteur_profit_min"],
         "detail": f"facteur de profit {sb['facteur_profit']:.2f} (minimum {seuils['facteur_profit_min']})"},
        {"nom": "Résiste à des coûts doublés", "ok": ss["trades"] > 0 and ss["gain_pct"] > 0,
         "detail": f"{ss['gain_pct']:+.1f} % avec frais et glissement × 2"},
        {"nom": "Gagnante sur plusieurs cryptos", "ok": gagnants >= seuils["actifs_gagnants_min"],
         "detail": f"{gagnants} sur {len(symboles)} (minimum {seuils['actifs_gagnants_min']})"},
        {"nom": "Stable dans le temps", "ok": per_ok >= seuils["periodes_gagnantes_min"],
         "detail": f"{per_ok} périodes gagnantes sur {n_per} (minimum {seuils['periodes_gagnantes_min']})"},
        {"nom": "Baisse maximale supportable", "ok": sb["trades"] > 0 and sb["baisse_max_pct"] <= seuils["baisse_max_pct"],
         "detail": f"{sb['baisse_max_pct']:.1f} % (maximum {seuils['baisse_max_pct']:.0f} %)"},
        {"nom": "Pas un coup de chance (Monte-Carlo)",
         "ok": proba >= seuils["mc_proba_gain_min"] and baisse95 <= seuils["mc_baisse95_max_pct"],
         "detail": f"{proba * 100:.0f} % de chances de finir gagnant (min. {seuils['mc_proba_gain_min'] * 100:.0f} %), "
                   f"pire baisse probable {baisse95:.0f} % (max. {seuils['mc_baisse95_max_pct']:.0f} %)"},
    ]
    return {
        "valide": all(p["ok"] for p in portes), "portes": portes, "spec": spec, "resume": decrire(spec),
        "global": sb, "stress": ss, "par_actif": par_actif, "periodes": periodes,
        "monte_carlo": {"proba_gain": proba, "baisse95_pct": baisse95},
        "courbe": _courbe(base), "historique": {"debut": int(bornes[0] // 1000), "fin": int(bornes[1] // 1000),
                                                 "symboles": list(symboles)},
        "hypotheses": f"1 % du capital risqué par trade, frais {FRAIS * 100:.1f} % + glissement {GLISSEMENT * 100:.2f} % "
                      "par côté, achat à l'ouverture suivant le signal, stop compté en premier si doute.",
        "duree_s": round(time.time() - debut_calcul, 1),
    }
