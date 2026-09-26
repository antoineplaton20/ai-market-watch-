"""Signaux de vie pour systemd (WatchdogSec) : un service figé est tué et relancé automatiquement."""
from __future__ import annotations

import math
import os
import socket
import time


def notifier(message):
    adresse = os.environ.get("NOTIFY_SOCKET")
    if not adresse:
        return
    if adresse.startswith("@"):
        adresse = "\0" + adresse[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(adresse)
            s.sendall(message.encode())
    except OSError:
        pass


def dormir(secondes):
    """Attente découpée : signe de vie toutes les 15 s sous systemd."""
    if not os.environ.get("NOTIFY_SOCKET"):
        time.sleep(secondes)
        return
    morceaux = max(1, math.ceil(secondes / 15))
    for _ in range(morceaux):
        notifier("WATCHDOG=1")
        time.sleep(secondes / morceaux)
    notifier("WATCHDOG=1")
