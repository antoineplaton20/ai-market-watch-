"""Le moteur de sortie : stop, objectif, gap, sécurisation, stop suiveur, prise partielle, durée max."""
import numpy as np
import pytest
from simulation import simuler_sortie, simuler_serie


def test_stop_loss_coute_1R_plus_frais_et_glissement():
    # stop à 1,5 % : -1,5 % de mouvement, -0,25 % de glissement du stop-limite, -0,2 % de frais = -1,95 %,
    # soit -1,30 R (v17.5 : glissement réaliste d'un stop-limite, avant 0,05 %)
    r, pnl, raison, n = simuler_sortie([(100, 100.5, 98.0, 98.2)], 100, 1.0)
    assert raison == "stop-loss"
    assert r == pytest.approx(-1.2975, abs=0.002)


def test_objectif_atteint():
    b = [(100, 101, 99.5, 100.5), (100.5, 103, 100, 102.8), (102.8, 106, 102, 105)]
    r, pnl, raison, n = simuler_sortie(b, 100, 1.0)
    assert raison == "objectif" and n == 3
    assert r == pytest.approx(3.83, abs=0.01)


def test_gap_sous_le_stop_vend_a_l_ouverture():
    r, pnl, raison, n = simuler_sortie([(100, 100.5, 99.5, 100), (97, 97.5, 96, 96.5)], 100, 1.0)
    assert raison == "stop (gap)"
    assert r < -1.9


def test_securisation_empeche_un_gagnant_de_devenir_perdant():
    b = [(100, 101.6, 99.8, 101.5), (101.5, 101.5, 99.0, 99.2)]
    r, pnl, raison, n = simuler_sortie(b, 100, 1.0)
    assert raison == "stop sécurisé"
    assert r > 0


def test_stop_suiveur_garde_l_essentiel_du_gain():
    b = [(100, 105, 99.8, 104.8), (104.8, 110, 104, 109.5), (109.5, 109.6, 100, 100.5)]
    r, pnl, raison, n = simuler_sortie(b, 100, 1.0, params={"objectif_atr": 20})
    assert raison == "stop sécurisé"
    assert r > 5


def test_prise_partielle_encaisse_une_partie():
    b = [(100, 101, 99.5, 100.5), (100.5, 103, 100, 102.8), (102.8, 104, 101, 101.2), (101.2, 101.5, 99, 99.5)]
    sans = simuler_sortie(b, 100, 1.0)[0]
    avec = simuler_sortie(b, 100, 1.0, params={"part_frac": 0.5, "part_r": 1.5})[0]
    assert avec > sans


def test_duree_max():
    b = [(100, 100.2, 99.9, 100.1)] * 10
    r, pnl, raison, n = simuler_sortie(b, 100, 1.0, duree_max_bougies=5)
    assert raison == "durée max" and n == 5


def test_serie_identique_au_calcul_unitaire():
    rng = np.random.default_rng(1)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, 500)))
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(o, c) * 1.002, np.minimum(o, c) * 0.998
    atr = np.full(500, 0.5)
    sig = np.zeros(500, dtype=np.bool_)
    sig[100] = True
    e, s, rs = simuler_serie(o, h, l, c, atr, sig, np.full(500, 1.5), 1.0, 2.0, 6.0, 0.0, 1.0, 48, 0.0005, 0.2, 0.0025)
    entree = o[101] * 1.0005
    unitaire = simuler_sortie(list(zip(o[101:150], h[101:150], l[101:150], c[101:150])), entree, 0.5, 48)[0]
    assert len(rs) == 1 and rs[0] == pytest.approx(unitaire)
