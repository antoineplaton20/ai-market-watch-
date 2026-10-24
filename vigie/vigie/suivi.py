"""Suivi multi-objets : un filtre de Kalman par piste et une association optimale image par image.

Chaque piste estime la position, la taille et leur vitesse de variation. À chaque image, les
détections sont associées aux pistes existantes par l'algorithme hongrois, en privilégiant le
recouvrement des boîtes puis, pour les petits objets rapides qui ne se recouvrent plus d'une image
à l'autre, la distance entre centres.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from .geometrie import depuis_cxcywh, iou_matrice, vers_cxcywh
from .types import Detection, EtatPiste

COUT_IMPOSSIBLE = 1e6
TAILLE_MIN_PX = 4.0
FENETRE_TAILLES = 15
"""Nombre de mesures de taille récentes utilisées pour estimer le rapprochement."""
TAILLES_MIN_REGRESSION = 8


@dataclass(frozen=True)
class ParametresSuivi:
    images_pour_confirmer: int = 3
    """Détections successives nécessaires avant de déclarer une piste confirmée."""
    images_sans_detection_max: int = 15
    """Images consécutives sans détection après lesquelles une piste est supprimée."""
    iou_min: float = 0.1
    """Recouvrement minimal pour associer par recouvrement."""
    distance_max_relative: float = 2.5
    """Distance maximale entre centres, en multiples de la taille de la piste, pour associer sans recouvrement."""
    score_min_creation: float = 0.4
    """Score de détection minimal pour créer une nouvelle piste."""


class FiltreKalman:
    """Filtre de Kalman à vitesse constante sur l'état [cx, cy, w, h, vcx, vcy, vw, vh]."""

    def __init__(self, mesure: np.ndarray):
        self.x = np.zeros(8)
        self.x[:4] = mesure
        hauteur = max(mesure[3], TAILLE_MIN_PX)
        ecarts = np.array([2, 2, 2, 2, 10, 10, 10, 10], dtype=np.float64) * hauteur / 20.0
        self.P = np.diag(ecarts**2)
        self.F = np.eye(8)
        self.F[:4, 4:] = np.eye(4)
        self.H = np.eye(4, 8)

    def _bruit_processus(self) -> np.ndarray:
        h = max(self.x[3], TAILLE_MIN_PX)
        pos, vit = h / 20.0, h / 160.0
        return np.diag([pos, pos, pos, pos, vit, vit, vit, vit]) ** 2

    def _bruit_mesure(self) -> np.ndarray:
        h = max(self.x[3], TAILLE_MIN_PX)
        return np.diag([h / 20.0] * 4) ** 2

    def predire(self) -> np.ndarray:
        self.x = self.F @ self.x
        self.x[2:4] = np.maximum(self.x[2:4], 1.0)
        self.P = self.F @ self.P @ self.F.T + self._bruit_processus()
        return self.x[:4].copy()

    def corriger(self, mesure: np.ndarray) -> None:
        S = self.H @ self.P @ self.H.T + self._bruit_mesure()
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ (mesure - self.H @ self.x)
        self.P = (np.eye(8) - K @ self.H) @ self.P


class _Piste:
    def __init__(self, identifiant: int, detection: Detection):
        self.identifiant = identifiant
        self.kalman = FiltreKalman(vers_cxcywh(detection.boite))
        self.score = detection.score
        self.age = 1
        self.detections_consecutives = 1
        self.images_sans_detection = 0
        self.confirmee = False
        self.historique_tailles: list[tuple[int, float]] = []
        self.enregistrer_taille(detection)

    def enregistrer_taille(self, detection: Detection) -> None:
        x1, y1, x2, y2 = detection.boite
        self.historique_tailles.append((self.age, float(np.sqrt(max(x2 - x1, 0.0) * max(y2 - y1, 0.0)))))
        del self.historique_tailles[:-FENETRE_TAILLES]

    def boite(self):
        cx, cy, w, h = self.kalman.x[:4]
        return depuis_cxcywh(cx, cy, w, h)

    def temps_avant_contact(self, images_par_seconde: float) -> float | None:
        """Temps avant contact estimé par la croissance apparente de l'objet (indice de rapprochement).

        Pour un objet qui se rapproche à vitesse constante, sa taille apparente s croît et
        s / (ds/dt) approche le temps restant avant le contact. On prend s = racine de l'aire.
        """
        # La croissance ds/dt est estimée par régression linéaire sur les tailles mesurées récentes. Elle
        # n'est retenue que si elle dépasse deux fois son erreur type : sinon le bruit des boîtes suffirait
        # à faire croire à un rapprochement.
        if len(self.historique_tailles) < TAILLES_MIN_REGRESSION or images_par_seconde <= 0:
            return None
        t = np.array([a for a, _ in self.historique_tailles], dtype=np.float64)
        s = np.array([v for _, v in self.historique_tailles], dtype=np.float64)
        t_centre = t - t.mean()
        denominateur = float(np.sum(t_centre**2))
        if denominateur <= 0:
            return None
        pente = float(np.sum(t_centre * (s - s.mean())) / denominateur)
        residus = s - (s.mean() + pente * t_centre)
        erreur_type = float(np.sqrt(np.sum(residus**2) / max(len(s) - 2, 1) / denominateur))
        if pente <= 1e-3 or pente <= 2.0 * erreur_type:
            return None
        taille_actuelle = s.mean() + pente * (t[-1] - t.mean())
        return float(taille_actuelle / pente) / images_par_seconde

    def etat(self, images_par_seconde: float) -> EtatPiste:
        return EtatPiste(
            identifiant=self.identifiant,
            boite=tuple(float(v) for v in self.boite()),
            vitesse=(float(self.kalman.x[4]), float(self.kalman.x[5])),
            score=float(self.score),
            age=self.age,
            confirmee=self.confirmee,
            images_sans_detection=self.images_sans_detection,
            temps_avant_contact=self.temps_avant_contact(images_par_seconde) if self.confirmee else None,
        )


class SuiviMultiObjets:
    """Maintient des pistes stables d'une image à l'autre à partir de détections indépendantes."""

    def __init__(self, parametres: ParametresSuivi | None = None, images_par_seconde: float = 25.0):
        self.parametres = parametres or ParametresSuivi()
        self.images_par_seconde = images_par_seconde
        self._pistes: list[_Piste] = []
        self._prochain_identifiant = 1

    def _matrice_cout(self, boites_predites: np.ndarray, boites_detectees: np.ndarray) -> np.ndarray:
        p = self.parametres
        recouvrement = iou_matrice(boites_predites, boites_detectees)
        cout = np.full(recouvrement.shape, COUT_IMPOSSIBLE)
        cout[recouvrement >= p.iou_min] = 1.0 - recouvrement[recouvrement >= p.iou_min]
        if cout.size == 0:
            return cout
        centres_p = (boites_predites[:, :2] + boites_predites[:, 2:]) / 2.0
        centres_d = (boites_detectees[:, :2] + boites_detectees[:, 2:]) / 2.0
        tailles_p = np.maximum(
            np.maximum(boites_predites[:, 2] - boites_predites[:, 0], boites_predites[:, 3] - boites_predites[:, 1]),
            TAILLE_MIN_PX,
        )
        distances = np.linalg.norm(centres_p[:, None, :] - centres_d[None, :, :], axis=2)
        distances_relatives = distances / tailles_p[:, None]
        par_distance = (cout >= COUT_IMPOSSIBLE) & (distances_relatives <= p.distance_max_relative)
        cout[par_distance] = 1.0 + distances_relatives[par_distance] / p.distance_max_relative
        return cout

    def mettre_a_jour(self, detections: list[Detection]) -> list[EtatPiste]:
        """Intègre les détections d'une nouvelle image et renvoie l'état de toutes les pistes actives."""
        p = self.parametres
        for piste in self._pistes:
            piste.kalman.predire()
            piste.age += 1

        boites_predites = np.array([piste.boite() for piste in self._pistes], dtype=np.float64).reshape(-1, 4)
        boites_detectees = np.array([d.boite for d in detections], dtype=np.float64).reshape(-1, 4)
        cout = self._matrice_cout(boites_predites, boites_detectees)

        pistes_associees: set[int] = set()
        detections_associees: set[int] = set()
        if cout.size:
            lignes, colonnes = linear_sum_assignment(cout)
            for i, j in zip(lignes, colonnes):
                if cout[i, j] >= COUT_IMPOSSIBLE:
                    continue
                piste, detection = self._pistes[i], detections[j]
                piste.kalman.corriger(vers_cxcywh(detection.boite))
                piste.enregistrer_taille(detection)
                piste.score = detection.score
                piste.detections_consecutives += 1
                piste.images_sans_detection = 0
                if piste.detections_consecutives >= p.images_pour_confirmer:
                    piste.confirmee = True
                pistes_associees.add(i)
                detections_associees.add(j)

        for i, piste in enumerate(self._pistes):
            if i not in pistes_associees:
                piste.images_sans_detection += 1
                piste.detections_consecutives = 0

        self._pistes = [
            piste
            for piste in self._pistes
            if piste.images_sans_detection <= p.images_sans_detection_max
            and (piste.confirmee or piste.images_sans_detection == 0)
        ]

        for j, detection in enumerate(detections):
            if j not in detections_associees and detection.score >= p.score_min_creation:
                self._pistes.append(_Piste(self._prochain_identifiant, detection))
                self._prochain_identifiant += 1

        return [piste.etat(self.images_par_seconde) for piste in self._pistes]

    def reinitialiser(self) -> None:
        self._pistes = []
        self._prochain_identifiant = 1
