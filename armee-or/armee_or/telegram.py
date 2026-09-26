"""Messages Telegram de l'armée de l'or.

- Bot Telegram DÉDIÉ (recommandé : @BotFather > /newbot) : l'armée envoie ses rapports ET reçoit ses commandes
  (/or, /or_levier, /or_bilan, /or_pause, /or_reprise, /or_mt5, /or_mt5_fermer), sans jamais gêner le bot existant.
- Sans bot dédié : réutilisation du bot existant en ENVOI SEUL (deux lecteurs sur un même bot se voleraient
  les commandes) ; les commandes passent alors par Termius (« or etat », « or pause »...).
Telegram en panne ne fait jamais tomber l'armée : le message est journalisé et l'armée continue.
"""
from __future__ import annotations

import logging
import time

from . import base, config

_log = logging.getLogger("or.telegram")
PREFIXE = "🟡 [or] "
LIMITE = 4000


def envoyer(texte, important=False, session=None):
    texte = (PREFIXE + texte)[:LIMITE]
    _log.info(texte.replace("\n", " | ")[:500])
    if not (config.TELEGRAM_JETON and config.TELEGRAM_CHAT):
        return False
    try:
        import requests
        s = session or requests
        s.post(f"https://api.telegram.org/bot{config.TELEGRAM_JETON}/sendMessage",
               json={"chat_id": config.TELEGRAM_CHAT, "text": texte, "disable_notification": not important},
               timeout=15)
        return True
    except Exception as ex:
        _log.warning("Telegram indisponible : %s", type(ex).__name__)
        return False


def alerte_rare(cle, texte, fenetre_s=3600, important=False):
    """Au plus un message par `cle` et par fenêtre (mémoire en base : survit aux redémarrages)."""
    deja = base.lire(f"alerte:{cle}", 0) or 0
    if time.time() - deja < fenetre_s:
        _log.info("(alerte déjà envoyée) %s", texte[:200])
        return False
    base.ecrire(f"alerte:{cle}", time.time())
    return envoyer(texte, important)


def commandes(session=None):
    """Commandes reçues sur le bot DÉDIÉ uniquement (jamais sur le bot partagé)."""
    if not (config.TELEGRAM_COMMANDES and config.TELEGRAM_JETON and config.TELEGRAM_CHAT):
        return []
    import requests
    s = session or requests
    decalage = base.lire("telegram_decalage", 0) or 0
    try:
        r = s.get(f"https://api.telegram.org/bot{config.TELEGRAM_JETON}/getUpdates",
                  params={"offset": decalage, "timeout": 0}, timeout=15).json()
    except Exception:
        return []
    out = []
    for u in r.get("result", []):
        decalage = max(decalage, u["update_id"] + 1)
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) == str(config.TELEGRAM_CHAT):
            t = (msg.get("text") or "").strip().split("@")[0].lower()
            if t.startswith("/"):
                out.append(t)
    base.ecrire("telegram_decalage", decalage)
    return out
