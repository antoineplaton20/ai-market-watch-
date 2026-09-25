"""Armée de renseignement : collecte perpétuelle, base partagée, synthèse, alertes, lecture par les bots — sans réseau."""
import datetime as dt
import json
import os
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import config
import lecture_renseignement as LR
import renseignement as RS
from moteurs import renseignement_sources as R

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAINTENANT = dt.datetime.now(dt.timezone.utc)


def rss(*titres):
    date = MAINTENANT.strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = "".join(f"<item><title>{t}</title><pubDate>{date}</pubDate></item>" for t in titres)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>'.encode()


GDACS = f"""<?xml version="1.0"?><rss version="2.0" xmlns:gdacs="http://www.gdacs.org"><channel>
<item><title>Red earthquake alert in Japan</title><pubDate>{MAINTENANT.strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>
<gdacs:alertlevel>Red</gdacs:alertlevel></item>
<item><title>Green flood alert in Thailand</title><gdacs:alertlevel>Green</gdacs:alertlevel></item>
</channel></rss>""".encode()
USGS = json.dumps({"features": [
    {"properties": {"mag": 7.8, "place": "Off the coast of Chile", "time": time.time() * 1000, "alert": "red",
                    "tsunami": 1, "url": "u"}},
    {"properties": {"mag": 4.7, "place": "Indonesia", "time": time.time() * 1000, "alert": None}}]}).encode()
POLY = json.dumps([
    {"question": "Will the Fed cut interest rates in October?", "outcomes": '["Yes", "No"]',
     "outcomePrices": '["0.62", "0.38"]', "oneDayPriceChange": 0.12, "slug": "fed"},
    {"question": "Packers vs Falcons", "outcomes": '["Packers", "Falcons"]', "outcomePrices": '["0.5", "0.5"]'},
]).encode()


def lire(url):
    if "usgs" in url:
        return USGS
    if "gdacs" in url:
        return GDACS
    if "polymarket" in url:
        return POLY
    if "federalreserve" in url:
        raise ConnectionError("injoignable")
    if "mastodon" in url:
        return rss("Bitcoin rally as inflation cools")
    return rss("Oil prices surge as OPEC cuts output", "Binance hacked: withdrawals suspended, bitcoin plunges",
               "Guerre commerciale : nouveaux droits de douane sur l'acier")


def gdelt(params):
    if params["mode"] == "timelinetone":
        return {"timeline": [{"series": "Average Tone", "data": [
            {"date": f"20260925T{h:02d}0000Z", "value": -1.0 if h < 18 else -3.0} for h in range(24)]}]}
    return {"articles": [{"title": "Bitcoin slumps as regulators tighten crypto rules", "url": "https://g/1",
                          "seendate": MAINTENANT.strftime("%Y%m%dT%H%M%SZ"), "domain": "reuters.com"},
                         {"title": "Wheat prices jump on drought fears", "url": "https://g/2",
                          "seendate": MAINTENANT.strftime("%Y%m%dT%H%M%SZ"), "domain": "lemonde.fr"}]}


@pytest.fixture
def armee(monkeypatch):
    envoyes = []
    monkeypatch.setattr(RS, "alerte", lambda m, important=True: envoyes.append((m, important)))
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    ctx = R.Contexte(lire=lire, gdelt_json=gdelt, actifs=lambda: [("BTC", "bitcoin"), ("MC.PA", "LVMH")],
                     pause_gdelt_s=0)
    a = RS.Armee(RS.Base(), ctx, ia=None)
    a.envoyes = envoyes
    return a


# ------------------------------------------------------------------ l'armée
def test_armee_complete_et_perpetuelle():
    bots = R.armee()
    familles = {b.famille for b in bots}
    assert len(bots) >= 25 and {"presse", "monde", "ton", "terrain", "foule", "social", "de_pres"} <= familles
    assert all(b.periode_min <= 30 for b in bots)                    # chacun revient au moins toutes les 30 min


def test_un_passage_de_tous_les_bots(armee):
    res = armee.passer_tout()
    c = armee.base.c
    assert sum(res.values()) >= 8
    erreurs = dict(c.execute("SELECT nom, erreur FROM bots").fetchall())
    assert all(e is None for e in erreurs.values())                  # la Fed en panne n'arrête pas son groupe
    # le même titre repris par plusieurs sources est renforcé, pas dupliqué
    r = c.execute("SELECT n_sources FROM faits WHERE titre LIKE 'Oil prices surge%'").fetchone()
    assert r[0] >= 2
    # actifs reconnus dans les titres, importance « danger » sans IA
    btc = c.execute("SELECT actifs, importance, ton FROM faits WHERE titre LIKE 'Binance hacked%'").fetchone()
    assert ",BTC," in btc["actifs"] and btc["importance"] == 2 and btc["ton"] == -2
    # terrain : seul le séisme majeur et l'alerte rouge sont gardés, en importance 3
    assert c.execute("SELECT COUNT(*) FROM faits WHERE source IN ('USGS', 'GDACS') AND importance = 3").fetchone()[0] == 2
    assert c.execute("SELECT COUNT(*) FROM faits WHERE titre LIKE '%Thailand%' OR titre LIKE '%Indonesia%'").fetchone()[0] == 0
    # foule : la question sportive est ignorée, la Fed est gardée
    assert c.execute("SELECT COUNT(*) FROM faits WHERE source = 'Polymarket'").fetchone()[0] == 1
    # ton de la presse mondiale (GDELT) : les dernières heures sont plus négatives que la moyenne
    assert armee.base.lire_signal("gdelt:geopolitique")["valeur"] < 0


def test_recul_apres_echec():
    def casse(ctx):
        raise TimeoutError("site muet")
    bot = R.Bot("Casse", "presse", 15, casse)
    a = RS.Armee(RS.Base(), R.Contexte(lire=lire), ia=None, bots=[bot])
    a.executer(bot)
    p1 = a.prochaine["Casse"] - time.time()
    a.executer(bot)
    p2 = a.prochaine["Casse"] - time.time()
    assert 25 * 60 < p1 < 35 * 60 and p2 > p1                         # 30 min, puis 60 min...
    assert "TimeoutError" in a.base.c.execute("SELECT erreur FROM bots").fetchone()[0]


def test_cycle_en_parallele_sans_bloquer(armee):
    armee.prochaine = {nom: 0 for nom in armee.prochaine}           # tout le monde part tout de suite
    with ThreadPoolExecutor(max_workers=4) as pool:
        armee.cycle(pool)
        for _ in range(100):
            if not armee.en_cours:
                break
            time.sleep(0.05)
            armee.cycle(pool)
    assert armee.base.c.execute("SELECT COUNT(*) FROM bots").fetchone()[0] == len(armee.bots)


# ------------------------------------------------------------------ synthèse et alertes
def test_synthese_signaux_et_alertes(armee):
    armee.passer_tout()
    armee.synthese()
    g = LR.signal("global")
    assert g is not None and g["valeur"] == 0                          # 1re synthèse : c'est la « normale »
    btc = LR.signal("actif:BTC")
    assert btc["valeur"] < 0 and btc["n"] >= 2
    assert LR.signal("secteur:Energy") is not None
    # BTC : mauvaise nouvelle grave reprise par plusieurs sources -> alerte ; séisme rouge -> alerte
    grave = LR.alerte_grave([LR.cle_actif("BTC/USDT")])
    assert grave and "Binance" in grave["titre"]
    assert LR.alerte_grave([LR.cle_actif("ETH/USDT")]) is None
    armee.sentinelle()
    assert any(important and "🚨" in m for m, important in armee.envoyes)
    n = len(armee.envoyes)
    armee.synthese()
    armee.sentinelle()
    assert len(armee.envoyes) == n                                     # jamais deux fois la même alerte


def test_climat_relatif_a_la_normale(armee):
    armee.passer_tout()
    armee.synthese()
    armee.base.ajouter("test", [{"titre": f"Stocks plunge and crash {i}", "source": f"s{i}", "themes": ["wall_street"]}
                                for i in range(40)], armee.repertoire)
    armee.synthese()
    assert LR.signal("global")["valeur"] < 0


def test_analyste_ia_limite_par_heure(armee, monkeypatch):
    monkeypatch.setattr(RS, "IA_PAR_HEURE", 1)
    armee.passer_tout()
    appels = []

    def ia(modele, prompt, n):
        appels.append(prompt)
        return {"1": {"ton": -2, "imp": 3, "actifs": ["BTC", "INCONNU"]}}
    armee.ia = ia
    assert armee.analyser_ia() == 1
    assert armee.analyser_ia() == 0 and len(appels) == 1                # plafond horaire respecté
    r = armee.base.c.execute("SELECT * FROM faits WHERE ia = 1").fetchone()
    assert r["importance"] == 3 and ",BTC," in r["actifs"] and "INCONNU" not in r["actifs"]


# ------------------------------------------------------------------ lecture par les bots de trading
def test_lecture_jamais_bloquante(tmp_path):
    assert LR.signal("global") is None and LR.alerte_grave(["actif:BTC"]) is None and LR.articles() == []
    abime = tmp_path / "abime.db"
    abime.write_bytes(b"ceci n'est pas une base")
    assert LR.signal("global", base=str(abime)) is None and LR.resume(str(abime))["bots"] == 0
    assert "pas encore déployée" in LR.texte_statut()


def test_lecture_pendant_ecriture(armee):
    armee.passer_tout()
    armee.synthese()
    armee.base.c.execute("BEGIN IMMEDIATE")                             # l'armée écrit...
    armee.base.c.execute("UPDATE signaux SET valeur = valeur")
    debut = time.time()
    assert LR.signal("actif:BTC") is not None                           # ... les bots lisent quand même, sans attendre
    assert time.time() - debut < 0.5
    armee.base.c.commit()


def test_statut_telegram(armee):
    armee.passer_tout()
    armee.synthese()
    texte = LR.texte_statut()
    assert "Armée de renseignement" in texte and "infos en 24 h" in texte and "BTC" in texte


def test_veto_du_bot_principal(armee):
    import equipe
    armee.passer_tout()
    armee.synthese()
    ok, raison = equipe.actualite("BTC")
    assert ok is False and raison.startswith("RENSEIGNEMENT")


def test_actifs_suivis_par_nos_bots(monkeypatch):
    json.dump({"positions": {"SOL/USDT": {}}}, open("etat.json", "w"))
    json.dump({"notes": {"AIR.PA": {"nom": "Airbus SE", "note": 4.5}}}, open("marches_etat.json", "w"))
    monkeypatch.setenv("V17_SYMBOLS", "BTC/USDT,ETH/USDT")
    monkeypatch.setattr(config, "MARCHES_PORTEFEUILLE", ["MC.PA"])
    monkeypatch.setattr(config, "MARCHES_SUIVIS", [])
    monkeypatch.setattr(config, "MARCHES_CRYPTOS", ["BTC-EUR"])
    suivis = dict(RS.actifs_suivis())
    assert suivis["SOL"] == "solana" and suivis["BTC"] == "bitcoin" and suivis["ETH"] == "ethereum"
    assert suivis["MC.PA"] == "LVMH" and suivis["AIR.PA"] == "Airbus"
    assert R.requete_actif("Airbus SE") == '"Airbus"'


def test_commande_telegram_et_telecommande(monkeypatch):
    import main
    envoyes = []
    monkeypatch.setattr(main, "commandes", lambda: ["/renseignement"])
    monkeypatch.setattr(main, "alerte", lambda m, important=True: envoyes.append(m))
    main.traiter_commandes(None, {"positions": {}})
    assert "Armée de renseignement" in envoyes[0]
    texte = open(os.path.join(RACINE, "bots"), encoding="utf-8").read()
    for cmd in ("renseignement-test)", "renseignement-demarrer)", "renseignement-arreter)", "renseignement-etat)",
                "renseignement-journal)", "Nice=15", "CPUQuota=50%", "IOSchedulingClass=idle"):
        assert cmd in texte
    assert subprocess.run(["bash", "-n", os.path.join(RACINE, "bots")]).returncode == 0
