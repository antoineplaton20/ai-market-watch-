"""ÉVOLUTION : le système engendre, teste et élimine ses propres stratégies, puis se met à jour.
Lancement (1 fois par semaine, par exemple le dimanche) : python evolution.py

Cycle : observer (nouvelles bougies) → muter / croiser → backtest → sélectionner → coffre-fort → duel réel.
- 4 espèces (momentum, reversion, breakout, range) avec quotas : aucune ne peut éliminer les autres.
- Mémoire génétique : la population survit d'une semaine à l'autre et repart des meilleures.
- Coffre-fort : les 20 % d'historique les plus récents ne sont JAMAIS montrés à l'évolution.
- Barre anti-chance : plus on a ouvert le coffre, plus le résultat exigé est élevé.
- Monte-Carlo : 1 000 ordres de trades tirés au hasard, la pire baisse probable doit rester sous 10 %.
- Le gagnant devient CHALLENGER : il ne remplace le champion qu'après l'avoir battu en conditions réelles."""
import csv
import datetime as dt
import json
import math
import os
import random
import time
import warnings
import numpy as np
import config
import backtest as B
import strategie as S
from simulation import simuler_serie
import surapprentissage as SA

warnings.filterwarnings("ignore")
np.seterr(all="ignore")
FICHIER_POP = "population.json"
FICHIER_ETAT = "evolution_etat.json"
FICHIER_JOURNAL = "evolution_journal.csv"


# ============================ CARACTÉRISTIQUES ============================
def caracteristiques(df, unite):
    """Traduit l'historique en colonnes que les génomes savent lire (votes, vetos, extrêmes)."""
    A = {k: df[k].to_numpy(dtype=float) for k in df.columns}
    c, e20, e50, v, vm = A["c"], A["ema20"], A["ema50"], A["v"], A["vol_moy"]
    par_jour = 1440 // config.MINUTES[unite]
    ech = config.echelle(unite)
    part = np.where(v > 0, A["v_achat"] / np.where(v > 0, v, 1), 0.5)
    evol_oi = A["oi"] / A["oi_3h"]
    foule, gros, liq, nq, dxy = A["ls_foule"], A["ls_gros"], A["liq_7j"], A["nasdaq_ok"], A["dxy_stress"]
    nan = np.nan
    F = {
        "c": c, "ema20": e20, "rsi": A["rsi"], "atr": A["atr"], "v": v, "vol_moy": vm, "sup1": A["sup1"],
        "hausse_24h": np.r_[np.full(par_jour, nan), (c[par_jour:] / c[:-par_jour] - 1) * 100],
        "vote_TENDANCE": ((c > e20) & (e20 > e50)).astype(float),
        "vote_MOMENTUM": ((A["rsi"] >= 50) & (A["rsi"] <= 68) & (v > vm)).astype(float),
        "vote_MULTI_UNITES": ((A["sup1"] == 1).astype(float) + (A["sup2"] == 1).astype(float)) / 2,
        "vote_CARNET": np.where(part >= 0.55, 1.0, np.where(part >= 0.50, 0.5, 0.0)),
        "vote_DERIVES": np.where(np.isnan(evol_oi), nan, np.where(evol_oi >= config.OI_HAUSSE_MIN, 1.0,
                                                                 np.where(evol_oi >= 0.99, 0.5, 0.2))),
        "vote_LIQUIDITE": np.where(np.isnan(liq), nan, np.where(liq > config.LIQUIDITE_ENTREE_PCT, 1.0, 0.5)),
        "vote_MACRO": np.where(np.isnan(nq) | np.isnan(dxy), nan, ((nq == 1).astype(float) + (dxy != 1).astype(float)) / 2),
        "vote_POSITIONNEMENT": np.where(np.isnan(foule) | np.isnan(gros), nan,
                                        np.where(gros > foule * 1.05, 1.0, np.where(gros > foule * 0.95, 0.5, 0.2))),
        "vote_MARCHES_MONDIAUX": np.where(np.isnan(A["spx_ok"]), nan, np.where(A["spx_ok"] == 1, 1.0, 0.3)),
        "sup2": A["sup2"], "fng": A["fng"],
    }
    F.update(S.indicateurs_encyclopedie(c))
    F.update(S.CH.caracteristiques(A["o"], A["h"], A["l"], c))            # bougies japonaises
    hausse_4b = np.r_[np.full(4, nan), (c[4:] / c[:-4] - 1) * 100]
    t = A["t_ferme"]
    idx = np.searchsorted(B.MACRO_MS, t)
    proche = np.minimum(np.abs(t - B.MACRO_MS[np.clip(idx, 0, len(B.MACRO_MS) - 1)]),
                        np.abs(t - B.MACRO_MS[np.clip(idx - 1, 0, len(B.MACRO_MS) - 1)]))
    F.update({
        "veto_METEO": A["btc_ok"] != 1,
        "veto_ANTI_HYPE": ((vm > 0) & (v > config.HYPE_VOLUME_X * vm)) | (hausse_4b > config.HYPE_HAUSSE_1H_PCT * ech),
        "veto_DERIVES_VETO": A["funding"] > config.FUNDING_MAX,
        "veto_PEUR_AVIDITE": (A["fng"] >= config.AVIDITE_FORTE) | (A["fng"] <= config.PEUR_EXTREME),
        "veto_CALENDRIER": proche <= config.CALENDRIER_MARGE_H * 3600000,
        "veto_LIQUIDITE_VETO": liq < config.LIQUIDITE_SORTIE_PCT,
        "veto_MACRO_VETO": (~np.isnan(nq)) & (~np.isnan(dxy)) & (nq != 1) & (dxy == 1),
        "veto_POSITIONNEMENT_VETO": foule > config.POS_FOULE_MAX,
        "veto_MARCHES_MONDIAUX_VETO": A["vix_stress"] == 1,
        "veto_ATTENTION_VETO": A["attention"] > config.ATTENTION_PIC_X,
    })
    for n in sorted(set(S.LOOKBACKS + S.LOOKBACKS_STOP)):
        F[f"hh_{n}"], F[f"ll_{n}"] = S.extremes(A["h"], A["l"], n)
    return {"F": F, "o": A["o"], "h": A["h"], "l": A["l"], "c": c, "atr": np.nan_to_num(A["atr"]),
            "t": A["t"].astype(np.int64), "t_ferme": t, "debut": max(200, par_jour + 5)}


def preparer_paires(unite, jours, nb_paires):
    donnees15, externes = B.charger(jours, nb_paires, config.EVO_UNIVERS)
    paires = []
    for sym, df15 in donnees15.items():
        P = caracteristiques(B.preparer(df15, unite, externes, sym.split("/")[0]), unite)
        P["nom"] = sym
        paires.append(P)
    t_min = min(P["t"][P["debut"]] for P in paires)
    t_max = max(P["t"][-1] for P in paires)
    coffre = t_max - (t_max - t_min) * config.EVO_COFFRE_PCT / 100
    marge = config.HORIZON_H[unite] * 2 * 3600 * 1000            # aucun trade d'entraînement ne déborde dans le coffre
    for P in paires:
        i = np.arange(len(P["t"]))
        P["masque_app"] = (i >= P["debut"]) & (P["t_ferme"] < coffre - marge)
        P["masque_coffre"] = (i >= P["debut"]) & (P["t_ferme"] >= coffre)
    return paires, (t_min, coffre, t_max)


# ================================ ÉVALUATION ================================
def trades_du_genome(g, paires, masque, unite):
    ps = S.params_sortie(g, unite)
    te, ts, rs, ks = [], [], [], []
    for k, P in enumerate(paires):
        sig, _ = S.decider(g, P["F"], unite)
        sig = np.asarray(sig & P[masque], dtype=np.bool_)
        dist = np.asarray(S.distance_stop(g, P["F"]), dtype=np.float64)
        e, s, r = simuler_serie(P["o"], P["h"], P["l"], P["c"], P["atr"], sig, dist, ps["secu_r"],
                                ps["trailing_atr"], ps["objectif_atr"], ps["part_frac"], ps["part_r"],
                                ps["horizon_bougies"], config.GLISSEMENT_PCT / 100, config.FRAIS_ALLER_RETOUR_PCT,
                                config.GLISSEMENT_STOP_PCT / 100)
        te.append(P["t"][e])
        ts.append(P["t"][np.minimum(s, len(P["t"]) - 1)])
        rs.append(r)
        ks.append(np.full(len(r), k))
    return np.concatenate(te), np.concatenate(ts), np.concatenate(rs), np.concatenate(ks)


def pire_baisse(te, ts, rs):
    """Portefeuille réaliste : 1 % risqué par trade, 3 positions maximum en même temps."""
    ordre = np.argsort(te)
    capital, pic, pire, ouvertes = 1.0, 1.0, 0.0, []
    for i in ordre:
        ouvertes = [f for f in ouvertes if f > te[i]]
        if len(ouvertes) >= config.POSITIONS_MAX:
            continue
        ouvertes.append(ts[i])
        capital *= 1 + config.RISQUE_PAR_TRADE_PCT / 100 * rs[i]
        pic = max(pic, capital)
        pire = min(pire, capital / pic - 1)
    return max(0.0, -pire)


def mesurer(te, ts, rs, ks, bornes, nb_paires):
    n = len(rs)
    if n == 0:
        return {"n": 0, "E": 0.0, "E_min": -1.0, "dd": 1.0, "pf": 0.0, "consistance": 0.0, "std": 1.0}
    periodes = [rs[(te >= bornes[p]) & (te < bornes[p + 1])] for p in range(len(bornes) - 1)]
    e_periodes = [float(x.mean()) if len(x) >= 5 else -0.5 for x in periodes]
    gains, pertes = rs[rs > 0].sum(), -rs[rs < 0].sum()
    par_paire = [rs[ks == k].mean() for k in range(nb_paires) if (ks == k).sum() >= 5]
    return {"n": n, "E": float(rs.mean()), "E_min": min(e_periodes), "E_periodes": e_periodes,
            "dd": pire_baisse(te, ts, rs), "pf": float(gains / pertes) if pertes > 0 else 9.9,
            "consistance": float(np.mean([x > 0 for x in par_paire])) if par_paire else 0.0,
            "std": float(rs.std()) if n > 1 else 1.0}


def fitness(m):
    """Robustesse d'abord : la PIRE période compte autant que la moyenne."""
    if m["n"] < config.EVO_TRADES_MIN:
        return -2 + m["n"] / config.EVO_TRADES_MIN, False
    vivant = m["dd"] <= config.EVO_DD_MAX and m["pf"] >= 1.05 and m["E_min"] > 0 and m["consistance"] >= 0.5
    f = (0.5 * m["E_min"] + 0.5 * m["E"]) * min(1.0, m["n"] / 150) \
        - 2 * max(0.0, m["dd"] - 0.05) - 0.2 * max(0.0, 0.5 - m["consistance"])
    return f, vivant


def evaluer(g, paires, unite, bornes_app):
    te, ts, rs, ks = trades_du_genome(g, paires, "masque_app", unite)
    m = mesurer(te, ts, rs, ks, bornes_app, len(paires))
    f, vivant = fitness(m)
    return {**g, "_fitness": f, "_vivant": vivant, "_m": m, "_te": te, "_rs": rs}


def diagnostic_surapprentissage(evalues, t_debut, t_fin):
    """PBO de la sélection, nombre de stratégies vraiment différentes, dispersion des Sharpe."""
    population = [g for e in S.ESPECES for g in evalues[e] if len(g["_rs"]) >= 10]
    if len(population) < 10:
        return {"pbo": None, "degradation": None, "n_effectif": 1.0, "var_sharpe": 0.0, "n": len(population)}
    M = SA.matrice_tranches([(g["_te"], g["_rs"]) for g in population], t_debut, t_fin, config.PBO_TRANCHES)
    pbo, degradation = SA.pbo_cscv(M)
    sharpes = [SA.sharpe(g["_rs"]) for g in population]
    return {"pbo": pbo, "degradation": degradation, "n_effectif": SA.n_effectif(M),
            "var_sharpe": SA.variance_robuste(sharpes), "n": len(population)}


def ligne_diagnostic(d):
    if d["pbo"] is None:
        return "🧪 Sur-apprentissage : non mesurable (trop peu de stratégies actives)."
    verdict = "sélection fiable ✅" if d["pbo"] <= config.PBO_MAX else "sélection peu fiable ⚠️"
    return (f"🧪 Sur-apprentissage : PBO {d['pbo']:.0%} (seuil {config.PBO_MAX:.0%}) → {verdict} | "
            f"stratégies vraiment différentes : {d['n_effectif']:.0f} sur {d['n']}")


# ================================ COFFRE-FORT ================================
def monte_carlo_dd(rs, tirages):
    """Pire baisse au 95e centile quand on mélange l'ordre des trades (la chance de l'ordre ne compte plus)."""
    if len(rs) < 10:
        return 1.0
    pires = []
    for _ in range(tirages):
        seq = np.random.choice(rs, size=len(rs), replace=True)
        cap = np.cumprod(1 + config.RISQUE_PAR_TRADE_PCT / 100 * seq)
        pires.append(-np.min(cap / np.maximum.accumulate(cap) - 1))
    return float(np.percentile(pires, 95))


def ouvrir_coffre(g, paires, unite, bornes_coffre, ouvertures):
    te, ts, rs, ks = trades_du_genome(g, paires, "masque_coffre", unite)
    m = mesurer(te, ts, rs, ks, bornes_coffre, len(paires))
    _, _, rs_app, _ = trades_du_genome(g, paires, "masque_app", unite)
    m["mc_dd95"] = monte_carlo_dd(np.concatenate([rs_app, rs]), config.EVO_MONTE_CARLO)
    m["barre"] = 0.05 + m["std"] * math.sqrt(2 * math.log(1 + ouvertures)) / math.sqrt(max(m["n"], 1))
    raisons = []
    if m["n"] < 20:
        raisons.append(f"trop peu de trades ({m['n']})")
    if m["E"] <= m["barre"]:
        raisons.append(f"espérance {m['E']:+.3f} R sous la barre anti-chance {m['barre']:.3f} R")
    if m["dd"] > config.EVO_DD_MAX:
        raisons.append(f"pire baisse {m['dd']:.1%}")
    if m["mc_dd95"] > config.EVO_DD_MAX:
        raisons.append(f"pire baisse probable (Monte-Carlo) {m['mc_dd95']:.1%}")
    return m, raisons


# ================================ PROGRESSION ================================
def meilleurs_precedents():
    """Meilleure espérance de chaque espèce lors du passage précédent (lue dans le journal)."""
    if not os.path.exists(FICHIER_JOURNAL):
        return {}
    with open(FICHIER_JOURNAL, encoding="utf-8") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    res = {}
    for l in lignes:                               # la dernière génération écrite l'emporte
        res[l["espece"]] = float(l["esperance_R"])
    return res


def progression(evalues, hier):
    lignes = [f"📈 Ce que l'équipe a appris ({dt.date.today()}) — meilleure stratégie de chaque espèce :"]
    for e in S.ESPECES:
        best = max(evalues[e], key=lambda g: (g["_vivant"], g["_fitness"]))
        m, avant = best["_m"], hier.get(e)
        tendance = "" if avant is None else (" ⬆️" if m["E"] > avant + 0.005 else " ⬇️" if m["E"] < avant - 0.005 else " =")
        lignes.append(f"• {e:<10} {m['E']:+.3f} R ({'vivante ✅' if best['_vivant'] else 'non validée'}), "
                      f"pire période {m['E_min']:+.3f} R{tendance}")
    lignes.append("Une baisse n'est pas un recul : les données de la semaine sont nouvelles, les stratégies "
                  "fragiles sont démasquées. Le champion ne change qu'après coffre-fort + duel réel.")
    return "\n".join(lignes)


# ================================ GÉNÉTIQUE ================================
def charger_json(f, defaut):
    if os.path.exists(f):
        with open(f, encoding="utf-8") as x:
            return json.load(x)
    return defaut


def ecrire_json(f, contenu):
    """Écriture atomique : le bot, qui relit ces fichiers en continu, ne voit jamais un fichier à moitié écrit."""
    tmp = f + ".tmp"
    with open(tmp, "w", encoding="utf-8") as x:
        json.dump(contenu, x, indent=2, ensure_ascii=False)
    os.replace(tmp, f)


def propre(g):
    return {k: v for k, v in g.items() if not k.startswith("_")}


def population_initiale():
    pop = [S.completer(propre(g)) for g in charger_json(FICHIER_POP, []) if g.get("espece") in S.ESPECES]
    for g in (S.genome_defaut(), S.champion(), S.challenger()):
        if g and all(g.get("id") != x.get("id") for x in pop):
            pop.append(propre(g))
    par_espece = {e: [g for g in pop if g["espece"] == e][:config.EVO_PAR_ESPECE] for e in S.ESPECES}
    for e in S.ESPECES:
        while len(par_espece[e]) < config.EVO_PAR_ESPECE:
            par_espece[e].append(S.aleatoire(e))
    return par_espece


def tournoi(evalues, k=3):
    return max(random.sample(evalues, min(k, len(evalues))), key=lambda g: (g["_vivant"], g["_fitness"]))


def generation_suivante(evalues):
    evalues = sorted(evalues, key=lambda g: (g["_vivant"], g["_fitness"]), reverse=True)
    elites = [propre(g) for g in evalues[:config.EVO_ELITES]]
    parents = evalues[: max(4, len(evalues) // 2)]
    enfants = []
    while len(elites) + len(enfants) < config.EVO_PAR_ESPECE - config.EVO_IMMIGRANTS:
        enfant = S.croiser(tournoi(parents), tournoi(parents))
        enfants.append(S.muter(enfant))
    immigrants = [S.aleatoire(evalues[0]["espece"]) for _ in range(config.EVO_IMMIGRANTS)]
    return elites + enfants + immigrants


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--quotidien", action="store_true", help="entraînement du jour, sans ouvrir le coffre")
    quotidien = ap.parse_args().quotidien
    nb_generations = config.EVO_GENERATIONS_QUOTIDIEN if quotidien else config.EVO_GENERATIONS
    debut = time.time()
    unite = config.EVO_UNITE
    etat = charger_json(FICHIER_ETAT, {"essais_total": 0, "ouvertures_coffre": 0, "historique": []})
    print(f"ÉVOLUTION {'QUOTIDIENNE' if quotidien else 'HEBDOMADAIRE'} en {unite} : {config.EVO_JOURS} jours, "
          f"{config.EVO_PAIRES} paires, {nb_generations} générations de {config.EVO_PAR_ESPECE * len(S.ESPECES)} stratégies")
    hier = meilleurs_precedents()
    paires, (t_min, coffre, t_max) = preparer_paires(unite, config.EVO_JOURS, config.EVO_PAIRES)
    bornes_app = np.linspace(t_min, coffre, 4)                    # 3 sous-périodes d'entraînement
    bornes_coffre = np.array([coffre, t_max + 1])
    jour = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
    print(f"Entraînement : {jour(t_min)} → {jour(coffre)} | coffre-fort (jamais vu) : {jour(coffre)} → {jour(t_max)}")

    pop = population_initiale()
    journal_neuf = not os.path.exists(FICHIER_JOURNAL)
    with open(FICHIER_JOURNAL, "a", newline="", encoding="utf-8") as fj:
        w = csv.writer(fj, delimiter=";")
        if journal_neuf:
            w.writerow(["date", "generation", "espece", "fitness", "esperance_R", "pire_periode_R", "trades",
                        "pire_baisse", "vivantes"])
        evalues = {}
        for gen in range(1, nb_generations + 1):
            ligne = []
            for e in S.ESPECES:
                evalues[e] = [evaluer(g, paires, unite, bornes_app) for g in pop[e]]
                etat["essais_total"] += len(evalues[e])
                best = max(evalues[e], key=lambda g: (g["_vivant"], g["_fitness"]))
                vivantes = sum(g["_vivant"] for g in evalues[e])
                m = best["_m"]
                w.writerow([dt.date.today(), gen, e, round(best["_fitness"], 4), round(m["E"], 4),
                            round(m["E_min"], 4), m["n"], round(m["dd"], 4), vivantes])
                ligne.append(f"{e[:4]} {m['E']:+.2f}R/{vivantes}v")
                if gen < nb_generations:
                    pop[e] = generation_suivante(evalues[e])
            print(f"  génération {gen:>2} | " + " | ".join(ligne))

    # Mémoire génétique : les meilleures de chaque espèce repartent la semaine prochaine
    survivants = []
    for e in S.ESPECES:
        survivants += [propre(g) for g in sorted(evalues[e], key=lambda g: (g["_vivant"], g["_fitness"]),
                                                  reverse=True)[:config.EVO_PAR_ESPECE]]
    ecrire_json(FICHIER_POP, survivants)
    diag = diagnostic_surapprentissage(evalues, t_min, coffre)
    progres = progression(evalues, hier) + "\n" + ligne_diagnostic(diag)
    print("\n" + progres)
    if quotidien:
        ecrire_json(FICHIER_ETAT, etat)
        with open("evolution_rapport_quotidien.txt", "w", encoding="utf-8") as f:
            f.write(progres)
        try:
            from alertes import alerte
            alerte(progres)
        except Exception:
            pass
        return

    # Coffre-fort : on ne l'ouvre que pour la meilleure stratégie VIVANTE de chaque espèce
    lignes = [f"=== ÉVOLUTION du {dt.date.today()} | unité {unite} | {etat['essais_total']} stratégies testées au total ===", ""]
    candidats = []
    for e in S.ESPECES:
        vivantes = [g for g in evalues[e] if g["_vivant"]]
        if vivantes:
            candidats.append(max(vivantes, key=lambda g: g["_fitness"]))
    ref = {}
    for nom, g in (("champion", S.champion()), ("challenger", S.challenger())):
        if g:
            te, ts, rs, ks = trades_du_genome(g, paires, "masque_coffre", unite)
            ref[nom] = mesurer(te, ts, rs, ks, bornes_coffre, len(paires))["E"]
    lignes.append("Référence sur le coffre : " + ", ".join(f"{k} {v:+.3f} R" for k, v in ref.items()))
    lignes.append(ligne_diagnostic(diag))
    admis = []
    if not candidats:
        lignes.append("Aucune stratégie vivante cette semaine (aucune ne tient sur toutes les périodes) : on garde le champion.")
    if diag["pbo"] is None or diag["pbo"] > config.PBO_MAX:
        if candidats:
            lignes.append("La sélection de cette semaine choisit trop souvent la chance : le coffre reste fermé, "
                          "aucun challenger. C'est une protection, pas un échec.")
        candidats = []
    for g in candidats:
        g["_dsr"] = SA.sharpe_degonfle(g["_rs"], diag["var_sharpe"], diag["n_effectif"])
        if g["_dsr"] < config.DSR_MIN:
            lignes.append(f"\n{g['espece']} [{g['id']}] écarté avant le coffre : Sharpe dégonflé {g['_dsr']:.0%} "
                          f"(minimum {config.DSR_MIN:.0%}), son avantage peut venir du nombre d'essais.")
            continue
        etat["ouvertures_coffre"] += 1
        m, raisons = ouvrir_coffre(g, paires, unite, bornes_coffre, etat["ouvertures_coffre"])
        meilleur_que = max(ref.values()) if ref else -9
        if not raisons and m["E"] <= meilleur_que:
            raisons.append(f"ne bat pas le champion/challenger actuel ({meilleur_que:+.3f} R)")
        mt = g["_m"]
        lignes.append(f"\n{g['espece']} [{g['id']}] {S.decrire(g)}")
        lignes.append(f"  entraînement : {mt['n']} trades, {mt['E']:+.3f} R, pire période {mt['E_min']:+.3f} R, "
                      f"pire baisse {mt['dd']:.1%}, paires gagnantes {mt['consistance']:.0%}, "
                      f"Sharpe dégonflé {g['_dsr']:.0%}")
        lignes.append(f"  COFFRE : {m['n']} trades, {m['E']:+.3f} R (barre {m['barre']:.3f}), pire baisse {m['dd']:.1%}, "
                      f"Monte-Carlo {m['mc_dd95']:.1%} → " + ("ADMIS ✅" if not raisons else "refusé : " + " ; ".join(raisons)))
        if not raisons:
            admis.append((m["E"], g, m))
    if admis:
        e, g, m = max(admis, key=lambda x: x[0])
        ecrire_json(S.FICHIER_CHALLENGER, {"genome": propre(g), "unite": unite, "date": str(dt.date.today()),
                                           "coffre": {k: v for k, v in m.items() if k != "E_periodes"},
                                           "entrainement": g["_m"], "pbo": diag["pbo"], "dsr": g["_dsr"],
                                           "n_effectif": diag["n_effectif"]})
        lignes.append(f"\n🧬 NOUVEAU CHALLENGER : {g['espece']} [{g['id']}]. Il va affronter le champion en conditions réelles "
                      f"({config.DUEL_JOURS_MIN} jours minimum) avant de pouvoir le remplacer.")
        etat["historique"].append({"date": str(dt.date.today()), "challenger": g["id"], "espece": g["espece"], "E_coffre": e})
    else:
        lignes.append("\nPas de nouveau challenger cette semaine. Le champion actuel reste en place.")
    lignes.append(f"\nDurée : {(time.time() - debut) / 60:.1f} min | ouvertures du coffre à ce jour : {etat['ouvertures_coffre']}")
    try:
        import registre
        registre.ajouter("evolution", {
            "unite": unite, "periode_entrainement": [jour(t_min), jour(coffre)], "periode_coffre": [jour(coffre), jour(t_max)],
            "essais_total": etat["essais_total"], "pbo": diag["pbo"], "n_effectif": diag["n_effectif"],
            "challenger": ({"id": max(admis, key=lambda x: x[0])[1]["id"],
                            "genome": propre(max(admis, key=lambda x: x[0])[1])} if admis else None)})
    except Exception as e:
        lignes.append(f"(registre indisponible : {e})")
    ecrire_json(FICHIER_ETAT, etat)
    texte = "\n".join(lignes)
    print("\n" + texte)
    with open("evolution_rapport.txt", "w", encoding="utf-8") as f:
        f.write(texte)
    try:
        from alertes import alerte
        if admis:
            alerte(f"🧬 Évolution terminée : nouveau challenger {max(admis, key=lambda x: x[0])[1]['espece']}. Duel en cours.\n"
                   + ligne_diagnostic(diag))
        else:
            alerte("🧬 Évolution terminée : pas de nouveau challenger, le champion reste.\n" + ligne_diagnostic(diag))
    except Exception:
        pass


if __name__ == "__main__":
    main()
