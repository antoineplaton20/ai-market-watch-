"""Application iPhone : code d'accès, données agrégées, commandes en liste blanche, fichiers de l'app."""
import json
import os
import struct
import time

import pytest

from v17_ops import commandes_app
from v17_ops.api import mobile as M
from v17_ops.core.store import OpsStore

CODE = "a" * 32


@pytest.fixture(autouse=True)
def code_acces(monkeypatch):
    monkeypatch.setenv("V17_APP_TOKEN", CODE)
    M._echecs.clear()
    yield
    M._echecs.clear()


def _etat_principal(dossier):
    etat = {"positions": {"SOL/USDT": {"entree": 150.0, "quantite": 2.0, "stop": 145.0, "objectif": 160.0,
                                       "id_stop": "eqb1", "securise": True, "mode": "strict", "ouvert": time.time()},
                          "ETH/USDT": {"entree": 2500.0, "quantite": 0.02, "stop": 2400.0, "id_stop": "aucun",
                                       "mode": "exploration"}},
            "arret_manuel": True, "latent": 12.5, "niveau_risque": "PRUDENT", "disjoncteur": {"raison": "baisse"}}
    (dossier / "etat.json").write_text(json.dumps(etat), encoding="utf-8")
    (dossier / "battement.json").write_text(json.dumps({"ts": time.time() - 30, "resume": "2 positions"}))


# ------------------------------------------------------------------ sécurité
def test_code_obligatoire(monkeypatch):
    with pytest.raises(M.HTTPException) as e:
        M.verifier_code(None)
    assert e.value.status_code == 401
    with pytest.raises(M.HTTPException) as e:
        M.verifier_code("Bearer faux")
    assert e.value.status_code == 401
    M.verifier_code("Bearer " + CODE)
    monkeypatch.setenv("V17_APP_TOKEN", "court")
    with pytest.raises(M.HTTPException) as e:                        # pas de code configuré : rien n'est lisible
        M.verifier_code("Bearer court")
    assert e.value.status_code == 503


def test_verrouillage_apres_trop_d_essais():
    for _ in range(M.ESSAIS_MAX):
        with pytest.raises(M.HTTPException):
            M.verifier_code("Bearer faux")
    with pytest.raises(M.HTTPException) as e:
        M.verifier_code("Bearer " + CODE)                            # même le bon code attend 10 min
    assert e.value.status_code == 429


def test_secrets_masques_dans_les_journaux(tmp_path):
    f = tmp_path / "bot.log"
    f.write_text("x | Telegram injoignable : https://api.telegram.org/bot123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw/send\n"
                 "y | binance GET /api/v3/order?symbol=BTCUSDT&signature=9f86d081884c7d659a2feaa0c55ad015a3bf4f1b\n"
                 "z | sk-ant-api03-abcdefghijklmnop\n", encoding="utf-8")
    texte = "\n".join(M.fin_de_fichier(str(f)))
    assert "AAHdqTcv" not in texte and "9f86d081" not in texte and "abcdefghij" not in texte
    assert "bot***" in texte and "signature=***" in texte


def test_fin_de_fichier_limite(tmp_path):
    f = tmp_path / "a.log"
    f.write_text("\n".join(f"ligne {i}" for i in range(1000)), encoding="utf-8")
    assert M.fin_de_fichier(str(f), 5) == [f"ligne {i}" for i in range(995, 1000)]
    assert M.fin_de_fichier(str(tmp_path / "absent.log")) == []


# ------------------------------------------------------------------ données
def test_tableau_complet(tmp_path, reglages):
    _etat_principal(tmp_path)
    s = reglages()
    st = OpsStore(s.ops_db)
    st.set('heartbeat', {'ts': time.time(), 'mode': 'paper', 'symbols': ['BTC/USDT'], 'prices': {'BTC/USDT': 100}})
    st.snapshot('BTC/USDT', {'price': 100, 'equity': 10010.0})
    st.order('i1', 'BTC/USDT', 'buy', 1.0, 100.0, 'filled')
    t = M.tableau(st, s, str(tmp_path))
    p = t["principal"]
    assert p["vivant"] and p["arret_manuel"] and p["latent"] == 12.5 and p["disjoncteur"] == "baisse"
    sol = next(x for x in p["positions"] if x["symbole"] == "SOL/USDT")
    eth = next(x for x in p["positions"] if x["symbole"] == "ETH/USDT")
    assert sol["valeur_entree"] == 300.0 and sol["securise"] and sol["protege"]
    assert eth["essai"] and not eth["protege"]
    assert t["v17"]["courbe"][-1][1] == 10010.0 and t["v17"]["ordres"][0]["symbole"] == "BTC/USDT"
    assert any("sécurité générale" in a for a in t["alertes"])
    assert set(t["services"]) == set(M.SERVICES)
    json.dumps(t)                                                     # sérialisable tel quel


def test_tableau_sans_rien_ne_plante_pas(tmp_path, reglages):
    (tmp_path / "etat.json").write_text("{abîmé", encoding="utf-8")
    s = reglages()
    t = M.tableau(OpsStore(s.ops_db), s, str(tmp_path))
    assert t["principal"]["positions"] == [] and not t["principal"]["vivant"]
    assert t["marches"] is None


# ------------------------------------------------------------------ commandes
def test_file_de_commandes_liste_blanche(tmp_path):
    commandes_app.deposer("/stop", tmp_path)
    commandes_app.deposer("/stop", tmp_path)
    with open(tmp_path / commandes_app.FICHIER, "a") as f:
        f.write("/exploration 3\n/vendre_tout\nrm -rf /\n")               # écrit à la main : filtré
    assert commandes_app.lire(tmp_path) == ["/stop", "/vendre_tout"]
    assert commandes_app.lire(tmp_path) == []                         # file vidée
    with pytest.raises(ValueError):
        commandes_app.deposer("/exploration 3", tmp_path)


def test_actions(tmp_path, reglages):
    s = reglages()
    st = OpsStore(s.ops_db)
    assert M.executer_action("principal_vendre_tout", st, s, str(tmp_path))["ok"]
    assert commandes_app.lire(tmp_path) == ["/vendre_tout"]
    M.executer_action("v17_stop", st, s, str(tmp_path))
    assert st.get('pause') is True
    M.executer_action("v17_reprise", st, s, str(tmp_path))
    assert st.get('pause') is False
    with pytest.raises(M.HTTPException):
        M.executer_action("supprimer_tout", st, s, str(tmp_path))


def test_le_bot_principal_applique_les_commandes_de_l_app(tmp_path, monkeypatch):
    import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "commandes", lambda: [])
    messages = []
    monkeypatch.setattr(main, "alerte", lambda m, important=True: messages.append(m))
    commandes_app.deposer("/stop")
    etat = {"positions": {}}
    main.traiter_commandes(None, etat)
    assert etat["arret_manuel"] is True and "Achats arrêtés" in messages[0]
    commandes_app.deposer("/reprise")
    main.traiter_commandes(None, etat)
    assert etat["arret_manuel"] is False


# ------------------------------------------------------------------ fichiers de l'application
def test_fichiers_de_l_application():
    d = M.DOSSIER_APP
    html = (d / "index.html").read_text(encoding="utf-8")
    for balise in ('apple-mobile-web-app-capable', 'apple-touch-icon', 'viewport-fit=cover', 'manifest.webmanifest',
                   'safe-area-inset-bottom', 'prefers-color-scheme: dark'):
        assert balise in html
    assert "innerHTML" not in html                                   # texte du serveur jamais interprété en HTML
    m = json.loads((d / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert m["display"] == "standalone" and m["start_url"] == "/app/"
    for taille in (180, 192, 512):
        data = (d / f"icon-{taille}.png").read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", data[16:24]) == (taille, taille)
    assert "/app/api/" in (d / "sw.js").read_text(encoding="utf-8")   # les données ne sont jamais mises en cache


def test_telecommande_app():
    texte = open(os.path.join(M.DOSSIER_APP.parent.parent.parent, "bots"), encoding="utf-8").read()
    assert "app|app-nouveau-code)" in texte and "app-tailscale)" in texte and "V17_APP_TOKEN" in texte


# ------------------------------------------------------------------ HTTP
def test_routes_http(tmp_path, monkeypatch, reglages):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from v17_ops.core import config as C
    from v17_ops.api.app import app
    monkeypatch.setattr(C, "settings", reglages())
    monkeypatch.chdir(tmp_path)
    _etat_principal(tmp_path)
    c = TestClient(app)
    r = c.get("/app/")
    assert r.status_code == 200 and "Équipe de bots" in r.text
    assert c.get("/app/manifest.webmanifest").status_code == 200
    assert c.get("/app/icon-180.png").headers["content-type"] == "image/png"
    assert c.get("/app/..%2Fapp.py.png").status_code == 404
    assert c.get("/app/api/tableau").status_code == 401
    ok = {"Authorization": "Bearer " + CODE}
    t = c.get("/app/api/tableau", headers=ok).json()
    assert t["principal"]["arret_manuel"] is True
    assert c.get("/app/api/verifier", headers=ok).status_code == 204
    assert c.get("/app/api/journal?source=../../etc/passwd", headers=ok).status_code == 400
    (tmp_path / "bot.log").write_text("bonjour\n", encoding="utf-8")
    assert c.get("/app/api/journal?source=principal", headers=ok).json()["lignes"] == ["bonjour"]
    assert c.post("/app/api/action", json={"action": "principal_stop"}, headers=ok).json()["ok"]
    assert (tmp_path / commandes_app.FICHIER).read_text().strip() == "/stop"
    assert c.post("/app/api/action", json={"action": "principal_stop"}).status_code == 401
    assert c.get("/health").status_code == 200                        # routes historiques inchangées


# ------------------------------------------------------------------ TradingView / Polymarket (V17.9)
def test_symboles_tradingview():
    assert M.symbole_tradingview("BTC/USDT") == "BINANCE:BTCUSDT"
    for invalide in (None, "", "BTCUSDT", "BTC/USDT\" onload=x", "../../x/USDT"):
        assert M.symbole_tradingview(invalide) is None
    principal = {"positions": [{"symbole": "SOL/USDT"}, {"symbole": "ETH/USDT"}]}
    w = {"positions": [{"symbol": "ETH/USDT"}], "symbols": ["BTC/USDT", "ETH/USDT"]}
    assert M.symboles_tradingview(principal, w) == ["BINANCE:SOLUSDT", "BINANCE:ETHUSDT", "BINANCE:BTCUSDT"]
    assert M.symboles_tradingview({}, {}) == []


def test_tableau_contient_les_marches_tradingview(tmp_path, reglages):
    _etat_principal(tmp_path)
    s = reglages()
    st = OpsStore(s.ops_db)
    st.set('heartbeat', {'ts': time.time(), 'mode': 'paper', 'symbols': ['BTC/USDT']})
    t = M.tableau(st, s, str(tmp_path))
    assert t["tradingview"][0] in ("BINANCE:SOLUSDT", "BINANCE:ETHUSDT") and "BINANCE:BTCUSDT" in t["tradingview"]


def test_predictions_polymarket_en_lecture_seule(tmp_path, monkeypatch):
    import sqlite3
    import lecture_renseignement as LR
    base = tmp_path / "renseignement.db"
    c = sqlite3.connect(base)
    c.executescript(LR.SCHEMA)
    maintenant = time.time()
    for i, (titre, source, imp, age) in enumerate([
            ("« Fed cut? » → Yes 62 %", "Polymarket", 2, 60), ("« BTC 120k? » → Yes 34 %", "Polymarket", 1, 30),
            ("Article Reuters", "Reuters", 3, 10), ("« Vieux marché » → Yes 5 %", "Polymarket", 2, 3 * 86400)]):
        c.execute("INSERT INTO faits(hash, ts, vu, bot, source, titre, importance) VALUES(?,?,?,?,?,?,?)",
                  (str(i), maintenant - age, maintenant, "foule", source, titre, imp))
    c.execute("INSERT INTO bots(nom, famille, derniere, ok) VALUES('Foule', 'foule', ?, 1)", (maintenant,))
    c.commit(); c.close()
    assert [x["titre"] for x in LR.par_source("Polymarket", base=str(base))] == ["« Fed cut? » → Yes 62 %",
                                                                                "« BTC 120k? » → Yes 34 %"]
    assert LR.par_source("Polymarket", base=str(tmp_path / "absente.db")) == []   # base absente : liste vide
    monkeypatch.setattr(LR, "BASE", str(base))
    r = M.renseignement()
    assert len(r["predictions"]) == 2 and r["predictions"][0]["importance"] == 2


def test_application_tradingview_et_polymarket():
    html = (M.DOSSIER_APP / "index.html").read_text(encoding="utf-8")
    assert "s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" in html
    assert "fr.tradingview.com/chart/?symbol=" in html and "Liste pour TradingView" in html
    assert "Polymarket · lecture seule" in html and "innerHTML" not in html


def test_bots_app_affiche_le_lien_d_activation_tailscale():
    texte = open(os.path.join(M.DOSSIER_APP.parent.parent.parent, "bots"), encoding="utf-8").read()
    bloc = texte[texte.index("  app|app-nouveau-code)"):texte.index("  app-tailscale)")]
    assert "timeout 300 tailscale serve --bg" in bloc
    assert "serve --bg \"$PORT\" > /dev/null" not in bloc          # la sortie (lien d'activation) reste visible
