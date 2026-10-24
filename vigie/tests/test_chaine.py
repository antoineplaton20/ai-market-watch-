import json

import cv2
import numpy as np
import pytest

from vigie.donnees import JeuDeDonneesYolo, lire_etiquettes, lister_echantillons
from vigie.pipeline import Vigie, traiter_video
from vigie.synthetique import ObjetSynthetique, detecteur_par_seuillage, ecrire_video, generer_images


def test_lecture_etiquettes_yolo(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("0 0.5 0.5 0.1 0.2\nligne invalide\n0 0.1 0.1 0 0.1\n")
    boites = lire_etiquettes(f, 640, 480)
    assert len(boites) == 1
    x1, y1, x2, y2 = boites[0]
    assert (x1, y1, x2, y2) == pytest.approx((288, 192, 352, 288))


def test_jeu_de_donnees_avec_image_sans_drone(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "labels").mkdir()
    image = np.full((64, 64, 3), 200, np.uint8)
    cv2.imwrite(str(tmp_path / "images" / "avec.jpg"), image)
    cv2.imwrite(str(tmp_path / "images" / "sans.jpg"), image)
    (tmp_path / "labels" / "avec.txt").write_text("0 0.5 0.5 0.25 0.25\n")
    echantillons = lister_echantillons(tmp_path)
    assert len(echantillons) == 2
    jeu = JeuDeDonneesYolo(echantillons)
    tenseur, cible = jeu[0]
    assert tenseur.shape == (3, 64, 64)
    assert cible["boxes"].shape == (1, 4)
    _, cible_vide = jeu[1]
    assert cible_vide["boxes"].shape == (0, 4)


def test_chaine_complete_sur_images_synthetiques():
    objets = [ObjetSynthetique(depart=(40, 300), vitesse=(5, -1), taille=10)]
    images, verites = generer_images(objets, 40)
    vigie = Vigie(detecteur_par_seuillage, 25.0)
    resultats = [vigie.traiter(im) for im in images]
    assert not resultats[0].alerte
    assert all(r.alerte for r in resultats[5:35])
    identifiants = {p.identifiant for r in resultats for p in r.pistes if p.confirmee}
    assert identifiants == {1}


def test_objet_en_approche_declenche_l_alerte_approche():
    objets = [ObjetSynthetique(depart=(320, 240), vitesse=(0, 0), taille=8, croissance=0.6)]
    images, _ = generer_images(objets, 50)
    vigie = Vigie(detecteur_par_seuillage, 25.0)
    resultats = [vigie.traiter(im) for im in images]
    assert vigie.en_approche(resultats[-1]) == [1]


def test_traitement_video_ecrit_video_et_journal(tmp_path):
    objets = [ObjetSynthetique(depart=(40, 300), vitesse=(5, -1), taille=10)]
    images, _ = generer_images(objets, 30)
    entree = tmp_path / "entree.mp4"
    ecrire_video(images, entree)
    bilan = traiter_video(entree, detecteur_par_seuillage, tmp_path / "sortie.mp4", tmp_path / "journal.jsonl")
    assert bilan["images"] == 30
    assert bilan["pistes_confirmees"] == 1
    lignes = (tmp_path / "journal.jsonl").read_text().splitlines()
    assert len(lignes) == 30
    assert "pistes" in json.loads(lignes[-1])
    assert (tmp_path / "sortie.mp4").stat().st_size > 0
