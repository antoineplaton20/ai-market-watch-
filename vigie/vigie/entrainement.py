"""Entraînement du détecteur sur un jeu de données YOLO, avec évaluation et sauvegarde à chaque époque."""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .detecteur import ConfigurationDetecteur, DetecteurDrones, construire_modele
from .donnees import JeuDeDonneesYolo, assembler_lot, lister_echantillons
from .evaluation import ExempleEvaluation, RapportEvaluation, evaluer


@dataclass(frozen=True)
class ParametresEntrainement:
    dossier_entrainement: str
    dossier_validation: str
    dossier_sortie: str
    images_entrainement_max: int | None = None
    images_validation_max: int | None = 500
    epoques: int = 5
    taille_lot: int = 4
    taux_apprentissage: float = 0.01
    graine: int = 0
    duree_max_minutes: float | None = None
    """Arrête proprement l'entraînement une fois cette durée dépassée, après sauvegarde."""
    fils_chargement: int = 2


def fixer_graine(graine: int) -> None:
    import torch

    random.seed(graine)
    np.random.seed(graine)
    torch.manual_seed(graine)


def evaluer_detecteur(detecteur: DetecteurDrones, dossier: Path, images_max: int | None, graine: int = 0,
                      taille_lot: int = 4) -> tuple[RapportEvaluation, float]:
    """Évalue un détecteur sur un dossier YOLO ; renvoie le rapport et le temps moyen par image (s)."""
    from .donnees import charger_image_rgb, lire_etiquettes

    echantillons = lister_echantillons(dossier, images_max, graine)
    exemples: list[ExempleEvaluation] = []
    duree = 0.0
    for debut in range(0, len(echantillons), taille_lot):
        lot = echantillons[debut:debut + taille_lot]
        images = [charger_image_rgb(e.chemin_image) for e in lot]
        t0 = time.perf_counter()
        sorties = detecteur.detecter_lot(images, seuil_score=0.01)
        duree += time.perf_counter() - t0
        for e, image, detections in zip(lot, images, sorties):
            h, w = image.shape[:2]
            exemples.append(
                ExempleEvaluation(
                    verites=lire_etiquettes(e.chemin_etiquettes, w, h),
                    predictions=[d.boite for d in detections],
                    scores=[d.score for d in detections],
                    largeur=w,
                    hauteur=h,
                )
            )
    return evaluer(exemples, 0.5), duree / max(len(echantillons), 1)


def entrainer(parametres: ParametresEntrainement, configuration: ConfigurationDetecteur | None = None) -> Path:
    import torch
    from torch.utils.data import DataLoader

    fixer_graine(parametres.graine)
    configuration = configuration or ConfigurationDetecteur()
    sortie = Path(parametres.dossier_sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    journal = sortie / "journal.jsonl"

    echantillons = lister_echantillons(
        Path(parametres.dossier_entrainement), parametres.images_entrainement_max, parametres.graine
    )
    chargeur = DataLoader(
        JeuDeDonneesYolo(echantillons, augmentation=True, graine=parametres.graine),
        batch_size=parametres.taille_lot,
        shuffle=True,
        num_workers=parametres.fils_chargement,
        collate_fn=assembler_lot,
    )

    modele = construire_modele(configuration, poids_coco=True)
    modele.train()
    params = [p for p in modele.parameters() if p.requires_grad]
    optimiseur = torch.optim.SGD(params, lr=parametres.taux_apprentissage, momentum=0.9, weight_decay=1e-4)
    iterations_totales = max(1, parametres.epoques * len(chargeur))
    iterations_echauffement = min(200, iterations_totales // 10)

    def facteur(iteration: int) -> float:
        if iteration < iterations_echauffement:
            return 0.1 + 0.9 * iteration / max(1, iterations_echauffement)
        progression = (iteration - iterations_echauffement) / max(1, iterations_totales - iterations_echauffement)
        return 0.5 * (1 + math.cos(math.pi * progression))

    planificateur = torch.optim.lr_scheduler.LambdaLR(optimiseur, facteur)
    debut = time.time()
    meilleure_ap = -1.0
    iteration = 0
    arret = False

    for epoque in range(1, parametres.epoques + 1):
        modele.train()
        pertes = []
        for images, cibles in chargeur:
            dictionnaire_pertes = modele(list(images), list(cibles))
            perte = sum(dictionnaire_pertes.values())
            optimiseur.zero_grad()
            perte.backward()
            torch.nn.utils.clip_grad_norm_(params, 10.0)
            optimiseur.step()
            planificateur.step()
            pertes.append(perte.item())
            iteration += 1
            if iteration % 50 == 0:
                with journal.open("a") as f:
                    f.write(json.dumps({"epoque": epoque, "iteration": iteration,
                                        "perte_moyenne_50": float(np.mean(pertes[-50:])),
                                        "taux": optimiseur.param_groups[0]["lr"],
                                        "minutes": (time.time() - debut) / 60}) + "\n")
            if parametres.duree_max_minutes and (time.time() - debut) / 60 > parametres.duree_max_minutes:
                arret = True
                break

        detecteur = DetecteurDrones(modele, configuration)
        rapport, secondes_par_image = evaluer_detecteur(
            detecteur, Path(parametres.dossier_validation), parametres.images_validation_max, parametres.graine
        )
        informations = {"epoque": epoque, "iterations": iteration, "evaluation": asdict(rapport),
                        "secondes_par_image": secondes_par_image, "parametres": asdict(parametres),
                        "images_entrainement": len(echantillons)}
        detecteur.sauvegarder(sortie / "dernier.pt", informations)
        if rapport.precision_moyenne > meilleure_ap:
            meilleure_ap = rapport.precision_moyenne
            detecteur.sauvegarder(sortie / "meilleur.pt", informations)
        with journal.open("a") as f:
            f.write(json.dumps({"epoque": epoque, "fin_epoque": True, "perte_moyenne": float(np.mean(pertes or [0])),
                                "ap50_validation": rapport.precision_moyenne,
                                "rappel_par_taille": rapport.rappel_par_taille,
                                "minutes": (time.time() - debut) / 60}) + "\n")
        modele.train()
        if arret:
            break

    return sortie / "meilleur.pt"
