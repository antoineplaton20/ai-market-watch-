"""Télécharge des séquences vidéo annotées du jeu Anti-UAV (version Hugging Face DestinyLove/AntiUAV300).

Ces séquences ne servent qu'à l'évaluation de la chaîne complète (détection et suivi) sur de la
vidéo réelle. Vérifier les conditions d'utilisation du jeu d'origine avant tout autre usage :
https://github.com/ZhaoJ9014/Anti-UAV

Exemple :
    python scripts/telecharger_sequences_antiuav.py --destination data/antiuav --sequences 10 --images 300
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

DEPOT = "https://huggingface.co/datasets/DestinyLove/AntiUAV300/resolve/main/yolo_rgb"


def telecharger(url: str, chemin: Path, essais: int = 4) -> None:
    if chemin.exists() and chemin.stat().st_size > 0:
        return
    for essai in range(essais):
        try:
            with urllib.request.urlopen(url, timeout=60) as reponse:
                chemin.write_bytes(reponse.read())
            return
        except Exception:
            if essai == essais - 1:
                raise
            time.sleep(2 ** (essai + 1))


def main() -> None:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--destination", required=True, type=Path)
    analyseur.add_argument("--sequences", type=int, default=10)
    analyseur.add_argument("--images", type=int, default=300, help="Images consécutives par séquence.")
    analyseur.add_argument("--pas", type=int, default=10, help="Prend une séquence de test sur `pas`.")
    args = analyseur.parse_args()

    args.destination.mkdir(parents=True, exist_ok=True)
    index = args.destination / "all_labels.txt"
    telecharger(f"{DEPOT}/all_labels.txt", index)

    sequences: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for ligne in index.read_text().splitlines():
        fichier, _, etiquette = ligne.partition("|||")
        if not fichier.startswith("test_"):
            continue
        dossier, nom = fichier.split("/")
        sequence, numero = nom.rsplit("_", 1)
        sequences[sequence].append((int(numero.split(".")[0]), dossier, etiquette))

    choisies = sorted(sequences)[:: args.pas][: args.sequences]
    taches = []
    manifeste = {}
    for sequence in choisies:
        images = sorted(sequences[sequence])[: args.images]
        dossier_sequence = args.destination / sequence
        (dossier_sequence / "images").mkdir(parents=True, exist_ok=True)
        (dossier_sequence / "labels").mkdir(parents=True, exist_ok=True)
        for numero, dossier, etiquette in images:
            nom = f"{sequence}_{numero:04d}"
            (dossier_sequence / "labels" / f"{nom}.txt").write_text(etiquette.replace("|", "\n").strip() + "\n"
                                                                     if etiquette.strip() else "")
            taches.append((f"{DEPOT}/images/{dossier}/{nom}.jpg", dossier_sequence / "images" / f"{nom}.jpg"))
        manifeste[sequence] = len(images)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executeur:
        list(executeur.map(lambda t: telecharger(*t), taches))
    (args.destination / "manifeste.json").write_text(json.dumps(manifeste, indent=1))
    print(json.dumps(manifeste, indent=1))


if __name__ == "__main__":
    main()
