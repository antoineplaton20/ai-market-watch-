"""APPRENTISSAGE — l'armée apprend de ce qu'elle observe et de ses propres trades, avec la discipline des
professionnels : rien n'influence les décisions sans avoir fait ses preuves, mesurées sans regarder le futur.

1. OBSERVATIONS : toute la veille est archivée (microstructure Binance, marchés liés, écart MT5, actualités…),
   et l'historique disponible gratuitement est rattrapé : 10 ans de marchés liés en journalier (Yahoo), 2 ans en
   horaire, 10 ans de rapports COT (CFTC), historique des taux de financement du perpétuel PAXG (Binance).
   Chaque valeur est rangée à l'instant où elle était CONNUE (clôture de la bougie, publication du rapport…).

2. CANDIDATS : chaque série observée devient un pronostiqueur candidat. Examen d'entrée, pour chaque unité de
   temps : calibration glissante (comme les autres pronostiqueurs), puis test de Diebold et Mariano (1995) contre
   le naïf, corrigé pour le nombre de candidats testés (Bonferroni ; Harvey, Liu et Zhu 2016 : exiger |t| ≥ 3).
   Seuls les admis entrent dans le consensus, où leur poids suit ensuite leur compétence récente.

3. FRAIS RÉELS : écart achat/vente, glissement, commissions et frais de nuit mesurés sur TES exécutions MT5
   remplacent progressivement les estimations fixes dans la règle « avantage > 1,5 × coûts ».

4. JOURNAL : chaque semaine, ce qui a changé (poids des pronostiqueurs, candidats admis ou rejetés, frais réels,
   score en direct de chaque pronostiqueur, résultats MT5), envoyé sur Telegram.
"""
from __future__ import annotations

import calendar
import math
import time
from statistics import NormalDist

import numpy as np

from . import base, config, levier as L, pronostiqueurs as P, strategie as S

# ============================================================================ observations
TICKERS_JOUR = {"DX-Y.NYB": "dollar", "^TNX": "taux_10ans", "TIP": "tip", "SI=F": "argent", "^VIX": "vix",
                "EURUSD=X": "euro", "USDJPY=X": "yen", "GDX": "mines", "^GSPC": "sp500", "CL=F": "petrole",
                "HG=F": "cuivre", "GC=F": "or_comex"}
TICKERS_HEURE = {"DX-Y.NYB": "dollar", "^TNX": "taux_10ans", "SI=F": "argent", "EURUSD=X": "euro"}
PAS_SNAPSHOT = 900                                            # un relevé de veille par quart d'heure


def enregistrer(cle, points):
    """points : [(ts_connu en s, valeur)] — instant où la valeur était CONNUE, jamais avant."""
    points = [(int(t), float(v)) for t, v in points if v is not None and np.isfinite(v)]
    if not points:
        return 0
    with base.connexion() as c:
        c.executemany("INSERT OR REPLACE INTO observations(cle, ts, valeur) VALUES(?,?,?)",
                      [(cle, t, v) for t, v in points])
    return len(points)


def serie(cle):
    with base.connexion() as c:
        r = c.execute("SELECT ts, valeur FROM observations WHERE cle=? ORDER BY ts", (cle,)).fetchall()
    return np.array([x[0] for x in r], dtype=np.int64), np.array([x[1] for x in r], dtype=float)


def cles():
    with base.connexion() as c:
        return {r[0]: r[1] for r in c.execute("SELECT cle, COUNT(*) FROM observations GROUP BY cle")}


def archiver_veille(maintenant=None):
    """Relevé de la veille vivante (valeurs sans historique gratuit), aligné sur le quart d'heure."""
    maintenant = maintenant or time.time()
    t = int(maintenant - maintenant % PAS_SNAPSHOT)
    n = 0
    m = base.lire("microstructure") or {}
    if maintenant - m.get("ts", 0) < 300:
        for k in ("financement_pct", "prime_pct", "positions_ouvertes_1h_pct", "acheteurs_pct", "desequilibre_pct"):
            n += enregistrer(f"veille:{k}", [(t, m.get(k))])
    mar = base.lire("marches") or {}
    if maintenant - mar.get("ts", 0) < 1800:
        n += enregistrer("veille:contexte", [(t, mar.get("contexte"))])
        n += enregistrer("veille:ratio_or_argent", [(t, mar.get("ratio_or_argent"))])
    ecarts = base.lire("eclair:ecarts") or []
    d = base.lire("direct:MT5") or {}
    if ecarts and d.get("prix") and maintenant - d.get("ts", 0) < 300:
        n += enregistrer("veille:ecart_mt5_pct", [(t, ecarts[-1] / d["prix"] * 100)])
    a = base.lire("actualites") or {}
    if maintenant - a.get("ts", 0) < 900:
        n += enregistrer("veille:actus_critiques", [(t, sum(1 for i in a.get("titres", []) if i["themes"]))])
    tend = base.lire("tendances") or {}
    if maintenant - tend.get("ts", 0) < 900:
        n += enregistrer("veille:alignement", [(t, tend.get("alignement"))])
    return n


def rattraper_historique(session=None, maintenant=None):
    """Historique gratuit rattrapé (et complété chaque jour). Chaque source isolée : une panne n'arrête rien."""
    from . import veille
    from .marches_lies import telecharger
    maintenant = maintenant or time.time()
    bilan, erreurs = {}, {}
    for tk, nom in TICKERS_JOUR.items():
        try:
            ts, c = telecharger(tk, "1d", "10y", session)
            connu = ts + 86400                                    # clôture connue au plus tard le lendemain
            ok = connu <= maintenant
            bilan[f"jour:{nom}"] = enregistrer(f"yahoo:{nom}:1d", zip(connu[ok], c[ok]))
        except Exception as ex:
            erreurs[f"jour:{nom}"] = type(ex).__name__
    for tk, nom in TICKERS_HEURE.items():
        try:
            ts, c = telecharger(tk, "1h", "730d", session)
            connu = ts + 3600
            ok = connu <= maintenant
            bilan[f"heure:{nom}"] = enregistrer(f"yahoo:{nom}:1h", zip(connu[ok], c[ok]))
        except Exception as ex:
            erreurs[f"heure:{nom}"] = type(ex).__name__
    try:
        rows = veille._get(veille.COT, session, {"cftc_contract_market_code": veille.CODE_OR,
                                                 "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": 520}).json()
        pts_net, pts_var = [], []
        rows = sorted(rows, key=lambda r: r["report_date_as_yyyy_mm_dd"])
        prec = None
        for r in rows:
            jour = calendar.timegm(time.strptime(r["report_date_as_yyyy_mm_dd"][:10], "%Y-%m-%d"))
            connu = jour + 4 * 86400                              # rapport du mardi, publié le vendredi soir
            net = float(r["m_money_positions_long_all"]) - float(r["m_money_positions_short_all"])
            oi = float(r["open_interest_all"]) or 1.0
            pts_net.append((connu, net / oi * 100))
            if prec is not None:
                pts_var.append((connu, (net - prec) / oi * 100))
            prec = net
        bilan["cot"] = enregistrer("cot:net_pct", pts_net) + enregistrer("cot:variation_pct", pts_var)
    except Exception as ex:
        erreurs["cot"] = type(ex).__name__
    try:
        pts, debut = [], int((maintenant - 5 * 365 * 86400) * 1000)
        for _ in range(12):                                       # 1 000 relevés (≈ 11 mois) par appel
            lot = veille._get("https://fapi.binance.com/fapi/v1/fundingRate", session,
                              {"symbol": "PAXGUSDT", "startTime": debut, "limit": 1000}).json()
            if not lot:
                break
            pts += [(int(x["fundingTime"]) // 1000, float(x["fundingRate"]) * 100) for x in lot]
            debut = int(lot[-1]["fundingTime"]) + 1
            if len(lot) < 1000:
                break
        bilan["financement"] = enregistrer("binance:financement_paxg_pct", pts)
    except Exception as ex:
        erreurs["financement"] = type(ex).__name__
    base.ecrire("apprentissage:rattrapage", {"ts": maintenant, "bilan": bilan, "erreurs": erreurs})
    return bilan, erreurs


# ============================================================================ candidats
def _asof(t_obs, v, instants):
    """Dernière valeur CONNUE à chaque instant (NaN avant la première)."""
    idx = np.searchsorted(t_obs, instants, side="right") - 1
    out = np.full(len(instants), np.nan)
    ok = idx >= 0
    out[ok] = v[idx[ok]]
    return out


def _variation(v, k):
    out = np.full(len(v), np.nan)
    if len(v) > k:
        with np.errstate(invalid="ignore", divide="ignore"):
            out[k:] = np.log(v[k:] / v[:-k])
    return out


def _zscore(v, n=60):
    out = np.full(len(v), np.nan)
    for i in range(n, len(v)):
        f = v[i - n:i]
        sd = f.std()
        out[i] = (v[i] - f.mean()) / sd if sd > 0 else 0.0
    return out


def definitions():
    """nom -> (description, clé d'observation, transformation de la série observée)."""
    d = {}
    for nom in TICKERS_JOUR.values():
        if nom != "or_comex":
            d[f"{nom}_5j"] = (f"Variation sur 5 jours : {nom}", f"yahoo:{nom}:1d", lambda v: _variation(v, 5))
    for nom in TICKERS_HEURE.values():
        d[f"{nom}_4h"] = (f"Variation sur 4 heures : {nom}", f"yahoo:{nom}:1h", lambda v: _variation(v, 4))
    d["cot_position"] = ("Position nette des gros spéculateurs (COT, % des positions)", "cot:net_pct", lambda v: v)
    d["cot_variation"] = ("Variation hebdomadaire de cette position (COT)", "cot:variation_pct", lambda v: v)
    d["financement_paxg"] = ("Taux de financement du perpétuel PAXG", "binance:financement_paxg_pct", lambda v: v)
    for k, desc in (("acheteurs_pct", "Part de comptes acheteurs (perpétuel or)"),
                    ("desequilibre_pct", "Déséquilibre du carnet PAXG"),
                    ("positions_ouvertes_1h_pct", "Variation des positions ouvertes sur 1 h"),
                    ("prime_pct", "Prime du perpétuel sur l'indice"), ("contexte", "Contexte des marchés liés"),
                    ("ratio_or_argent", "Ratio or / argent (écart à sa moyenne 60)"),
                    ("ecart_mt5_pct", "Écart achat/vente MT5"), ("actus_critiques", "Titres critiques dans l'actualité"),
                    ("alignement", "Alignement des tendances 15 min à 1 j")):
        f = (lambda v: _zscore(v, 60)) if k == "ratio_or_argent" else (lambda v: v)
        d[k] = (desc, f"veille:{k}", f)
    return d


def scores(b, tf):
    """Score brut de chaque candidat pour chaque bougie, connu à la CLÔTURE de la bougie (jamais avant)."""
    pas_s = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}[tf]
    clotures = b["ts"] // 1000 + pas_s
    out = {}
    for nom, (_, cle, transfo) in definitions().items():
        t, v = serie(cle)
        if len(v) < 30:
            continue
        out[nom] = _asof(t, transfo(v), clotures)
    return out


def diebold_mariano(p, base_p, y, h):
    """z de Diebold et Mariano (1995) : le pronostic bat-il le naïf ? Erreurs chevauchantes : n effectif = n / h."""
    ok = ~np.isnan(p) & ~np.isnan(base_p) & ~np.isnan(y)
    d = (base_p[ok] - y[ok]) ** 2 - (p[ok] - y[ok]) ** 2          # > 0 quand le candidat fait mieux
    n = len(d)
    if n < 200 or d.std() == 0:
        return 0.0, n
    return float(d.mean() / (d.std() / math.sqrt(max(1.0, n / h)))), n


def seuil_admission(nb_tests, risque=0.05):
    return NormalDist().inv_cdf(1 - risque / max(1, nb_tests))


def examiner(barres_par_unite):
    """barres_par_unite : {tf: bougies}. -> {tf: {candidat: {...}}} ; admis = bat le naïf sur les deux moitiés
    ET z de Diebold-Mariano au-delà du seuil corrigé pour tous les tests effectués."""
    resultats, nb = {}, 0
    for tf, b in barres_par_unite.items():
        h = S.UNITES[tf][0]
        y = P._cible(b["c"], h)
        naif = P.base_glissante(y, h)
        resultats[tf] = {}
        for nom, sc in scores(b, tf).items():
            p = P.calibrer(sc, y, h)
            valides = np.flatnonzero(~np.isnan(p) & ~np.isnan(y) & ~np.isnan(naif))
            if len(valides) < 400:
                resultats[tf][nom] = {"n": int(len(valides)), "admis": False, "raison": "pas encore assez d'historique"}
                continue
            milieu = valides[len(valides) // 2]
            m1 = P.competence(p, naif, y, int(valides[0]), int(milieu))[0]
            m2 = P.competence(p, naif, y, int(milieu), int(valides[-1]) + 1)[0]
            z, n = diebold_mariano(p, naif, y, h)
            resultats[tf][nom] = {"n": n, "competence_1": m1, "competence_2": m2, "z": z}
            nb += 1
    seuil = seuil_admission(nb)
    for tf in resultats:
        for nom, r in resultats[tf].items():
            if "z" in r:
                r["admis"] = bool(r["z"] >= seuil and r["competence_1"] > 0 and r["competence_2"] > 0)
                r["raison"] = "admis" if r["admis"] else f"z={r['z']:+.2f} < {seuil:.2f} ou compétence ≤ 0 sur une moitié"
    base.ecrire("apprentissage:examen", {"ts": time.time(), "seuil": seuil, "tests": nb, "resultats": resultats})
    return resultats, seuil


def admis(tf):
    ex = base.lire("apprentissage:examen") or {}
    return [n for n, r in ex.get("resultats", {}).get(tf, {}).items() if r.get("admis")]


def probas_admis(b, tf, h, y):
    noms = admis(tf)
    if not noms:
        return {}
    sc = scores(b, tf)
    return {f"candidat:{n}": P.calibrer(sc[n], y, h) for n in noms if n in sc}


# ============================================================================ frais réels (MT5)
def enregistrer_execution(equipe, sens, prix_demande, prix_execute, volume):
    if not prix_demande or not prix_execute:
        return
    ex = base.lire("apprentissage:executions") or []
    ex.append({"ts": time.time(), "equipe": equipe, "sens": int(sens), "demande": float(prix_demande),
               "execute": float(prix_execute), "volume": float(volume)})
    base.ecrire("apprentissage:executions", ex[-500:])


def mesurer_couts(deals=None, taille_contrat=100.0):
    """Frais réels mesurés, en fraction du prix : écart achat/vente, glissement, commissions, frais de nuit."""
    out = {"ts": time.time()}
    d = base.lire("direct:MT5") or {}
    ecarts = base.lire("eclair:ecarts") or []
    if ecarts and d.get("prix"):
        out["ecart"] = float(np.median(ecarts)) / d["prix"]
    ex = base.lire("apprentissage:executions") or []
    if ex:
        g = [e["sens"] * (e["execute"] - e["demande"]) / e["demande"] for e in ex]
        out["glissement"] = float(np.mean(g))
        out["executions"] = len(ex)
    if deals:
        par_pos = {}
        for x in deals:
            p = par_pos.setdefault(x["position_id"], {"frais": 0.0, "swap": 0.0, "notionnel": 0.0, "t": []})
            p["frais"] += x.get("commission", 0) + x.get("fee", 0)
            p["swap"] += x.get("swap", 0)
            p["t"].append(x.get("time", 0))
            if x.get("entry") == 0:
                p["notionnel"] = x["volume"] * taille_contrat * x["price"]
        fermees = [p for p in par_pos.values() if p["notionnel"] > 0 and len(p["t"]) >= 2]
        if fermees:
            notion = sum(p["notionnel"] for p in fermees)
            out["commission"] = float(-sum(p["frais"] for p in fermees) / notion)
            heures = sum(p["notionnel"] * max(1.0, (max(p["t"]) - min(p["t"])) / 3600) for p in fermees)
            out["financement_heure"] = float(max(0.0, -sum(p["swap"] for p in fermees)) / heures)
            out["positions"] = len(fermees)
    base.ecrire("apprentissage:couts", out)
    return out


def couts_reels(prior=30):
    """Frais à utiliser pour décider : estimation fixe tant que peu d'exécutions, puis mesure réelle
    (moyenne pondérée : poids de la mesure = n / (n + 30))."""
    m = base.lire("apprentissage:couts")
    if not m or m.get("executions", 0) < 5 or "ecart" not in m:
        return None
    n = m["executions"]
    w = n / (n + prior)
    estime_ar = 2 * (L.FRAIS + L.GLISSEMENT)
    estime_h = L.FINANCEMENT_8H / 8
    reel_ar = m["ecart"] + 2 * max(0.0, m.get("glissement", 0.0)) + max(0.0, m.get("commission", 0.0))
    reel_h = m.get("financement_heure", estime_h)
    return {"aller_retour": w * reel_ar + (1 - w) * estime_ar, "financement_heure": w * reel_h + (1 - w) * estime_h,
            "poids_mesure": w, "executions": n}


def appliquer_couts():
    S.COUTS_REELS = couts_reels()
    return S.COUTS_REELS


# ============================================================================ journal
def score_en_direct(jours=7):
    """Score de Brier réel des pronostics JUGÉS ces derniers jours, comparé au naïf (pas un backtest)."""
    depuis = int((time.time() - jours * 86400) * 1000)
    with base.connexion() as c:
        rows = c.execute("SELECT bot, AVG(brier), COUNT(*) FROM pronostics WHERE issue IS NOT NULL AND ts >= ? "
                         "GROUP BY bot", (depuis,)).fetchall()
    b = {r[0]: (r[1], r[2]) for r in rows}
    out = {}
    for nom, (br, n) in b.items():
        tf, _, qui = nom.partition(":")
        naif = b.get(f"{tf}:naif")
        if qui != "naif" and naif and naif[0]:
            out[nom] = {"competence": 1 - br / naif[0], "n": n}
    return out


# ============================================================================ croissance de la mémoire
MEMOIRE = {                                                   # ce que l'armée accumule, compté dans sa base
    "bougies (toutes sources)": "SELECT COUNT(*) FROM bougies",
    "bougies du courtier MT5": "SELECT COUNT(*) FROM bougies WHERE source='MT5'",
    "observations de veille": "SELECT COUNT(*) FROM observations",
    "pronostics émis": "SELECT COUNT(*) FROM pronostics",
    "pronostics jugés (notés)": "SELECT COUNT(*) FROM pronostics WHERE issue IS NOT NULL",
    "décisions du chef": "SELECT COUNT(*) FROM decisions",
    "ordres MT5 journalisés": "SELECT COUNT(*) FROM ordres_mt5",
    "trades papier": "SELECT COUNT(*) FROM trades",
}
GARDE_RELEVES_S = 35 * 86400


def compter_memoire():
    with base.connexion() as c:
        return {nom: c.execute(sql).fetchone()[0] for nom, sql in MEMOIRE.items()}


def releve_memoire(maintenant=None, pas=3600):
    """Un relevé des compteurs par heure (35 jours gardés) : la croissance se lit en comparant les relevés."""
    maintenant = maintenant or time.time()
    releves = base.lire("memoire:releves") or []
    if releves and maintenant - releves[-1]["ts"] < pas:
        return releves
    releves = [r for r in releves if maintenant - r["ts"] <= GARDE_RELEVES_S]
    releves.append({"ts": maintenant, "n": compter_memoire()})
    base.ecrire("memoire:releves", releves)
    return releves


def texte_memoire(maintenant=None):
    maintenant = maintenant or time.time()
    actuel = compter_memoire()
    releves = base.lire("memoire:releves") or []

    def il_y_a(secondes):
        anciens = [r for r in releves if r["ts"] <= maintenant - secondes + 1800]
        return anciens[-1]["n"] if anciens else None

    j1, j7 = il_y_a(86400), il_y_a(7 * 86400)
    lignes = ["📈 Mémoire de l'armée (total · gagné en 24 h · en 7 j)"]

    def ecart(n, avant, nom):
        return f"{n - avant[nom]:+,}".replace(",", " ") if avant and nom in avant else "—"

    for nom, n in actuel.items():
        lignes.append(f"• {nom} : {n:,} · {ecart(n, j1, nom)} · {ecart(n, j7, nom)}".replace(",", " "))
    if not j1:
        lignes.append("(« — » : pas encore de relevé assez ancien ; un relevé par heure depuis cette version)")
    return "\n".join(lignes)


def journal():
    lignes = ["🧠 Journal d'apprentissage de l'armée de l'or"]
    obs = cles()
    with base.connexion() as c:
        nb_bougies = c.execute("SELECT COUNT(*) FROM bougies").fetchone()[0]
        nb_jugés = c.execute("SELECT COUNT(*) FROM pronostics WHERE issue IS NOT NULL").fetchone()[0]
    lignes.append(f"Mémoire : {nb_bougies:,} bougies · {sum(obs.values()):,} observations de veille "
                  f"({len(obs)} séries) · {nb_jugés:,} pronostics jugés")
    avant = base.lire("journal:poids") or {}
    maintenant = {}
    for tf in ("1h", "4h", "1d"):
        p = base.lire(f"prono:{tf}") or {}
        poids = p.get("poids") or {}
        maintenant[tf] = poids
        if poids:
            txt = []
            for k, w in sorted(poids.items(), key=lambda kv: -kv[1]):
                delta = w - (avant.get(tf, {}).get(k, 0.0))
                txt.append(f"{k} {w * 100:.2f}" + (f" ({delta * 100:+.2f})" if abs(delta) >= 0.0001 else ""))
            lignes.append(f"Poids {tf} (compétence récente, % ; variation sur la semaine) : " + " · ".join(txt[:6]))
    base.ecrire("journal:poids", maintenant)
    direct = score_en_direct()
    if direct:
        meilleurs = sorted(((k, v) for k, v in direct.items() if v["n"] >= 30),       # n < 30 : du bruit
                           key=lambda kv: -kv[1]["competence"])[:5]
        if meilleurs:
            lignes.append("Score EN DIRECT sur 7 jours (compétence contre le naïf, au moins 30 pronostics) : " + " · ".join(
                f"{k} {v['competence'] * 100:+.1f} % (n={v['n']})" for k, v in meilleurs))
    ex = base.lire("apprentissage:examen")
    if ex:
        adm = [f"{n} ({tf})" for tf, r in ex["resultats"].items() for n, x in r.items() if x.get("admis")]
        attente = sum(1 for r in ex["resultats"].values() for x in r.values() if "z" not in x)
        lignes.append(f"Candidats : {ex['tests']} examinés (seuil z ≥ {ex['seuil']:.2f}) · admis : "
                      f"{', '.join(adm) if adm else 'aucun'} · en attente d'historique : {attente}")
    m, cr = base.lire("apprentissage:couts"), couts_reels()
    if m and "ecart" in m:
        lignes.append(f"Frais réels MT5 : écart achat/vente {m['ecart'] * 100:.4f} % · glissement "
                      f"{m.get('glissement', 0) * 100:+.4f} % · commission {m.get('commission', 0) * 100:.4f} % "
                      f"· {m.get('executions', 0)} exécutions")
    if cr:
        lignes.append(f"Coûts utilisés pour décider : {cr['aller_retour'] * 100:.4f} % aller-retour "
                      f"(mesure réelle à {cr['poids_mesure'] * 100:.0f} %, estimation "
                      f"{2 * (L.FRAIS + L.GLISSEMENT) * 100:.2f} % pour le reste)")
    else:
        lignes.append(f"Coûts utilisés pour décider : estimation {2 * (L.FRAIS + L.GLISSEMENT) * 100:.2f} % aller-retour "
                      "(moins de 5 exécutions MT5 mesurées)")
    st = base.lire("stats_chandeliers:4h")
    if st:
        from . import chandeliers
        motifs = {k: v for k, v in st.items() if not k.startswith("_")}
        exige = chandeliers.seuil_z(len(motifs))
        fiables = [k for k, v in motifs.items() if (v.get("n") or 0) >= 30 and abs(v.get("z") or 0) >= exige]
        lignes.append(f"Chandeliers fiables (4 h) : {', '.join(fiables) if fiables else 'aucun'}")
    r = base.lire("mt5:resultats")
    if r and config.MT5_ACTIF:
        lignes.append("Résultats MT5 : " + " · ".join(f"{k} {v['pnl']:+.2f} ({v['trades']} trades, {v['gagnants']} gagnants)"
                                                    for k, v in r["equipes"].items()))
    return "\n".join(lignes)
