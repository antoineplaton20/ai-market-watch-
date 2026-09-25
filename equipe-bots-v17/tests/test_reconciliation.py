"""RÉCONCILIATION : le bot et Binance doivent toujours être d'accord."""
import pandas as pd
import gardien as G
import auditeur
from reconciliation import reconcilier
from fausse_binance import FausseBinance


def _position(ex, etat):
    df = pd.DataFrame({"atr": [1.0] * 5, "c": [100.0] * 5})
    o = G.calculer_ordre(ex, "SOL/USDT", {"df": df}, 1000, stop_atr=1.5)
    G.acheter(ex, "SOL/USDT", o, etat, 0.9, {}, None)
    return etat["positions"]["SOL/USDT"]


def test_stop_disparu_est_repose():
    ex, etat = FausseBinance(), G.charger_etat()
    p = _position(ex, etat)
    ancien = p["id_stop"]
    ex.ordres[ancien]["status"] = "canceled"
    reconcilier(ex, etat)
    assert etat["positions"]["SOL/USDT"]["id_stop"] != ancien
    assert ex.ordres[etat["positions"]["SOL/USDT"]["id_stop"]]["status"] == "open"


def test_position_vendue_pendant_une_coupure():
    ex, etat = FausseBinance(), G.charger_etat()
    p = _position(ex, etat)
    ex.executer_stop(p["id_stop"], p["stop"])
    reconcilier(ex, etat)
    assert "SOL/USDT" not in etat["positions"]
    assert len(auditeur.trades_depuis(0)) == 1


def test_quantite_corrigee_et_stop_ajuste():
    ex, etat = FausseBinance(), G.charger_etat()
    p = _position(ex, etat)
    ex.solde["SOL"] = p["quantite"] / 2
    reconcilier(ex, etat)
    p2 = etat["positions"]["SOL/USDT"]
    assert p2["quantite"] == ex.solde["SOL"]
    assert ex.ordres[p2["id_stop"]]["amount"] == float(f"{ex.solde['SOL']:.4f}")


def test_ordre_orphelin_du_bot_annule_mais_pas_les_autres():
    ex, etat = FausseBinance(), G.charger_etat()
    ex.create_order("ETH/USDT", "STOP_LOSS_LIMIT", "sell", 1, 90, {"newClientOrderId": "eqb123"})
    ex.create_order("ETH/USDT", "limit", "sell", 1, 150, {"newClientOrderId": "manuel"})
    reconcilier(ex, etat)
    statuts = {o["clientOrderId"]: o["status"] for o in ex.ordres.values()}
    assert statuts["eqb123"] == "canceled" and statuts["manuel"] == "open"


def test_prix_sous_le_stop_sans_protection_vend():
    ex, etat = FausseBinance(), G.charger_etat()
    p = _position(ex, etat)
    ex.ordres[p["id_stop"]]["status"] = "canceled"
    ex.prix["SOL/USDT"] = p["stop"] * 0.95
    reconcilier(ex, etat)
    assert "SOL/USDT" not in etat["positions"]
