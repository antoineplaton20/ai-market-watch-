"""DISJONCTEUR : le système s'arrête seul quand le réel fait nettement pire que prévu."""
import json
import time
import auditeur
import disjoncteur as D
import gardien as G


def _trade(pnl_usdt, r):
    p = {"entree": 100.0, "quantite": abs(pnl_usdt) / 1.0 if pnl_usdt else 1.0, "stop_initial": 99.0,
         "ouvert": time.time(), "votes": {}}
    auditeur.enregistrer("SOL/USDT", p, 100.0 + (1.0 if pnl_usdt > 0 else -1.0), "test")


def test_pire_baisse_declenche():
    etat = G.charger_etat()
    for _ in range(4):
        _trade(-45, -1)                         # environ -180 USDT sur 1 000 : 18 % > 1,5 x 10 %
    D.verifier(etat)
    assert etat.get("disjoncteur") and not G.peut_acheter(etat)


def test_rearmer_repart_de_zero():
    etat = G.charger_etat()
    for _ in range(4):
        _trade(-45, -1)
    D.verifier(etat)
    D.rearmer(etat)
    time.sleep(0.01)
    D.verifier(etat)
    assert not etat.get("disjoncteur")


def test_pertes_en_serie_pause_24h_une_seule_fois():
    etat = G.charger_etat()
    for _ in range(7):
        _trade(-5, -1)
    D.verifier(etat)
    assert etat["pause_jusqua"] > time.time() + 23 * 3600
    etat["pause_jusqua"] = 0
    D.verifier(etat)
    assert etat["pause_jusqua"] == 0            # même série : pas de nouvelle pause


def test_esperance_nettement_sous_la_prevision():
    with open("champion.json", "w") as f:
        json.dump({"genome": {"id": "x"}, "unite": "15m", "date": "2020-01-01",
                   "coffre": {"E": 0.3, "std": 1.0, "mc_dd95": 0.5}}, f)
    etat = G.charger_etat()
    for i in range(30):
        _trade(-1 if i % 3 else 0.5, -1)
    D.verifier(etat)
    assert etat.get("disjoncteur") and "espérance" in etat["disjoncteur"]["raison"]
