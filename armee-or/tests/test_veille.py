"""Veille : calendrier, niveaux, microstructure, COT, actualités, éclair, tendances, bots en fond. Aucun réseau."""
import datetime as dt
import json
import time

import numpy as np

from armee_or import base, chef, veille


class Reponse:
    def __init__(self, donnees=None, contenu=b""):
        self.donnees, self.content = donnees, contenu

    def json(self):
        return self.donnees

    def raise_for_status(self):
        pass


class Session:
    """Répond selon le début de l'adresse demandée."""

    def __init__(self, routes):
        self.routes, self.appels = routes, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.appels.append(url)
        for debut, rep in self.routes.items():
            if url.startswith(debut):
                if isinstance(rep, Exception):
                    raise rep
                return rep
        raise ConnectionError(url)


def _alertes(monkeypatch):
    envoyes = []
    monkeypatch.setattr(veille.telegram, "alerte_rare", lambda cle, texte, *a, **k: envoyes.append((cle, texte)) or True)
    monkeypatch.setattr(veille.telegram, "envoyer", lambda texte, *a, **k: envoyes.append(("envoi", texte)) or True)
    return envoyes


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone(dt.timedelta(hours=-4))).isoformat()


# ------------------------------------------------------------------ calendrier
def test_calendrier_alerte_avant_l_annonce_et_bloque_les_ordres(monkeypatch):
    envoyes = _alertes(monkeypatch)
    maintenant = time.time()
    evts = [{"title": "Non-Farm Employment Change", "country": "USD", "date": _iso(maintenant + 20 * 60), "impact": "High",
             "forecast": "150K", "previous": "142K"},
            {"title": "Minutes", "country": "JPY", "date": _iso(maintenant + 60), "impact": "High"},
            {"title": "Retail Sales", "country": "USD", "date": _iso(maintenant + 3 * 86400), "impact": "Medium"}]
    s = Session({veille.CALENDRIER: Reponse(evts)})
    msg = veille.surveiller_calendrier(s, maintenant)
    assert [e["titre"] for e in base.lire("calendrier")["evenements"]] == ["Non-Farm Employment Change"]
    assert any("Non-Farm" in t and "Paris" in t for _, t in envoyes) and "prochaine" in msg
    assert veille.evenement_proche(maintenant) is None                   # 20 min avant : pas encore bloqué
    assert veille.evenement_proche(maintenant + 10 * 60)["titre"] == "Non-Farm Employment Change"
    assert "Non-Farm" in veille.texte_calendrier()


# ------------------------------------------------------------------ niveaux
def _jours(n=80, depart=4000.0):
    c = depart + np.cumsum(np.random.default_rng(3).normal(0, 20, n))
    return {"ts": np.arange(n) * 86_400_000, "o": c - 3, "h": c + 21, "l": c - 9, "c": c, "v": np.ones(n)}


def test_niveaux_calcules_et_cassure_signalee(monkeypatch):
    envoyes = _alertes(monkeypatch)
    j = _jours()
    niv = veille.calculer_niveaux(j, _jours(120), float(j["c"][-1]))
    noms = {n["nom"] for n in niv}
    assert {"pivot", "R1", "S1", "plus haut d'hier", "chiffre rond"} <= noms and any("Fibonacci" in x for x in noms)
    assert [n["prix"] for n in niv] == sorted(n["prix"] for n in niv)
    r1 = next(n["prix"] for n in niv if n["nom"] == "R1")
    base.ecrire("niveaux", {"ts": time.time(), "niveaux": niv, "dernier_prix": r1 - 1})
    base.ecrire("direct:XAUUSDT", {"prix": r1 + 1, "ts": time.time(), "retard_ms": 10, "source": "x"})
    assert "cassure" in veille.surveiller_niveaux()
    assert any("R1" in t and "hausse" in t for _, t in envoyes)
    assert "Au-dessus" in veille.texte_niveaux()


# ------------------------------------------------------------------ tendances
def test_tendance_haussiere_detectee():
    n = 300
    c = np.linspace(4000, 4400, n) + np.sin(np.arange(n)) * 2
    b = {"ts": np.arange(n) * 3_600_000, "o": c - 1, "h": c + 3, "l": c - 3, "c": c, "v": np.ones(n)}
    t = veille.tendance(b)
    assert t["sens"] == 1 and t["rsi"] > 50


# ------------------------------------------------------------------ microstructure
def test_microstructure_et_alertes_extremes(monkeypatch):
    envoyes = _alertes(monkeypatch)
    s = Session({
        "https://fapi.binance.com/fapi/v1/premiumIndex": Reponse({"lastFundingRate": "0.0008", "markPrice": "4300",
                                                                   "indexPrice": "4299"}),
        "https://fapi.binance.com/futures/data/openInterestHist": Reponse(
            [{"sumOpenInterest": "100", "sumOpenInterestValue": "430000"}] * 12
            + [{"sumOpenInterest": "115", "sumOpenInterestValue": "494500"}]),
        "https://fapi.binance.com/futures/data/globalLongShortAccountRatio": Reponse([{"longAccount": "0.63"}]),
        "https://api.binance.com/api/v3/depth": Reponse({"bids": [["4299.5", "50"], ["4298", "40"]],
                                                         "asks": [["4300.5", "5"], ["4301", "5"]]}),
    })
    texte = veille.surveiller_microstructure(s)
    m = base.lire("microstructure")
    assert m["financement_pct"] == 0.08 and round(m["positions_ouvertes_1h_pct"]) == 15 and m["acheteurs_pct"] == 63
    assert m["desequilibre_pct"] > 60 and "financement" in texte
    assert {c for c, _ in envoyes} >= {"financement", "oi", "carnet"}


def test_microstructure_source_bloquee_n_arrete_rien():
    s = Session({"https://fapi.binance.com": ConnectionError("451"), "https://api.binance.com": ConnectionError("451")})
    m = veille.microstructure(s)
    assert "erreur_perpetuel" in m and "erreur_carnet" in m
    assert "indisponibles" in veille.texte_microstructure(m)


# ------------------------------------------------------------------ COT
def test_cot_extreme_signale_une_fois(monkeypatch):
    envoyes = _alertes(monkeypatch)
    rows = [{"report_date_as_yyyy_mm_dd": f"2026-{1 + i // 4:02d}-{1 + (i % 4) * 7:02d}T00:00:00.000",
             "m_money_positions_long_all": str(100000 + i * 1000), "m_money_positions_short_all": "10000",
             "open_interest_all": "400000"} for i in range(36)]
    s = Session({veille.COT: Reponse(rows)})
    texte = veille.surveiller_cot(s)
    assert base.lire("cot")["rang_3_ans"] == 1.0 and "COT" in texte
    assert len([t for c, t in envoyes if "EXTRÊME" in t]) == 1
    veille.surveiller_cot(s)
    assert len([t for c, t in envoyes if "EXTRÊME" in t]) == 1                  # même rapport : pas de répétition


# ------------------------------------------------------------------ actualités
def _rss(titres):
    items = "".join(f"<item><title>{t}</title><link>https://ex/{i}</link><pubDate>x</pubDate></item>"
                    for i, t in enumerate(titres))
    return f"<rss><channel>{items}</channel></rss>".encode()


def test_actualites_themes_et_pas_de_rafale_au_demarrage(monkeypatch):
    envoyes = _alertes(monkeypatch)
    s = Session({veille.FLUX_ACTUS: Reponse(contenu=_rss(["Gold hits record high as Fed signals rate cut", "Calm day"]))})
    veille.surveiller_actualites(s)
    assert not envoyes                                                           # premier passage : aucun envoi
    items = base.lire("actualites")["titres"]
    assert set(items[0]["themes"]) >= {"Fed / taux", "record"} and items[1]["themes"] == []
    s.routes[veille.FLUX_ACTUS] = Reponse(contenu=_rss(["Gold hits record high as Fed signals rate cut", "Calm day",
                                                        "Missile attack lifts gold"]))
    veille.surveiller_actualites(s)
    assert len(envoyes) == 1 and "Missile" in envoyes[0][1] and "géopolitique" in envoyes[0][1]


# ------------------------------------------------------------------ éclair
def test_eclair_mouvement_brutal(monkeypatch):
    envoyes = _alertes(monkeypatch)
    base.ecrire("eclair:sigma", {"ts": time.time(), "v": 0.02})                  # 0,02 % par minute d'habitude
    e = veille.Eclair()
    t0 = time.time()
    base.ecrire("direct:XAUUSDT", {"prix": 4300.0, "ts": t0, "retard_ms": 5, "source": "x"})
    e.observer(t0 - 70)
    base.ecrire("direct:XAUUSDT", {"prix": 4320.0, "ts": time.time(), "retard_ms": 5, "source": "x"})
    msg = e.observer(t0)
    assert "+0.47 % en 1 min" in msg and any("Mouvement brutal" in t for _, t in envoyes)


# ------------------------------------------------------------------ bots en fond
def test_un_bot_lent_ne_bloque_pas_le_chef():
    lent = chef.Bot("lent", "x", 1, lambda c: time.sleep(0.5) or "ok", fond=True)
    rapide = chef.Bot("rapide", "x", 1, lambda c: "ok")
    fake = type("Chef", (), {"bots": [lent, rapide], "pause": False, "tour": chef.Chef.tour,
                             "attendre": chef.Chef.attendre})()
    t = time.time()
    fake.tour()
    assert time.time() - t < 0.3 and rapide.ok == 1                               # le rapide n'a pas attendu le lent
    lent.prochaine = 0
    fake.tour()                                                                   # encore au travail : pas de 2e fil
    fake.attendre()
    assert lent.ok == 1


def test_texte_veille_complet():
    texte = veille.texte_veille()
    for mot in ("Tendances", "Niveaux", "Microstructure", "COT", "Calendrier", "Actualités"):
        assert mot in texte or mot.lower() in texte.lower(), mot
    json.dumps(texte)


def test_niveaux_voisins_fusionnes_et_titres_en_double_ecartes():
    j = _jours()
    h4 = {k: v.copy() for k, v in _jours(120).items()}
    niv = veille.calculer_niveaux(j, h4, float(j["c"][-1]))
    prix = [n["prix"] for n in niv]
    assert all(b - a > float(j["c"][-1]) * 0.0005 for a, b in zip(prix, prix[1:]))
    s = Session({veille.FLUX_ACTUS: Reponse(contenu=_rss(["Gold falls - Yahoo", "Gold falls - Kitco", "Other"]))})
    assert [i["titre"] for i in veille.actualites(s)] == ["Gold falls - Yahoo", "Other"]
