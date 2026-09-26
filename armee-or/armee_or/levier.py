"""STRATÈGE DU LEVIER — tous les calculs qu'un professionnel fait AVANT de prendre une position à levier.

Contrat modélisé : perpétuel linéaire réglé en USDT (comme XAUUSDT) ou CFD sur l'or, marge « croisée » (tout le
capital du compte sert de garantie). Les mêmes formules valent pour un CFD en remplaçant le financement par le
coût de portage (« swap ») du courtier.

Repères réglementaires :
- UE (ESMA / AMF) : levier maximal de 20 sur l'or pour un particulier, protection contre le solde négatif,
  coupure des positions quand la marge tombe à 50 % du minimum ;
- Binance XAUUSDT : jusqu'à 50 (entité ADGM), non accessible aux résidents de l'UE.
"""
from __future__ import annotations

import math

import numpy as np

FRAIS = 0.0005                 # 0,05 % par côté (frais « taker » typiques d'un perpétuel)
GLISSEMENT = 0.0002            # 0,02 % par côté
FINANCEMENT_8H = 0.0001        # 0,01 % toutes les 8 h (moyenne typique ; payé par les acheteurs si positif)
MARGE_MAINTIEN = 0.005         # 0,5 % du notionnel
LEVIER_MAX_UE = 20
LEVIER_MAX_BINANCE = 50

PROFILS = {
    # nom : (mode, valeur) ; « fixe » = notionnel = capital × levier (ce que font beaucoup de débutants)
    "x1": ("fixe", 1), "x3": ("fixe", 3), "x5": ("fixe", 5), "x10": ("fixe", 10),
    "x20 (max. UE)": ("fixe", 20), "x50 (max. Binance)": ("fixe", 50),
    "pro 1 % risqué": ("risque", 0.01),
}


def prix_liquidation(entree, sens, marge, notionnel, mmr=MARGE_MAINTIEN):
    """Prix où la perte atteint la marge disponible moins la marge de maintien (sens +1 achat, -1 vente)."""
    if notionnel <= 0:
        return 0.0 if sens > 0 else math.inf
    ecart = marge / notionnel - mmr
    return entree * (1 - ecart) if sens > 0 else entree * (1 + ecart)


def taille(profil, capital, entree, stop):
    """-> (notionnel, levier effectif) selon le profil."""
    mode, val = PROFILS[profil]
    if mode == "fixe":
        return capital * val, float(val)
    risque_pct = abs(entree - stop) / entree
    if risque_pct <= 0:
        return 0.0, 0.0
    notionnel = min(capital * val / risque_pct, capital * LEVIER_MAX_UE)
    return notionnel, notionnel / capital


def kelly(p, gain_r, perte_r=1.0):
    """Fraction de Kelly (J. L. Kelly, 1956) : part du capital à risquer pour une probabilité p de gagner
    gain_r contre perte_r. En pratique on n'en risque qu'une fraction (1/4) : les probabilités sont incertaines."""
    b = gain_r / perte_r
    return max(0.0, p - (1 - p) / b)


def excursion_defavorable(b, horizon=24):
    """Pour chaque bougie : pire mouvement contre un achat et contre une vente dans les `horizon` bougies
    suivantes (en % du prix). Sert à estimer la probabilité de liquidation d'après l'historique réel."""
    c, h, l = b["c"], b["h"], b["l"]
    n = len(c)
    if n <= horizon:
        return np.array([]), np.array([])
    fen_l = np.lib.stride_tricks.sliding_window_view(l[1:], horizon).min(axis=1)
    fen_h = np.lib.stride_tricks.sliding_window_view(h[1:], horizon).max(axis=1)
    base = c[:len(fen_l)]
    return (base - fen_l) / base, (fen_h - base) / base


def fiche(capital, prix, atr, sens, p_gain, profil, stop_atr=1.5, rr=1.5, heures=24, excursions=None):
    """Fiche complète d'une position envisagée (affichée au chef d'orchestre et sur Telegram)."""
    stop = prix - sens * stop_atr * atr
    objectif = prix + sens * rr * stop_atr * atr
    notionnel, lev = taille(profil, capital, prix, stop)
    liq = prix_liquidation(prix, sens, capital, notionnel)
    dist_liq = abs(prix - liq) / prix
    dist_stop = abs(prix - stop) / prix
    frais = notionnel * 2 * (FRAIS + GLISSEMENT)
    financement = notionnel * FINANCEMENT_8H * heures / 8
    perte_stop = notionnel * dist_stop + frais + financement
    gain_obj = notionnel * dist_stop * rr - frais - financement
    p_liq = None
    if excursions is not None and len(excursions[0]):
        adverse = excursions[0] if sens > 0 else excursions[1]
        p_liq = float((adverse >= dist_liq).mean())
    esperance = p_gain * gain_obj - (1 - p_gain) * perte_stop
    return {
        "profil": profil, "sens": "achat" if sens > 0 else "vente", "prix": prix, "stop": stop, "objectif": objectif,
        "notionnel": notionnel, "levier": lev, "marge": capital, "liquidation": liq,
        "distance_liquidation_pct": dist_liq * 100, "distance_stop_pct": dist_stop * 100,
        "liquidation_avant_stop": dist_liq <= dist_stop,
        "frais_aller_retour": frais, "financement": financement,
        "perte_si_stop": perte_stop, "gain_si_objectif": gain_obj,
        "perte_si_stop_pct_capital": perte_stop / capital * 100,
        "proba_liquidation_historique": p_liq, "esperance": esperance,
        "kelly_quart": kelly(p_gain, rr) / 4,
    }
