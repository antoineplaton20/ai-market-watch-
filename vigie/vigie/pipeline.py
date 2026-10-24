"""Traitement d'une vidéo : détection, suivi, alerte, vidéo annotée et journal d'événements."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

from .suivi import ParametresSuivi, SuiviMultiObjets
from .types import Detection, ResultatImage

FonctionDetection = Callable[[np.ndarray], list[Detection]]


@dataclass(frozen=True)
class ParametresAlerte:
    temps_avant_contact_alerte: float = 10.0
    """Une piste confirmée dont le temps avant contact estimé passe sous ce seuil déclenche l'alerte « en approche »."""


class Vigie:
    """Assemble un détecteur et le suivi, et décide de l'alerte image par image."""

    def __init__(self, detecter: FonctionDetection, images_par_seconde: float = 25.0,
                 parametres_suivi: ParametresSuivi | None = None, parametres_alerte: ParametresAlerte | None = None):
        self.detecter = detecter
        self.images_par_seconde = images_par_seconde
        self.suivi = SuiviMultiObjets(parametres_suivi, images_par_seconde)
        self.parametres_alerte = parametres_alerte or ParametresAlerte()
        self._indice = 0

    def traiter(self, image_rgb: np.ndarray) -> ResultatImage:
        detections = self.detecter(image_rgb)
        pistes = self.suivi.mettre_a_jour(detections)
        confirmees = [p for p in pistes if p.confirmee and p.images_sans_detection == 0]
        resultat = ResultatImage(
            indice=self._indice,
            instant=self._indice / self.images_par_seconde,
            detections=detections,
            pistes=pistes,
            alerte=bool(confirmees),
        )
        self._indice += 1
        return resultat

    def en_approche(self, resultat: ResultatImage) -> list[int]:
        seuil = self.parametres_alerte.temps_avant_contact_alerte
        return [
            p.identifiant
            for p in resultat.pistes
            if p.confirmee and p.temps_avant_contact is not None and p.temps_avant_contact <= seuil
        ]


def lire_video(chemin: str | Path) -> tuple[Iterator[np.ndarray], float, tuple[int, int]]:
    capture = cv2.VideoCapture(str(chemin))
    if not capture.isOpened():
        raise ValueError(f"Vidéo illisible : {chemin}")
    ips = capture.get(cv2.CAP_PROP_FPS) or 25.0
    taille = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def images():
        try:
            while True:
                ok, image = capture.read()
                if not ok:
                    break
                yield cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        finally:
            capture.release()

    return images(), float(ips), taille


def annoter(image_rgb: np.ndarray, resultat: ResultatImage, en_approche: list[int]) -> np.ndarray:
    sortie = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    for piste in resultat.pistes:
        if not piste.confirmee or piste.images_sans_detection > 0:
            continue
        x1, y1, x2, y2 = (int(round(v)) for v in piste.boite)
        couleur = (0, 0, 255) if piste.identifiant in en_approche else (0, 200, 255)
        cv2.rectangle(sortie, (x1, y1), (x2, y2), couleur, 2)
        texte = f"#{piste.identifiant} {piste.score:.2f}"
        if piste.temps_avant_contact is not None:
            texte += f" contact ~{piste.temps_avant_contact:.0f}s"
        cv2.putText(sortie, texte, (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, couleur, 1, cv2.LINE_AA)
    if resultat.alerte:
        bandeau = "ALERTE DRONE" + (" - EN APPROCHE" if en_approche else "")
        cv2.putText(sortie, bandeau, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
    return sortie


def traiter_video(chemin_entree: str | Path, detecter: FonctionDetection, chemin_video_sortie: str | Path | None,
                  chemin_journal: str | Path | None, parametres_suivi: ParametresSuivi | None = None) -> dict:
    """Traite une vidéo complète ; écrit la vidéo annotée et un journal JSON Lines d'une ligne par image."""
    images, ips, (largeur, hauteur) = lire_video(chemin_entree)
    vigie = Vigie(detecter, ips, parametres_suivi)
    ecrivain = None
    if chemin_video_sortie:
        Path(chemin_video_sortie).parent.mkdir(parents=True, exist_ok=True)
        ecrivain = cv2.VideoWriter(str(chemin_video_sortie), cv2.VideoWriter_fourcc(*"mp4v"), ips, (largeur, hauteur))
    journal = open(chemin_journal, "w") if chemin_journal else None
    nombre_images = images_en_alerte = 0
    identifiants: set[int] = set()
    try:
        for image in images:
            resultat = vigie.traiter(image)
            approche = vigie.en_approche(resultat)
            nombre_images += 1
            images_en_alerte += int(resultat.alerte)
            identifiants.update(p.identifiant for p in resultat.pistes if p.confirmee)
            if ecrivain is not None:
                ecrivain.write(annoter(image, resultat, approche))
            if journal is not None:
                ligne = asdict(resultat)
                ligne["en_approche"] = approche
                journal.write(json.dumps(ligne) + "\n")
    finally:
        if ecrivain is not None:
            ecrivain.release()
        if journal is not None:
            journal.close()
    return {
        "images": nombre_images,
        "images_par_seconde_video": ips,
        "images_en_alerte": images_en_alerte,
        "pistes_confirmees": len(identifiants),
    }
