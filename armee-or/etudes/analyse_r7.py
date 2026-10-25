"""R7 : jugement de tous les essais (permis), contrôles des survivants et Sharpe dégonflé (Bailey et López de Prado).

1. Chaque essai de recherche_r7.py et d'autres_r7.py jugé comme le permis : gagner sur chaque moitié, battre
   « toujours acheter » le même panier sur chaque moitié, 30 trades par moitié au moins.
2. Survivants (et règles gagnantes sur les deux moitiés sans battre le naïf) : 20 tirages d'entrées au hasard avec les
   mêmes sorties ; frais doublés.
3. Sharpe dégonflé : probabilité que le vrai Sharpe dépasse le meilleur Sharpe attendu PAR HASARD parmi tous les
   essais comptés (R7 + les fiches H01 à H47 et les variantes des études précédentes), pour chaque survivant et pour
   le momentum 12 mois de l'équipe.

Usage : python etudes/analyse_r7.py BINANCE YAHOO MACRO RACINE_ARMEE ESSAIS_R7.json AUTRES_R7.json
"""
import json
import os
import sys

import numpy as np

ICI = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], *sys.argv[1:5], "/dev/null", *sys.argv[5:]]
sys.path.insert(0, ICI)
sys.path.insert(0, sys.argv[4])
import recherche_r7 as R      # noqa: E402
import moteur_r7 as M         # noqa: E402

ESSAIS_AVANT = 47 + 8 + 10                            # fiches H01-H47, variantes R5.1, réglages voisins R6 à R6.2


def main(fichier_essais, fichier_autres):
    data = json.load(open(fichier_essais))
    essais, naifs = data["essais"], data["naifs"]
    autres = json.load(open(fichier_autres))
    erreurs = [e for e in essais if "erreur" in e]
    ok = [e for e in essais if "erreur" not in e]
    print(f"{len(essais)} essais règle × unité ({len(erreurs)} en erreur), {len(autres)} essais spéciaux")
    for e in erreurs:
        print("   ERREUR", e["regle"], e["unite"], e["erreur"])
    permis, positifs = [], []
    for e in ok:
        raisons = R.juge(e, naifs[e["unite"]])
        e["raisons"] = raisons
        if not raisons:
            permis.append(e)
        elif e["sharpe"][0] > 0 and e["sharpe"][1] > 0:
            positifs.append(e)
    print(f"\nPERMIS (gagne sur chaque moitié ET bat le naïf, ≥ 30 trades par moitié) : {len(permis)}")
    for e in sorted(permis, key=lambda e: -sum(e["sharpe"])):
        print(f"   {e['regle'][:52]:52} {e['unite']:4} {e['sharpe'][0]:+.2f} / {e['sharpe'][1]:+.2f} "
              f"(naïf {naifs[e['unite']]['sharpe'][0]:+.2f} / {naifs[e['unite']]['sharpe'][1]:+.2f}) "
              f"trades {e['trades']} gagnants {e['gagnants'] * 100:.0f} %")
    print(f"\nGagnent sur les deux moitiés SANS battre le naïf : {len(positifs)}")
    for e in sorted(positifs, key=lambda e: -sum(e["sharpe"])):
        print(f"   {e['regle'][:52]:52} {e['unite']:4} {e['sharpe'][0]:+.2f} / {e['sharpe'][1]:+.2f} "
              f"(naïf {naifs[e['unite']]['sharpe'][0]:+.2f} / {naifs[e['unite']]['sharpe'][1]:+.2f}) "
              f"trades {e['trades']} — {'; '.join(e['raisons'])}")
    perdants = [e for e in ok if e["sharpe"][0] <= 0 or e["sharpe"][1] <= 0]
    print(f"\nPerdent sur au moins une moitié : {len(perdants)} sur {len(ok)}")
    gagnants_pct = [e["gagnants"] for e in ok if e["trades"][0] + e["trades"][1] > 0]
    print(f"   part de trades gagnants : médiane {np.median(gagnants_pct) * 100:.0f} %, "
          f"de {min(gagnants_pct) * 100:.0f} à {max(gagnants_pct) * 100:.0f} %")
    hauts = [e for e in ok if e["gagnants"] >= 0.6 and e["trades"][0] + e["trades"][1] >= 60]
    print(f"   règles à 60 % de gagnants ou plus : {len(hauts)}, dont gagnantes sur les deux moitiés : "
          f"{sum(1 for e in hauts if e['sharpe'][0] > 0 and e['sharpe'][1] > 0)}")

    print("\nJOURNALIER : stop et objectif touchés le même jour, ordre probable de la bougie au lieu du stop d'abord")
    chg = []
    for e in ok:
        if e["unite"] != "1j":
            continue
        r = R.essai(e["regle"], "1j", chemin="ohlc")
        raisons = R.juge(r, naifs["1j"])
        chg.append((e, r, raisons))
        if not raisons or (r["sharpe"][0] > 0 and r["sharpe"][1] > 0):
            print(f"   {e['regle'][:52]:52} prudent {e['sharpe'][0]:+.2f} / {e['sharpe'][1]:+.2f} → ordre probable "
                  f"{r['sharpe'][0]:+.2f} / {r['sharpe'][1]:+.2f} {'✅ PERMIS' if not raisons else '; '.join(raisons)}")
    print(f"   {sum(1 for _, r, x in chg if not x)} permis sur {len(chg)} règles journalières avec l'ordre probable")
    for e, r, raisons in chg:
        if not raisons and e not in permis:
            r["raisons"] = []
            r["regle"] = e["regle"] + " (ordre probable)"
            permis.append(r)

    print("\nCONTRÔLES des règles retenues (permis ou gagnantes sur les deux moitiés)")
    controles = []
    for e in permis + positifs:
        hasard = []
        nom_r = e["regle"].replace(" (ordre probable)", "")
        ch = "ohlc" if e["regle"].endswith("(ordre probable)") else "prudent"
        for g in range(20):
            r = R.essai(nom_r, e["unite"], graine=g, chemin=ch)
            hasard.append(r["sharpe_total"])
        frais2 = R.essai(nom_r, e["unite"], facteur_frais=2.0, chemin=ch)
        rang = float(np.mean([e["sharpe_total"] > h for h in hasard]))
        ctl = {"regle": e["regle"], "unite": e["unite"], "sharpe_total": e["sharpe_total"],
               "hasard_max": max(hasard), "hasard_median": float(np.median(hasard)), "rang_hasard": rang,
               "frais_x2": frais2["sharpe"], "permis_frais_x2": not R.juge(frais2, naifs[e["unite"]])}
        controles.append(ctl)
        print(f"   {e['regle'][:46]:46} {e['unite']:4} Sharpe {e['sharpe_total']:+.2f} | hasard : médiane "
              f"{ctl['hasard_median']:+.2f}, max {ctl['hasard_max']:+.2f} → {'signal ✅' if rang >= 0.95 else 'pas mieux que le hasard ✖'}"
              f" | frais × 2 : {frais2['sharpe'][0]:+.2f} / {frais2['sharpe'][1]:+.2f} "
              f"{'(permis)' if ctl['permis_frais_x2'] else '(pas de permis)'}", flush=True)

    print("\nSHARPE DÉGONFLÉ (Bailey et López de Prado) et seuil t ≥ 3 (Harvey, Liu et Zhu)")
    reels = [e for e in ok if e["trades"][0] + e["trades"][1] > 0]
    n_total = len(reels) + sum(1 for a in autres if a.get("sharpe_total") is not None) + ESSAIS_AVANT
    print(f"   essais comptés : {len(reels)} règle × unité ayant tradé, "
          f"{sum(1 for a in autres if a.get('sharpe_total') is not None)} spéciaux, {ESSAIS_AVANT} avant R7 = {n_total}")
    print("   variance du Sharpe sans aucun avantage : 252 / observations quotidiennes ; deux comptes : les 3 règles que "
          "le permis compare (CANDIDATES), et TOUS les essais (le plus sévère)")
    candidats = [(e["regle"] + " " + e["unite"], e) for e in permis] + \
                [(a["regle"], a) for a in autres if a.get("permis")]
    from armee_or import marches as MM
    propres = R.yahoo()
    banc = MM.banc(propres, strategies=("momentum_12m",), sorties=MM.SORTIES, serie=True)["momentum_12m"]
    j, p = banc["serie"]
    eq = {"regle": "momentum 12 mois de l'équipe (verrou, par famille)", "sharpe_total": M.sharpe(p),
          "jours": len(p), "annees": (j[-1] - j[0]) / 365.25, "asym": R._moment(p, 3), "aplat": R._moment(p, 4)}
    candidats.append((eq["regle"], eq))
    resultat = []
    for nom, e in candidats:
        # Sharpe annualisé par √252 sur la série quotidienne (week-ends des cryptos compris, comme le banc) : sa
        # variance sans avantage est 252 / observations, et t = Sharpe × √(observations / 252)
        t_stat = e["sharpe_total"] * (e["jours"] / 252) ** 0.5
        ligne = {"regle": nom, "sharpe": e["sharpe_total"], "annees": round(e["annees"], 1), "t": round(t_stat, 2)}
        txt = f"   {nom[:52]:52} Sharpe {e['sharpe_total']:+.2f} sur {e['annees']:.0f} ans, t = {t_stat:.2f} " \
              f"({'≥ 3 ✅' if t_stat >= 3 else '< 3 ✖'})"
        for n_e in (3, n_total):
            prob, sr0 = M.sharpe_degonfle(e["sharpe_total"], n_e, 252 / e["jours"], e["jours"], e.get("asym", 0.0),
                                          e.get("aplat", 3.0))
            ligne[f"probabilite_{n_e}"] = round(prob, 3)
            ligne[f"seuil_{n_e}"] = round(sr0, 3)
            txt += f" | {n_e} essais : hasard {sr0:+.2f}, avantage réel {prob * 100:.0f} %"
        resultat.append(ligne)
        print(txt)
    return {"permis": [(e["regle"], e["unite"]) for e in permis], "controles": controles, "degonfle": resultat,
            "n_essais": n_total}


if __name__ == "__main__":
    out = main(sys.argv[6], sys.argv[7])
    if len(sys.argv) > 8:
        json.dump(out, open(sys.argv[8], "w"), ensure_ascii=False, indent=1)
