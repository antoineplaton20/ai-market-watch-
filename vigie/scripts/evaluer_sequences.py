"""Évalue la chaîne complète sur des séquences vidéo annotées (un dossier YOLO par séquence).

Exemple :
    python scripts/evaluer_sequences.py --modele runs/v1/meilleur.pt --donnees data/antiuav \
        --seuil 0.5 --rapport resultats/sequences.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vigie.detecteur import DetecteurDrones  # noqa: E402
from vigie.donnees import charger_image_rgb, lire_etiquettes, lister_echantillons  # noqa: E402
from vigie.evaluation_video import evaluer_sequence  # noqa: E402


def main() -> None:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--modele", required=True)
    analyseur.add_argument("--donnees", required=True, type=Path)
    analyseur.add_argument("--seuil", type=float, default=0.5)
    analyseur.add_argument("--ips", type=float, default=25.0, help="Images par seconde des séquences.")
    analyseur.add_argument("--rapport", type=Path, default=None)
    analyseur.add_argument("--tuiles", type=int, default=1, help="Grille de tuiles (1 : image entière seulement).")
    args = analyseur.parse_args()

    detecteur = DetecteurDrones.charger(args.modele, seuil_score=args.seuil)
    if args.tuiles > 1:
        def detecter(image):
            return detecteur.detecter_par_tuiles(image, args.tuiles)
    else:
        detecter = detecteur.detecter
    bilans = []
    for dossier in sorted(p for p in args.donnees.iterdir() if (p / "images").is_dir()):
        echantillons = lister_echantillons(dossier)
        if not echantillons:
            continue
        hauteur, largeur = charger_image_rgb(echantillons[0].chemin_image).shape[:2]
        images = (charger_image_rgb(e.chemin_image) for e in echantillons)
        verites = [lire_etiquettes(e.chemin_etiquettes, largeur, hauteur) for e in echantillons]
        bilan = evaluer_sequence(dossier.name, images, verites, detecter, args.ips)
        bilans.append(asdict(bilan))
        print(json.dumps(asdict(bilan), ensure_ascii=False))

    suivis = [b["taux_suivi"] for b in bilans if b["taux_suivi"] is not None]
    delais = [b["delai_alerte_s"] for b in bilans if b["delai_alerte_s"] is not None]
    synthese = {
        "sequences": len(bilans),
        "images": sum(b["images"] for b in bilans),
        "taux_suivi_moyen": sum(suivis) / len(suivis) if suivis else None,
        "delai_alerte_median_s": sorted(delais)[len(delais) // 2] if delais else None,
        "sequences_sans_alerte": sum(1 for b in bilans if b["alerte_jamais_donnee"]),
        "part_images_fausse_alerte_moyenne": sum(b["part_images_fausse_alerte"] for b in bilans) / max(len(bilans), 1),
        "changements_identifiant_total": sum(b["changements_identifiant"] for b in bilans),
        "millisecondes_par_image_moyenne": sum(b["millisecondes_par_image"] for b in bilans) / max(len(bilans), 1),
        "seuil_score": args.seuil,
        "tuiles": args.tuiles,
        "images_par_seconde_supposees": args.ips,
        "modele": args.modele,
    }
    print(json.dumps(synthese, indent=2, ensure_ascii=False))
    if args.rapport:
        args.rapport.parent.mkdir(parents=True, exist_ok=True)
        args.rapport.write_text(json.dumps({"synthese": synthese, "sequences": bilans}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
