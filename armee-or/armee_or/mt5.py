"""Client du pont MetaTrader 5 (côté Linux) : une ligne JSON par demande vers 127.0.0.1, jamais ailleurs."""
from __future__ import annotations

import json
import math
import socket

from . import config, levier as L


class ErreurMT5(Exception):
    pass


def appel(op, delai=30, port=None, **parametres):
    """port : celui du pont de l'armée par défaut ; config.VIDEO_PORT pour le 2e compte (équipe vidéo)."""
    port = port or config.MT5_PORT
    service = "armee-or-mt5-video" if port == config.VIDEO_PORT else "armee-or-mt5"
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=delai) as s:
            s.sendall((json.dumps({"op": op, **parametres}) + "\n").encode())
            morceaux = b""
            while not morceaux.endswith(b"\n"):
                bloc = s.recv(65536)
                if not bloc:
                    break
                morceaux += bloc
                if len(morceaux) > 8 * 1024 * 1024:
                    raise ErreurMT5("réponse du pont trop volumineuse")
    except OSError as ex:
        raise ErreurMT5(f"pont MT5 injoignable ({ex.__class__.__name__}) : service {service} arrêté ou en démarrage")
    try:
        rep = json.loads(morceaux)
    except ValueError:
        raise ErreurMT5("réponse illisible du pont MT5")
    if not isinstance(rep, dict) or not isinstance(rep.get("ok"), bool):
        raise ErreurMT5("format de réponse du pont invalide")
    if not rep.get("ok"):
        raise ErreurMT5(rep.get("erreur") or "erreur inconnue")
    if "r" not in rep:
        raise ErreurMT5("résultat absent de la réponse du pont")
    return rep["r"]



PROFILS_COURTS = {"x1": "x1", "x3": "x3", "x5": "x5", "x10": "x10", "x20": "x20 (max. UE)",
                  "x50": "x50 (max. Binance)", "pro": "pro 1 % risqué",
                  "agressif": "agressif 3 % risqué"}


def nom_profil(texte):
    """« x20 » -> « x20 (max. UE) » ; renvoie None si inconnu."""
    t = (texte or "").strip()
    if t in L.PROFILS:
        return t
    return PROFILS_COURTS.get(t.lower())


def volume(profil, equite, prix, stop, specs, marge_par_lot, marge_libre):
    """Lots à envoyer pour un profil de levier, arrondis au pas du symbole, jamais au-delà de 90 % de la marge libre.
    -> (lots, explication)."""
    notionnel, lev = L.taille(profil, equite, prix, stop)
    taille_lot = prix * specs["trade_contract_size"]
    pas = specs["volume_step"] or 0.01
    lots = math.floor(notionnel / taille_lot / pas + 1e-9) * pas
    if marge_par_lot and marge_par_lot > 0:
        lots = min(lots, math.floor(0.9 * marge_libre / marge_par_lot / pas + 1e-9) * pas)
    lots = round(min(lots, specs["volume_max"]), 8)
    if lots < specs["volume_min"]:
        return 0.0, (f"taille trop petite pour le profil {profil} ({notionnel:.0f} $ visés, minimum "
                     f"{specs['volume_min']} lot = {specs['volume_min'] * taille_lot:.0f} $) ou marge insuffisante")
    return lots, f"{lots:g} lot = {lots * taille_lot:.0f} $ (levier effectif {lots * taille_lot / equite:.1f})"
