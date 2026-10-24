"""Vidéos synthétiques pour tester la chaîne de traitement sans modèle entraîné ni données réelles.

Elles montrent un ciel en dégradé, du bruit de capteur et de petits objets sombres qui se déplacent,
dont la vérité terrain est connue. Elles servent aux tests automatiques, pas à mesurer la qualité
de détection en conditions réelles.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .types import Boite, Detection


@dataclass(frozen=True)
class ObjetSynthetique:
    depart: tuple[float, float]
    vitesse: tuple[float, float]
    """Pixels par image."""
    taille: float
    croissance: float = 0.0
    """Variation de taille par image, en pixels (positive pour un objet qui se rapproche)."""


def generer_images(objets: list[ObjetSynthetique], nombre_images: int, largeur: int = 640, hauteur: int = 480,
                   graine: int = 0) -> tuple[list[np.ndarray], list[list[Boite]]]:
    aleatoire = np.random.default_rng(graine)
    ciel = np.linspace(200, 140, hauteur, dtype=np.float32)[:, None, None] * np.array([0.8, 0.9, 1.0], np.float32)
    fond = np.broadcast_to(ciel, (hauteur, largeur, 3)).copy()
    images, verites = [], []
    for t in range(nombre_images):
        image = fond + aleatoire.normal(0, 3, fond.shape).astype(np.float32)
        boites: list[Boite] = []
        for o in objets:
            taille = max(2.0, o.taille + o.croissance * t)
            cx = o.depart[0] + o.vitesse[0] * t
            cy = o.depart[1] + o.vitesse[1] * t
            boite = (cx - taille / 2, cy - taille / 2, cx + taille / 2, cy + taille / 2)
            if boite[2] < 0 or boite[3] < 0 or boite[0] > largeur or boite[1] > hauteur:
                continue
            cv2.rectangle(image, (int(boite[0]), int(boite[1])), (int(boite[2]), int(boite[3])), (40, 40, 45), -1)
            boites.append(boite)
        images.append(np.clip(image, 0, 255).astype(np.uint8))
        verites.append(boites)
    return images, verites


def ecrire_video(images: list[np.ndarray], chemin: str | Path, images_par_seconde: float = 25.0) -> None:
    hauteur, largeur = images[0].shape[:2]
    ecrivain = cv2.VideoWriter(str(chemin), cv2.VideoWriter_fourcc(*"mp4v"), images_par_seconde, (largeur, hauteur))
    for image in images:
        ecrivain.write(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    ecrivain.release()


def detecteur_par_seuillage(image_rgb: np.ndarray, seuil: int = 90, aire_min: int = 4) -> list[Detection]:
    """Détecteur de référence pour les vidéos synthétiques : objets sombres sur ciel clair."""
    gris = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    _, masque = cv2.threshold(gris, seuil, 255, cv2.THRESH_BINARY_INV)
    nombre, _, stats, _ = cv2.connectedComponentsWithStats(masque)
    detections = []
    for i in range(1, nombre):
        x, y, w, h, a = stats[i]
        if a >= aire_min:
            detections.append(Detection(boite=(float(x), float(y), float(x + w), float(y + h)), score=0.9))
    return detections
