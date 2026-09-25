"""Veille marchés mondiaux : presse, notes de 0 à 5, moments d'achat / vente, Telegram — sans réseau."""
import datetime as dt
import os

import numpy as np
import pandas as pd
import pytest

import config
import veille_marches as V
from moteurs import notation as N
from moteurs import sources_marches as S

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAINTENANT = dt.datetime.now(dt.timezone.utc)


def rss(*titres, age_h=1):
    date = (MAINTENANT - dt.timedelta(hours=age_h)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = "".join(f"<item><title>{t}</title><link>https://x/{i}</link><pubDate>{date}</pubDate></item>"
                    for i, t in enumerate(titres))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'.encode()


ATOM = f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Fed signals rate cut as inflation cools</title><link href="https://a/1"/>
<updated>{MAINTENANT.strftime('%Y-%m-%dT%H:%M:%SZ')}</updated></entry></feed>""".encode()


def serie(tendance, n=300, depart=100.0):
    pas = {"hausse": 0.004, "baisse": -0.004, "plat": 0.0}[tendance]
    bruit = np.sin(np.arange(n) / 3) * 0.004
    c = depart * np.cumprod(1 + pas + bruit)
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)


class FauxYahoo:
    def __init__(self, tendances=None, info=None):
        self.tendances = tendances or {}
        self.infos = info or {}
        self.appels = []

    def historique(self, ticker, periode="1y"):
        self.appels.append(ticker)
        t = self.tendances.get(ticker, "hausse")
        return None if t is None else serie(t)

    def info(self, ticker):
        return self.infos.get(ticker, {})

    def news(self, ticker):
        return [{"content": {"title": f"{ticker} soars after record results", "pubDate":
                             MAINTENANT.strftime('%Y-%m-%dT%H:%M:%SZ'), "provider": {"displayName": "Reuters"}}}]


INFO_BONNE = {"quoteType": "EQUITY", "recommendationMean": 1.6, "recommendationKey": "buy",
              "numberOfAnalystOpinions": 25, "targetMeanPrice": 400, "currentPrice": 300, "revenueGrowth": 0.12,
              "earningsGrowth": 0.15, "profitMargins": 0.2, "forwardPE": 20, "sector": "Technology",
              "longName": "Super Tech", "currency": "USD"}
INFO_MAUVAISE = {"quoteType": "EQUITY", "recommendationMean": 4.2, "recommendationKey": "sell",
                 "numberOfAnalystOpinions": 10, "targetMeanPrice": 50, "currentPrice": 60, "revenueGrowth": -0.1,
                 "earningsGrowth": -0.3, "profitMargins": -0.05, "forwardPE": 80, "sector": "Energy"}


def lire_flux_ok(url):
    if "federalreserve" in url:
        raise ConnectionError("injoignable")
    if "ecb" in url:
        return ATOM
    return rss("Oil prices surge as OPEC cuts output", "Le CAC 40 recule, la BCE maintient ses taux",
               "Goldman Sachs relève son objectif de cours sur LVMH", "Wheat prices jump on drought fears",
               "Guerre commerciale : nouveaux droits de douane sur l'acier")


@pytest.fixture(autouse=True)
def reglages(monkeypatch):
    for nom, v in {"MARCHES_PORTEFEUILLE": [], "MARCHES_SUIVIS": [], "MARCHES_CRYPTOS": ["BTC-EUR"],
                   "MARCHES_DEVISES": ["EURUSD=X"], "MARCHES_INDICES": ["^FCHI"], "MARCHES_PAR_TOUR": 50,
                   "MARCHES_RAPPORT_HEURE": 0, "ANTHROPIC_API_KEY": ""}.items():
        monkeypatch.setattr(config, nom, v)
    monkeypatch.setattr(V, "GRANDES_VALEURS", ["MC.PA", "XOM"])


# ------------------------------------------------------------------ presse
def test_flux_rss_atom_et_themes():
    a = S.analyser_flux(rss("Nvidia unveils new AI chip", "Prix du blé : la sécheresse inquiète"), "src", "economie")
    assert [x["themes"] for x in a] == [["industrie", "tech"], ["alimentaire"]]
    b = S.analyser_flux(ATOM, "BCE", "banques_centrales")
    assert b[0]["titre"].startswith("Fed signals") and "banques_centrales" in b[0]["themes"]
    assert abs(b[0]["ts"] - MAINTENANT.timestamp()) < 5


def test_collecte_tolere_les_sources_en_panne_et_retire_les_doublons():
    articles, etat = S.collecter(lire=lire_flux_ok, pause_s=0)
    assert etat["Réserve fédérale (Fed)"].startswith("ko") and etat["BCE"].startswith("ok")
    titres = [a["titre"] for a in articles]
    assert len(titres) == len(set(titres)) == 6                       # 5 titres répétés partout + 1 Atom


def test_vieux_titres_ignores():
    articles, _ = S.collecter(flux=[("economie", "vieux", "u")], lire=lambda u: rss("Old news", age_h=100), pause_s=0)
    assert articles == []


def test_actualites_yahoo_ancien_et_nouveau_format():
    ts = MAINTENANT.timestamp()
    brut = [{"title": "Ancien format", "providerPublishTime": ts, "publisher": "AFP"},
            {"content": {"title": "Nouveau format", "pubDate": MAINTENANT.strftime('%Y-%m-%dT%H:%M:%SZ'),
                         "provider": {"displayName": "Reuters"}}}]
    assert [(a["titre"], a["source"]) for a in S.actus_yahoo(brut)] == [("Ancien format", "AFP"),
                                                                        ("Nouveau format", "Reuters")]


# ------------------------------------------------------------------ notes
def test_note_haute_pour_un_bon_dossier_basse_pour_un_mauvais():
    bon = N.noter(serie("hausse"), INFO_BONNE, 1.5, 1, detenu=False)
    mauvais = N.noter(serie("baisse"), INFO_MAUVAISE, -1.5, -1, detenu=False)
    assert bon["note"] >= 4 and mauvais["note"] <= 1.5
    assert mauvais["action"] == "ÉVITER"
    assert 0 <= mauvais["note"] <= bon["note"] <= 5 and (bon["note"] * 2).is_integer()


def test_avis_absents_retires_du_calcul():
    r = N.noter(serie("hausse"), {}, None, None)                    # crypto : ni analystes, ni comptes, ni presse
    assert r is not None and list(k for k, v in r["avis"].items() if v is not None) == ["technique"]
    assert N.noter(serie("hausse").iloc[:30], {}, None, None) is None      # historique trop court : pas de note


def test_moments_acheter_attendre_vendre():
    ind = N.indicateurs(serie("hausse"))
    assert N.decision(4.5, {**ind, "rsi": 55}, detenu=False)["action"] == "ACHETER"
    assert N.decision(4.5, {**ind, "rsi": 78}, detenu=False)["action"] == "ATTENDRE UN REPLI"
    d = N.decision(1.5, ind, detenu=True)
    assert d["action"] == "VENDRE / ALLÉGER" and d["urgence"]
    assert N.decision(4.5, ind, detenu=True)["action"] == "GARDER"
    achat = N.decision(4.5, {**ind, "rsi": 55}, detenu=False, cible=ind["close"] * 1.3)
    assert achat["stop"] < ind["close"] < achat["objectif"]


def test_analystes_consensus_yahoo():
    assert N.note_analystes({"recommendationMean": 1.0, "numberOfAnalystOpinions": 20})[0] == 5
    assert N.note_analystes({"recommendationMean": 5.0, "numberOfAnalystOpinions": 20})[0] == 0
    assert N.note_analystes({"recommendationMean": 1.0, "numberOfAnalystOpinions": 1})[0] is None


def test_etoiles():
    assert N.etoiles(4.5) == "★★★★½" and N.etoiles(0) == "☆☆☆☆☆" and N.etoiles(5) == "★★★★★"


# ------------------------------------------------------------------ briefing
def test_briefing_sans_ia_lecture_par_mots_cles():
    articles, sources = S.collecter(lire=lire_flux_ok, pause_s=0)
    b = V.faire_briefing(articles, sources)
    assert not b["ia"] and b["sources_ok"] == b["sources_total"] - 1 and -2 <= b["climat"] <= 2
    assert "energie" in b["themes"] and "Energy" in b["secteurs"]


def test_briefing_avec_ia_valeurs_bornees():
    articles, sources = S.collecter(lire=lire_flux_ok, pause_s=0)
    reponse = {"climat": -5, "resume": "Tensions.", "themes": {"energie": {"tendance": 2, "fait_cle": "OPEP"},
                                                               "inconnu": {"tendance": 1}},
               "secteurs": {"Energy": 2, "Martiens": 1}, "risques": ["a", "b", "c", "d"], "opportunites": []}
    b = V.faire_briefing(articles, sources, ia=lambda m, p, n: reponse)
    assert b["ia"] and b["climat"] == -2 and list(b["themes"]) == ["energie"] and b["secteurs"] == {"Energy": 2}
    assert len(b["risques"]) == 3
    assert V.faire_briefing(articles, sources, ia=lambda m, p, n: None)["ia"] is False    # IA en panne : secours


# ------------------------------------------------------------------ service
def test_un_tour_complet(monkeypatch):
    envoyes = []
    monkeypatch.setattr(V, "alerte", lambda m, important=True: envoyes.append((m, important)))
    monkeypatch.setattr(config, "MARCHES_PORTEFEUILLE", ["XOM"])
    y = FauxYahoo({"XOM": "baisse"}, {"XOM": {**INFO_MAUVAISE, "longName": "Exxon"}, "MC.PA": INFO_BONNE})
    etat = V.charger_etat()
    V.un_tour(etat, y, lire_flux=lire_flux_ok)
    assert etat["briefing"]["n_titres"] == 6 and "^FCHI" in etat["reperes"]
    assert set(etat["notes"]) == {"XOM", "BTC-EUR", "MC.PA"}
    assert etat["notes"]["XOM"]["detenu"] and etat["notes"]["XOM"]["action"] == "VENDRE / ALLÉGER"
    assert any("Un de tes titres" in m and important for m, important in envoyes)        # alerte de vente
    assert any("Rapport marchés du jour" in m for m, _ in envoyes)
    n = len(envoyes)
    V.un_tour(etat, y, lire_flux=lire_flux_ok)                                             # rien de nouveau
    assert len(envoyes) == n
    V.sauver_etat(etat)
    texte = V.texte_statut()
    assert "Climat mondial" in texte and "Tes titres" in texte and "Exxon" in texte


def test_demande_note_par_telegram(monkeypatch):
    envoyes = []
    monkeypatch.setattr(V, "alerte", lambda m, important=True: envoyes.append(m))
    etat = V.charger_etat()
    V.sauver_etat(etat)
    assert "lancée" in V.demander_note("AAPL")
    V.un_tour(etat, FauxYahoo(info={"AAPL": INFO_BONNE}), lire_flux=lire_flux_ok)
    assert any("(AAPL)" in m and "/5" in m for m in envoyes)
    assert N.sentiment_lexical(["Fed signals rate cut as inflation cools"]) > 0
    V.sauver_etat(etat)
    assert "/5" in V.demander_note("aapl")                               # note fraîche : réponse immédiate


def test_resolution_des_noms(monkeypatch):
    monkeypatch.setattr(V, "_instruments_tr", lambda: {"MC.PA": {"isin": "FR0000121014", "nom": "LVMH MOET HENNESSY"}})
    monkeypatch.setattr(config, "MARCHES_CRYPTOS", ["BTC-EUR", "ETH-EUR"])
    assert V.resoudre("lvmh") == ("MC.PA", "LVMH MOET HENNESSY")
    assert V.resoudre("FR0000121014") == ("MC.PA", "LVMH MOET HENNESSY")
    assert V.resoudre("bitcoin")[0] == "BTC-EUR" and V.resoudre("eth")[0] == "ETH-EUR"
    assert V.resoudre("AAPL") == ("AAPL", "AAPL")
    assert V.resoudre("US0000000000", reseau=False) is None


def test_commandes_telegram_du_bot_principal(monkeypatch):
    import main
    envoyes = []
    monkeypatch.setattr(main, "commandes", lambda: ["/marches", "/briefing", "/note AAPL", "/note"])
    monkeypatch.setattr(main, "alerte", lambda m, important=True: envoyes.append(m))
    main.traiter_commandes(None, {"positions": {}})
    assert "Climat mondial" in envoyes[0] or "presse" in envoyes[0]
    assert "AAPL" in envoyes[2] and "Écris" in envoyes[3]


def test_telecommande_et_service():
    import subprocess
    texte = open(os.path.join(RACINE, "bots"), encoding="utf-8").read()
    for cmd in ("marches-test)", "marches-demarrer)", "marches-arreter)", "marches-journal)", "marches-note)",
                "marches-portefeuille|marches-suivre)", "equipe-bots-marches"):
        assert cmd in texte
    assert subprocess.run(["bash", "-n", os.path.join(RACINE, "bots")]).returncode == 0
