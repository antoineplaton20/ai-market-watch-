"""Archive du courtier en UTC, conformément à l'API MetaQuotes copy_rates_range.
R3 utilise MT5_UTC_R3 pour ne pas mélanger les anciens horodatages corrigés empiriquement.
Source : https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py
Les erreurs de lecture ne sont jamais assimilées à une fin d'historique.
"""
from __future__ import annotations

import time

from . import base, disque, donnees, mt5

SOURCE = "MT5_UTC_R3"
PAS_S = {"1d": 86400, "4h": 14400, "1h": 3600, "15m": 900}
FENETRE_S = {"1d": 10 * 365 * 86400, "4h": 2 * 365 * 86400, "1h": 365 * 86400, "15m": 90 * 86400}
UNITES = ("1d", "4h", "1h", "15m")


def decalage_serveur():
    """L'API transmet des secondes Unix UTC : aucun décalage à estimer."""
    return 0


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
    plein = disque.garde()                                  # R8.5 : pas d'historique ancien quand le disque est plein
    msgs = []
    for tf in unites:
        etat = base.lire(f"mt5:archive:utc-r3:{tf}") or {"vides": 0, "fini": False}
        premier, dernier, n = _etendue(tf)
        if plein and not dernier:
            msgs.append(f"{tf}: suspendu")
            continue
        # 1) en avant : bougies nouvelles depuis la dernière gardée
        debut = (dernier / 1000 + dec + PAS_S[tf]) if dernier else serveur - FENETRE_S[tf]
        ajout = _inserer(tf, mt5.appel("bougies_periode", tf=tf, debut=int(debut), fin=int(serveur), delai=180),
                         dec, serveur)
        # 2) en arrière : jusqu'au début de l'historique du courtier
        for _ in range(fenetres_par_passage):
            if etat["fini"] or plein:
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
        base.ecrire(f"mt5:archive:utc-r3:{tf}", etat)
        premier, _, n = _etendue(tf)
        msgs.append(f"{tf}: {n} bougies" + (f" depuis {time.strftime('%Y', time.gmtime(premier / 1000))}" if premier else "")
                    + (" (complet)" if etat["fini"] else "") + (f", +{ajout}" if ajout else ""))
    return "historique MT5 " + " · ".join(msgs) + (f" (historique ancien suspendu : {plein})" if plein else "")


def resume():
    parts = []
    for tf in UNITES:
        premier, _, n = _etendue(tf)
        if n:
            parts.append(f"{tf} {n} depuis {time.strftime('%m/%Y', time.gmtime(premier / 1000))}")
    return ("Historique XAUUSD du courtier : " + " · ".join(parts)) if parts else "Historique XAUUSD du courtier : pas encore archivé"
