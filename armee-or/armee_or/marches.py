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

R5 : l'équipe démarre DÉSACTIVÉE (elle calcule et montre ce qu'elle ferait). Ses achats exigent le permis de son banc
ET l'activation du propriétaire (/or_marches_on, qui vérifie le compte et l'absence d'incident R2). Ils passent par le
chemin dédié du pont (marches_ouvrir) : achat seulement, stop obligatoire, 0,5 % du compte risqué au plus par ordre,
et le plafond R3 de 2 % de pertes cumulées jusqu'aux stops, toutes positions du compte comprises (environ 6 marchés
tenus à la fois). Intention écrite avant l'envoi (r2:ordre_incertain) : une réponse perdue verrouille les entrées
jusqu'à réconciliation, comme pour les autres équipes.

R8.1 et R8.2 (décisions du propriétaire du 26/10/2026) : /or_marches_1000 fait imiter à la démo un compte de 1 000 € :
chaque trade fait exactement 0,01 lot, s'il risque jusqu'au stop au plus 3 % de min(1 000, équité) ; 3 positions au
plus (familles différentes d'abord), 9 % au total ; plafonds fixés dans le pont (equipes_pont). /or_marches_normal :
retour.
"""
from __future__ import annotations

import logging
import math
import re
import time

import numpy as np

from . import base, config, donnees, indicateurs as I, mt5, qualite as Q, risque, telegram
from .equipes_pont import (CAPITAL_LOT, CAPITAL_MAX_MARCHES, CAPITAL_REFERENCE, CAPITAL_RISQUE_ORDRE,
                           CAPITAL_RISQUE_TOTAL)

_log = logging.getLogger("or.marches")

MAGIQUE = 770050
CLE = "marches:etat"
CLE_CAPITAL = "marches:capital"     # R8.1 : la démo imite un compte de 1 000 € (/or_marches_1000, /or_marches_normal)
RESERVE_COUTS = 1.25                # comme le pont (pont_mt5.RESERVE_COUTS) : le risque estimé garde une marge
STRATEGIES = {"sma200": "au-dessus de sa moyenne 200 jours", "croisement_20_50": "moyenne 20 j au-dessus de la 50 j "
              "(3e vidéo)", "momentum_12m": "en hausse sur 12 mois (Moskowitz, Ooi et Pedersen, 2012)",
              "toujours_acheter": "toujours acheter (étalon naïf)"}
# R6 (25/10/2026) : le momentum 12 mois est le seul des 13 essais de la recherche à passer tous les contrôles
# (etudes/recherche_r6.py, etudes/robustesse_r6.py). Le permis choisit, sur l'historique du COURTIER, la meilleure
# règle qui gagne sur chaque moitié et bat le naïf.
CANDIDATES = ("sma200", "croisement_20_50", "momentum_12m")
MOMENTUM = 252                      # 12 mois de bourse
STOP_ATR = 5.0                      # stop de catastrophe : 5 ATR(20) journaliers sous l'entrée
VOL_BANC = 0.10                     # banc : chaque marché à 10 % de volatilité annuelle (portefeuille à risque égal)
LEVIER_MAX = 5.0
VOL_PORTEFEUILLE = 0.10             # équipe : volatilité annuelle visée pour l'ensemble du portefeuille
CORRELATION = 0.15                  # corrélation moyenne supposée entre les positions (budget de risque par marché)
MIN_MARCHES, MIN_ENTREES, MIN_BOUGIES = 6, 30, 750
MARGE_MAX = 0.5                     # pas de nouvel achat au-delà de 50 % de la marge utilisée
MARCHE_FERME = 10018
REFUS_CERTAINS = {10004, 10006, 10013, 10014, 10015, 10016, 10017, 10018, 10019, 10021, 10030}   # comme R4
INCERTAIN = "r2:ordre_incertain"
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
GAGNANTS_MESURES = "22 %"           # étude du 25/10/2026, 3 432 trades (LISEZMOI : « Gagner à chaque trade ? »)
# R6.2 : verrou de gain — dès une clôture à +2 ATR (ATR de l'entrée), stop remonté à +0,5 ATR : le trade ne peut plus
# finir en perte (sauf trou de cotation) ; rachat si la règle tient encore. Neutre sur le résultat (etudes/
# robustesse_r62.py), 42 % de trades gagnants au lieu de 34 % : choix du propriétaire (« un petit gain par trade »).
VERROU = (2.0, 0.5)
SORTIES = {"verrou": VERROU, "rachat": True}


def lire():
    return base.lire(CLE) or {}


def ecrire(e):
    base.ecrire(CLE, e)


def actif():
    return bool(base.lire("marches:actif", False))


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
    if strategie == "momentum_12m":                         # Moskowitz, Ooi et Pedersen (2012), acheteur seulement
        s = np.zeros(len(c))
        s[MOMENTUM:] = c[MOMENTUM:] > c[:-MOMENTUM]
        return s
    s = np.ones(len(c))
    s[:200] = 0.0                                           # même départ que la moyenne 200 j
    return s


def volatilite(c, i, n=60):
    r = np.diff(c[max(0, i - n):i + 1]) / c[max(0, i - n):i]
    return float(r.std() * math.sqrt(252)) if len(r) >= 20 else 0.0


def simuler_marche(o, h, l, c, strategie, cout, vol_cible=VOL_BANC, journal=None, sorties=None):
    """-> (rendement net quotidien en part du capital, nombre d'entrées). Comme l'équipe en direct, qui n'agit
    qu'après la clôture : décision à la clôture du jour i, exécutée à l'OUVERTURE du jour i+1 (jamais au cours de
    clôture qui a servi à décider). Taille fixée à l'entrée ; stop de catastrophe à 5 ATR(20) sous le prix d'entrée,
    ATR des bougies closes ; touché, on attend que le signal retombe avant de reprendre. « Toujours acheter »
    (l'étalon) n'a pas de stop et sa taille est revue chaque mois, pour rester à risque constant sur vingt ans.
    journal : liste qui reçoit chaque trade (jour d'entrée, jour de sortie ou None, résultat net en part du capital).
    sorties (R6.2, études) : {"verrou": (k, m)} → dès une clôture à +k ATR d'entrée, stop remonté à +m ATR (le trade
    ne peut plus finir en perte, sauf trou de cotation) ; {"suiveur": k} → stop suiveur de LeBeau, plus haut atteint
    − k ATR ; {"rachat": True} → après une sortie qui protège un gain, rachat possible si la règle tient encore."""
    sorties = sorties or {}
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    n = len(c)
    sig = signal(c, strategie)
    atr = I.atr(h, l, c, 20)
    avec_stop = strategie != "toujours_acheter"
    ecart, swap = cout["ecart"], cout["swap_long"]
    net = np.zeros(n)
    w, stop, bloque, entrees, ordre, taille, debut, resultat = 0.0, 0.0, False, 0, None, 0.0, 0, 0.0
    entree, atr_entree, plus_haut, stop_initial = 0.0, 0.0, 0.0, 0.0

    def proteger(i):                                              # à la clôture i : le stop ne fait que monter
        nonlocal stop, plus_haut
        plus_haut = max(plus_haut, h[i])
        if "verrou" in sorties and c[i] >= entree + sorties["verrou"][0] * atr_entree:
            stop = max(stop, entree + sorties["verrou"][1] * atr_entree)
        if "suiveur" in sorties and np.isfinite(atr[i]):
            stop = max(stop, plus_haut - sorties["suiveur"] * atr[i])

    def apres_stop():
        return not (sorties.get("rachat") and stop > stop_initial)  # gain protégé : rachat permis si la règle tient

    def clore(i, r):
        nonlocal w, resultat
        net[i] += r
        if journal is not None:
            journal.append((debut, i, resultat + r))
        w = 0.0
    for i in range(1, n):
        if ordre == "sortir":                                     # vendu à l'ouverture : l'écart de la nuit est subi
            clore(i, w * (o[i] / c[i - 1] - 1) - w * ecart)
        elif ordre == "entrer":                                   # acheté à l'ouverture
            w, debut = taille, i
            stop = stop_initial = o[i] - STOP_ATR * atr[i - 1]
            entree, atr_entree, plus_haut = o[i], atr[i - 1], o[i]
            entrees += 1
            if avec_stop and l[i] <= stop:
                net[i] -= w * ecart
                resultat = -w * ecart
                clore(i, w * (stop / o[i] - 1) - w * ecart)
                bloque = True
            else:
                net[i] += w * (c[i] / o[i] - 1) - w * ecart + w * swap
                resultat = net[i]
                if avec_stop:
                    proteger(i)
        elif w:
            if avec_stop and l[i] <= stop:                        # stop touché dans la journée (au pire : l'ouverture)
                clore(i, w * (min(o[i], stop) / c[i - 1] - 1) - w * ecart)
                bloque = apres_stop()
            else:
                r = w * (c[i] / c[i - 1] - 1) + w * swap
                if not avec_stop and i % 21 == 0:                 # étalon : retour au risque visé chaque mois
                    vol = volatilite(c, i)
                    if vol > 0:
                        nouveau = min(LEVIER_MAX, vol_cible / vol)
                        r -= abs(nouveau - w) * ecart
                        w = nouveau
                net[i] += r
                resultat += r
                if avec_stop:
                    proteger(i)
        ordre = None
        if sig[i] == 0:                                           # décisions à la clôture, pour le lendemain
            if w:
                ordre = "sortir"
            bloque = False
        elif not w and not bloque and i >= 60 and i + 1 < n:
            vol = volatilite(c, i)
            if vol > 0 and np.isfinite(atr[i]):
                ordre, taille = "entrer", min(LEVIER_MAX, vol_cible / vol)
    if w and journal is not None:
        journal.append((debut, None, resultat))                   # encore ouvert à la fin de l'historique
    return net, entrees


def bilan_trades(trades):
    """Résultat de chaque trade -> part de gagnants, gain moyen, perte moyenne, pire et meilleur (part du capital)."""
    r = np.array([t[2] for t in trades], dtype=float)
    if not len(r):
        return {"n": 0}
    g, p = r[r > 0], r[r <= 0]
    return {"n": int(len(r)), "gagnants": float(len(g) / len(r)), "gain_moyen": float(g.mean()) if len(g) else 0.0,
            "perte_moyenne": float(p.mean()) if len(p) else 0.0, "pire": float(r.min()), "meilleur": float(r.max()),
            "esperance": float(r.mean())}


def statistiques(x):
    x = np.asarray(x, dtype=float)
    if len(x) < 250:
        return None
    an, vol = float(x.mean() * 252), float(x.std() * math.sqrt(252))
    courbe = np.cumsum(x)
    return {"rendement": an, "vol": vol, "sharpe": an / vol if vol else 0.0,
            "pire_baisse": float((courbe - np.maximum.accumulate(courbe)).min())}


def banc(marches, strategies=(*CANDIDATES, "toujours_acheter"), sorties=None, serie=False):
    """marches : {symbole: {"ts": ms, "o","h","l","c": tableaux, "cout": {...}, "famille": ...}} -> résultats par règle :
    portefeuille à risque égal PAR FAMILLE (R6.1, Dalio : chaque famille présente pèse autant, ses marchés se la
    partagent ; sans famille, chaque marché pèse autant), deux moitiés, entrées, Sharpe par marché."""
    garde = {s: d for s, d in marches.items() if len(d["c"]) >= MIN_BOUGIES}
    if not garde:
        return {}
    jours = np.array(sorted({int(t) // 86_400_000 for d in garde.values() for t in d["ts"]}))
    position = {j: i for i, j in enumerate(jours)}
    coupe = jours[len(jours) // 2]
    out = {}
    for strat in strategies:
        familles = {}
        entrees, par_marche, trades, moities = 0, {}, [], [0, 0]
        for s, d in garde.items():
            journal = []
            net, k = simuler_marche(d["o"], d["h"], d["l"], d["c"], strat, d["cout"], journal=journal, sorties=sorties)
            idx = np.array([position[int(t) // 86_400_000] for t in d["ts"]])
            somme, nb = familles.setdefault(d.get("famille") or "?", (np.zeros(len(jours)), np.zeros(len(jours))))
            somme[idx] += net
            nb[idx] += 1
            entrees += k
            for debut, _, _ in journal:
                moities[int(jours[idx[debut]] >= coupe)] += 1
            trades += [t for t in journal if t[1] is not None]           # trades terminés seulement
            st = statistiques(net[200:])
            par_marche[s] = round(st["sharpe"], 2) if st else None
        moyennes = np.array([np.where(n > 0, s / np.maximum(n, 1), np.nan) for s, n in familles.values()])
        presentes = np.isfinite(moyennes).sum(axis=0)
        ok = presentes > 0
        p, j = np.nansum(moyennes, axis=0)[ok] / presentes[ok], jours[ok]
        out[strat] = {"tout": statistiques(p), "moitie1": statistiques(p[j < coupe]),
                      "moitie2": statistiques(p[j >= coupe]), "entrees": entrees, "entrees_moities": moities,
                      "marches": len(garde), "par_marche": par_marche, "coupe_jour": int(coupe),
                      "trades": bilan_trades(trades)}
        if serie:                                                     # études seulement (jamais stocké en base)
            out[strat]["serie"] = (j, p)
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
        par_moitie = r.get("entrees_moities") or [r["entrees"], r["entrees"]]
        raisons = [m for m, faux in (
            (f"seulement {r['marches']} marchés (minimum {MIN_MARCHES})", r["marches"] < MIN_MARCHES),
            (f"seulement {min(par_moitie)} entrées sur une moitié (minimum {MIN_ENTREES} sur chacune)",
             min(par_moitie) < MIN_ENTREES),
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
            out[s] = {**d, "cout": couts((e.get("specs") or {}).get(s) or {}, info["famille"], float(d["c"][-1])),
                      "famille": info["famille"]}
    return out


def bot_banc(chef=None):
    if not config.MT5_ACTIF:
        return "MT5 non configuré"
    e = lire()
    marches = charger_marches(e)
    controles = {s: Q.controler(list(zip(d["ts"], d["o"], d["h"], d["l"], d["c"])), famille=d.get("famille", ""))
                 for s, d in marches.items()}              # aucune preuve sur un historique douteux
    base.ecrire("marches:qualite", {s: {"verdict": q["verdict"], "raisons": q["raisons"]} for s, q in controles.items()})
    marches = {s: d for s, d in marches.items() if controles[s]["verdict"] != "écarté"}
    tradables = set(e.get("tradables") or [])
    sous = {s: d for s, d in marches.items() if s in tradables}
    res = banc(sous if len(sous) >= MIN_MARCHES else marches, sorties=SORTIES)  # le banc juge l'équipe telle qu'elle trade
    if not res:
        return "pas encore assez d'historique journalier"
    ancien = base.lire("marches:permis") or {}
    nouveau = permis(res)
    base.ecrire("marches:banc", {"ts": time.time(), "resultats": res, "panier": "tradables" if len(sous) >= MIN_MARCHES
                                 else "tous"})
    base.ecrire("marches:permis", nouveau)
    for s, v in nouveau.items():
        if not ancien or bool((ancien.get(s) or {}).get("ok")) != v["ok"]:
            from . import registre                          # trace dans le registre R3 (il ne délivre aucun permis)
            essai = registre.declarer("MULTI_MARCHES_R5", s, "MT5 journalier, panier du courtier",
                                      "historique du courtier, deux moitiés", STRATEGIES[s], "R5")
            registre.conclure(essai, {**v, "sharpe": list(v.get("sharpe") or ()), "naif": list(v.get("naif") or ())},
                              "exploratoire")
        if bool((ancien.get(s) or {}).get("ok")) != v["ok"]:
            telegram.envoyer(f"🪪 Multi-marchés · {STRATEGIES[s]} : permis {'ACCORDÉ' if v['ok'] else 'RETIRÉ'} "
                             f"({v['raison']} ; Sharpe {v['sharpe'][0]:+.2f} / {v['sharpe'][1]:+.2f}, naïf "
                             f"{v['naif'][0]:+.2f} / {v['naif'][1]:+.2f}).", True)
    return " · ".join(f"{s} {'✅' if v['ok'] else '✖'}" for s, v in nouveau.items())


# ============================================================================ 4) taille des positions
def budget_risque(n, vol_portefeuille=VOL_PORTEFEUILLE, rho=CORRELATION):
    """Volatilité annuelle (en part de l'équité) donnée à chaque marché pour viser vol_portefeuille au total."""
    return vol_portefeuille / math.sqrt(n * (1 + (n - 1) * rho)) if n else 0.0


def mode_capital():
    """R8.1 : l'équipe se dimensionne comme un compte de CAPITAL_REFERENCE (décision du propriétaire, 26/10/2026)."""
    return bool(base.lire(CLE_CAPITAL, False))


def lots_marche(equite, valeur_lot, vol, budget, specs, capital=False):
    """-> (lots, explication). valeur_lot : notionnel d'UN lot en devise du compte. Lot minimum accepté s'il ne
    dépasse pas 2 fois le budget ; au-delà, le marché est trop gros pour ce capital.
    capital (R8.1, R8.2) : exactement CAPITAL_LOT (0,01 lot), si le courtier l'accepte et si sa perte jusqu'au stop
    (STOP_ATR × ATR, avec la réserve de coûts du pont) ne dépasse pas CAPITAL_RISQUE_ORDRE de min(CAPITAL_REFERENCE,
    équité) ; specs["_atr_rel"] = ATR(20) / cours."""
    if capital:
        atr_rel = specs.get("_atr_rel")
        mini, pas = specs.get("volume_min") or 0.01, specs.get("volume_step") or 0.01
        if not (valeur_lot and atr_rel and math.isfinite(atr_rel) and atr_rel > 0):
            return 0.0, "ATR ou valeur du lot inconnue"
        if mini > CAPITAL_LOT + 1e-9 or abs(CAPITAL_LOT / pas - round(CAPITAL_LOT / pas)) > 1e-6:
            return 0.0, f"0,01 lot impossible chez ce courtier (minimum {mini:g}, pas {pas:g})"
        perte = CAPITAL_LOT * valeur_lot * STOP_ATR * atr_rel * RESERVE_COUTS
        permis = CAPITAL_RISQUE_ORDRE * min(CAPITAL_REFERENCE, equite)
        if perte <= permis:
            return CAPITAL_LOT, f"0,01 lot, {_n(perte)} risqués jusqu'au stop ({_n(permis)} permis)"
        return 0.0, f"0,01 lot trop risqué pour {CAPITAL_REFERENCE:g} ({_n(perte)} jusqu'au stop, {_n(permis)} permis)"
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


def budgets_par_famille(symboles, familles=None):
    """Risque égal PAR FAMILLE (R6.1) : chaque famille reçoit le budget d'un marché d'un portefeuille de F familles ;
    ses n marchés se le partagent à parts égales (prudent : comme si ses marchés bougeaient ensemble). Sans familles,
    chaque marché est sa propre famille (budget égal par marché)."""
    familles = familles or {}
    compte = {}
    for s in symboles:
        compte[familles.get(s, s)] = compte.get(familles.get(s, s), 0) + 1
    b = budget_risque(len(compte))
    return {s: b / compte[familles.get(s, s)] for s in symboles}


def selection(candidats, equite, familles=None, capital=False):
    """candidats : {symbole: (valeur_lot, vol, specs)} -> (marchés retenus, budget de chacun, exclus avec raison).
    Le budget dépend des marchés retenus et de leurs familles : on recommence tant que la liste bouge."""
    garde, exclus = dict(candidats), {}
    for _ in range(8):
        budgets = budgets_par_famille(garde, familles)
        nouveaux = {}
        for s, (valeur, vol, specs) in candidats.items():
            budget = budgets[s] if s in budgets else budgets_par_famille([*garde, s], familles)[s]
            lots, note = lots_marche(equite, valeur, vol, budget, specs, capital)
            if lots:
                nouveaux[s] = (valeur, vol, specs)
            else:
                exclus[s] = note
        if set(nouveaux) == set(garde):
            break
        garde = nouveaux
    return garde, budgets_par_famille(garde, familles), {s: r for s, r in exclus.items() if s not in garde}


# ============================================================================ 5) l'équipe (toutes les 5 minutes)
def reconcilier(e, positions, maintenant):
    """Ordre multi-marchés dont la réponse s'est perdue : adopté s'il est chez le courtier ; oublié s'il n'a jamais été
    exécuté (aucune transaction 770050 depuis l'intention, 10 min plus tard). Sinon le verrou R2 reste : diagnostic."""
    i = base.lire(INCERTAIN)
    if not i or i.get("equipe") != "marches":
        return None
    s = i.get("symbole")
    if s in positions:
        p = positions[s][0]
        e.setdefault("positions", {})[s] = {"strategie": i.get("strategie") or "sma200", "ts": i["ts"],
                                            "lots": p["volume"], "prix": p["price_open"], "stop": p["sl"]}
        base.ecrire(INCERTAIN, None)
        return f"{s} : ordre incertain retrouvé chez le courtier, position suivie"
    if maintenant - i["ts"] < 600:
        return None
    deals = mt5.appel("historique", depuis=i["ts"] - 60)
    if any(d.get("magic") == MAGIQUE and d.get("entry") == 0 and d.get("time", 0) >= i["ts"] - 5 for d in deals):
        return None
    base.ecrire(INCERTAIN, None)
    return f"{s} : ordre incertain jamais exécuté (aucune transaction depuis), verrou levé"


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
    from .executant import _verifier_compte
    _verifier_compte(compte)                                # compte changé : verrou R2, rien d'automatique
    equite = float(compte["equity"])
    positions = {}
    for p in mt5.appel("positions"):
        if p["magic"] == MAGIQUE:
            positions.setdefault(p["symbol"], []).append(p)
    suivi, annonces = e.setdefault("positions", {}), []
    reconcilie = reconcilier(e, positions, m)
    if reconcilie:
        annonces.append(reconcilie + " (entrées : /or_marches_on pour reprendre)")
    coupe = bool((base.lire("risque:etat") or {}).get("coupe"))
    for s in list(suivi):                                   # disparue sans nous : stop de catastrophe (ou à la main)
        if s not in positions:
            if coupe:                                       # fermée par le coupe-circuit : rachat permis à la reprise
                annonces.append(f"{s} : fermée par le coupe-circuit")
            elif suivi[s].get("verrou"):                    # stop au-dessus de l'entrée : gain encaissé, rachat permis
                annonces.append(f"{s} : gain verrouillé encaissé (stop {suivi[s]['verrou']} au-dessus de l'entrée "
                                f"{suivi[s].get('prix')}) ; rachat si la règle tient encore")
                e.setdefault("bloque", {})[s] = False
            else:
                annonces.append(f"{s} : sortie par le stop de catastrophe (ou à la main), pas de rachat tant que le "
                                "signal n'est pas retombé")
                e.setdefault("bloque", {})[s] = True
            suivi.pop(s)
    strat = strategie_permise()
    risque_ok, raison_risque = risque.autorise()
    marge_ok = float(compte.get("margin_free") or equite) >= (1 - MARGE_MAX) * equite
    incident = bool(base.lire(INCERTAIN) or base.lire("r2:compte_change"))
    entrees_ok = (strat is not None and actif() and risque_ok and marge_ok and not incident
                  and not getattr(chef, "pause", False) and not base.lire("mt5:pause", True))
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
        if (base.lire("marches:qualite") or {}).get(s, {}).get("verdict") == "écarté":
            msgs.append(f"{s} : historique douteux, aucun achat")     # ses sorties restent gérées
            continue
        atr_rel = float(I.atr(h, l, c, 20)[-1]) / c[-1]
        candidats[s] = (valeur, vol, {**(specs_tous.get(s) or {}), "_atr_rel": atr_rel})
    capital = mode_capital()
    retenus, budgets, exclus = selection(candidats, equite, {s: univers[s]["famille"] for s in candidats}, capital)
    places = None                                           # R8.1 : 3 positions au plus, familles nouvelles d'abord
    if capital:
        libres = CAPITAL_MAX_MARCHES - len(positions)
        prises = [univers.get(x, {}).get("famille") for x in positions]
        prets = sorted(s for s, v in signaux.items() if v[0] == 1 and s in retenus and s not in positions
                       and not e.get("bloque", {}).get(s))
        places = []
        for tour in (0, 1):
            for s in prets:
                if len(places) < libres and s not in places and (tour or univers[s]["famille"] not in prises):
                    places.append(s)
                    prises.append(univers[s]["famille"])
        places = set(places)
    for s, ps in positions.items():                         # verrou de gain : le stop ne fait que monter
        if s not in suivi or s not in signaux:
            continue
        _, _, c_s, h_s, l_s = signaux[s]
        atr_e = suivi[s].get("atr") or float(I.atr(h_s, l_s, c_s, 20)[-1])
        suivi[s]["atr"] = atr_e
        chiffres = int((specs_tous.get(s) or {}).get("digits") or 5)
        for p in ps:
            cible = round(p["price_open"] + VERROU[1] * atr_e, chiffres)
            if c_s[-1] >= p["price_open"] + VERROU[0] * atr_e and (p.get("sl") or 0) < cible:
                try:
                    r = mt5.appel("marches_stop", ticket=p["ticket"], sl=cible)
                except mt5.ErreurMT5 as ex:                 # rien de grave : le stop de catastrophe reste en place
                    msgs.append(f"{s} : verrou non posé ({ex}), nouvel essai")
                    continue
                if r.get("ok"):
                    suivi[s]["verrou"] = cible
                    annonces.append(f"{s} : gain verrouillé, stop remonté à {cible} (entrée {p['price_open']}, "
                                    f"+{VERROU[1]:g} ATR) : ce trade ne peut plus finir en perte, sauf trou de cotation")
                else:
                    msgs.append(f"{s} : verrou refusé ({r.get('commentaire')})")
    e.update(tradables=sorted(retenus), budgets=budgets, exclus=exclus,
             intentions=sorted(s for s, v in signaux.items() if v[0] == 1 and s in retenus and s not in positions))
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
            positions.pop(s, None)
            regle = (suivi.pop(s, None) or {}).get("strategie") or strat or "sma200"
            annonces.append(f"{s} ({univers[s]['nom']}) : sortie, plus « {STRATEGIES[regle]} » · "
                            f"{gain:+.2f} {compte.get('currency', '')}")
            msgs.append(f"{s} sortie {gain:+.2f}")
        elif (not ouverte and sig == 1 and s in retenus and entrees_ok and not e.get("bloque", {}).get(s)
              and (places is None or s in places)):
            valeur, vol, specs = retenus[s]
            lots, note = lots_marche(equite, valeur, vol, budgets[s], specs, capital)
            atr = I.atr(h, l, c, 20)[-1]
            tick = mt5.appel("tick", symbole=s)
            stop = round(tick["ask"] - STOP_ATR * atr, int(specs.get("digits") or 5))
            base.ecrire(INCERTAIN, {"ts": m, "equipe": "marches", "symbole": s, "sens": 1, "volume": lots, "sl": stop,
                                    "strategie": strat, "compte": compte.get("login"), "serveur": compte.get("server")})
            try:                                            # intention écrite AVANT l'envoi, jamais renvoyée ici
                r = (mt5.appel("marches_ouvrir", symbole=s, volume=lots, sl=stop, capital=True) if capital
                     else mt5.appel("marches_ouvrir", symbole=s, volume=lots, sl=stop))
            except mt5.ErreurMT5 as ex:
                base.ecrire("mt5:pause", True)
                annonces.append(f"{s} : réponse du pont perdue ({ex}) — ordre INCERTAIN, entrées verrouillées "
                                "jusqu'à réconciliation")
                break
            if not r.get("ok") and (r.get("avant_envoi") or r.get("retcode") in REFUS_CERTAINS):
                base.ecrire(INCERTAIN, None)                # rien n'est parti, ou refus certain du courtier
                motif = str(r.get("commentaire") or "")
                if r.get("retcode") == MARCHE_FERME or "périmé" in motif:
                    reessai[s] = m + 1800                   # marché fermé : à sa réouverture
                    continue
                e.setdefault("refus", {})[s] = motif
                msgs.append(f"{s} : achat refusé ({r.get('retcode')} {motif})")
                vus[s] = t_barre                            # même bougie : pas de nouvel essai
                continue
            confirme = [p for p in mt5.appel("positions") if p["magic"] == MAGIQUE and p["symbol"] == s]
            if not r.get("ok") or not confirme:
                base.ecrire("mt5:pause", True)
                telegram.alerte_rare(f"marches-incertain-{s}", f"⚠️ Multi-marchés : ordre {s} non confirmé "
                                     f"({r.get('retcode')} {r.get('commentaire')}). Entrées verrouillées jusqu'à "
                                     "réconciliation.", 3600, important=True)
                msgs.append(f"{s} : ordre non confirmé, entrées verrouillées")
                break
            base.ecrire(INCERTAIN, None)
            p = confirme[0]
            lots = p["volume"]
            suivi[s] = {"strategie": strat, "ts": m, "lots": lots, "prix": p["price_open"], "stop": p["sl"],
                        "atr": float(atr)}
            positions[s] = confirme
            e.get("refus", {}).pop(s, None)
            annonces.append(f"ACHAT {lots:g} lot {s} ({univers[s]['nom']}, {univers[s]['famille']}) à "
                            f"{p['price_open']} : {STRATEGIES[strat]} · stop {p['sl']} ({STOP_ATR:g} ATR) · {note}"
                            + (f" · risque {r['risque']:.2f} {r.get('devise', '')}" if r.get("risque") else ""))
            msgs.append(f"{s} achat {lots:g}")
        if entrees_ok or ouverte:                           # désactivée ou en pause : décision au prochain passage
            vus[s] = t_barre
    ecrire(e)
    if annonces:                                            # un seul message par passage, même pour 15 marchés
        telegram.envoyer("🌍 Multi-marchés (MT5 démo)\n" + "\n".join("• " + a for a in annonces))
    etat_entrees = ("entrées autorisées" if entrees_ok else "pas de permis" if strat is None else
                    "désactivée (/or_marches_on)" if not actif() else raison_risque if not risque_ok
                    else "incident R2 non réconcilié" if incident else "marge utilisée au-delà de 50 %" if not marge_ok
                    else "entrées en pause")
    return (f"{len(positions)} marchés en position, {len(retenus)} tradables sur {len(univers)} · {etat_entrees}"
            + (" · " + " · ".join(msgs) if msgs else ""))


def bot_archive(chef=None):
    if not config.MT5_ACTIF:
        return "MT5 non configuré"
    return archiver()


# ============================================================================ pilotage
def fermer_tout():
    from .executant import _verifier_compte
    _verifier_compte(mt5.appel("etat").get("compte"))
    faits = 0
    for p in mt5.appel("positions"):
        if p["magic"] == MAGIQUE:
            faits += bool(mt5.appel("fermer", ticket=p["ticket"], commentaire="armee-or marches stop").get("ok"))
    base.ecrire("marches:actif", False)
    e = lire()
    e["positions"] = {}
    ecrire(e)
    return f"🛑 Multi-marchés : {faits} position(s) fermée(s), plus de nouvel achat (/or_marches_on pour reprendre)."


def activer(chef=None):
    """Activation explicite du propriétaire, comme /or_demo_on : compte démo confirmé et aucun incident R2."""
    if not config.MT5_ACTIF:
        return "🌍 Multi-marchés : MT5 non branché."
    try:
        etat = mt5.appel("etat", delai=150)
        if not etat.get("connecte"):
            raise mt5.ErreurMT5("connexion démo non confirmée")
        from .executant import _verifier_compte
        _verifier_compte(etat.get("compte"))
    except mt5.ErreurMT5 as ex:
        return f"🌍 Multi-marchés NON activé : {ex}"
    if base.lire(INCERTAIN) or base.lire("r2:compte_change"):
        return ("🌍 Multi-marchés NON activé : incident R2 non résolu (ordre incertain ou compte changé). "
                "/or_diagnostic pour le détail.")
    base.ecrire("marches:actif", True)
    base.ecrire("mt5:pause", False)
    base.ecrire("pause", False)
    if chef is not None:
        chef.pause = False
    strat = strategie_permise()
    return ("▶️ Multi-marchés ACTIVÉ sur le compte DÉMO (pause levée). "
            + (f"Permis : {STRATEGIES[strat]}. " if strat else "Pas encore de permis : aucun achat tant que le banc "
               "ne l'accorde pas (/or_marches). ")
            + (f"Comme un compte de {CAPITAL_REFERENCE:g} : {CAPITAL_RISQUE_ORDRE * 100:g} % par trade, "
               f"{CAPITAL_MAX_MARCHES} positions au plus. " if mode_capital() else
               "Plafond R3 : 2 % de pertes cumulées jusqu'aux stops, tout le compte. ")
            + "La démo R4 n'est pas relancée "
            "(sa commande : /or_demo_on) ; une position multi-marchés bloque d'ailleurs ses entrées. "
            "/or_marches_off pour arrêter.")


def commande(c, chef=None):
    c = c.replace("/or_", "").strip()
    if c == "marches_on":
        return activer(chef)
    if c == "marches_1000":
        base.ecrire(CLE_CAPITAL, True)
        return (f"💶 Multi-marchés : le compte démo imite maintenant un compte de {CAPITAL_REFERENCE:g} (décision du "
                f"26/10/2026). Chaque trade fait {CAPITAL_LOT:g} lot, {CAPITAL_RISQUE_ORDRE * 100:g} % du capital "
                f"risqués au plus jusqu'au stop, {CAPITAL_MAX_MARCHES} positions au plus, "
                f"{CAPITAL_RISQUE_TOTAL * 100:g} % au total. Les marchés où {CAPITAL_LOT:g} lot risque plus sont "
                "exclus (souvent l'or et le bitcoin). "
                "Toujours sous permis ; freins du jour et coupe-circuit inchangés. /or_marches pour voir les marchés "
                "tenables · /or_marches_normal pour revenir aux règles d'avant.")
    if c == "marches_normal":
        base.ecrire(CLE_CAPITAL, False)
        return ("🌍 Multi-marchés : retour aux règles normales (taille selon la volatilité, 0,5 % par ordre, plafond R3 "
                "de 2 %). Les positions ouvertes gardent leurs stops.")
    if c == "marches_off":
        base.ecrire("marches:actif", False)
        return "⏸ Multi-marchés : plus de nouvel achat ; les positions gardent leurs sorties et leurs stops."
    if c == "marches_fermer":
        try:
            return fermer_tout()
        except mt5.ErreurMT5 as ex:
            base.ecrire("marches:actif", False)
            return f"🛑 Multi-marchés arrêté, mais fermeture impossible pour l'instant ({ex}). Réessaie /or_marches_fermer."
    return texte_marches()


def ligne_courte():
    """Une ligne pour le rapport MT5."""
    pos = lire().get("positions") or {}
    strat = strategie_permise()
    return (f"🌍 Multi-marchés : {'activé' if actif() else 'désactivé'} · permis "
            f"{STRATEGIES[strat] if strat else 'aucun'} · {len(pos)} marché(s) tenu(s)"
            + (f" · comme un compte de {CAPITAL_REFERENCE:g}" if mode_capital() else "") + " · /or_marches")


def texte_marches():
    if not config.MT5_ACTIF:
        return "🌍 Multi-marchés : MT5 non branché."
    e = lire()
    univers = e.get("univers") or {}
    lignes = ["🌍 Armée multi-marchés (forex, métaux, énergie, agricoles, indices, crypto)"
              + ("" if actif() else " · DÉSACTIVÉE : elle montre ce qu'elle ferait (/or_marches_on pour l'activer)")]
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
                tr = r.get("trades") or {}
                if tr.get("n"):
                    lignes.append(f"   trades : {tr['gagnants'] * 100:.0f} % gagnants, gain moyen {tr['gain_moyen'] * 100:+.2f} %, "
                                  f"perte moyenne {tr['perte_moyenne'] * 100:+.2f} %, pire {tr['pire'] * 100:+.1f} % "
                                  "(part de la mise du marché)")
        if naif.get("tout"):
            lignes.append(f"   étalon « toujours acheter » : Sharpe {naif['moitie1']['sharpe']:+.2f} / "
                          f"{naif['moitie2']['sharpe']:+.2f}, pire baisse {naif['tout']['pire_baisse'] * 100:.0f} %")
    else:
        lignes.append("Banc d'essai : historique journalier en cours d'archivage.")
    tradables, exclus = e.get("tradables") or [], e.get("exclus") or {}
    if tradables or exclus:
        fams = sorted({univers[s]["famille"] for s in tradables if s in univers})
        if mode_capital():
            lignes.append(f"Capital imité : {CAPITAL_REFERENCE:g} ({CAPITAL_LOT:g} lot par trade, "
                          f"{CAPITAL_RISQUE_ORDRE * 100:g} % au plus, "
                          f"{CAPITAL_MAX_MARCHES} positions au plus, {CAPITAL_RISQUE_TOTAL * 100:g} % au total) · "
                          f"{len(tradables)} marchés tenables ({', '.join(sorted(tradables)) or '—'})")
            if exclus:
                lignes.append("Trop risqués pour ce capital : " + " · ".join(
                    f"{s} ({r})" for s, r in sorted(exclus.items())[:12]) + (" …" if len(exclus) > 12 else ""))
        else:
            lignes.append(f"Capital : {len(tradables)} marchés tenables, risque égal entre {len(fams)} familles "
                          f"({', '.join(fams) or '—'}) · trop gros pour ce capital : {', '.join(sorted(exclus)) or 'aucun'}")
    pos = e.get("positions") or {}
    lignes.append("Positions : " + (", ".join(f"{s} {v['lots']:g} lot" + (" 🔒 gain verrouillé" if v.get("verrou") else "")
                                         for s, v in sorted(pos.items())) or "aucune"))
    qual = base.lire("marches:qualite") or {}
    if qual:
        ecartes = sorted(s for s, q in qual.items() if q.get("verdict") == "écarté")
        reserve = sum(q.get("verdict") == "réserve" for q in qual.values())
        lignes.append(f"Données contrôlées : {len(qual) - len(ecartes) - reserve} bonnes, {reserve} sous réserve, "
                      f"{len(ecartes)} écartées" + (f" ({', '.join(ecartes)} : ni preuve ni achat)" if ecartes else ""))
    intentions = e.get("intentions") or []
    if intentions:
        lignes.append(("Achats qu'elle ferait (pas de permis ou désactivée) : " if not actif() or not strategie_permise()
                       else "Achats en attente (bougie, marché ouvert, budget R3) : ") + ", ".join(intentions))
    if e.get("refus"):
        lignes.append("Refusés par le pont : " + " · ".join(f"{s} ({r})" for s, r in sorted(e["refus"].items())))
    if base.lire(INCERTAIN):
        lignes.append("⚠️ Ordre incertain non réconcilié : entrées verrouillées (/or_diagnostic).")
    lignes.append("Rappel : 34 marchés, Yahoo 2000-2026, exécution à l'ouverture suivante, stop 5 ATR, risque égal par "
                  "famille → momentum 12 mois Sharpe +0,51 / +0,92 (moitiés), 34 % de trades gagnants ; règle 200 jours "
                  f"+0,47 / +0,83, {GAGNANTS_MESURES} de trades gagnants ; « toujours acheter » +0,37 / +0,77. Viser 80 % "
                  "de trades gagnants (prise de gain rapide) rend la règle perdante. /or_marches_off · /or_marches_on · "
                  "/or_marches_fermer")
    return "\n".join(lignes)
