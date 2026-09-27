# -*- coding: utf-8 -*-
"""Voix de Jarvis : oreilles (Whisper via Groq) et bouche (edge-tts, voix neuronales Microsoft gratuites).

Claude ne traite pas l'audio : on transcrit le vocal en texte avant de le lui passer.
"""
import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

from .config import GROQ_KEY, VOIX_TTS, WHISPER_MODELE

LONGUEUR_MAX_ORALE = 1800   # au-delà, on lit le début et on renvoie au texte


def transcrire(audio: bytes, nom_fichier: str = "vocal.ogg") -> str:
    if not GROQ_KEY:
        raise RuntimeError("GROQ_API_KEY absente : impossible de transcrire les vocaux.")
    r = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {GROQ_KEY}"},
        files={"file": (nom_fichier, audio)},
        data={"model": WHISPER_MODELE, "response_format": "text"},
        timeout=120,
    )
    r.raise_for_status()
    return r.text.strip()


def texte_oral(texte: str) -> str:
    """Retire ce qui se lit mal à voix haute (liens, code, markdown)."""
    t = re.sub(r"```.*?```", " (voir le code dans le message) ", texte, flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[*_`#>|]", "", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    if len(t) > LONGUEUR_MAX_ORALE:
        t = t[:LONGUEUR_MAX_ORALE].rsplit(".", 1)[0] + ". La suite est dans le message écrit."
    return t


def synthetiser(texte: str) -> tuple[bytes, str] | None:
    """Renvoie (audio, format) avec format « ogg » (note vocale) ou « mp3 », ou None si indisponible."""
    try:
        import edge_tts
    except ImportError:
        return None
    t = texte_oral(texte)
    if not t:
        return None
    with tempfile.TemporaryDirectory() as d:
        mp3 = Path(d) / "jarvis.mp3"
        asyncio.run(edge_tts.Communicate(t, VOIX_TTS).save(str(mp3)))
        if shutil.which("ffmpeg"):
            ogg = Path(d) / "jarvis.ogg"
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-c:a", "libopus",
                                "-b:a", "48k", str(ogg)], capture_output=True, timeout=120)
            if r.returncode == 0:
                return ogg.read_bytes(), "ogg"
        return mp3.read_bytes(), "mp3"
