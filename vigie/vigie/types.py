"""Types de données partagés par les modules de Vigie."""

from __future__ import annotations

from dataclasses import dataclass, field

Boite = tuple[float, float, float, float]
"""Boîte englobante en pixels : (x1, y1, x2, y2), coin haut-gauche puis coin bas-droit."""


@dataclass(frozen=True)
class Detection:
    """Un objet détecté dans une image."""

    boite: Boite
    score: float
    classe: str = "drone"


@dataclass(frozen=True)
class EtatPiste:
    """Ce que le suivi sait d'un objet à une image donnée."""

    identifiant: int
    boite: Boite
    vitesse: tuple[float, float]
    """Déplacement du centre de la boîte, en pixels par image."""
    score: float
    age: int
    """Nombre d'images depuis la création de la piste."""
    confirmee: bool
    images_sans_detection: int
    temps_avant_contact: float | None = None
    """Temps estimé avant que l'objet n'atteigne la caméra, en secondes ; None si l'objet ne se rapproche pas."""


@dataclass
class ResultatImage:
    """Résultat complet du traitement d'une image."""

    indice: int
    instant: float
    """Instant de l'image dans la vidéo, en secondes."""
    detections: list[Detection] = field(default_factory=list)
    pistes: list[EtatPiste] = field(default_factory=list)
    alerte: bool = False
