"""R8.5 : garde du disque du serveur.

MT5 garde son historique en bougies d'une minute, même quand on ne lui demande que des bougies journalières. L'archive
de ~170 marchés (R8.3) lui a fait télécharger 14 Go, dont 6 Go en 8 heures (mesure du 26/10/2026, 3,3 Go libres).
Sous le seuil d'espace libre, l'armée ne lui demande plus d'historique ancien ni de marché qu'il n'a pas encore : le
disque plein arrêterait la base, MT5 et le bot Gold. Le trading et le suivi des positions ne changent pas.
"""
from __future__ import annotations

import shutil
import time

from . import base, config, telegram

SEUIL_GO = 5.0                          # sous 5 Go libres : plus de nouvel historique demandé à MT5
ALERTE_S = 86400                        # une alerte Telegram par jour au plus


def libre_go(chemin=None):
    """Espace libre en Go (Gio, comme « df -h ») sur le disque de l'armée."""
    return shutil.disk_usage(chemin or config.RACINE).free / 1024 ** 3


def garde(maintenant=None):
    """-> None si l'espace suffit, sinon la raison (et une alerte Telegram par jour au plus)."""
    libre = libre_go()
    if libre >= SEUIL_GO:
        return None
    raison = f"disque presque plein ({libre:.1f} Go libres, seuil {SEUIL_GO:.0f} Go)"
    m = maintenant or time.time()
    if m - (base.lire("disque:alerte") or 0) >= ALERTE_S:
        base.ecrire("disque:alerte", m)
        telegram.envoyer(f"💾 Disque du serveur presque plein : {libre:.1f} Go libres (seuil {SEUIL_GO:.0f} Go).\n"
                         "L'armée ne demande plus d'historique ancien à MT5 : c'est lui qui remplissait le disque "
                         "(bougies d'une minute de chaque marché archivé). Le trading et les positions ne changent "
                         "pas ; seuls les marchés sans historique sont ignorés.", important=True)
    return raison
