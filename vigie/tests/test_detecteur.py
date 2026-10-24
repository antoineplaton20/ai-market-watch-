import numpy as np

from vigie.detecteur import ConfigurationDetecteur, DetecteurDrones, construire_modele


def test_inference_et_sauvegarde_rechargement(tmp_path):
    configuration = ConfigurationDetecteur(taille_entree=320, seuil_score=0.0)
    detecteur = DetecteurDrones(construire_modele(configuration, poids_coco=False), configuration)
    image = np.random.default_rng(0).integers(0, 255, (240, 320, 3), dtype=np.uint8)
    detections = detecteur.detecter(image)
    assert isinstance(detections, list)
    for d in detections:
        assert 0.0 <= d.score <= 1.0
        assert d.boite[0] <= d.boite[2] and d.boite[1] <= d.boite[3]

    chemin = tmp_path / "modele.pt"
    detecteur.sauvegarder(chemin, {"essai": True})
    recharge = DetecteurDrones.charger(chemin, seuil_score=0.0)
    assert recharge.configuration == configuration
    autres = recharge.detecter(image)
    assert [d.boite for d in autres] == [d.boite for d in detections]
