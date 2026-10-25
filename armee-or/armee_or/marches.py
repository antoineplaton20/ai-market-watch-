"""ARMÉE MULTI-MARCHÉS — tous les instruments de MT5 : forex, métaux, énergie, agricoles, indices, crypto.

Pourquoi : sur l'or seul, rien n'a battu le naïf (§5 du prompt maître). Sur 34 marchés (Yahoo 2000-2026, frais et
financement compris), la règle la plus simple et la mieux documentée — n'être acheteur d'un marché qu'au-dessus de
sa moyenne de 200 jours (Paul Tudor Jones ; Faber, 2007), taille réglée par la volatilité — donne un Sharpe de +0,47 à
+0,81 selon le coût du financement, positif sur les deux moitiés (2000-2013, 2013-2026), avec une baisse maximale
moitié moindre que « tout acheter ». C'est la diversification qui travaille, pas la prédiction. Le croisement 20/50
jours de la 3e vidéo (Apple) ne fait pas mieux que « tout acheter » ; la cassure 55/20 des Turtles perd après frais.

Ce module refait tout sur l'historique DU COURTIER (ses prix, ses écarts, ses swaps) :
1. inventaire : tous les symboles du serveur ; un panier liquide choisi par famille ;
2. archive : bougies journalières de chaque marché du panier (source « MT5:<symbole> ») ;
3. banc d'essai : chaque règle sur chaque marché, puis le portefeuille à risque égal, sur deux moitiés ;
4. permis : une règle trade si le portefeuille gagne sur CHAQUE moitié ET bat « toujours acheter » le même panier ;
5. équipe : une décision par marché et par jour (bougie journalière close), taille réglée par la volatilité, seulement
   les marchés dont le lot minimum tient dans le budget de risque du compte, stop de catastrophe chez le courtier
   (5 ATR journaliers), numéro magique 770050 (jamais géré par l'exécutant de l'or).
"""
from __future__ import annotations

import logging
import math
import re
import time

import numpy as np

from . import base, config, donnees, indicateurs as I, mt5, risque, telegram

_log = logging.getLogger("or.marches")

MAGIQUE = 770050
CLE = "marches:etat"
STRATEGIES = {"sma200": "au-dessus de sa moyenne 200 jours", "croisement_20_50": "moyenne 20 j au-dessus de la 50 j "
              "(3e vidéo)", "toujours_acheter": "toujours acheter (étalon naïf)"}
CANDIDATES = ("sma200", "croisement_20_50")
STOP_ATR = 5.0                      # stop de catastrophe : 5 ATR(20) journaliers sous l'entrée
VOL_BANC = 0.10                     # banc : chaque marché à 10 % de volatilité annuelle (portefeuille à risque égal)
LEVIER_MAX = 5.0
VOL_PORTEFEUILLE = 0.10             # équipe : volatilité annuelle visée pour l'ensemble du portefeuille
CORRELATION = 0.15                  # corrélation moyenne supposée entre les positions (budget de risque par marché)
MIN_MARCHES, MIN_ENTREES, MIN_BOUGIES = 6, 30, 750
MARGE_MAX = 0.5                     # pas de nouvel achat au-delà de 50 % de la marge utilisée
MARCHE_FERME = 10018
FRAIS_DEFAUT = {"forex": 0.0002, "métaux": 0.0003, "énergie": 0.0005, "agricoles": 0.001, "indices": 0.0002,
                "crypto": 0.001}
FINANCEMENT_DEFAUT = -0.03          # par an, quand le swap du courtier est illisible

UNIVERS = [
    ("forex", "EURUSD", ("EURUSD",)), ("forex", "GBPUSD", ("GBPUSD",)), ("forex", "USDJPY", ("USDJPY",)),
    ("forex", "USDCHF", ("USDCHF",)), ("forex", "AUDUSD", ("AUDUSD",)), ("forex", "USDCAD", ("USDCAD",)),
    ("forex", "NZDUSD", ("NZDUSD",)), ("forex", "EURGBP", ("EURGBP",)), ("forex", "EURJPY", ("EURJPY",)),
    ("forex", "GBPJPY", ("GBPJPY",)), ("forex", "EURCHF", ("EURCHF",)), ("forex", "AUDJPY", ("AUDJPY",)),
    ("métaux", "or", ("XAUUSD", "GOLD")), ("métaux", "argent", ("XAGUSD", "SILVER")),
    ("métaux", "platine", ("XPTUSD", "PLATINUM")), ("métaux", "cuivre", ("XCUUSD", "COPPER")),
    ("énergie", "pétrole WTI", ("XTIUSD", "USOIL", "WTI")), ("énergie", "pétrole Brent", ("XBRUSD", "UKOIL", "BRENT")),
    ("énergie", "gaz naturel", ("XNGUSD", "NATGAS", "NGAS")),
    ("agricoles", "blé", ("WHEAT",)), ("agricoles", "maïs", ("CORN",)), ("agricoles", "café", ("COFFEE",)),
    ("agricoles", "sucre", ("SUGAR",)), ("agricoles", "cacao", ("COCOA",)),
    ("indices", "S&P 500", ("US500", "SPX500", "SP500")), ("indices", "Nasdaq 100", ("NAS100", "USTEC", "US100")),
    ("indices", "Dow Jones", ("US30", "DJ30", "WS30")), ("indices", "DAX", ("GER40", "DE40", "DAX40", "GER30")),
    ("indices", "CAC 40", ("FRA40", "F40", "CAC40")), ("indices", "FTSE 100", ("UK100", "FTSE100")),
    ("indices", "Nikkei 225", ("JP225", "JPN225", "NIK225")), ("indices", "Euro Stoxx 50", ("EU50", "STOXX50")),
    ("crypto", "Bitcoin", ("BTCUSD",)), ("crypto", "Ether", ("ETHUSD",)),
]
FAMILLES = ("forex", "métaux", "énergie", "agricoles", "indices", "crypto")


def lire():
    return base.lire(CLE) or {}


def ecrire(e):
    base.ecrire(CLE, e)


def actif():
    v = base.lire("marches:actif")
    return True if v is None else bool(v)


def _n(x, decimales=0):
    return f"{x:,.{decimales}f}".replace(",", " ")


# ============================================================================ 1) inventaire
def _rang(nom, candidat):
    """Le nom du courtier correspond-il au marché ? « EURUSD », « EURUSD.a », « XAUUSDm », « US500.cash »…"""
    n, c = nom.upper(), candidat.upper()
    if n == c:
        return 0
    reste = n[len(c):]
    if n.startswith(c) and re.fullmatch(r"[.\-_#]?[A-Z0-9]{0,5}", reste) and not re.match(r"[A-Z]{3}$", reste):
        return 1 + len(reste)
    return None


def choisir_univers(symboles):
    """symboles : [{name, trade_mode, …}] du serveur -> {symbole: {"famille", "nom"}} (un symbole par marché)."""
    utilisables = [s["name"] for s in symboles if s.get("trade_mode") in (None, 4)]
    choix = {}
    for famille, nom, candidats in UNIVERS:
        meilleurs = sorted((r, i, s) for i, c in enumerate(candidats) for s in utilisables
                           if (r := _rang(s, c)) is not None)
        if meilleurs and meilleurs[0][2] not in choix:
            choix[meilleurs[0][2]] = {"famille": famille, "nom": nom}
    return choix


def couts(specs, famille, prix):
    """Coûts d'un marché en part du notionnel : écart payé à chaque passage d'ordre, swap par jour de bourse
    (week-ends compris, × 7/5). Lus chez le courtier ; valeurs prudentes par défaut si illisibles."""
    point, ecart = specs.get("point") or 0.0, specs.get("spread") or 0
    frac = ecart * point / prix / 2 if prix and point and ecart else 0.0
    if not 0 < frac < 0.01:
        frac = FRAIS_DEFAUT.get(famille, 0.0005) / 2
    mode, swap = specs.get("swap_mode"), specs.get("swap_long")
    if swap is None or not prix:
        jour = FINANCEMENT_DEFAUT / 365
    elif mode == 1:                                             # en points
        jour = swap * point / prix
    elif mode in (2, 3, 4):                                     # en argent par lot
        jour = swap / ((specs.get("trade_contract_size") or 1.0) * prix)
    elif mode in (5, 6):                                        # en % par an
        jour = swap / 100 / 365
    else:
        jour = FINANCEMENT_DEFAUT / 365
    return {"ecart": frac, "swap_long": max(-0.002, min(0.002, jour)) * 7 / 5}


def inventaire(e, maintenant):
    symboles = mt5.appel("symboles", delai=120)
    choix = choisir_univers(symboles)
    specs = {}
    for s in choix:
        try:
            specs[s] = mt5.appel("specs", symbole=s)
        except mt5.ErreurMT5 as ex:
            _log.warning("specs de %s illisibles : %s", s, ex)
    e.update(univers={s: v for s, v in choix.items() if s in specs}, specs=specs, univers_ts=maintenant,
             nb_symboles=len(symboles))
    return e


# ============================================================================ 2) archive (bougies journalières)
def source(symbole):
    return f"MT5:{symbole}"


def archiver(par_passage=3, maintenant=None):
    e = lire()
    univers = sorted(e.get("univers") or {})
    if not univers:
        return "inventaire pas encore fait"
    m = maintenant or time.time()
    serveur = m + (base.lire("mt5:decalage") or 0)
    etat = e.setdefault("archive", {})
    debut = e.get("archive_i", 0) % len(univers)
    msgs = []
    for s in (univers[debut:] + univers[:debut])[:par_passage]:
        a = etat.setdefault(s, {"vides": 0, "fini": False})
        with base.connexion() as c:
            r = c.execute("SELECT MIN(ts), MAX(ts), COUNT(*) FROM bougies WHERE source=? AND tf='1d'",
                          (source(s),)).fetchone()
        premier, dernier, n = (r[0], r[1], r[2]) if r and r[2] else (None, None, 0)
        fin_avant = int((premier / 1000 - 1) if premier else serveur)
        lots = []
        if dernier:
            lots.append(mt5.appel("bougies_periode", tf="1d", debut=int(dernier / 1000 + 86400), fin=int(serveur),
                                  symbole=s, delai=180))
        if not a["fini"]:
            arriere = mt5.appel("bougies_periode", tf="1d", debut=fin_avant - 10 * 365 * 86400, fin=fin_avant,
                                symbole=s, delai=180)
            a["vides"] = 0 if arriere else a["vides"] + 1
            a["fini"] = a["vides"] >= 2 or fin_avant < 946_684_800          # 2 fenêtres vides, ou avant l'an 2000
            lots.append(arriere)
        ajout = donnees.inserer(source(s), "1d", [[t * 1000, o, h, l, c, v] for barres in lots
                                                  for t, o, h, l, c, v in barres if t + 86400 <= serveur])
        msgs.append(f"{s} {n + ajout}")
    e["archive_i"] = debut + par_passage
    ecrire(e)
    return "archive journalière : " + " · ".join(msgs)


# ============================================================================ 3) banc d'essai (mêmes règles qu'en direct)
def signal(c, strategie):
    """1 = acheteur, 0 = dehors (règles acheteuses seulement : vendre à découvert a perdu sur 34 marchés)."""
    c = np.asarray(c, dtype=float)
    if strategie == "sma200":
        m = I.sma(c, 200)
        return np.where(np.isfinite(m) & (c > m), 1.0, 0.0)
    if strategie == "croisement_20_50":
        a, b = I.sma(c, 20), I.sma(c, 50)
        return np.where(np.isfinite(b) & (a > b), 1.0, 0.0)
    s = np.ones(len(c))
    s[:200] = 0.0                                           # même départ que la moyenne 200 j
    return s


def volatilite(c, i, n=60):
    r = np.diff(c[max(0, i - n):i + 1]) / c[max(0, i - n):i]
    return float(r.std() * math.sqrt(252)) if len(r) >= 20 else 0.0


def simuler_marche(o, h, l, c, strategie, cout, vol_cible=VOL_BANC):
    """-> (rendement net quotidien en part du capital, nombre d'entrées). Décision à la clôture du jour i, appliquée
    à partir du jour i+1 ; taille fixée à l'entrée ; stop de catastrophe : touché, on attend que le signal retombe
    avant de reprendre. « Toujours acheter » (l'étalon) n'a pas de stop et sa taille est revue chaque mois, pour
    rester à risque constant sur vingt ans."""
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    n = len(c)
    sig = signal(c, strategie)
    atr = I.atr(h, l, c, 20)
    avec_stop = strategie != "toujours_acheter"
    net = np.zeros(n)
    w, stop, bloque, entrees = 0.0, 0.0, False, 0
    for i in range(1, n):
        if w:
            if avec_stop and l[i] <= stop:                        # stop touché dans la journée (au pire : l'ouverture)
                net[i] = w * (min(o[i], stop) / c[i - 1] - 1) - w * cout["ecart"] + w * cout["swap_long"]
                w, bloque = 0.0, True
                continue
            net[i] = w * (c[i] / c[i - 1] - 1) + w * cout["swap_long"]
            if not avec_stop and i % 21 == 0:                     # étalon : retour au risque visé chaque mois
                vol = volatilite(c, i)
                if vol > 0:
                    nouveau = min(LEVIER_MAX, vol_cible / vol)
                    net[i] -= abs(nouveau - w) * cout["ecart"]
                    w = nouveau
        if sig[i] == 0:
            if w:
                net[i] -= w * cout["ecart"]
                w = 0.0
            bloque = False
        elif not w and not bloque and i >= 60:
            vol = volatilite(c, i)
            if vol > 0 and np.isfinite(atr[i]):
                w = min(LEVIER_MAX, vol_cible / vol)
                stop = c[i] - STOP_ATR * atr[i]
                net[i] -= w * cout["ecart"]
                entrees += 1
    return net, entrees


def statistiques(x):
    x = np.asarray(x, dtype=float)
    if len(x) < 250:
        return None
    an, vol = float(x.mean() * 252), float(x.std() * math.sqrt(252))
    courbe = np.cumsum(x)
    return {"rendement": an, "vol": vol, "sharpe": an / vol if vol else 0.0,
            "pire_baisse": float((courbe - np.maximum.accumulate(courbe)).min())}


def banc(marches, strategies=("sma200", "croisement_20_50", "toujours_acheter")):
    """marches : {symbole: {"ts": ms, "o","h","l","c": tableaux, "cout": {...}}} -> résultats par règle :
    portefeuille à risque égal (moyenne des marchés présents chaque jour), deux moitiés, entrées, Sharpe par marché."""
    garde = {s: d for s, d in marches.items() if len(d["c"]) >= MIN_BOUGIES}
    if not garde:
        return {}
    jours = np.array(sorted({int(t) // 86_400_000 for d in garde.values() for t in d["ts"]}))
    position = {j: i for i, j in enumerate(jours)}
    coupe = jours[len(jours) // 2]
    out = {}
    for strat in strategies:
        somme, nb = np.zeros(len(jours)), np.zeros(len(jours))
        entrees, par_marche = 0, {}
        for s, d in garde.items():
            net, k = simuler_marche(d["o"], d["h"], d["l"], d["c"], strat, d["cout"])
            idx = np.array([position[int(t) // 86_400_000] for t in d["ts"]])
            somme[idx] += net
            nb[idx] += 1
            entrees += k
            st = statistiques(net[200:])
            par_marche[s] = round(st["sharpe"], 2) if st else None
        ok = nb > 0
        p, j = somme[ok] / nb[ok], jours[ok]
        out[strat] = {"tout": statistiques(p), "moitie1": statistiques(p[j < coupe]),
                      "moitie2": statistiques(p[j >= coupe]), "entrees": entrees, "marches": len(garde),
                      "par_marche": par_marche, "coupe_jour": int(coupe)}
    return out


def permis(resultats):
    """{strategie: {"ok", "raison"}} : gagner sur CHAQUE moitié ET battre « toujours acheter » le même panier."""
    naif = resultats.get("toujours_acheter") or {}
    out = {}
    for strat in CANDIDATES:
        r = resultats.get(strat)
        if not r or not r["moitie1"] or not r["moitie2"] or not naif.get("moitie1") or not naif.get("moitie2"):
            out[strat] = {"ok": False, "raison": "historique insuffisant"}
            continue
        s1, s2 = r["moitie1"]["sharpe"], r["moitie2"]["sharpe"]
        n1, n2 = naif["moitie1"]["sharpe"], naif["moitie2"]["sharpe"]
        raisons = [m for m, faux in (
            (f"seulement {r['marches']} marchés (minimum {MIN_MARCHES})", r["marches"] < MIN_MARCHES),
            (f"seulement {r['entrees']} entrées (minimum {MIN_ENTREES})", r["entrees"] < MIN_ENTREES),
            ("perd sur une moitié", s1 <= 0 or s2 <= 0),
            ("ne bat pas « toujours acheter » sur chaque moitié", s1 <= n1 or s2 <= n2)) if faux]
        out[strat] = {"ok": not raisons, "raison": " ; ".join(raisons) or "gagne sur chaque moitié et bat le naïf",
                      "sharpe": (round(s1, 2), round(s2, 2)), "naif": (round(n1, 2), round(n2, 2))}
    return out


def strategie_permise():
    p = base.lire("marches:permis") or {}
    bonnes = [(v.get("sharpe", (0, 0))[0] + v.get("sharpe", (0, 0))[1], s) for s, v in p.items() if v.get("ok")]
    return max(bonnes)[1] if bonnes else None


def charger_marches(e=None):
    e = e or lire()
    out = {}
    for s, info in (e.get("univers") or {}).items():
        d = donnees.charger(source(s), "1d")
        if len(d["c"]) >= MIN_BOUGIES:
            out[s] = {**d, "cout": couts((e.get("specs") or {}).get(s) or {}, info["famille"], float(d["c"][-1]))}
    return out


def bot_banc(chef=None):
    if not config.MT5_ACTIF:
        return "MT5 non configuré"
    e = lire()
    marches = charger_marches(e)
    tradables = set(e.get("tradables") or [])
    sous = {s: d for s, d in marches.items() if s in tradables}
    res = banc(sous if len(sous) >= MIN_MARCHES else marches)
    if not res:
        return "pas encore assez d'historique journalier"
    ancien = base.lire("marches:permis") or {}
    nouveau = permis(res)
    base.ecrire("marches:banc", {"ts": time.time(), "resultats": res, "panier": "tradables" if len(sous) >= MIN_MARCHES
                                 else "tous"})
    base.ecrire("marches:permis", nouveau)
    for s, v in nouveau.items():
        if bool((ancien.get(s) or {}).get("ok")) != v["ok"]:
            telegram.envoyer(f"🪪 Multi-marchés · {STRATEGIES[s]} : permis {'ACCORDÉ' if v['ok'] else 'RETIRÉ'} "
                             f"({v['raison']} ; Sharpe {v['sharpe'][0]:+.2f} / {v['sharpe'][1]:+.2f}, naïf "
                             f"{v['naif'][0]:+.2f} / {v['naif'][1]:+.2f}).", True)
    return " · ".join(f"{s} {'✅' if v['ok'] else '✖'}" for s, v in nouveau.items())


# ============================================================================ 4) taille des positions
def budget_risque(n, vol_portefeuille=VOL_PORTEFEUILLE, rho=CORRELATION):
    """Volatilité annuelle (en part de l'équité) donnée à chaque marché pour viser vol_portefeuille au total."""
    return vol_portefeuille / math.sqrt(n * (1 + (n - 1) * rho)) if n else 0.0


def lots_marche(equite, valeur_lot, vol, budget, specs):
    """-> (lots, explication). valeur_lot : notionnel d'UN lot en devise du compte. Lot minimum accepté s'il ne
    dépasse pas 2 fois le budget ; au-delà, le marché est trop gros pour ce capital."""
    if not (valeur_lot and vol and budget):
        return 0.0, "volatilité ou valeur du lot inconnue"
    cible = equite * budget / vol
    pas, mini = specs.get("volume_step") or 0.01, specs.get("volume_min") or 0.01
    lots = math.floor(cible / valeur_lot / pas + 1e-9) * pas
    if lots < mini:
        if mini * valeur_lot <= 2 * cible:
            return mini, f"lot minimum ({_n(mini * valeur_lot)} pour {_n(cible)} visés)"
        return 0.0, f"lot minimum trop gros pour ce capital ({_n(mini * valeur_lot)} pour {_n(cible)} visés)"
    return round(min(lots, specs.get("volume_max") or lots), 8), f"{_n(lots * valeur_lot)} de notionnel"


def selection(candidats, equite):
    """candidats : {symbole: (valeur_lot, vol, specs)} -> (marchés retenus, budget par marché, exclus avec raison).
    Le budget dépend du nombre de marchés : on recommence tant que la liste bouge."""
    garde, exclus = dict(candidats), {}
    for _ in range(6):
        budget = budget_risque(len(garde))
        nouveaux = {}
        for s, (valeur, vol, specs) in candidats.items():
            lots, note = lots_marche(equite, valeur, vol, budget, specs)
            if lots:
                nouveaux[s] = (valeur, vol, specs)
            else:
                exclus[s] = note
        if set(nouveaux) == set(garde):
            break
        garde = nouveaux
    return garde, budget_risque(len(garde)), {s: r for s, r in exclus.items() if s not in garde}


# ============================================================================ 5) l'équipe (toutes les 5 minutes)
def bot_marches(chef=None, maintenant=None):
    if not config.MT5_ACTIF:
        return "MT5 non configuré"
    m = maintenant or time.time()
    e = lire()
    if not e.get("univers") or m - e.get("univers_ts", 0) > 86400:
        inventaire(e, m)
    etat = base.lire("mt5:etat") or {}
    compte = etat.get("compte")
    if not compte or m - etat.get("ts", 0) > 120:
        etat = mt5.appel("etat", delai=150)
        compte = etat.get("compte")
    if not etat.get("connecte") or not compte:
        ecrire(e)
        return "MT5 non connecté"
    if not compte.get("demo"):
        ecrire(e)
        return "compte réel : aucun ordre"
    equite = float(compte["equity"])
    positions = {}
    for p in mt5.appel("positions"):
        if p["magic"] == MAGIQUE:
            positions.setdefault(p["symbol"], []).append(p)
    suivi, annonces = e.setdefault("positions", {}), []
    coupe = bool((base.lire("risque:etat") or {}).get("coupe"))
    for s in list(suivi):                                   # disparue sans nous : stop de catastrophe (ou à la main)
        if s not in positions:
            if coupe:                                       # fermée par le coupe-circuit : rachat permis à la reprise
                annonces.append(f"{s} : fermée par le coupe-circuit")
            else:
                annonces.append(f"{s} : sortie par le stop de catastrophe (ou à la main), pas de rachat tant que le "
                                "signal n'est pas retombé")
                e.setdefault("bloque", {})[s] = True
            suivi.pop(s)
    strat = strategie_permise()
    risque_ok, raison_risque = risque.autorise()
    marge_ok = float(compte.get("margin_free") or equite) >= (1 - MARGE_MAX) * equite
    entrees_ok = (strat is not None and actif() and risque_ok and marge_ok and not getattr(chef, "pause", False)
                  and not base.lire("mt5:pause"))
    reessai = e.setdefault("reessai", {})
    univers, specs_tous = e.get("univers") or {}, e.get("specs") or {}
    vus, msgs = e.setdefault("vu", {}), []
    candidats, signaux = {}, {}
    for s in sorted(univers):
        try:
            barres = mt5.appel("bougies", tf="1d", n=260, symbole=s)[:-1]          # la dernière est en cours
        except mt5.ErreurMT5 as ex:
            msgs.append(f"{s} : {ex}")
            continue
        if len(barres) < 210:
            continue
        c = np.array([b[4] for b in barres], dtype=float)
        h, l = np.array([b[2] for b in barres], dtype=float), np.array([b[3] for b in barres], dtype=float)
        regle = (suivi.get(s) or {}).get("strategie") or strat or "sma200"
        signaux[s] = (int(signal(c, regle)[-1]), barres[-1][0], c, h, l)
        vol = volatilite(c, len(c) - 1)
        try:
            valeur = mt5.appel("valeur_lot", symbole=s)
        except mt5.ErreurMT5:
            continue
        candidats[s] = (valeur, vol, specs_tous.get(s) or {})
    retenus, budget, exclus = selection(candidats, equite)
    e.update(tradables=sorted(retenus), budget=budget, exclus=exclus)
    for s, (sig, t_barre, c, h, l) in signaux.items():
        ouverte = positions.get(s)
        if sig == 0:
            e.setdefault("bloque", {})[s] = False
        if (vus.get(s) == t_barre and not (ouverte and sig == 0)) or m < reessai.get(s, 0):
            continue                                        # une décision par bougie close ; marché fermé : plus tard
        if ouverte and sig == 0:                           # sortie : le marché est repassé sous sa règle
            refus = [r for r in (mt5.appel("fermer", ticket=p["ticket"], commentaire="armee-or marches sortie")
                                 for p in ouverte) if not r.get("ok")]
            if refus:
                reessai[s] = m + (1800 if refus[0].get("retcode") == MARCHE_FERME else 300)
                msgs.append(f"{s} : sortie refusée ({refus[0].get('retcode')}), nouvel essai")
                continue
            gain = sum((p.get("profit") or 0) + (p.get("swap") or 0) for p in ouverte)
            regle = (suivi.pop(s, None) or {}).get("strategie") or strat or "sma200"
            annonces.append(f"{s} ({univers[s]['nom']}) : sortie, plus « {STRATEGIES[regle]} » · "
                            f"{gain:+.2f} {compte.get('currency', '')}")
            msgs.append(f"{s} sortie {gain:+.2f}")
        elif not ouverte and sig == 1 and s in retenus and entrees_ok and not e.get("bloque", {}).get(s):
            valeur, vol, specs = retenus[s]
            lots, note = lots_marche(equite, valeur, vol, budget, specs)
            atr = I.atr(h, l, c, 20)[-1]
            tick = mt5.appel("tick", symbole=s)
            stop = round(tick["ask"] - STOP_ATR * atr, int(specs.get("digits") or 5))
            r = mt5.appel("ouvrir", sens=1, volume=lots, sl=stop, magic=MAGIQUE, commentaire="armee-or marches",
                          symbole=s)
            if not r.get("ok"):
                reessai[s] = m + (1800 if r.get("retcode") == MARCHE_FERME else 300)
                msgs.append(f"{s} : achat refusé ({r.get('retcode')} {r.get('commentaire')}), nouvel essai")
                continue
            suivi[s] = {"strategie": strat, "ts": m, "lots": lots, "prix": r.get("prix"), "stop": stop}
            annonces.append(f"ACHAT {lots:g} lot {s} ({univers[s]['nom']}, {univers[s]['famille']}) à {r.get('prix')} : "
                            f"{STRATEGIES[strat]} · stop {stop} ({STOP_ATR:g} ATR) · {note}")
            msgs.append(f"{s} achat {lots:g}")
        vus[s] = t_barre
    ecrire(e)
    if annonces:                                            # un seul message par passage, même pour 15 marchés
        telegram.envoyer("🌍 Multi-marchés (MT5 démo)\n" + "\n".join("• " + a for a in annonces))
    etat_entrees = ("entrées autorisées" if entrees_ok else "pas de permis" if strat is None else
                    raison_risque if not risque_ok else "marge utilisée au-delà de 50 %" if not marge_ok
                    else "entrées en pause")
    return (f"{len(positions)} marchés en position, {len(retenus)} tradables sur {len(univers)} · {etat_entrees}"
            + (" · " + " · ".join(msgs) if msgs else ""))


def bot_archive(chef=None):
    if not config.MT5_ACTIF:
        return "MT5 non configuré"
    return archiver()


# ============================================================================ pilotage
def fermer_tout():
    faits = 0
    for p in mt5.appel("positions"):
        if p["magic"] == MAGIQUE:
            faits += bool(mt5.appel("fermer", ticket=p["ticket"], commentaire="armee-or marches stop").get("ok"))
    base.ecrire("marches:actif", False)
    e = lire()
    e["positions"] = {}
    ecrire(e)
    return f"🛑 Multi-marchés : {faits} position(s) fermée(s), plus de nouvel achat (/or_marches_on pour reprendre)."


def commande(c):
    c = c.replace("/or_", "").strip()
    if c == "marches_on":
        base.ecrire("marches:actif", True)
        return "▶️ Multi-marchés : achats autorisés (toujours sous permis)."
    if c == "marches_off":
        base.ecrire("marches:actif", False)
        return "⏸ Multi-marchés : plus de nouvel achat ; les positions gardent leurs sorties et leurs stops."
    if c == "marches_fermer":
        return fermer_tout()
    return texte_marches()


def texte_marches():
    if not config.MT5_ACTIF:
        return "🌍 Multi-marchés : MT5 non branché."
    e = lire()
    univers = e.get("univers") or {}
    lignes = ["🌍 Armée multi-marchés (forex, métaux, énergie, agricoles, indices, crypto)"
              + ("" if actif() else " · achats en pause")]
    if not univers:
        return lignes[0] + "\nInventaire MT5 pas encore fait (dans les 5 minutes après le démarrage)."
    trouves = {f: [v["nom"] for v in univers.values() if v["famille"] == f] for f in FAMILLES}
    attendus = {f: sum(1 for x in UNIVERS if x[0] == f) for f in FAMILLES}
    lignes.append(f"Courtier : {e.get('nb_symboles', '?')} symboles · panier : "
                  + " · ".join(f"{f} {len(trouves[f])}/{attendus[f]}" for f in FAMILLES))
    b = base.lire("marches:banc") or {}
    perm = base.lire("marches:permis") or {}
    res = b.get("resultats") or {}
    if res:
        naif = res.get("toujours_acheter") or {}
        lignes.append(f"Banc d'essai (historique du courtier, écarts et swaps réels, {b.get('panier')}) :")
        for s in CANDIDATES:
            r, p = res.get(s) or {}, perm.get(s) or {}
            if r.get("tout"):
                lignes.append(f"{'✅' if p.get('ok') else '✖'} {STRATEGIES[s]} : Sharpe {r['moitie1']['sharpe']:+.2f} / "
                              f"{r['moitie2']['sharpe']:+.2f} (moitiés), {r['tout']['rendement'] * 100:+.1f} %/an, pire "
                              f"baisse {r['tout']['pire_baisse'] * 100:.0f} %, {r['marches']} marchés, {r['entrees']} "
                              f"entrées · {p.get('raison', '')}")
        if naif.get("tout"):
            lignes.append(f"   étalon « toujours acheter » : Sharpe {naif['moitie1']['sharpe']:+.2f} / "
                          f"{naif['moitie2']['sharpe']:+.2f}, pire baisse {naif['tout']['pire_baisse'] * 100:.0f} %")
    else:
        lignes.append("Banc d'essai : historique journalier en cours d'archivage.")
    tradables, exclus = e.get("tradables") or [], e.get("exclus") or {}
    if tradables or exclus:
        lignes.append(f"Capital : {len(tradables)} marchés tenables (budget {e.get('budget', 0) * 100:.2f} % de volatilité "
                      f"chacun) · trop gros pour ce capital : {', '.join(sorted(exclus)) or 'aucun'}")
    pos = e.get("positions") or {}
    lignes.append("Positions : " + (", ".join(f"{s} {v['lots']:g} lot" for s, v in sorted(pos.items())) or "aucune"))
    lignes.append("Rappel : 34 marchés, Yahoo 2000-2026 → règle 200 jours Sharpe +0,47 à +0,81 selon le financement, "
                  "positive sur les deux moitiés. /or_marches_off · /or_marches_on · /or_marches_fermer")
    return "\n".join(lignes)
