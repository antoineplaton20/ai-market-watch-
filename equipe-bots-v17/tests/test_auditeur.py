"""AUDITEUR : calcul du R, duel champion / challenger."""
import datetime as dt
import json
import sqlite3
import time
import pytest
import auditeur
import strategie as S


def test_r_calcule_sur_le_risque_initial():
    p = {"entree": 100.0, "quantite": 1.0, "stop_initial": 98.0, "ouvert": time.time(), "votes": {}}
    auditeur.enregistrer("SOL/USDT", p, 104.0, "test")
    r, pnl = auditeur.trades_depuis(0)[0]
    assert r == pytest.approx((4 - 0.2) / 2, rel=1e-3)


def _duel(e_challenger, e_champion, jours=20, n=25):
    g = S.aleatoire("MACD")
    json.dump({"genome": g, "unite": "15m", "date": (dt.date.today() - dt.timedelta(days=jours)).isoformat()},
              open("challenger.json", "w"))
    auditeur._cnx_ombres().close()
    c = sqlite3.connect("journal.db")
    for _ in range(n):
        for gid, r in ((g["id"], e_challenger), ("defaut", e_champion)):
            c.execute("INSERT INTO ombres(role,genome,symbole,ts,entree,atr,params,r,resolu) VALUES (?,?,?,?,?,?,?,?,1)",
                      ("x", gid, "SOL/USDT", time.time() - 86400, 100, 1, "{}", r))
    c.commit()
    return g, auditeur.duel()


def test_challenger_gagnant_attend_l_approbation_humaine():
    import approbations
    g, msg = _duel(0.4, 0.05)
    assert S.champion()["id"] == "defaut"                        # rien ne change sans ton accord
    demande = approbations.resoudre(f"champion-{g['id']}", True)
    assert "NOUVEAU CHAMPION" in auditeur.promouvoir(demande)
    assert S.champion()["id"] == g["id"] and S.challenger() is None


def test_challenger_moins_bon_elimine():
    g, msg = _duel(-0.3, 0.2)
    assert "éliminé" in msg and S.champion()["id"] == "defaut"


def test_pas_de_verdict_trop_tot():
    g, msg = _duel(0.9, 0.0, jours=3)
    assert msg is None and S.challenger()["id"] == g["id"]
