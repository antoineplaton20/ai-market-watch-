# -*- coding: utf-8 -*-
"""Configuration de Jarvis : tout vient des variables d'environnement (fichier jarvis/.env)."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ICI = Path(__file__).resolve().parent
RACINE_PROJET = ICI.parent                     # dépôt ai-market-watch- (bots, bilans, v17...)
DONNEES = Path(os.getenv("JARVIS_DATA_DIR", ICI / "data"))
MEMOIRES = DONNEES / "memoires"                # mémoire long terme (outil memory de Claude)
CONVERSATIONS = DONNEES / "conversations"      # historique par conversation (Telegram / terminal)


def _charger_env(fichier: Path):
    """Charge jarvis/.env sans dépendance externe (les variables déjà définies gagnent)."""
    if not fichier.exists():
        return
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, val = ligne.split("=", 1)
        os.environ.setdefault(cle.strip(), val.strip().strip('"').strip("'"))


_charger_env(ICI / ".env")

# Cerveau
MODELE = os.getenv("JARVIS_MODEL", "claude-opus-5")
EFFORT = os.getenv("JARVIS_EFFORT", "high")            # low | medium | high | xhigh | max
MAX_TOKENS = int(os.getenv("JARVIS_MAX_TOKENS", "32000"))
MAX_TOURS_OUTILS = int(os.getenv("JARVIS_MAX_TOOL_ROUNDS", "25"))
HISTORIQUE_MAX = int(os.getenv("JARVIS_HISTORY_MESSAGES", "60"))  # messages gardés par conversation

# Telegram (bot DÉDIÉ à Jarvis : ne pas réutiliser TELEGRAM_TOKEN des bots de trading,
# sinon les deux se volent les messages via getUpdates)
TG_TOKEN = os.getenv("JARVIS_TELEGRAM_TOKEN", "").strip()
TG_AUTORISES = {c.strip() for c in os.getenv("JARVIS_TELEGRAM_CHAT_IDS", "").split(",") if c.strip()}

# Voix : transcription Whisper via Groq (clé déjà utilisée par bot.py), synthèse via edge-tts
GROQ_KEY = os.getenv("GROQ_API_KEY", os.getenv("LLM_API_KEY", "")).strip()
WHISPER_MODELE = os.getenv("JARVIS_WHISPER_MODEL", "whisper-large-v3-turbo")
VOIX_TTS = os.getenv("JARVIS_TTS_VOICE", "fr-FR-HenriNeural")
VOIX_PAR_DEFAUT = os.getenv("JARVIS_VOICE_REPLIES", "auto")   # auto (vocal si on lui parle en vocal) | on | off

FUSEAU = ZoneInfo(os.getenv("JARVIS_TZ", "Europe/Paris"))
NOM_UTILISATEUR = os.getenv("JARVIS_USER_NAME", "Monsieur")

for d in (MEMOIRES, CONVERSATIONS):
    d.mkdir(parents=True, exist_ok=True)
