import numpy as np
import pytest

from vigie.suivi import ParametresSuivi, SuiviMultiObjets
from vigie.types import Detection


def boite_carree(cx, cy, taille):
    return (cx - taille / 2, cy - taille / 2, cx + taille / 2, cy + taille / 2)


def test_un_objet_garde_le_meme_identifiant_malgre_le_bruit():
    rng = np.random.default_rng(1)
    suivi = SuiviMultiObjets()
    identifiants = set()
    for t in range(60):
        cx, cy = 50 + 4 * t + rng.normal(0, 0.8), 200 - t + rng.normal(0, 0.8)
        etats = suivi.mettre_a_jour([Detection(boite_carree(cx, cy, 12), 0.9)])
        identifiants.update(e.identifiant for e in etats if e.confirmee)
    assert identifiants == {1}


def test_la_piste_est_confirmee_apres_trois_detections():
    suivi = SuiviMultiObjets(ParametresSuivi(images_pour_confirmer=3))
    etats = []
    for t in range(3):
        etats = suivi.mettre_a_jour([Detection(boite_carree(100 + t, 100, 20), 0.9)])
        assert etats[0].confirmee == (t == 2)


def test_une_fausse_alarme_isolee_n_est_jamais_confirmee():
    suivi = SuiviMultiObjets()
    etats = suivi.mettre_a_jour([Detection(boite_carree(300, 300, 10), 0.9)])
    assert not etats[0].confirmee
    for _ in range(5):
        etats = suivi.mettre_a_jour([])
    assert etats == []


def test_identifiant_conserve_apres_detections_manquees():
    suivi = SuiviMultiObjets(ParametresSuivi(images_sans_detection_max=10))
    for t in range(10):
        suivi.mettre_a_jour([Detection(boite_carree(100 + 5 * t, 100, 16), 0.9)])
    for t in range(10, 15):
        suivi.mettre_a_jour([])
    etats = suivi.mettre_a_jour([Detection(boite_carree(100 + 5 * 15, 100, 16), 0.9)])
    assert [e.identifiant for e in etats if e.confirmee] == [1]


def test_deux_objets_qui_se_croisent_gardent_leur_identifiant():
    suivi = SuiviMultiObjets()
    trajectoires = {1: [], 2: []}
    for t in range(40):
        a = Detection(boite_carree(50 + 8 * t, 150, 14), 0.9)
        b = Detection(boite_carree(370 - 8 * t, 170, 14), 0.9)
        etats = suivi.mettre_a_jour([a, b])
        for e in etats:
            if e.confirmee:
                trajectoires.setdefault(e.identifiant, []).append((e.boite[0] + e.boite[2]) / 2)
    assert set(k for k, v in trajectoires.items() if v) == {1, 2}
    assert trajectoires[1][-1] > trajectoires[1][0]
    assert trajectoires[2][-1] < trajectoires[2][0]


def test_petit_objet_rapide_sans_recouvrement_reste_associe():
    suivi = SuiviMultiObjets()
    for t in range(20):
        etats = suivi.mettre_a_jour([Detection(boite_carree(20 + 12 * t, 100, 6), 0.9)])
    assert [e.identifiant for e in etats if e.confirmee] == [1]


def test_temps_avant_contact_pour_objet_qui_grossit():
    ips = 25.0
    suivi = SuiviMultiObjets(images_par_seconde=ips)
    taille0, croissance = 10.0, 0.5
    for t in range(40):
        etats = suivi.mettre_a_jour([Detection(boite_carree(320, 240, taille0 + croissance * t), 0.9)])
    taille = taille0 + croissance * 39
    attendu = (taille / croissance) / ips
    assert etats[0].temps_avant_contact == pytest.approx(attendu, rel=0.25)


def test_objet_qui_s_eloigne_n_a_pas_de_temps_avant_contact():
    suivi = SuiviMultiObjets()
    for t in range(30):
        etats = suivi.mettre_a_jour([Detection(boite_carree(320, 240, 40 - 0.5 * t), 0.9)])
    assert etats[0].temps_avant_contact is None


def test_detection_faible_ne_cree_pas_de_piste():
    suivi = SuiviMultiObjets(ParametresSuivi(score_min_creation=0.5))
    assert suivi.mettre_a_jour([Detection(boite_carree(10, 10, 8), 0.2)]) == []
