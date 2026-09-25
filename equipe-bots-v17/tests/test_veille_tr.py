"""Veille Trade Republic : univers officiel, Yahoo (simulé), 4 unités, coûts, signaux et suivi — sans réseau."""
import os
import time

import numpy as np
import pandas as pd
import pytest

import config
import veille_tr as V
from moteurs import tr_analyse as A
from moteurs import tr_univers as U
from moteurs import tr_yahoo as Y

ICI = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(ICI, "donnees", "univers_test.pdf")
H = 3_600_000


# ------------------------------ outils ------------------------------
def serie(minutes, n, fin_ms, pente=0.001, depart=100.0, ouverture_h=8, fermeture_h=17, bruit=0.0005, seed=1):
    """Bougies de bourse (séances 8 h - 17 h UTC, jours ouvrés) finissant juste avant fin_ms."""
    rng = np.random.default_rng(seed)
    pas = minutes * 60_000
    t = (fin_ms // pas) * pas - pas
    ts = []
    while len(ts) < n:
        d = pd.Timestamp(t, unit="ms", tz="UTC")
        if d.weekday() < 5 and (minutes >= 1440 or ouverture_h <= d.hour < fermeture_h):
            ts.append(t)
        t -= pas
    ts = ts[::-1]
    c = depart * np.cumprod(1 + pente + rng.normal(0, bruit, n))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"t": np.array(ts, dtype="int64"), "o": o, "h": np.maximum(o, c) * 1.001,
                         "l": np.minimum(o, c) * 0.999, "c": c, "v": np.full(n, 10_000.0)})


def maintenant_seance():
    """Un mardi 14 h 02 UTC : bourse ouverte, dernière bougie 5 min close à 14 h 00."""
    return pd.Timestamp("2026-09-22 14:02", tz="UTC").value // 1_000_000


# ------------------------------ univers ------------------------------
def test_isin_cle_de_controle():
    assert U.isin_valide("US67066G1040") and U.isin_valide("IE00B4L5Y983") and U.isin_valide("DE000ENER6Y0")
    assert not U.isin_valide("US67066G1041") and not U.isin_valide("NVIDIA")


def test_pdf_officiel_lu_et_ecrit(monkeypatch):
    monkeypatch.setattr(config, "TR_UNIVERS_MIN", 3)
    open("univers_trade_republic.csv", "w").write("symbol,kind\nUS0000000000,stock\n")    # ancienne liste manuelle
    r = U.mettre_a_jour(pdf_local=PDF)
    assert r["ok"] and r["n"] == 7 and r["par_type"] == {"stock": 5, "etf": 2}
    assert os.path.exists("univers_trade_republic_manuel.csv")                           # sauvegardée, pas perdue
    lus = {i["isin"]: i for i in U.lire()}
    assert "US67066G1041" not in lus and lus["IE00B4L5Y983"]["kind"] == "etf"
    from moteurs.instrument_registry import InstrumentRegistry
    reg = InstrumentRegistry()
    assert reg.load_trade_republic_file("univers_trade_republic.csv") == 7                 # le registre v12 le lit


def test_lecture_ratee_ne_remplace_pas_un_univers_valide(monkeypatch):
    monkeypatch.setattr(config, "TR_UNIVERS_MIN", 3)
    assert U.mettre_a_jour(pdf_local=PDF)["ok"]
    monkeypatch.setattr(config, "TR_UNIVERS_MIN", 1000)
    r = U.mettre_a_jour(pdf_local=PDF)
    assert not r["ok"] and "ancien univers conservé" in r["erreur"] and len(U.lire()) == 7


def test_telechargement_essaie_les_sources_dans_l_ordre(monkeypatch):
    import requests

    class Rep:
        def __init__(self, code, contenu):
            self.status_code, self.content = code, contenu
    reponses = iter([Rep(403, b""), Rep(200, b"%PDF-1.4 ...")])
    monkeypatch.setattr(requests, "get", lambda *a, **k: next(reponses))
    contenu, url, erreurs = U.telecharger(["https://x/a.pdf", "https://x/b.pdf"])
    assert contenu.startswith(b"%PDF") and url.endswith("b.pdf") and "403" in erreurs[0]


# ------------------------------ Yahoo ------------------------------
def test_choix_de_la_cotation_yahoo():
    action = [{"symbol": "NVDA", "quoteType": "EQUITY", "exchange": "NMS"},
              {"symbol": "NVD.F", "quoteType": "EQUITY", "exchange": "FRA"},
              {"symbol": "NVDAX", "quoteType": "EQUITY", "exchange": "PNK"}]
    assert Y.choisir_cotation(action, "stock")["symbol"] == "NVDA"
    assert Y.choisir_cotation(list(reversed(action)), "stock")["symbol"] == "NVDA"       # OTC et régional écartés
    etf = [{"symbol": "SWDA.L", "quoteType": "ETF"}, {"symbol": "EUNL.F", "quoteType": "ETF"},
           {"symbol": "EUNL.DE", "quoteType": "ETF"}]
    assert Y.choisir_cotation(etf, "etf")["symbol"] == "EUNL.DE"
    assert Y.choisir_cotation([{"symbol": "X.ZZ", "quoteType": "EQUITY"}], "stock") is None  # devise inconnue
    assert Y.devise("RR.L") == "GBp" and Y.devise("7203.T") == "JPY" and Y.devise("BRK-B") == "USD"


def test_correspondance_cache_et_limite_yahoo():
    univers = [{"isin": f"ISIN{i}", "nom": "", "kind": "stock"} for i in range(5)] + \
              [{"isin": "OBLIG", "nom": "", "kind": "bond"}]
    appels = []

    def chercher(isin, genre):
        appels.append(isin)
        if isin == "ISIN3":
            raise Y.LimiteYahoo("Too Many Requests")
        return None if isin == "ISIN1" else {"ticker": isin.lower(), "devise": "USD"}
    cache = {}
    with pytest.raises(Y.LimiteYahoo):
        Y.cartographier(univers, cache, budget_s=60, pause_s=0, chercher=chercher)
    assert set(cache) == {"ISIN0", "ISIN1", "ISIN2"} and cache["ISIN1"]["ticker"] is None
    r = Y.cartographier(univers, cache, budget_s=60, pause_s=0,
                        chercher=lambda i, g: {"ticker": i.lower(), "devise": "USD"})
    assert r["restants"] == 0 and "OBLIG" not in cache                         # obligations : pas sur Yahoo
    assert appels.count("ISIN0") == 1                                          # le cache évite de redemander


def test_normalisation_et_telechargement_par_lots():
    idx = pd.date_range("2026-09-22 13:30", periods=3, freq="1h", tz="America/New_York")
    brut = pd.DataFrame({"Open": [1, 2, 3], "High": [2, 3, 4], "Low": [0.5, 1, 2], "Close": [1.5, 2.5, 3.5],
                         "Volume": [10, 20, None]}, index=idx)
    d = Y.normaliser(brut)
    assert list(d.columns) == ["t", "o", "h", "l", "c", "v"] and d["v"].iloc[-1] == 0
    assert d["t"].iloc[0] == pd.Timestamp("2026-09-22 13:30", tz="America/New_York").value // 1_000_000

    def faux(paquet, **k):
        return pd.concat({t: brut for t in paquet}, axis=1)                    # colonnes (titre, champ)
    res = Y.telecharger(["AAA", "BBB", "CCC"], "5d", "1h", lot=2, pause_s=0, telechargeur=faux)
    assert set(res) == {"AAA", "BBB", "CCC"} and len(res["CCC"]) == 3


def test_limite_yahoo_detectee():
    import logging

    def bloque(paquet, **k):
        logging.getLogger("yfinance").error("['AAA']: YFRateLimitError('Too Many Requests. Rate limited.')")
        return pd.DataFrame()
    with pytest.raises(Y.LimiteYahoo):
        Y.telecharger(["AAA"], "5d", "1h", telechargeur=bloque)
    with pytest.raises(Y.LimiteYahoo):                                          # 5 titres, zéro donnée
        Y.telecharger([f"T{i}" for i in range(5)], "5d", "1h", telechargeur=lambda p, **k: pd.DataFrame())
    assert Y.telecharger(["INCONNU"], "5d", "1h", telechargeur=lambda p, **k: pd.DataFrame()) == {}


def test_taux_de_change_et_sous_unites():
    def faux(paquet, **k):
        return pd.concat({t: pd.DataFrame({"Close": [1.10 if "USD" in t else 0.85]},
                                          index=pd.DatetimeIndex(["2026-09-22"])) for t in paquet}, axis=1)
    taux = Y.taux_de_change({"USD", "GBp", "EUR"}, telechargeur=faux)
    assert taux["EUR"] == 1 and taux["USD"] == pytest.approx(1.10) and taux["GBp"] == pytest.approx(85.0)


# ------------------------------ analyse ------------------------------
def test_bougie_en_cours_jamais_utilisee():
    fin = maintenant_seance()
    d5 = serie(5, 400, fin)
    en_cours = pd.DataFrame({"t": [fin - 2 * 60_000], "o": [1.0], "h": [1.0], "l": [1.0], "c": [1.0], "v": [1.0]})
    a = A.analyser_titre(pd.concat([d5, en_cours], ignore_index=True), serie(60, 400, fin), fin)
    assert a["ok"] and a["prix"] == pytest.approx(d5["c"].iloc[-1])              # la bougie à 1.0 est ignorée


def test_regroupement_ne_garde_que_les_bougies_completes():
    fin = maintenant_seance()
    d5 = A.fermees(serie(5, 100, fin), 5, fin)
    r = A.regrouper(d5, 15, float(d5["t"].iloc[-1]) + 5 * 60_000)
    assert (r["t"] + 15 * 60_000 <= d5["t"].iloc[-1] + 5 * 60_000).all()
    assert r["v"].iloc[-1] == 30_000                                           # 3 bougies de 5 min


def test_tendance_haussiere_4_unites_et_signal():
    fin = maintenant_seance()
    a = A.analyser_titre(serie(5, 400, fin), serie(60, 400, fin, pente=0.002), fin)
    assert a["ok"] and a["donnees_ok"] and all(a["checks"].values())
    opp = A.opportunite(a, montant=5000)
    assert opp.allowed and opp.net_potential_pct > 0


def test_tendance_baissiere_aucun_signal():
    fin = maintenant_seance()
    a = A.analyser_titre(serie(5, 400, fin, pente=-0.001), serie(60, 400, fin, pente=-0.002), fin)
    assert a["ok"] and not any(a["checks"].values()) and not A.opportunite(a, 5000).allowed


def test_donnees_perimees_aucun_signal():
    fin = maintenant_seance()
    a = A.analyser_titre(serie(5, 400, fin), serie(60, 400, fin), fin + 3 * H)   # 3 h sans nouvelle bougie
    assert a["ok"] and not a["donnees_ok"] and not A.opportunite(a, 5000).allowed


def test_frais_fixes_bloquent_les_petits_montants():
    fin = maintenant_seance()
    a = A.analyser_titre(serie(5, 400, fin), serie(60, 400, fin, pente=0.002), fin)
    petit, gros = A.opportunite(a, montant=20), A.opportunite(a, montant=5000)
    assert petit.cost_pct > 10 and not petit.allowed and "cost_margin" in petit.reasons and gros.allowed


def test_tri_journalier_en_euros():
    fin = maintenant_seance()
    d = serie(1440, 130, fin, pente=0.003)
    r = A.journalier(d, 1.10, fin)                                             # USD : 1,10 $ pour 1 €
    brut = float((A.fermees(d, 1440, fin)["c"] * d["v"].iloc[0]).tail(20).median())
    assert r["haussier"] and r["liq"] == pytest.approx(brut / 1.10)
    assert A.journalier(d, None, fin) is None                                  # devise inconnue : écarté


def _position(prix=100.0, atr=1.0):
    opp = type("O", (), {"cost_pct": 0.6, "net_potential_pct": 5.0, "gross_potential_pct": 6.0})()
    a = {"prix": prix, "atr": atr}
    return A.nouvelle_position({"isin": "X", "nom": "Titre", "ticker": "T", "devise": "USD"}, a, opp, time.time())


def _lecture(prix, haut=None, bas=None, baissier=False):
    return {"ok": True, "donnees_ok": True, "prix": prix, "haut": haut or prix, "bas": bas or prix,
            "baissier_1h": baissier}


def test_suivi_stop_securisation_suiveur_objectif():
    p = _position()
    assert A.suivre(p, _lecture(100.5)) == ([], None)
    evts, c = A.suivre(p, _lecture(101.6, haut=101.6))                         # +1 R (1,5 ATR)
    assert evts[0][0] == "securiser" and p["stop"] == 100.0 and c is None
    evts, c = A.suivre(p, _lecture(104, haut=104.2))
    assert evts and evts[0][0] == "suiveur" and p["stop"] == pytest.approx(102.2)
    evts, c = A.suivre(p, _lecture(102.5, bas=102.1))
    assert c["raison"] == "stop" and c["brut_pct"] == pytest.approx(2.2) and c["net_pct"] == pytest.approx(1.6)
    q = _position()
    assert A.suivre(q, _lecture(106.5, haut=106.1))[1]["raison"] == "objectif"


def test_suivi_retournement_et_duree():
    p = _position()
    assert A.suivre(p, _lecture(99.5, baissier=True))[1]["raison"] == "retournement"
    q = _position()
    q["ts"] -= (config.TR_SUIVI_JOURS + 1) * 86400
    assert A.suivre(q, None)[1]["raison"] == "duree"


# ------------------------------ veille complète ------------------------------
def test_veille_bout_en_bout(monkeypatch):
    fin = maintenant_seance()
    messages = []
    monkeypatch.setattr(V, "alerte", lambda m, important=True: messages.append(m))
    monkeypatch.setattr(config, "TR_MONTANT_ORDRE_EUR", 5000.0)
    monkeypatch.setattr(config, "TR_VOLUME_MIN_EUR", 0.0)
    cours = {"HAUT": (serie(5, 400, fin), serie(60, 400, fin, pente=0.002), serie(1440, 130, fin, pente=0.003)),
             "BAS": (serie(5, 400, fin, pente=-0.001), serie(60, 400, fin, pente=-0.002),
                     serie(1440, 130, fin, pente=-0.003))}
    choix = {"5m": 0, "1h": 1, "1d": 2}

    def faux(tickers, periode, intervalle, **k):
        return {t: cours[t][choix[intervalle]] for t in tickers if t in cours}
    instruments = {"HAUT": {"isin": "US67066G1040", "nom": "Haussier SA", "ticker": "HAUT", "devise": "EUR", "kind": "stock"},
                   "BAS": {"isin": "DE0007164600", "nom": "Baissier AG", "ticker": "BAS", "devise": "EUR", "kind": "stock"}}
    etat = V.charger_etat()
    monkeypatch.setattr(Y, "taux_de_change", lambda devises, **k: {"EUR": 1.0})
    V.etape_prefiltre(etat, instruments, budget_s=60, telecharger=faux)
    assert [x["ticker"] for x in etat["prefiltre"]["selection"]] == ["HAUT"]     # le baissier est écarté dès le tri

    memoire = {}
    V.etape_intraday(etat, instruments, memoire, telecharger=faux, maintenant=fin / 1000)
    assert "US67066G1040" in etat["suivis"] and any("IDÉE D'ACHAT" in m and "Haussier SA" in m for m in messages)
    V.etape_intraday(etat, instruments, memoire, telecharger=faux, maintenant=fin / 1000)
    assert sum("IDÉE D'ACHAT" in m for m in messages) == 1                    # pas deux fois le même signal

    d5 = cours["HAUT"][0]
    krach = pd.DataFrame({"t": [int(d5["t"].iloc[-1]) + 300_000], "o": [d5["c"].iloc[-1]], "h": [d5["c"].iloc[-1]],
                          "l": [1.0], "c": [1.0], "v": [10_000.0]})           # nouvelle bougie 5 min : krach
    cours["HAUT"] = (pd.concat([d5, krach], ignore_index=True),) + cours["HAUT"][1:]
    V.etape_intraday(etat, instruments, memoire, telecharger=faux, maintenant=fin / 1000 + 300)
    assert not etat["suivis"] and etat["historique"][0]["raison"] == "stop"
    assert any("VENDS" in m and "seuil de protection" in m for m in messages)
    V.sauver_etat(etat)
    texte = V.texte_statut()
    assert "Bilan des idées terminées : 1" in texte and "Surveillés de près aujourd'hui : 1" in texte


def test_quota_de_signaux_par_jour(monkeypatch):
    fin = maintenant_seance()
    monkeypatch.setattr(V, "alerte", lambda m, important=True: None)
    monkeypatch.setattr(config, "TR_MONTANT_ORDRE_EUR", 5000.0)
    monkeypatch.setattr(config, "TR_SIGNAUX_MAX_JOUR", 2)
    isins = ["US67066G1040", "DE0007164600", "FR0000121972", "NL0010273215"]
    instruments = {f"T{i}": {"isin": isin, "nom": f"T{i}", "ticker": f"T{i}", "devise": "EUR", "kind": "stock"}
                   for i, isin in enumerate(isins)}
    etat = V.charger_etat()
    etat["prefiltre"]["selection"] = list(instruments.values())
    cours5, cours1 = serie(5, 400, fin), serie(60, 400, fin, pente=0.002)
    faux = lambda t, p, i, **k: {x: (cours5 if i == "5m" else cours1) for x in t}
    V.etape_intraday(etat, instruments, {}, telecharger=faux, maintenant=fin / 1000)
    assert len(etat["suivis"]) == 2 and etat["jour"]["signaux"] == 2


def test_commande_telegram_tr(monkeypatch):
    import main
    recus = []
    monkeypatch.setattr(main, "commandes", lambda: ["/tr"])
    monkeypatch.setattr(main, "alerte", lambda m, important=True: recus.append(m))
    main.traiter_commandes(None, {"positions": {}})
    assert recus and "Veille Trade Republic" in recus[0]


def test_boucle_premier_demarrage_progresse(monkeypatch):
    """Premier démarrage à vide : univers -> Yahoo -> tri -> analyse, sans rester bloqué."""
    monkeypatch.setattr(config, "TR_UNIVERS_MIN", 3)
    monkeypatch.setattr(config, "TR_VOLUME_MIN_EUR", 0.0)
    monkeypatch.setattr(V, "alerte", lambda m, important=True: None)
    monkeypatch.setattr(U, "telecharger", lambda *a, **k: (open(PDF, "rb").read(), "liste_test.pdf", []))
    monkeypatch.setattr(Y, "chercher_isin", lambda isin, genre: {"ticker": isin, "devise": "EUR"})
    monkeypatch.setattr(Y, "taux_de_change", lambda devises, **k: {"EUR": 1.0})
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(V, "jour_ouvre", lambda ts=None: True)       # le test ne dépend pas du jour réel
    fin = time.time() * 1000
    jour = serie(1440, 130, fin, pente=0.003)
    appels = []

    def faux(tickers, periode, intervalle, **k):
        appels.append(intervalle)
        return {t: jour for t in tickers} if intervalle == "1d" else {}
    monkeypatch.setattr(Y, "telecharger", faux)
    etat, memoire = V.charger_etat(), {}
    V.un_tour(etat, memoire)
    assert etat["univers"]["n"] == 7 and etat["correspondance"]["reconnus"] == 7
    assert len(etat["prefiltre"]["selection"]) == 7 and "1d" in appels
    V.un_tour(etat, memoire)
    assert etat["analyse"]["ts"] and "5m" in appels and "1h" in appels


def test_panne_reseau_ne_marque_pas_les_isin_introuvables():
    univers = [{"isin": f"ISIN{i}", "nom": "", "kind": "stock"} for i in range(8)]

    def panne(isin, genre):
        raise ConnectionError("réseau coupé")
    cache = {}
    with pytest.raises(Y.LimiteYahoo):
        Y.cartographier(univers, cache, budget_s=60, pause_s=0, chercher=panne)
    assert cache == {}                                           # rien de mémorisé : tout sera recherché à nouveau
    r = Y.cartographier(univers, cache, budget_s=60, pause_s=0,
                        chercher=lambda i, g: {"ticker": i, "devise": "USD"})
    assert r["trouves"] == 8


def test_source_suivante_si_la_premiere_est_illisible(monkeypatch):
    monkeypatch.setattr(config, "TR_UNIVERS_MIN", 3)
    monkeypatch.setattr(config, "TR_URLS_UNIVERS", ["https://x/fr.pdf", "https://x/de.pdf"])
    bon = open(PDF, "rb").read()
    reponses = {"https://x/fr.pdf": (b"%PDF-1.4 pas un vrai pdf", "https://x/fr.pdf", []),
                "https://x/de.pdf": (bon, "https://x/de.pdf", [])}
    monkeypatch.setattr(U, "telecharger", lambda urls: reponses[urls[0]])
    r = U.mettre_a_jour()
    assert r["ok"] and r["source"] == "de.pdf" and "fr.pdf" in r["erreurs_sources"][0]


def test_stop_touche_pendant_une_pause_yahoo_est_vu():
    fin = maintenant_seance()
    d5, d1 = serie(5, 400, fin), serie(60, 400, fin, pente=0.002)
    a = A.analyser_titre(d5, d1, fin - 45 * 60_000)                      # signal 45 min plus tôt
    opp = type("O", (), {"cost_pct": 0.5, "net_potential_pct": 3.0, "gross_potential_pct": 3.5})()
    pos = A.nouvelle_position({"isin": "X", "nom": "T", "ticker": "T", "devise": "EUR"}, a, opp, fin / 1000 - 2700)
    creux = d5.copy()
    i = creux.index[-6]                                                     # 30 min avant : chute puis rebond
    creux.loc[i, "l"] = pos["stop"] * 0.99
    b = A.analyser_titre(creux, d1, fin)
    assert b["bas"] > pos["stop"]                                           # invisible sur les 15 dernières minutes
    evts, cloture = A.suivre(pos, b, fin / 1000)
    assert cloture and cloture["raison"] == "stop"



# ------------------------------ v14 : heures TR, prix, devises ------------------------------
def _paris(texte):
    from zoneinfo import ZoneInfo
    return pd.Timestamp(texte, tz=ZoneInfo("Europe/Paris")).timestamp()


def test_heures_d_ouverture_trade_republic():
    assert V.tr_ouvert(_paris("2026-09-22 16:00"))                          # mardi après-midi
    assert not V.tr_ouvert(_paris("2026-09-22 03:12"))                      # la nuit (signal Ibiden)
    assert not V.tr_ouvert(_paris("2026-09-22 07:29")) and V.tr_ouvert(_paris("2026-09-22 07:30"))
    assert not V.tr_ouvert(_paris("2026-09-22 22:45"))                      # trop près de la fermeture de 23 h
    assert not V.tr_ouvert(_paris("2026-09-26 12:00"))                      # samedi


def test_aucun_signal_d_achat_quand_tr_est_ferme_mais_suivi_maintenu(monkeypatch):
    nuit = _paris("2026-09-22 03:12")
    fin = nuit * 1000 - 120_000
    messages = []
    monkeypatch.setattr(V, "alerte", lambda m, important=True: messages.append(m))
    monkeypatch.setattr(config, "TR_MONTANT_ORDRE_EUR", 5000.0)
    instruments = {"HAUT": {"isin": "US67066G1040", "nom": "Haussier SA", "ticker": "HAUT", "devise": "JPY", "kind": "stock"}}
    etat = V.charger_etat()
    etat["prefiltre"]["selection"] = list(instruments.values())
    cours5, cours1 = serie(5, 400, fin, ouverture_h=0, fermeture_h=24), serie(60, 400, fin, pente=0.002, ouverture_h=0, fermeture_h=24)
    faux = lambda t, p, i, **k: {x: (cours5 if i == "5m" else cours1) for x in t}
    V.etape_intraday(etat, instruments, {}, telecharger=faux, maintenant=nuit)
    assert not etat["suivis"] and not any("IDÉE D'ACHAT" in m for m in messages)
    matin = _paris("2026-09-22 09:00")                                      # TR ouvert, cours à jour
    c5, c1 = serie(5, 400, matin * 1000 - 120_000, ouverture_h=0, fermeture_h=24), \
        serie(60, 400, matin * 1000 - 120_000, pente=0.002, ouverture_h=0, fermeture_h=24)
    faux2 = lambda t, p, i, **k: {x: (c5 if i == "5m" else c1) for x in t}
    V.etape_intraday(etat, instruments, {}, telecharger=faux2, maintenant=matin)
    assert etat["suivis"] and any("IDÉE D'ACHAT" in m for m in messages)


def test_alerte_de_vente_de_nuit_precise_l_ouverture(monkeypatch):
    messages = []
    monkeypatch.setattr(V, "alerte", lambda m, important=True: messages.append(m))
    fin = maintenant_seance()
    etat = V.charger_etat()
    pos = _position()
    pos["ts"] = _paris("2026-09-22 01:00") - (config.TR_SUIVI_JOURS + 1) * 86400   # suivi expiré
    etat["suivis"]["X"] = pos
    V.etape_intraday(etat, {}, {}, telecharger=lambda *a, **k: {}, maintenant=_paris("2026-09-22 03:00"))
    assert any("Fin du suivi" in m and "7 h 30" in m for m in messages)


def test_prix_lisibles():
    assert A.prix_lisible(23080.0) == "23\u202f080" and A.prix_lisible(182.35) == "182,35"
    assert A.prix_lisible(0.012345) == "0,01235"
    p = _position(prix=23080.0, atr=200.0)
    evts, _ = A.suivre(p, _lecture(23500, haut=23400))
    assert "remonte ton ordre stop à ton prix d'achat" in evts[0][1] and "e+" not in evts[0][1] and "." not in evts[0][1].split("%")[0]
    evts, cloture = A.suivre(p, _lecture(24000, haut=24100))                # stop suiveur : 24 100 − 2 ATR
    assert cloture is None and evts and "23\u202f700" in evts[-1][1] and "+2,7 %" in evts[-1][1]


def test_devise_reelle_des_cotations_londoniennes():
    class Info:
        def __init__(self, d):
            self.currency = d
    fabrique = lambda devise: (lambda t: type("T", (), {"fast_info": Info(devise)})())
    assert Y.devise_reelle("IWDA.L", fabrique("USD")) == "USD"
    assert Y.devise_reelle("RR.L", fabrique("GBp")) == "GBp"
    assert Y.devise_reelle("X.L", fabrique("GBX")) == "GBp"
    cache = {"IE00B4L5Y983": {"ticker": "IWDA.L", "devise": "GBp"}, "US0": {"ticker": "NVDA", "devise": "USD"}}
    assert Y.verifier_devises(cache, 60, pause_s=0, verifier=lambda t: "USD") == 1
    assert cache["IE00B4L5Y983"] == {"ticker": "IWDA.L", "devise": "USD", "devise_ok": True}
    assert Y.verifier_devises(cache, 60, pause_s=0, verifier=lambda t: "USD") == 0            # une seule fois
