"""SUR-APPRENTISSAGE : la PBO et le Sharpe dégonflé mesurent bien ce qu'ils prétendent mesurer."""
import numpy as np
import pytest
import surapprentissage as SA


def test_pbo_du_hasard_vaut_environ_50_pourcent_en_moyenne():
    rng = np.random.default_rng(1)
    valeurs = [SA.pbo_cscv(rng.normal(0, 1, (12, 100)))[0] for _ in range(40)]
    assert 0.40 < np.mean(valeurs) < 0.60


def test_pbo_basse_quand_une_strategie_a_un_vrai_avantage():
    rng = np.random.default_rng(2)
    M = rng.normal(0, 1, (12, 100))
    M[:, 7] += 1.5
    assert SA.pbo_cscv(M)[0] < 0.10


def test_pbo_non_calculable_avec_trop_peu_de_strategies():
    assert SA.pbo_cscv(np.zeros((12, 5)))[0] is None


def test_clones_comptent_pour_une_seule_strategie():
    rng = np.random.default_rng(3)
    base = rng.normal(0, 1, (200, 1))
    clones = np.tile(base, (1, 30)) + rng.normal(0, 0.01, (200, 30))
    assert SA.n_effectif(clones) < 1.5
    assert SA.n_effectif(rng.normal(0, 1, (200, 30))) > 20


def test_sharpe_degonfle_distingue_avantage_reel_et_chance():
    rng = np.random.default_rng(4)
    assert SA.sharpe_degonfle(rng.normal(0.5, 1, 300), 0.01, 10) > 0.95
    assert SA.sharpe_degonfle(rng.normal(0.05, 1, 100), 0.02, 1000) < 0.50


def test_plus_d_essais_exige_plus_de_preuves():
    rs = np.random.default_rng(5).normal(0.15, 1, 200)
    assert SA.sharpe_degonfle(rs, 0.01, 1000) < SA.sharpe_degonfle(rs, 0.01, 2)


def test_matrice_des_tranches_additionne_les_R():
    M = SA.matrice_tranches([(np.array([0, 5, 9]), np.array([1.0, 2.0, -1.0]))], 0, 10, 2)
    assert M[:, 0].tolist() == [1.0, 1.0]


def test_une_strategie_degeneree_ne_fausse_pas_la_mesure():
    normales = list(np.random.default_rng(6).normal(0.2, 0.1, 100))
    assert SA.variance_robuste(normales + [-129.0]) == pytest.approx(SA.variance_robuste(normales), rel=0.1)
