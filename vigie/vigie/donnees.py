"""Lecture des jeux de données au format YOLO (images/*.jpg et labels/*.txt).

Chaque ligne d'un fichier d'étiquettes vaut « classe cx cy w h », coordonnées normalisées entre 0 et 1.
Une image sans fichier d'étiquettes, ou avec un fichier vide, est une image sans drone.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .types import Boite

EXTENSIONS_IMAGES = (".jpg", ".jpeg", ".png", ".bmp")


@dataclass(frozen=True)
class EchantillonAnnote:
    chemin_image: Path
    chemin_etiquettes: Path | None


def lire_etiquettes(chemin: Path | None, largeur: int, hauteur: int) -> list[Boite]:
    """Convertit un fichier d'étiquettes YOLO en boîtes en pixels ; ignore les lignes mal formées."""
    if chemin is None or not chemin.exists():
        return []
    boites: list[Boite] = []
    for ligne in chemin.read_text().splitlines():
        champs = ligne.split()
        if len(champs) < 5:
            continue
        try:
            cx, cy, w, h = (float(v) for v in champs[1:5])
        except ValueError:
            continue
        if w <= 0 or h <= 0:
            continue
        x1 = max(0.0, (cx - w / 2) * largeur)
        y1 = max(0.0, (cy - h / 2) * hauteur)
        x2 = min(float(largeur), (cx + w / 2) * largeur)
        y2 = min(float(hauteur), (cy + h / 2) * hauteur)
        if x2 - x1 >= 1 and y2 - y1 >= 1:
            boites.append((x1, y1, x2, y2))
    return boites


def lister_echantillons(racine: Path, nombre_max: int | None = None, graine: int = 0) -> list[EchantillonAnnote]:
    """Liste les images d'un dossier « racine/images » et leurs étiquettes dans « racine/labels »."""
    dossier_images = racine / "images"
    dossier_etiquettes = racine / "labels"
    images = sorted(p for p in dossier_images.rglob("*") if p.suffix.lower() in EXTENSIONS_IMAGES)
    echantillons = []
    for image in images:
        relatif = image.relative_to(dossier_images).with_suffix(".txt")
        etiquettes = dossier_etiquettes / relatif
        echantillons.append(EchantillonAnnote(image, etiquettes if etiquettes.exists() else None))
    if nombre_max is not None and len(echantillons) > nombre_max:
        aleatoire = random.Random(graine)
        echantillons = sorted(aleatoire.sample(echantillons, nombre_max), key=lambda e: e.chemin_image)
    return echantillons


def charger_image_rgb(chemin: Path) -> np.ndarray:
    image = cv2.imread(str(chemin), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Image illisible : {chemin}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


class JeuDeDonneesYolo:
    """Jeu de données compatible avec torch.utils.data.DataLoader pour un détecteur torchvision."""

    def __init__(self, echantillons: list[EchantillonAnnote], augmentation: bool = False, graine: int = 0):
        self.echantillons = echantillons
        self.augmentation = augmentation
        self._aleatoire = random.Random(graine)

    def __len__(self) -> int:
        return len(self.echantillons)

    def __getitem__(self, indice: int):
        import torch

        echantillon = self.echantillons[indice]
        image = charger_image_rgb(echantillon.chemin_image)
        hauteur, largeur = image.shape[:2]
        boites = lire_etiquettes(echantillon.chemin_etiquettes, largeur, hauteur)

        if self.augmentation and self._aleatoire.random() < 0.5:
            image = image[:, ::-1, :].copy()
            boites = [(largeur - x2, y1, largeur - x1, y2) for (x1, y1, x2, y2) in boites]

        tenseur = torch.from_numpy(image).permute(2, 0, 1).float() / 255.0
        cible = {
            "boxes": torch.tensor(boites, dtype=torch.float32).reshape(-1, 4),
            "labels": torch.ones(len(boites), dtype=torch.int64),
        }
        return tenseur, cible


def assembler_lot(lot):
    return tuple(zip(*lot))
