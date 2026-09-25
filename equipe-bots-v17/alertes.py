"""Journal local + Telegram : alertes (avec ou sans son), boutons d'approbation, commandes."""
import logging
from logging.handlers import RotatingFileHandler
import requests
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    # 5 fichiers de 5 Mo maximum : le journal ne remplit jamais le disque du serveur
    handlers=[RotatingFileHandler("bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"),
              logging.StreamHandler()],
)
_log = logging.getLogger("equipe")
_offset = 0
_URL = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
_ACTIF = bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def log(msg):
    _log.info(msg)


def _envoyer(corps):
    try:
        requests.post(f"{_URL}/sendMessage", json=corps, timeout=10)
    except Exception as e:
        log(f"Telegram injoignable : {e}")


def alerte(msg, important=True):
    """important=True : notification avec son (achats, ventes, arrêts).
    important=False : message silencieux (routine : stop suiveur, signe de vie...)."""
    log(msg)
    if not _ACTIF:
        return
    texte = msg if len(msg) <= 4000 else msg[:3990] + "\n[...]"      # limite Telegram : 4 096 caractères
    _envoyer({"chat_id": config.TELEGRAM_CHAT_ID, "text": texte, "disable_notification": not important})


def boutons(msg, choix):
    """Message avec boutons à toucher sur le téléphone. choix : liste de (texte du bouton, commande)."""
    log(msg + " | choix : " + ", ".join(c for _, c in choix))
    if not _ACTIF:
        return
    clavier = {"inline_keyboard": [[{"text": t, "callback_data": c[:64]} for t, c in choix]]}
    _envoyer({"chat_id": config.TELEGRAM_CHAT_ID, "text": msg[:4000], "reply_markup": clavier})


def _normaliser(texte):
    morceaux = texte.strip().split()
    if not morceaux or not morceaux[0].startswith("/"):
        return None
    morceaux[0] = morceaux[0].lower().split("@")[0]                 # "/stop@MonBot" -> "/stop"
    return " ".join(morceaux)


def commandes():
    """Commandes reçues (tapées ou boutons touchés). Tout ce qui ne vient pas de TON compte est ignoré.
    Renvoie des chaînes du type "/stop" ou "/approuver champion-1a2b3c4d"."""
    global _offset
    if not _ACTIF:
        return []
    try:
        r = requests.get(f"{_URL}/getUpdates", params={"offset": _offset, "timeout": 0}, timeout=10).json()
    except Exception:
        return []
    cmds = []
    for u in r.get("result", []):
        _offset = u["update_id"] + 1
        if "callback_query" in u:                                    # bouton touché
            cq = u["callback_query"]
            if str(((cq.get("message") or {}).get("chat") or {}).get("id")) != str(config.TELEGRAM_CHAT_ID):
                continue
            try:
                requests.post(f"{_URL}/answerCallbackQuery", json={"callback_query_id": cq["id"]}, timeout=10)
            except Exception:
                pass
            c = _normaliser(cq.get("data") or "")
        else:
            msg = u.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != str(config.TELEGRAM_CHAT_ID):
                continue
            c = _normaliser(msg.get("text") or "")
        if c:
            cmds.append(c)
    return cmds


def ignorer_anciennes():
    """Au démarrage, on jette les vieilles commandes (évite un /vendre_tout d'hier)."""
    commandes()
