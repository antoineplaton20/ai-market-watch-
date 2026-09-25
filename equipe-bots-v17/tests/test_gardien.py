"""Le GARDIEN : taille des positions, stop posé chez Binance, jamais de position sans protection, sorties."""
import pandas as pd
import pytest
import config
import gardien as G
import auditeur
from fausse_binance import FausseBinance


def _d(atr):
    df = pd.DataFrame({"atr": [atr] * 5, "c": [100.0] * 5})
    return {"df": df}


def _etat():
    return G.charger_etat()


def _risque_reel(o, dist):
    stop = o["prix"] - dist
    return o["quantite"] * (dist + o["prix"] * config.FRAIS_ALLER_RETOUR_PCT / 100 + stop * 0.005)


def test_perte_max_1_pourcent_du_capital_frais_compris():
    ex = FausseBinance()
    o = G.calculer_ordre(ex, "SOL/USDT", _d(5.0), 1000, stop_atr=1.5)
    assert _risque_reel(o, 7.5) == pytest.approx(10, rel=0.01)


def test_position_plafonnee_a_20_pourcent():
    ex = FausseBinance()
    o = G.calculer_ordre(ex, "SOL/USDT", _d(0.1), 1000, stop_atr=1.5)
    assert o["quantite"] * o["prix"] <= 200.5


def test_modulateur_divise_le_risque():
    ex = FausseBinance()
    o = G.calculer_ordre(ex, "SOL/USDT", _d(5.0), 1000, multiplicateur=0.5, stop_atr=1.5)
    assert _risque_reel(o, 7.5) == pytest.approx(5, rel=0.01)


def _acheter(ex, etat, genome=None):
    o = G.calculer_ordre(ex, "SOL/USDT", _d(1.0), 1000, stop_atr=1.5)
    G.acheter(ex, "SOL/USDT", o, etat, 0.9, {"TENDANCE": (1.0, "")}, genome)
    return etat["positions"].get("SOL/USDT")


def test_achat_pose_un_stop_signe_chez_binance():
    ex, etat = FausseBinance(), _etat()
    p = _acheter(ex, etat)
    stop = ex.ordres[p["id_stop"]]
    assert stop["type"] == "STOP_LOSS_LIMIT" and stop["clientOrderId"].startswith("eqb")
    assert stop["stopPrice"] == pytest.approx(p["stop"], rel=1e-3)


def test_jamais_de_position_sans_stop():
    ex, etat = FausseBinance(), _etat()
    ex.stop_en_panne = True
    p = _acheter(ex, etat)
    assert p is None
    assert ex.historique[-1][:2] == ("market", "sell")        # revendu immédiatement


def test_stop_execute_est_journalise():
    ex, etat = FausseBinance(), _etat()
    p = _acheter(ex, etat)
    ex.executer_stop(p["id_stop"], p["stop"])
    G.surveiller(ex, etat)
    assert "SOL/USDT" not in etat["positions"]
    assert auditeur.trades_depuis(0)[0][0] < 0


def test_prise_partielle_et_comptabilite_au_centime():
    ex, etat = FausseBinance(), _etat()
    import strategie as S
    g = S.genome_defaut()
    g.update({"part_frac": 0.5, "part_r": 0.8})
    p = _acheter(ex, etat, g)
    for prix in (101, 102.5):
        ex.prix["SOL/USDT"] = prix
        G.surveiller(ex, etat)
    p = etat["positions"]["SOL/USDT"]
    assert p["partiel"] and p["quantite"] == pytest.approx(p["qte_initiale"] / 2, rel=0.01)
    ex.executer_stop(p["id_stop"], 103.0)
    G.surveiller(ex, etat)
    r, pnl_usdt = auditeur.trades_depuis(0)[0]
    q, e = p["qte_initiale"], p["entree"]
    vendu = float(f"{q * 0.5:.4f}")                  # la fausse plateforme exécute au prix affiché
    attendu = (102.5 - e) * vendu + (103.0 - e) * (q - vendu) - q * e * config.FRAIS_ALLER_RETOUR_PCT / 100
    assert pnl_usdt == pytest.approx(attendu, abs=0.05)


def test_filet_de_secours_si_le_stop_ne_part_pas():
    ex, etat = FausseBinance(), _etat()
    p = _acheter(ex, etat)
    ex.prix["SOL/USDT"] = p["stop"] * 0.97
    G.surveiller(ex, etat)
    assert "SOL/USDT" not in etat["positions"]


def test_disjoncteur_et_pause_bloquent_les_achats():
    etat = _etat()
    assert G.peut_acheter(etat)
    etat["disjoncteur"] = {"raison": "test"}
    assert not G.peut_acheter(etat)
    etat["disjoncteur"] = None
    import time
    etat["pause_jusqua"] = time.time() + 60
    assert not G.peut_acheter(etat)
