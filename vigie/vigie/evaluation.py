"""Mesure des performances de détection : précision moyenne (AP), rappel par taille, seuil optimal.

Les définitions suivent l'usage courant en détection d'objets (protocole PASCAL VOC, interpolation
sur tous les points) : une détection est juste si elle recouvre une vérité terrain non encore
attribuée avec un IoU au moins égal au seuil ; les détections sont examinées par score décroissant.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .geometrie import categorie_taille, iou_matrice
from .types import Boite


@dataclass
class ExempleEvaluation:
    """Prédictions et vérité terrain pour une image."""

    verites: list[Boite]
    predictions: list[Boite]
    scores: list[float]
    largeur: int = 640
    hauteur: int = 640


@dataclass
class RapportEvaluation:
    nombre_images: int
    nombre_verites: int
    seuil_iou: float
    precision_moyenne: float
    """AP : aire sous la courbe précision-rappel."""
    rappel_maximal: float
    meilleur_seuil_score: float
    precision_au_meilleur_seuil: float
    rappel_au_meilleur_seuil: float
    f1_au_meilleur_seuil: float
    rappel_par_taille: dict[str, float] = field(default_factory=dict)
    verites_par_taille: dict[str, int] = field(default_factory=dict)
    fausses_alarmes_par_image_vide: float | None = None
    """Détections au meilleur seuil sur les images sans drone, en moyenne par image."""


def _precision_moyenne(rappels: np.ndarray, precisions: np.ndarray) -> float:
    r = np.concatenate(([0.0], rappels, [1.0]))
    p = np.concatenate(([0.0], precisions, [0.0]))
    for i in range(len(p) - 2, -1, -1):
        p[i] = max(p[i], p[i + 1])
    indices = np.where(r[1:] != r[:-1])[0]
    return float(np.sum((r[indices + 1] - r[indices]) * p[indices + 1]))


def evaluer(exemples: list[ExempleEvaluation], seuil_iou: float = 0.5) -> RapportEvaluation:
    toutes: list[tuple[float, int, int]] = []
    """(score, indice image, indice prédiction)"""
    for i, ex in enumerate(exemples):
        for k, s in enumerate(ex.scores):
            toutes.append((float(s), i, k))
    toutes.sort(key=lambda t: -t[0])

    nombre_verites = sum(len(ex.verites) for ex in exemples)
    recouvrements = [
        iou_matrice(np.array(ex.predictions).reshape(-1, 4), np.array(ex.verites).reshape(-1, 4)) for ex in exemples
    ]
    attribuees = [np.zeros(len(ex.verites), dtype=bool) for ex in exemples]
    vrai = np.zeros(len(toutes))
    score_detection_verite: dict[tuple[int, int], float] = {}

    for rang, (score, i, k) in enumerate(toutes):
        if len(exemples[i].verites) == 0:
            continue
        ligne = recouvrements[i][k].copy()
        ligne[attribuees[i]] = -1.0
        j = int(np.argmax(ligne))
        if ligne[j] >= seuil_iou:
            attribuees[i][j] = True
            vrai[rang] = 1.0
            score_detection_verite[(i, j)] = score

    vp_cumules = np.cumsum(vrai)
    fp_cumules = np.cumsum(1.0 - vrai)
    rappels = vp_cumules / max(nombre_verites, 1)
    precisions = vp_cumules / np.maximum(vp_cumules + fp_cumules, 1e-9)
    ap = _precision_moyenne(rappels, precisions) if len(toutes) else 0.0

    if len(toutes):
        f1 = 2 * precisions * rappels / np.maximum(precisions + rappels, 1e-9)
        meilleur = int(np.argmax(f1))
        seuil = toutes[meilleur][0]
        p_best, r_best, f1_best = float(precisions[meilleur]), float(rappels[meilleur]), float(f1[meilleur])
    else:
        seuil, p_best, r_best, f1_best = 1.0, 0.0, 0.0, 0.0

    trouvees_par_taille: dict[str, int] = defaultdict(int)
    verites_par_taille: dict[str, int] = defaultdict(int)
    for i, ex in enumerate(exemples):
        aire_image = float(ex.largeur * ex.hauteur)
        for j, boite in enumerate(ex.verites):
            categorie = categorie_taille(boite, aire_image)
            verites_par_taille[categorie] += 1
            if score_detection_verite.get((i, j), -1.0) >= seuil:
                trouvees_par_taille[categorie] += 1
    rappel_par_taille = {
        c: trouvees_par_taille[c] / n for c, n in sorted(verites_par_taille.items()) if n > 0
    }

    images_vides = [ex for ex in exemples if len(ex.verites) == 0]
    fausses_alarmes = (
        sum(sum(1 for s in ex.scores if s >= seuil) for ex in images_vides) / len(images_vides)
        if images_vides
        else None
    )

    return RapportEvaluation(
        nombre_images=len(exemples),
        nombre_verites=nombre_verites,
        seuil_iou=seuil_iou,
        precision_moyenne=ap,
        rappel_maximal=float(rappels[-1]) if len(toutes) else 0.0,
        meilleur_seuil_score=float(seuil),
        precision_au_meilleur_seuil=p_best,
        rappel_au_meilleur_seuil=r_best,
        f1_au_meilleur_seuil=f1_best,
        rappel_par_taille=rappel_par_taille,
        verites_par_taille=dict(verites_par_taille),
        fausses_alarmes_par_image_vide=fausses_alarmes,
    )
