"""Réglages de l'armée de l'or : fichier .env de SON dossier (jamais celui des autres bots)."""
from __future__ import annotations

import os
from pathlib import Path

RACINE = Path(os.getenv("OR_DOSSIER") or Path(__file__).resolve().parent.parent)


def _lire_env(chemin):
    valeurs = {}
    try:
        for ligne in Path(chemin).read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, val = ligne.split("=", 1)
                valeurs[cle.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass
    return valeurs


_ENV = _lire_env(RACINE / ".env")


def txt(nom, defaut=""):
    v = os.getenv(nom, _ENV.get(nom, ""))
    return v.strip() if v and v.strip() else defaut


def nombre(nom, defaut):
    try:
        return float(txt(nom, str(defaut)).replace(",", "."))
    except ValueError:
        return float(defaut)


def booleen(nom, defaut=False):
    return txt(nom, "1" if defaut else "0").lower() in {"1", "true", "oui", "yes", "on"}


BASE = Path(txt("OR_BASE", str(RACINE / "runtime" / "or.db")))
DONNEES_INITIALES = RACINE / "donnees_initiales"
JOURNAL = RACINE / "runtime" / "or.log"

# Marchés suivis en direct (Binance, données publiques, aucune clé)
SOURCE_PRINCIPALE = txt("OR_SOURCE", "XAUUSDT")          # contrat perpétuel or (suit l'once d'or au comptant)
SOURCES_DIRECT = ("XAUUSDT", "PAXGUSDT")                  # PAXG : jeton adossé à 1 once d'or physique
UNITE_DECISION = "1h"                                     # bougies sur lesquelles le chef décide

# Telegram : bot SÉPARÉ recommandé (commandes possibles) ; sinon envoi seul avec le bot existant
TELEGRAM_JETON = txt("OR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = txt("OR_TELEGRAM_CHAT_ID")
TELEGRAM_COMMANDES = booleen("OR_TELEGRAM_COMMANDES", False)  # True seulement avec un bot Telegram dédié

# Papier : capital fictif de départ de chaque profil de levier
CAPITAL_PAPIER = nombre("OR_CAPITAL_PAPIER", 1000)
SEUIL_CONSENSUS = nombre("OR_SEUIL_CONSENSUS", 0.56)      # probabilité de hausse (ou 1 - baisse) pour agir
RAPPORT_HEURES = nombre("OR_RAPPORT_HEURES", 6)

# MetaTrader 5 (compte DÉMO) : ordres automatiques via le pont Wine (service armee-or-mt5)
MT5_ACTIF = booleen("OR_MT5_ACTIF", False) and bool(txt("OR_MT5_LOGIN"))
MT5_SYMBOLE = txt("OR_MT5_SYMBOLE", "XAUUSD")
MT5_PORT = int(nombre("OR_MT5_PORT", 18777))
MT5_PROFIL = txt("OR_MT5_PROFIL", "pro 1 % risqué")         # profil de levier des équipes de décision
MT5_ENTRAINEMENT = booleen("OR_MT5_ENTRAINEMENT", True)     # équipe d'entraînement : lot minimum, toutes les heures
