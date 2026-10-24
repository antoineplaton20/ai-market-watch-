import numpy as np

from vigie.suivi import SuiviMultiObjets
from vigie.types import Detection


def boite_carree(cx, cy, taille):
    return (cx - taille / 2, cy - taille / 2, cx + taille / 2, cy + taille / 2)


def test_bruit_de_taille_ne_declenche_pas_d_approche():
    rng = np.random.default_rng(3)
    suivi = SuiviMultiObjets()
    approches = 0
    for t in range(200):
        taille = 20 + rng.normal(0, 1.5)
        etats = suivi.mettre_a_jour([Detection(boite_carree(300 + rng.normal(0, 1), 200, taille), 0.9)])
        approches += sum(1 for e in etats if e.temps_avant_contact is not None and e.temps_avant_contact < 10)
    assert approches <= 4


def test_rapprochement_net_est_detecte_malgre_le_bruit():
    rng = np.random.default_rng(4)
    suivi = SuiviMultiObjets()
    for t in range(60):
        taille = 10 + 0.8 * t + rng.normal(0, 1.0)
        etats = suivi.mettre_a_jour([Detection(boite_carree(300, 200, taille), 0.9)])
    assert etats[0].temps_avant_contact is not None
    assert etats[0].temps_avant_contact < 5
