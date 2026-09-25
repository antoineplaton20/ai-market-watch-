"""File de commandes de l'application iPhone vers le bot principal (sans dépendance : importé par main.py).

L'API dépose une commande de la liste blanche dans commandes_app.txt ; main.py la lit à chaque tour et
l'applique exactement comme si elle venait de Telegram (même code, même confirmation sur Telegram)."""
from __future__ import annotations

import os
from pathlib import Path

FICHIER = "commandes_app.txt"
ACTIONS = {
    "principal_stop": "/stop", "principal_reprise": "/reprise", "principal_vendre_tout": "/vendre_tout",
    "principal_rearmer": "/rearmer",
}


def deposer(commande, dossier="."):
    if commande not in ACTIONS.values():
        raise ValueError(commande)
    with open(Path(dossier) / FICHIER, "a", encoding="utf-8") as f:
        f.write(commande + "\n")


def lire(dossier="."):
    """Commandes en attente (liste blanche uniquement, sans doublon), puis la file est vidée."""
    chemin = Path(dossier) / FICHIER
    if not chemin.exists():
        return []
    tmp = chemin.with_name(FICHIER + ".en_cours")
    try:
        os.replace(chemin, tmp)
        lignes = tmp.read_text(encoding="utf-8").split("\n")
        tmp.unlink()
    except OSError:
        return []
    autorisees = set(ACTIONS.values())
    return [c for c in dict.fromkeys(x.strip() for x in lignes) if c in autorisees]
