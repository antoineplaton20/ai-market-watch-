"""Messages Telegram de la V17 : passe par alertes.py de la plateforme (même bot Telegram, même chat).
La V17 ne lit JAMAIS les commandes Telegram (c'est le bot principal qui le fait, /v17 compris) :
deux lecteurs sur le même bot Telegram se voleraient les messages."""
from __future__ import annotations

import logging
import time

_log = logging.getLogger("v17")
PREFIXE = "[v17] "


class Notifier:
    def __init__(self, enabled=True, anti_repetition_s=1800):
        self.enabled = enabled
        self.anti_repetition_s = anti_repetition_s
        self._deja = {}

    def send(self, msg, important=True):
        texte = PREFIXE + msg
        if not self.enabled:
            _log.info(texte)
            return
        try:
            from alertes import alerte           # module de la plateforme (journal + Telegram)
            alerte(texte, important=important)
        except Exception as e:                   # Telegram ne doit jamais faire tomber le moteur
            _log.info(texte)
            _log.warning("Telegram indisponible pour la v17 : %s", e)

    def erreur(self, cle, msg, fenetre_s=None):
        """Erreur répétitive (réseau...) : au plus un message Telegram par `cle` toutes les 30 min."""
        maintenant = time.time()
        if maintenant - self._deja.get(cle, 0) < (fenetre_s or self.anti_repetition_s):
            _log.warning(PREFIXE + msg)
            return
        self._deja[cle] = maintenant
        self.send(msg, important=False)


class NullNotifier(Notifier):
    """Pour les tests et l'API : journal local seulement, et garde les messages en mémoire."""

    def __init__(self):
        super().__init__(enabled=False)
        self.messages = []

    def send(self, msg, important=True):
        self.messages.append((msg, important))
        _log.info(PREFIXE + msg)
