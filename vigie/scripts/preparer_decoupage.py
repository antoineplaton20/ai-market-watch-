"""Crée des sous-ensembles disjoints d'entraînement et de validation par liens symboliques.

Le jeu de test d'origine n'est jamais utilisé pour l'entraînement ni pour le choix du modèle :
il sert uniquement à la mesure finale des performances.

Exemple :
    python scripts/preparer_decoupage.py --source data/seraphim/train --destination data/decoupe \
        --entrainement 7000 --validation 500 --graine 0
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")


def main() -> None:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--source", required=True, type=Path)
    analyseur.add_argument("--destination", required=True, type=Path)
    analyseur.add_argument("--entrainement", type=int, required=True)
    analyseur.add_argument("--validation", type=int, required=True)
    analyseur.add_argument("--graine", type=int, default=0)
    args = analyseur.parse_args()

    images = sorted(p for p in (args.source / "images").iterdir() if p.suffix.lower() in EXTENSIONS)
    aleatoire = random.Random(args.graine)
    aleatoire.shuffle(images)
    if args.entrainement + args.validation > len(images):
        raise SystemExit(f"Seulement {len(images)} images disponibles.")
    parts = {
        "entrainement": images[: args.entrainement],
        "validation": images[args.entrainement : args.entrainement + args.validation],
    }
    for nom, liste in parts.items():
        for sous in ("images", "labels"):
            (args.destination / nom / sous).mkdir(parents=True, exist_ok=True)
        for image in liste:
            lien_image = args.destination / nom / "images" / image.name
            if not lien_image.exists():
                lien_image.symlink_to(image.resolve())
            etiquette = args.source / "labels" / (image.stem + ".txt")
            if etiquette.exists():
                lien_etiquette = args.destination / nom / "labels" / etiquette.name
                if not lien_etiquette.exists():
                    lien_etiquette.symlink_to(etiquette.resolve())
    (args.destination / "decoupage.json").write_text(
        json.dumps({k: [p.name for p in v] for k, v in parts.items()} | {"graine": args.graine}, indent=1)
    )
    print({k: len(v) for k, v in parts.items()})


if __name__ == "__main__":
    main()
