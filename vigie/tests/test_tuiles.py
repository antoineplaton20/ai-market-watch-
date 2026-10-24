import numpy as np

from vigie.detecteur import ConfigurationDetecteur, DetecteurDrones, construire_modele, decouper_tuiles, fusionner
from vigie.types import Detection


def test_les_tuiles_couvrent_toute_l_image_avec_recouvrement():
    tuiles = decouper_tuiles(1920, 1080, 2, 0.2)
    assert len(tuiles) == 4
    couverture = np.zeros((1080, 1920), dtype=np.int32)
    for x1, y1, x2, y2 in tuiles:
        couverture[y1:y2, x1:x2] += 1
    assert couverture.min() >= 1
    assert couverture.max() >= 2


def test_une_seule_tuile_sans_grille():
    assert decouper_tuiles(640, 480, 1) == [(0, 0, 640, 480)]


def test_fusion_supprime_les_doublons():
    d = [Detection((10, 10, 30, 30), 0.9), Detection((11, 11, 31, 31), 0.8), Detection((200, 200, 220, 220), 0.7)]
    gardees = fusionner(d)
    assert len(gardees) == 2
    assert gardees[0].score == 0.9


def test_detection_par_tuiles_renvoie_des_coordonnees_dans_l_image():
    configuration = ConfigurationDetecteur(taille_entree=320, seuil_score=0.0)
    detecteur = DetecteurDrones(construire_modele(configuration), configuration)
    image = np.random.default_rng(0).integers(0, 255, (360, 640, 3), dtype=np.uint8)
    for d in detecteur.detecter_par_tuiles(image, grille=2):
        assert 0 <= d.boite[0] <= d.boite[2] <= 640 + 1
        assert 0 <= d.boite[1] <= d.boite[3] <= 360 + 1
