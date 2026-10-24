import pytest

from vigie.evaluation_video import evaluer_sequence
from vigie.synthetique import ObjetSynthetique, detecteur_par_seuillage, generer_images
from vigie.types import Detection


def test_sequence_synthetique_suivie_sans_fausse_alerte():
    objets = [ObjetSynthetique(depart=(40, 300), vitesse=(5, -1), taille=12)]
    images, verites = generer_images(objets, 60)
    bilan = evaluer_sequence("synthetique", images, verites, detecteur_par_seuillage, 25.0)
    assert bilan.images == 60
    assert bilan.taux_suivi > 0.9
    assert bilan.delai_alerte_s == pytest.approx(2 / 25.0)
    assert bilan.part_images_fausse_alerte == 0.0
    assert bilan.changements_identifiant == 0
    assert not bilan.alerte_jamais_donnee


def test_fausse_alerte_comptee_quand_aucun_drone():
    images, verites = generer_images([], 20)

    def detecteur_fantome(_image):
        return [Detection((100, 100, 110, 110), 0.9)]

    bilan = evaluer_sequence("vide", images, verites, detecteur_fantome, 25.0)
    assert bilan.images_avec_drone == 0
    assert bilan.taux_suivi is None
    assert bilan.part_images_fausse_alerte == pytest.approx(18 / 20)
