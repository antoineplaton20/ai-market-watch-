"""Alertes de prix, brief du matin : sans réseau."""
import time

from armee_or import alertes as AL, base, chef


def test_alerte_posee_puis_declenchee_une_seule_fois(monkeypatch):
    envois = []
    monkeypatch.setattr(AL.telegram, "envoyer", lambda t, *a, **k: envois.append((t, k)) or True)
    assert "≥ 4200.00" in AL.ajouter("4200", prix=4150.0)
    assert "≤ 4108.50" in AL.ajouter("-1%", prix=4150.0)
    assert "illisible" in AL.ajouter("abc", prix=4150.0) and "50 %" in AL.ajouter("9000", prix=4150.0)
    assert "1. or ≥ 4200.00" in AL.texte_liste(prix=4150.0) and "2. or ≤ 4108.50" in AL.texte_liste(prix=4150.0)
    assert AL.verifier(4199.9) == 0 and AL.verifier(4200.1) == 1
    assert envois[-1][1].get("important") and "4200.00" in envois[-1][0]
    assert AL.verifier(4300) == 0                                   # retirée après déclenchement
    assert AL.verifier(4100) == 1 and AL.texte_liste(prix=4100).startswith("⏰ Aucune")


def test_commandes_d_alerte(monkeypatch):
    monkeypatch.setattr(AL, "_cours", lambda: 4000.0)
    assert "Alerte posée" in AL.commande("/or_alerte 4 050,5")
    assert "Alerte posée" in AL.commande("/or_alerte_3990")
    assert "1. or ≥ 4050.50" in AL.commande("/or_alertes")
    assert "supprimée" in AL.commande("/or_alerte_suppr 1") and "Numéro inconnu" in AL.commande("/or_alerte_suppr 9")
    assert "1 alerte(s) supprimée(s)" in AL.commande("/or_alerte_suppr_tout")
    assert AL.commande("/or_go") is None
    assert "Alerte posée" in AL.commande("alerte +0.5%")               # depuis Termius


def test_alertes_depuis_telegram_et_bot(monkeypatch):
    monkeypatch.setattr(AL, "_cours", lambda: 4000.0)
    envois = []
    monkeypatch.setattr(chef.telegram, "envoyer", lambda t, *a, **k: envois.append(t) or True)
    monkeypatch.setattr(chef.telegram, "commandes", lambda *a, **k: ["/or_alerte 4010", "/or_alertes"])
    chef.bot_commandes(type("Chef", (), {"pause": False, "bots": []})())
    assert "Alerte posée" in envois[0] and "4010.00" in envois[1]
    assert "1 alerte(s) en attente" in chef.bot_alertes(None)
    monkeypatch.setattr(AL, "_cours", lambda: 4011.0)
    assert "1 alerte(s) déclenchée(s)" in chef.bot_alertes(None)
    assert base.lire(AL.CLE) == []


def _donnees_brief(maintenant):
    import numpy as np
    from armee_or import donnees
    ts = int(maintenant // 60 * 60 * 1000) - np.arange(900)[::-1] * 60_000
    donnees.inserer("XAUUSDT", "1m", [[int(t), 4100.0 + i * 0.05, 4101.0 + i * 0.05, 4099.0 + i * 0.05,
                                       4100.0 + i * 0.05, 1.0] for i, t in enumerate(ts)])
    base.ecrire("direct:XAUUSDT", {"prix": 4145.0, "ts": maintenant, "retard_ms": 50, "source": "Binance"})
    base.ecrire("calendrier", {"ts": maintenant, "evenements": [
        {"titre": "CPI m/m", "ts": maintenant + 6 * 3600, "prevision": "0.3%", "precedent": "0.4%"}]})
    base.ecrire("tresor", {"date": "2026-10-13", "reel_10a": 1.91, "reel_10a_5j": -0.06})
    base.ecrire("mt5:permis", {"1h": {"ok": False}})


def test_brief_du_matin_contenu_et_envoi_une_fois(monkeypatch):
    import calendar
    from armee_or import brief
    mardi_8h05 = calendar.timegm((2026, 10, 13, 6, 5, 0))               # 8 h 05 à Paris (heure d'été)
    _donnees_brief(mardi_8h05)
    texte = brief.texte_brief(mardi_8h05)
    for attendu in ("Brief de l'or · mar. 13/10", "Nuit (depuis 23 h)", "14:05 CPI m/m (prév. 0.3%)",
                    "taux réel 10 ans 1.91 %", "permis 1h ✖"):
        assert attendu in texte, attendu
    envois = []
    monkeypatch.setattr(brief.telegram, "envoyer", lambda t, *a, **k: envois.append(t) or True)
    assert brief.bot_brief(mardi_8h05 - 3600) == "prochain brief à 8 h"        # 7 h 05
    assert brief.bot_brief(mardi_8h05) == "brief envoyé" and len(envois) == 1
    assert brief.bot_brief(mardi_8h05 + 600) == "brief déjà envoyé aujourd'hui"
    samedi = calendar.timegm((2026, 10, 17, 6, 5, 0))
    assert brief.bot_brief(samedi) == "week-end : pas de brief"
