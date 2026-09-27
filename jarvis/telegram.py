# -*- coding: utf-8 -*-
"""Jarvis sur Telegram : texte, vocaux, photos, PDF. Réservé aux chat_id autorisés."""
import base64
import html
import json
import logging
import re
import threading
import time

import requests

from . import voix
from .cerveau import Jarvis
from .config import DONNEES, MEMOIRES, TG_AUTORISES, TG_TOKEN, VOIX_PAR_DEFAUT

log = logging.getLogger("jarvis.telegram")
API = f"https://api.telegram.org/bot{TG_TOKEN}"
FICHIER = f"https://api.telegram.org/file/bot{TG_TOKEN}"
PREFS = DONNEES / "telegram_prefs.json"
LIMITE_MESSAGE = 4000

AIDE = """🤖 *JARVIS* à votre service.

Parlez-moi normalement : texte, message vocal, photo, capture d'écran ou PDF.

Commandes :
/etat : état de vos bots de trading
/voix auto|on|off : réponses vocales (auto : si vous m'envoyez un vocal)
/memoire : ce dont je me souviens
/oubli : nouvelle conversation (la mémoire long terme reste)
/oui /non : confirmer ou annuler une action sur les bots
/aide : ce message"""


def _api(methode: str, **kw):
    fichiers = kw.pop("files", None)
    if fichiers:
        r = requests.post(f"{API}/{methode}", data=kw, files=fichiers, timeout=120)
    else:
        r = requests.post(f"{API}/{methode}", json=kw, timeout=60)
    return r.json()


def _html(texte: str) -> str:
    """Markdown simple de Claude -> HTML Telegram."""
    blocs = []

    def garder(m):
        blocs.append(f"<pre>{html.escape(m.group(2))}</pre>")
        return f"\x00{len(blocs) - 1}\x00"

    t = re.sub(r"```(\w*)\n?(.*?)```", garder, texte, flags=re.S)
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", t, flags=re.M)
    return re.sub(r"\x00(\d+)\x00", lambda m: blocs[int(m.group(1))], t)


def _morceaux(texte: str):
    while len(texte) > LIMITE_MESSAGE:
        coupe = texte.rfind("\n", 0, LIMITE_MESSAGE)
        coupe = coupe if coupe > LIMITE_MESSAGE // 2 else LIMITE_MESSAGE
        yield texte[:coupe]
        texte = texte[coupe:].lstrip("\n")
    if texte:
        yield texte


def envoyer(chat, texte: str):
    for bout in _morceaux(texte):
        r = _api("sendMessage", chat_id=chat, text=_html(bout), parse_mode="HTML", disable_web_page_preview=True)
        if not r.get("ok"):          # HTML refusé : on renvoie en texte brut
            _api("sendMessage", chat_id=chat, text=bout, disable_web_page_preview=True)


def envoyer_vocal(chat, texte: str):
    try:
        res = voix.synthetiser(texte)
    except Exception:
        log.exception("synthèse vocale")
        return
    if not res:
        return
    audio, fmt = res
    if fmt == "ogg":
        _api("sendVoice", chat_id=chat, files={"voice": ("jarvis.ogg", audio, "audio/ogg")})
    else:
        _api("sendAudio", chat_id=chat, title="Jarvis", files={"audio": ("jarvis.mp3", audio, "audio/mpeg")})


class Frappe:
    """Affiche « Jarvis écrit… » tant que la réponse se prépare."""

    def __init__(self, chat):
        self.chat, self.stop = chat, threading.Event()

    def __enter__(self):
        def boucle():
            while not self.stop.is_set():
                try:
                    _api("sendChatAction", chat_id=self.chat, action="typing")
                except Exception:
                    pass
                self.stop.wait(4)
        threading.Thread(target=boucle, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.stop.set()


def _telecharger(file_id: str) -> tuple[bytes, str]:
    info = _api("getFile", file_id=file_id)["result"]
    r = requests.get(f"{FICHIER}/{info['file_path']}", timeout=120)
    r.raise_for_status()
    return r.content, info["file_path"].rsplit("/", 1)[-1]


class BotTelegram:
    def __init__(self):
        if not TG_TOKEN:
            raise SystemExit("JARVIS_TELEGRAM_TOKEN manquant dans jarvis/.env (créez un bot avec @BotFather).")
        self.jarvis = Jarvis()
        try:
            self.prefs = json.loads(PREFS.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.prefs = {}

    def _pref_voix(self, chat) -> str:
        return self.prefs.get(str(chat), {}).get("voix", VOIX_PAR_DEFAUT)

    def _set_voix(self, chat, mode: str):
        self.prefs.setdefault(str(chat), {})["voix"] = mode
        PREFS.write_text(json.dumps(self.prefs), encoding="utf-8")

    # ── Traitement d'un message ─────────────────────────────────────────────
    def _contenu(self, msg) -> tuple[list | str | None, bool]:
        """Construit le contenu pour Claude. Renvoie (contenu, reçu_en_vocal)."""
        legende = msg.get("caption", "")
        if "voice" in msg or "audio" in msg:
            media = msg.get("voice") or msg.get("audio")
            audio, nom = _telecharger(media["file_id"])
            texte = voix.transcrire(audio, nom)
            return f"(message vocal transcrit) {texte}", True
        if "photo" in msg:
            image, _ = _telecharger(msg["photo"][-1]["file_id"])
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                  "data": base64.standard_b64encode(image).decode()}},
                    {"type": "text", "text": legende or "Analyse cette image."}], False
        if "document" in msg:
            doc = msg["document"]
            donnees, nom = _telecharger(doc["file_id"])
            mime = doc.get("mime_type", "")
            if mime == "application/pdf":
                bloc = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                       "data": base64.standard_b64encode(donnees).decode()}}
            elif mime.startswith("image/") and mime in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                bloc = {"type": "image", "source": {"type": "base64", "media_type": mime,
                                                    "data": base64.standard_b64encode(donnees).decode()}}
            else:
                try:
                    bloc = {"type": "text", "text": f"Fichier {doc.get('file_name', nom)} :\n{donnees.decode('utf-8')}"}
                except UnicodeDecodeError:
                    return None, False
            return [bloc, {"type": "text", "text": legende or f"Analyse ce fichier ({doc.get('file_name', nom)})."}], False
        return msg.get("text"), False

    def _commande(self, chat, texte: str) -> bool:
        cmd, _, arg = texte.strip().partition(" ")
        cmd = cmd.split("@")[0].lower()
        conv = f"tg_{chat}"
        if cmd in ("/start", "/aide", "/help"):
            envoyer(chat, AIDE)
        elif cmd == "/oubli":
            self.jarvis.oublier(conv)
            envoyer(chat, "Conversation effacée. Ma mémoire long terme, elle, reste intacte.")
        elif cmd == "/voix":
            mode = arg.strip().lower()
            if mode not in ("on", "off", "auto"):
                envoyer(chat, f"Mode vocal actuel : {self._pref_voix(chat)}. Utilisez /voix on, off ou auto.")
            else:
                self._set_voix(chat, mode)
                envoyer(chat, f"Mode vocal : {mode}.")
        elif cmd == "/memoire":
            fichiers = sorted(p for p in MEMOIRES.rglob("*") if p.is_file())
            if not fichiers:
                envoyer(chat, "Ma mémoire long terme est encore vide.")
            for p in fichiers:
                envoyer(chat, f"**{p.relative_to(MEMOIRES)}**\n{p.read_text(encoding='utf-8')}")
        elif cmd == "/non":
            annule = self.jarvis.en_attente.pop(conv, None)
            envoyer(chat, "Action annulée." if annule else "Aucune action en attente.")
        elif cmd == "/oui":
            if conv not in self.jarvis.en_attente:
                envoyer(chat, "Aucune action en attente.")
                return True
            with Frappe(chat):
                resultat = self.jarvis.executer_action_en_attente(conv)
                reponse = self.jarvis.repondre(conv, f"[Système] L'utilisateur a confirmé. Résultat de l'action :\n{resultat}\nRésume-lui le résultat.")
            envoyer(chat, reponse)
        elif cmd == "/etat":
            return False            # traité comme une question normale
        else:
            return False
        return True

    def traiter(self, msg):
        chat = str(msg["chat"]["id"])
        if chat not in TG_AUTORISES:
            log.warning("chat non autorisé %s", chat)
            envoyer(chat, f"Accès refusé. Votre chat_id est {chat} : ajoutez-le à JARVIS_TELEGRAM_CHAT_IDS dans jarvis/.env puis redémarrez Jarvis.")
            return
        texte = msg.get("text", "")
        if texte.startswith("/") and self._commande(chat, texte):
            return
        if texte.split("@")[0].strip().lower() == "/etat":
            texte = msg["text"] = "Fais-moi un point complet sur l'état de mes bots de trading."
        try:
            with Frappe(chat):
                contenu, vocal = self._contenu(msg)
                if not contenu:
                    envoyer(chat, "Je ne sais pas encore lire ce type de message.")
                    return
                reponse = self.jarvis.repondre(f"tg_{chat}", contenu)
        except Exception as e:
            log.exception("traitement")
            envoyer(chat, f"Un incident est survenu : {type(e).__name__}: {e}")
            return
        envoyer(chat, reponse)
        mode = self._pref_voix(chat)
        if mode == "on" or (mode == "auto" and vocal):
            envoyer_vocal(chat, reponse)

    # ── Boucle principale ───────────────────────────────────────────────────
    def lancer(self):
        moi = _api("getMe")
        if not moi.get("ok"):
            raise SystemExit(f"Token Telegram invalide : {moi}")
        _api("setMyCommands", commands=[
            {"command": "etat", "description": "État des bots de trading"},
            {"command": "voix", "description": "Réponses vocales : auto / on / off"},
            {"command": "memoire", "description": "Ce dont Jarvis se souvient"},
            {"command": "oubli", "description": "Nouvelle conversation"},
            {"command": "aide", "description": "Aide"},
        ])
        log.info("Jarvis en ligne sur Telegram : @%s", moi["result"]["username"])
        decalage = None
        while True:
            try:
                r = requests.get(f"{API}/getUpdates", params={"timeout": 50, "offset": decalage}, timeout=70).json()
                for maj in r.get("result", []):
                    decalage = maj["update_id"] + 1
                    msg = maj.get("message") or maj.get("edited_message")
                    if msg:
                        self.traiter(msg)
            except requests.RequestException as e:
                log.warning("réseau Telegram : %s", e)
                time.sleep(5)
            except Exception:
                log.exception("boucle Telegram")
                time.sleep(5)
