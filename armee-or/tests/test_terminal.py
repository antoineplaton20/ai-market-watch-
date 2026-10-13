"""Terminal de l'or : chaque écran s'affiche, tient dans la largeur, sans réseau."""
import time

import numpy as np

from armee_or import apprentissage as A, base, chef, donnees, telegram, terminal as T


def _remplir(maintenant):
    minute = int(maintenant // 60 * 60 * 1000)
    n = 2000
    ts = minute - np.arange(n)[::-1] * 60_000
    c = 4100 + np.cumsum(np.random.default_rng(3).normal(0, 0.8, n))
    donnees.inserer("XAUUSDT", "1m", [[t, x, x + 1, x - 1, x, 1.0] for t, x in zip(ts, c)])
    donnees.consolider("XAUUSDT")
    base.ecrire("direct:XAUUSDT", {"prix": float(c[-1]), "ts": maintenant, "retard_ms": 80,
                                   "source": "Binance XAUUSDT (WebSocket)"})
    base.ecrire("direct:MT5", {"prix": float(c[-1]), "bid": float(c[-1]) - 0.19, "ask": float(c[-1]) + 0.19,
                               "ts": maintenant, "retard_ms": 50, "source": "MetaTrader 5 XAUUSD (démo)"})
    base.ecrire("niveaux", {"ts": maintenant, "dernier_prix": float(c[-1]), "niveaux": [
        {"nom": "creux 1 j", "prix": float(c[-1]) - 25}, {"nom": "chiffre rond", "prix": float(c[-1]) - 8},
        {"nom": "sommet 4 h récent", "prix": float(c[-1]) + 6}, {"nom": "sommet 1 j", "prix": float(c[-1]) + 30}]})
    base.ecrire("tendances", {"ts": maintenant, "alignement": 2, "unites": {
        tf: {"sens": s, "rsi": 55.0, "adx": 22.0, "force": "faible"} for tf, s in
        (("15m", 1), ("1h", 1), ("4h", -1), ("1d", 1))}})
    base.ecrire("marches", {"ts": maintenant, "contexte": 0.3, "ratio_or_argent": 79.4, "marches": [
        {"ticker": "DX-Y.NYB", "nom": "Dollar (DXY)", "dernier": 98.2, "var_1j": -0.3, "var_5j": -1.1,
         "correlation_60j": -0.45},
        {"ticker": "SI=F", "nom": "Argent", "dernier": 52.1, "var_1j": 1.2, "var_5j": 3.0, "correlation_60j": 0.81},
        {"ticker": "EURUSD=X", "nom": "Euro / dollar", "dernier": 1.12, "var_1j": 0.1, "var_5j": 0.4,
         "correlation_60j": 0.3},
        {"ticker": "^VIX", "nom": "Peur (VIX)", "dernier": 15.2, "var_1j": 0.0, "var_5j": 2.0, "correlation_60j": None}]})
    base.ecrire("microstructure", {"ts": maintenant, "financement_pct": 0.01, "acheteurs_pct": 62.0,
                                   "desequilibre_pct": 12.0, "positions_ouvertes_1h_pct": -0.4})
    base.ecrire("calendrier", {"ts": maintenant, "evenements": [
        {"titre": "CPI m/m", "ts": maintenant + 3 * 3600, "prevision": "0.3%", "precedent": "0.4%"},
        {"titre": "Unemployment Claims", "ts": maintenant + 600, "prevision": "230K", "precedent": "225K"}]})
    base.ecrire("actualites", {"ts": maintenant, "titres": [
        {"titre": "Gold price holds critical $4,100 support, but can it break $4,200 as inflation risks loom? - Kitco",
         "lien": "x", "date": "", "themes": ["inflation"]},
        {"titre": "Gold eases on strong dollar - Reuters", "lien": "y", "date": "", "themes": []}]})
    base.ecrire("cot", {"ts": maintenant, "date": "2026-10-07", "net": 180000.0, "net_pct_oi": 35.0,
                        "rang_3_ans": 0.9, "variation": -5000.0})
    base.ecrire("mt5:permis", {"1h": {"ok": False}, "4h": {"ok": False}, "1d": {"ok": True}})
    base.ecrire("tresor", {"date": "2026-10-09", "reel_10a": 1.91, "reel_10a_5j": -0.06, "nominal_10a": 4.12,
                           "nominal_10a_5j": 0.02, "inflation_10a": 2.21, "inflation_10a_5j": 0.08,
                           "pente_10_2": 0.44, "pente_10_2_5j": None})
    base.ecrire("chef", {"ts": maintenant, "pause": False, "bots": [{"nom": "a", "echecs_suite": 0},
                                                                     {"nom": "b", "echecs_suite": 2}]})
    return c


def test_tous_les_ecrans_tiennent_dans_la_largeur():
    m = time.time()
    _remplir(m)
    for w in (36, 60, 100):
        for code in T.ECRANS:
            texte = T.rendu(code, w=w, couleur=True)
            for ligne in texte.split("\n"):
                assert T.visible(ligne) <= w, (code, w, ligne)
    go = T.rendu("go", w=60, couleur=False)
    for attendu in ("TERMINAL OR", "NIVEAUX", "TENDANCES", "MARCHÉS", "FLUX BINANCE", "AGENDA", "ACTUALITÉS",
                    "ARMÉE", "permis 1h ✖ 4h ✖ 1d ✔", "bots 1/2 sains", "MT5", "écart 0.38 $", "OR/ARG 79.4", "TAUX RÉEL 10A 1.91"):
        assert attendu in go, attendu
    assert "\033[" not in go and "\033[" in T.rendu("go", w=60, couleur=True)


def test_graphique_et_codes():
    _remplir(time.time())
    lignes = T.graphique(np.linspace(100, 200, 500), 40, 6)
    assert len(lignes) == 6 and all(T.visible(x) <= 40 for x in lignes)
    assert lignes[0].rstrip().endswith("200.00") and lignes[-1].rstrip().endswith("100.00")
    assert "█" in lignes[-1] and "pas encore" in T.graphique([1.0], 40)[0]
    gp = T.rendu("gp", "15m", w=60, couleur=False)
    assert "GP  XAU/USD  15m" in gp and "ATR 14" in gp
    assert "GP  XAU/USD  1h" in T.rendu("gp", "nimporte", w=60, couleur=False)
    assert "CODES" in T.rendu("inconnu", w=60, couleur=False)


def test_marche_ouvert_et_seances():
    import calendar
    samedi = calendar.timegm((2026, 10, 10, 12, 0, 0))
    mardi_midi_utc = calendar.timegm((2026, 10, 13, 12, 0, 0))
    pause = calendar.timegm((2026, 10, 13, 21, 30, 0))                  # 17 h 30 à New York
    assert T.marche_ouvert(samedi) == (False, "FERMÉ (week-end)")
    assert T.marche_ouvert(mardi_midi_utc)[0] and T.marche_ouvert(pause) == (False, "PAUSE quotidienne")
    assert dict(T.seances(mardi_midi_utc)) == {"Asie": False, "Londres": True, "New York": True}


def test_valeur_relative_or_argent():
    t = 1_500_000_000 + np.arange(400) * 86400
    A.enregistrer("yahoo:or_comex:1d", [(int(x), 2000.0 + i) for i, x in enumerate(t)])
    A.enregistrer("yahoo:argent:1d", [(int(x), 25.0) for x in t])
    base.ecrire("marches", {"ratio_or_argent": 95.0, "marches": []})
    rv = T.rendu("rv", w=60, couleur=False)
    assert "actuel 95.0" in rv and "rang" in rv and "BON MARCHÉ" in rv


def test_ecrans_sur_telegram_en_police_fixe(monkeypatch):
    _remplir(time.time())
    envois = []
    monkeypatch.setattr(chef.telegram, "envoyer", lambda t, *a, **k: envois.append((t, k)) or True)
    monkeypatch.setattr(chef.telegram, "commandes", lambda *a, **k: ["/or_go", "/or_gp_15m"])
    chef.bot_commandes(type("Chef", (), {"pause": False, "bots": []})())
    (go, k1), (gp, k2) = envois
    assert k1.get("mono") and k2.get("mono") and "TERMINAL OR" in go and "GP  XAU/USD  15m" in gp
    assert all(len(x) <= chef.TELEGRAM_COLONNES for x in go.split("\n"))


def test_envoi_mono_echappe_le_html(monkeypatch):
    from armee_or import config
    envoye = {}

    class S:
        def post(self, url, json=None, timeout=None):
            envoye.update(json)
    monkeypatch.setattr(config, "TELEGRAM_JETON", "x")
    monkeypatch.setattr(config, "TELEGRAM_CHAT", "1")
    assert telegram.envoyer("a < b & c", session=S(), mono=True)
    assert envoye["parse_mode"] == "HTML" and "<pre>a &lt; b &amp; c</pre>" in envoye["text"]



def test_tresor_dans_les_marches_lies():
    _remplir(time.time())
    for w in (36, 80):
        wei = T.rendu("wei", w=w, couleur=False)
        assert "TRÉSOR US" in wei and "Taux réel 10 ans 1.91 %" in wei and "Inflation attendue 10 ans 2.21 %" in wei



def test_annonces_a_la_meme_heure_regroupees():
    m = time.time()
    _remplir(m)
    base.ecrire("calendrier", {"ts": m, "evenements": [
        {"titre": t, "ts": m + 7200, "prevision": p, "precedent": ""} for t, p in
        (("Core CPI m/m", "0.2%"), ("Core CPI y/y", "2.5%"), ("CPI m/m", "0.6%"))]})
    go = T.rendu("go", w=72, couleur=False)
    assert go.count("dans 2 h") == 1 and "Core CPI y/y (prév. 2.5%)" in go and "CPI m/m (prév. 0.6%)" in go
