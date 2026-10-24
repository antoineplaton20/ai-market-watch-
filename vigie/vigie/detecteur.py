"""Détecteur de drones image par image, fondé sur un Faster R-CNN MobileNetV3-FPN (torchvision).

Le réseau est léger pour tourner sur processeur ou sur un calculateur embarqué, et ses ancres sont
réduites pour mieux voir les petits objets, cas habituel d'un drone vu de loin.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import __version__
from .types import Detection

CLASSES = ("fond", "drone")


@dataclass(frozen=True)
class ConfigurationDetecteur:
    taille_entree: int = 640
    """Côté de l'image vue par le réseau, en pixels."""
    seuil_score: float = 0.3
    detections_max: int = 50
    tailles_ancres: tuple[int, ...] = (16, 32, 64, 128, 256)


def construire_modele(configuration: ConfigurationDetecteur, poids_coco: bool = False):
    """Construit le réseau. Avec `poids_coco`, part des poids publiés par torchvision (entraînés sur COCO)."""
    from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_fpn
    from torchvision.models.detection.anchor_utils import AnchorGenerator
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

    kwargs = dict(
        min_size=configuration.taille_entree,
        max_size=configuration.taille_entree,
        box_score_thresh=0.01,
        box_detections_per_img=configuration.detections_max,
    )
    if poids_coco:
        from torchvision.models.detection import FasterRCNN_MobileNet_V3_Large_FPN_Weights

        modele = fasterrcnn_mobilenet_v3_large_fpn(weights=FasterRCNN_MobileNet_V3_Large_FPN_Weights.COCO_V1, **kwargs)
    else:
        modele = fasterrcnn_mobilenet_v3_large_fpn(weights=None, weights_backbone=None, num_classes=91, **kwargs)

    ratios = ((0.5, 1.0, 2.0),) * 3
    modele.rpn.anchor_generator = AnchorGenerator(sizes=(configuration.tailles_ancres,) * 3, aspect_ratios=ratios)
    entree = modele.roi_heads.box_predictor.cls_score.in_features
    modele.roi_heads.box_predictor = FastRCNNPredictor(entree, len(CLASSES))
    return modele


def decouper_tuiles(largeur: int, hauteur: int, grille: int, recouvrement: float = 0.2) -> list[tuple[int, int, int, int]]:
    """Découpe l'image en grille × grille tuiles qui se recouvrent ; renvoie (x1, y1, x2, y2) en pixels."""
    if grille <= 1:
        return [(0, 0, largeur, hauteur)]
    tuiles = []
    l_tuile = int(np.ceil(largeur / (grille - (grille - 1) * recouvrement)))
    h_tuile = int(np.ceil(hauteur / (grille - (grille - 1) * recouvrement)))
    for i in range(grille):
        for j in range(grille):
            x1 = int(round(j * (largeur - l_tuile) / (grille - 1)))
            y1 = int(round(i * (hauteur - h_tuile) / (grille - 1)))
            tuiles.append((x1, y1, min(largeur, x1 + l_tuile), min(hauteur, y1 + h_tuile)))
    return tuiles


def fusionner(detections: list[Detection], seuil_iou: float = 0.5) -> list[Detection]:
    """Supprime les doublons venant de tuiles voisines par suppression des non-maxima."""
    if not detections:
        return []
    import torch
    from torchvision.ops import nms

    boites = torch.tensor([d.boite for d in detections], dtype=torch.float32)
    scores = torch.tensor([d.score for d in detections], dtype=torch.float32)
    gardees = nms(boites, scores, seuil_iou).tolist()
    return [detections[i] for i in gardees]


class DetecteurDrones:
    """Enveloppe d'inférence : image RGB (numpy) en entrée, liste de détections en sortie."""

    def __init__(self, modele, configuration: ConfigurationDetecteur, appareil: str = "cpu"):
        import torch

        self.configuration = configuration
        self.appareil = torch.device(appareil)
        self.modele = modele.to(self.appareil).eval()

    @classmethod
    def charger(cls, chemin: str | Path, appareil: str = "cpu", seuil_score: float | None = None) -> "DetecteurDrones":
        import torch

        sauvegarde = torch.load(str(chemin), map_location="cpu", weights_only=False)
        valeurs = dict(sauvegarde["configuration"])
        valeurs["tailles_ancres"] = tuple(valeurs["tailles_ancres"])
        if seuil_score is not None:
            valeurs["seuil_score"] = seuil_score
        configuration = ConfigurationDetecteur(**valeurs)
        modele = construire_modele(configuration, poids_coco=False)
        modele.load_state_dict(sauvegarde["poids"])
        return cls(modele, configuration, appareil)

    def sauvegarder(self, chemin: str | Path, informations: dict | None = None) -> None:
        import torch

        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "version_vigie": __version__,
                "classes": CLASSES,
                "configuration": asdict(self.configuration),
                "poids": self.modele.state_dict(),
                "informations": informations or {},
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            str(chemin),
        )

    def detecter(self, image_rgb: np.ndarray, seuil_score: float | None = None) -> list[Detection]:
        return self.detecter_lot([image_rgb], seuil_score)[0]

    def detecter_par_tuiles(self, image_rgb: np.ndarray, grille: int = 2, seuil_score: float | None = None
                            ) -> list[Detection]:
        """Analyse l'image entière puis chaque tuile à meilleure résolution, et fusionne les résultats.

        Utile pour les images haute définition où un drone lointain ne fait que quelques pixels une fois
        l'image réduite à la taille d'entrée du réseau. Le temps de calcul est multiplié par grille² + 1.
        """
        hauteur, largeur = image_rgb.shape[:2]
        tuiles = decouper_tuiles(largeur, hauteur, grille)
        morceaux = [image_rgb] + [image_rgb[y1:y2, x1:x2] for (x1, y1, x2, y2) in tuiles]
        sorties = self.detecter_lot(morceaux, seuil_score)
        toutes = list(sorties[0])
        for (x1, y1, _, _), detections in zip(tuiles, sorties[1:]):
            for d in detections:
                bx1, by1, bx2, by2 = d.boite
                toutes.append(Detection((bx1 + x1, by1 + y1, bx2 + x1, by2 + y1), d.score, d.classe))
        return fusionner(toutes)

    def detecter_lot(self, images_rgb: list[np.ndarray], seuil_score: float | None = None) -> list[list[Detection]]:
        import torch

        seuil = self.configuration.seuil_score if seuil_score is None else seuil_score
        tenseurs = [
            torch.from_numpy(np.ascontiguousarray(im)).permute(2, 0, 1).float().div(255.0).to(self.appareil)
            for im in images_rgb
        ]
        with torch.inference_mode():
            sorties = self.modele(tenseurs)
        resultats = []
        for sortie in sorties:
            boites = sortie["boxes"].cpu().numpy()
            scores = sortie["scores"].cpu().numpy()
            resultats.append(
                [
                    Detection(boite=tuple(float(v) for v in b), score=float(s))
                    for b, s in zip(boites, scores)
                    if s >= seuil
                ]
            )
        return resultats
