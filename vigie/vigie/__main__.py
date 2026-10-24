"""Interface en ligne de commande : python -m vigie <commande> ..."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


def commande_detecter(args) -> int:
    from .detecteur import DetecteurDrones
    from .pipeline import traiter_video

    detecteur = DetecteurDrones.charger(args.modele, args.appareil, args.seuil)
    if args.tuiles > 1:
        def detecter(image):
            return detecteur.detecter_par_tuiles(image, args.tuiles)
    else:
        detecter = detecteur.detecter
    bilan = traiter_video(args.video, detecter, args.sortie, args.journal)
    print(json.dumps(bilan, indent=2, ensure_ascii=False))
    return 0


def commande_evaluer(args) -> int:
    from .detecteur import DetecteurDrones
    from .entrainement import evaluer_detecteur

    detecteur = DetecteurDrones.charger(args.modele, args.appareil)
    rapport, secondes = evaluer_detecteur(detecteur, Path(args.donnees), args.images_max, args.graine)
    resultat = {"evaluation": asdict(rapport), "secondes_par_image": secondes, "modele": args.modele,
                "donnees": args.donnees, "images_max": args.images_max, "graine": args.graine}
    texte = json.dumps(resultat, indent=2, ensure_ascii=False)
    if args.rapport:
        Path(args.rapport).write_text(texte)
    print(texte)
    return 0


def commande_entrainer(args) -> int:
    from .entrainement import ParametresEntrainement, entrainer

    parametres = ParametresEntrainement(
        dossier_entrainement=args.entrainement,
        dossier_validation=args.validation,
        dossier_sortie=args.sortie,
        images_entrainement_max=args.images_max,
        images_validation_max=args.validation_max,
        epoques=args.epoques,
        taille_lot=args.lot,
        taux_apprentissage=args.taux,
        graine=args.graine,
        duree_max_minutes=args.duree_max,
        fils_chargement=args.fils,
    )
    meilleur = entrainer(parametres)
    print(f"Modèle retenu : {meilleur}")
    return 0


def commande_demo(args) -> int:
    from .pipeline import traiter_video
    from .synthetique import ObjetSynthetique, detecteur_par_seuillage, ecrire_video, generer_images

    objets = [
        ObjetSynthetique(depart=(40, 300), vitesse=(6, -1.5), taille=10),
        ObjetSynthetique(depart=(600, 80), vitesse=(-3, 1), taille=6, croissance=0.25),
    ]
    images, _ = generer_images(objets, 100)
    entree = Path(args.dossier) / "demo_entree.mp4"
    entree.parent.mkdir(parents=True, exist_ok=True)
    ecrire_video(images, entree)
    bilan = traiter_video(entree, detecteur_par_seuillage, Path(args.dossier) / "demo_sortie.mp4",
                          Path(args.dossier) / "demo_journal.jsonl")
    print(json.dumps(bilan, indent=2, ensure_ascii=False))
    return 0


def construire_analyseur() -> argparse.ArgumentParser:
    analyseur = argparse.ArgumentParser(prog="vigie", description="Détection et suivi de drones pour l'alerte précoce.")
    sous = analyseur.add_subparsers(dest="commande", required=True)

    d = sous.add_parser("detecter", help="Traiter une vidéo et produire une vidéo annotée et un journal.")
    d.add_argument("video")
    d.add_argument("--modele", required=True)
    d.add_argument("--sortie", default="sortie.mp4")
    d.add_argument("--journal", default="journal.jsonl")
    d.add_argument("--seuil", type=float, default=None)
    d.add_argument("--appareil", default="cpu")
    d.add_argument("--tuiles", type=int, default=1, help="Grille de tuiles pour la haute définition (ex. 2).")
    d.set_defaults(fonction=commande_detecter)

    e = sous.add_parser("evaluer", help="Mesurer les performances sur un jeu de données YOLO.")
    e.add_argument("donnees")
    e.add_argument("--modele", required=True)
    e.add_argument("--images-max", type=int, default=None)
    e.add_argument("--graine", type=int, default=0)
    e.add_argument("--rapport", default=None)
    e.add_argument("--appareil", default="cpu")
    e.set_defaults(fonction=commande_evaluer)

    t = sous.add_parser("entrainer", help="Entraîner le détecteur.")
    t.add_argument("--entrainement", required=True)
    t.add_argument("--validation", required=True)
    t.add_argument("--sortie", required=True)
    t.add_argument("--images-max", type=int, default=None)
    t.add_argument("--validation-max", type=int, default=500)
    t.add_argument("--epoques", type=int, default=5)
    t.add_argument("--lot", type=int, default=4)
    t.add_argument("--taux", type=float, default=0.01)
    t.add_argument("--graine", type=int, default=0)
    t.add_argument("--duree-max", type=float, default=None, help="Durée maximale en minutes.")
    t.add_argument("--fils", type=int, default=2)
    t.set_defaults(fonction=commande_entrainer)

    m = sous.add_parser("demo", help="Démonstration sur vidéo synthétique, sans modèle entraîné.")
    m.add_argument("--dossier", default="demo")
    m.set_defaults(fonction=commande_demo)
    return analyseur


def main(argv: list[str] | None = None) -> int:
    args = construire_analyseur().parse_args(argv)
    return args.fonction(args)


if __name__ == "__main__":
    sys.exit(main())
