"""Calculs géométriques sur les boîtes englobantes."""

from __future__ import annotations

import numpy as np

from .types import Boite


def aire(boite: Boite) -> float:
    x1, y1, x2, y2 = boite
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def centre(boite: Boite) -> tuple[float, float]:
    x1, y1, x2, y2 = boite
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def iou(a: Boite, b: Boite) -> float:
    """Recouvrement entre deux boîtes : aire de l'intersection divisée par aire de l'union."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = aire(a) + aire(b) - inter
    return inter / union if union > 0 else 0.0


def iou_matrice(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Recouvrement de chaque boîte de `a` (N×4) avec chaque boîte de `b` (M×4), en matrice N×M."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float64)
    a = np.asarray(a, dtype=np.float64)[:, None, :]
    b = np.asarray(b, dtype=np.float64)[None, :, :]
    ix1 = np.maximum(a[..., 0], b[..., 0])
    iy1 = np.maximum(a[..., 1], b[..., 1])
    ix2 = np.minimum(a[..., 2], b[..., 2])
    iy2 = np.minimum(a[..., 3], b[..., 3])
    inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
    aire_a = np.clip(a[..., 2] - a[..., 0], 0, None) * np.clip(a[..., 3] - a[..., 1], 0, None)
    aire_b = np.clip(b[..., 2] - b[..., 0], 0, None) * np.clip(b[..., 3] - b[..., 1], 0, None)
    union = aire_a + aire_b - inter
    return np.where(union > 0, inter / np.where(union > 0, union, 1.0), 0.0)


def vers_cxcywh(boite: Boite) -> np.ndarray:
    x1, y1, x2, y2 = boite
    return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0, x2 - x1, y2 - y1], dtype=np.float64)


def depuis_cxcywh(cx: float, cy: float, w: float, h: float) -> Boite:
    return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def categorie_taille(boite: Boite, aire_image: float) -> str:
    """Catégorie de taille relative à l'image, selon les seuils du jeu de données Seraphim.

    tres_petit : < 0,0625 % de l'image (moins de 16×16 px sur une image 640×640)
    petit      : 0,0625 % à 0,25 %
    moyen      : 0,25 % à 2,25 %
    grand      : 2,25 % et plus
    """
    ratio = aire(boite) / aire_image if aire_image > 0 else 0.0
    if ratio < 0.000625:
        return "tres_petit"
    if ratio < 0.0025:
        return "petit"
    if ratio < 0.0225:
        return "moyen"
    return "grand"
