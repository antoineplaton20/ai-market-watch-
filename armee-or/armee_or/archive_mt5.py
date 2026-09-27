"""ARCHIVISTE MT5 — rapatrie l'historique XAUUSD du courtier (l'instrument sur lequel l'armée trade vraiment).

- Remonte le temps par fenêtres (10 ans en 1 jour, 2 ans en 4 h, 1 an en 1 h, 3 mois en 15 min) jusqu'au début de
  l'historique que le serveur MT5 fournit (deux fenêtres vides d'affilée), puis complète chaque heure les bougies
  nouvelles. Travail découpé : quelques fenêtres par passage, sans jamais bloquer le chef.
- Les heures MT5 sont celles du SERVEUR du courtier (souvent UTC+2/+3) : elles sont ramenées en UTC avec le décalage
  mesuré sur le dernier cours (seulement marché ouvert). Décalage d'été/hiver non corrigé pour le passé : au pire
  une heure d'écart sur les séances, sans effet sur la lecture des bougies.
- Bougies stockées sous la source « MT5 » ; seules les bougies terminées sont gardées.
"""
from __future__ import annotations

import time

from . import base, donnees, mt5

SOURCE = "MT5"
PAS_S = {"1d": 86400, "4h": 14400, "1h": 3600, "15m": 900}
FENETRE_S = {"1d": 10 * 365 * 86400, "4h": 2 * 365 * 86400, "1h": 365 * 86400, "15m": 90 * 86400}
UNITES = ("1d", "4h", "1h", "15m")


def decalage_serveur():
    """Heure du serveur MT5 moins heure UTC (secondes, arrondi à la demi-heure), mesuré marché ouvert."""
    d = base.lire("direct:MT5")
    if d and time.time() - d.get("ts", 0) < 900:
        tick = mt5.appel("tick")
        ecart = tick["time"] - time.time()
        if abs(ecart) <= 14 * 3600:
            dec = int(round(ecart / 1800.0) * 1800)
            base.ecrire("mt5:decalage", dec)
            return dec
    return base.lire("mt5:decalage")


def _etendue(tf):
    with base.connexion() as c:
        r = c.execute("SELECT MIN(ts), MAX(ts), COUNT(*) FROM bougies WHERE source=? AND tf=?", (SOURCE, tf)).fetchone()
    return (r[0], r[1], r[2]) if r and r[2] else (None, None, 0)


def _inserer(tf, barres, dec, maintenant_serveur):
    lignes = [[(t - dec) * 1000, o, h, l, c, v] for t, o, h, l, c, v in barres
              if t + PAS_S[tf] <= maintenant_serveur]                   # bougie terminée seulement
    return donnees.inserer(SOURCE, tf, lignes)


def archiver(unites=UNITES, fenetres_par_passage=4):
    dec = decalage_serveur()
    if dec is None:
        return "en attente de l'ouverture du marché (décalage horaire du serveur MT5 inconnu)"
    serveur = time.time() + dec
    msgs = []
    for tf in unites:
        etat = base.lire(f"mt5:archive:{tf}") or {"vides": 0, "fini": False}
        premier, dernier, n = _etendue(tf)
        # 1) en avant : bougies nouvelles depuis la dernière gardée
        debut = (dernier / 1000 + dec + PAS_S[tf]) if dernier else serveur - FENETRE_S[tf]
        ajout = _inserer(tf, mt5.appel("bougies_periode", tf=tf, debut=int(debut), fin=int(serveur), delai=180),
                         dec, serveur)
        # 2) en arrière : jusqu'au début de l'historique du courtier
        for _ in range(fenetres_par_passage):
            if etat["fini"]:
                break
            premier, _, _ = _etendue(tf)
            fin = (premier / 1000 + dec - 1) if premier else serveur - FENETRE_S[tf]
            barres = mt5.appel("bougies_periode", tf=tf, debut=int(fin - FENETRE_S[tf]), fin=int(fin), delai=180)
            if barres:
                ajout += _inserer(tf, barres, dec, serveur)
                etat["vides"] = 0
            else:
                etat["vides"] += 1
                etat["fini"] = etat["vides"] >= 2
        base.ecrire(f"mt5:archive:{tf}", etat)
        premier, _, n = _etendue(tf)
        msgs.append(f"{tf}: {n} bougies" + (f" depuis {time.strftime('%Y', time.gmtime(premier / 1000))}" if premier else "")
                    + (" (complet)" if etat["fini"] else "") + (f", +{ajout}" if ajout else ""))
    return "historique MT5 " + " · ".join(msgs)


def resume():
    parts = []
    for tf in UNITES:
        premier, _, n = _etendue(tf)
        if n:
            parts.append(f"{tf} {n} depuis {time.strftime('%m/%Y', time.gmtime(premier / 1000))}")
    return ("Historique XAUUSD du courtier : " + " · ".join(parts)) if parts else "Historique XAUUSD du courtier : pas encore archivé"
