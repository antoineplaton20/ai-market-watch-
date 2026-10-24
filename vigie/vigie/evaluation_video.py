"""Évaluation de la chaîne complète (détection, suivi, alerte) sur des séquences vidéo annotées.

Indicateurs, du point de vue du guetteur :
- taux de suivi : part des images où le drone est visible et couvert par une piste confirmée ;
- délai d'alerte : temps entre la première apparition du drone et la première piste confirmée sur lui ;
- fausses alertes : part des images où une piste confirmée ne correspond à aucun drone ;
- changements d'identifiant : nombre de pistes différentes attribuées au même drone, moins une.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .evaluation import ExempleEvaluation, evaluer
from .geometrie import iou_matrice
from .pipeline import FonctionDetection, Vigie
from .suivi import ParametresSuivi
from .types import Boite


@dataclass
class BilanSequence:
    nom: str
    images: int
    images_avec_drone: int
    taux_suivi: float | None
    delai_alerte_s: float | None
    """None si le drone n'a jamais été suivi, ou s'il n'apparaît jamais."""
    alerte_jamais_donnee: bool
    part_images_fausse_alerte: float
    changements_identifiant: int
    precision_moyenne_detection: float
    millisecondes_par_image: float


def evaluer_sequence(nom: str, images: Iterable[np.ndarray], verites: list[list[Boite]], detecter: FonctionDetection,
                     images_par_seconde: float = 25.0, iou_suivi: float = 0.3, iou_fausse_alerte: float = 0.05,
                     parametres_suivi: ParametresSuivi | None = None) -> BilanSequence:
    vigie = Vigie(detecter, images_par_seconde, parametres_suivi)
    exemples: list[ExempleEvaluation] = []
    images_avec_drone = images_suivies = images_fausse_alerte = 0
    premiere_apparition: int | None = None
    premiere_alerte: int | None = None
    identifiants_sur_drone: set[int] = set()
    duree = 0.0
    nombre = 0

    for indice, (image, verite) in enumerate(zip(images, verites)):
        t0 = time.perf_counter()
        resultat = vigie.traiter(image)
        duree += time.perf_counter() - t0
        nombre += 1
        h, w = image.shape[:2]
        exemples.append(ExempleEvaluation(verite, [d.boite for d in resultat.detections],
                                          [d.score for d in resultat.detections], w, h))
        actives = [p for p in resultat.pistes if p.confirmee and p.images_sans_detection == 0]
        boites_actives = np.array([p.boite for p in actives], dtype=np.float64).reshape(-1, 4)
        recouvrement = iou_matrice(boites_actives, np.array(verite, dtype=np.float64).reshape(-1, 4))

        if verite:
            images_avec_drone += 1
            if premiere_apparition is None:
                premiere_apparition = indice
            if recouvrement.size and recouvrement.max() >= iou_suivi:
                images_suivies += 1
                if premiere_alerte is None:
                    premiere_alerte = indice
                for k, piste in enumerate(actives):
                    if recouvrement[k].max() >= iou_suivi:
                        identifiants_sur_drone.add(piste.identifiant)

        fausses = [k for k in range(len(actives)) if not verite or recouvrement[k].max() < iou_fausse_alerte]
        if fausses:
            images_fausse_alerte += 1

    delai = None
    if premiere_apparition is not None and premiere_alerte is not None:
        delai = (premiere_alerte - premiere_apparition) / images_par_seconde
    return BilanSequence(
        nom=nom,
        images=nombre,
        images_avec_drone=images_avec_drone,
        taux_suivi=images_suivies / images_avec_drone if images_avec_drone else None,
        delai_alerte_s=delai,
        alerte_jamais_donnee=images_avec_drone > 0 and premiere_alerte is None,
        part_images_fausse_alerte=images_fausse_alerte / max(nombre, 1),
        changements_identifiant=max(0, len(identifiants_sur_drone) - 1),
        precision_moyenne_detection=evaluer(exemples, 0.5).precision_moyenne,
        millisecondes_par_image=1000.0 * duree / max(nombre, 1),
    )
