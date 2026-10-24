import pytest

from vigie.evaluation import ExempleEvaluation, evaluer
from vigie.geometrie import categorie_taille, iou, iou_matrice


def test_iou_cas_connus():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(50 / 150)


def test_iou_matrice_coherente_avec_iou():
    a = [(0, 0, 10, 10), (5, 5, 20, 20)]
    b = [(0, 0, 10, 10), (5, 0, 15, 10), (100, 100, 110, 110)]
    m = iou_matrice(a, b)
    for i in range(2):
        for j in range(3):
            assert m[i, j] == pytest.approx(iou(a[i], b[j]))


def test_predictions_parfaites():
    ex = [ExempleEvaluation(verites=[(10, 10, 50, 50)], predictions=[(10, 10, 50, 50)], scores=[0.9])]
    r = evaluer(ex)
    assert r.precision_moyenne == pytest.approx(1.0)
    assert r.rappel_au_meilleur_seuil == pytest.approx(1.0)


def test_aucune_prediction():
    r = evaluer([ExempleEvaluation(verites=[(10, 10, 50, 50)], predictions=[], scores=[])])
    assert r.precision_moyenne == 0.0
    assert r.rappel_maximal == 0.0


def test_moitie_trouvee_et_une_fausse_alarme():
    ex = [
        ExempleEvaluation(verites=[(0, 0, 20, 20)], predictions=[(0, 0, 20, 20)], scores=[0.9]),
        ExempleEvaluation(verites=[(0, 0, 20, 20)], predictions=[(300, 300, 320, 320)], scores=[0.8]),
    ]
    r = evaluer(ex)
    assert r.rappel_maximal == pytest.approx(0.5)
    assert r.precision_moyenne == pytest.approx(0.5)


def test_double_detection_comptee_une_seule_fois():
    ex = [ExempleEvaluation(verites=[(0, 0, 20, 20)], predictions=[(0, 0, 20, 20), (1, 1, 21, 21)], scores=[0.9, 0.8])]
    r = evaluer(ex)
    assert r.rappel_maximal == pytest.approx(1.0)
    assert r.precision_au_meilleur_seuil == pytest.approx(1.0)
    assert r.meilleur_seuil_score == pytest.approx(0.9)


def test_fausses_alarmes_sur_images_vides():
    ex = [
        ExempleEvaluation(verites=[(0, 0, 20, 20)], predictions=[(0, 0, 20, 20)], scores=[0.9]),
        ExempleEvaluation(verites=[], predictions=[(5, 5, 9, 9)], scores=[0.95]),
    ]
    r = evaluer(ex)
    assert r.fausses_alarmes_par_image_vide is not None


def test_categories_de_taille():
    aire = 640 * 640
    assert categorie_taille((0, 0, 10, 10), aire) == "tres_petit"
    assert categorie_taille((0, 0, 20, 20), aire) == "petit"
    assert categorie_taille((0, 0, 60, 60), aire) == "moyen"
    assert categorie_taille((0, 0, 200, 200), aire) == "grand"
