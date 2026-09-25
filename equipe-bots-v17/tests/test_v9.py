"""v9 : approbation humaine, paliers, états de risque, coupe-circuit absolu, fraîcheur des données,
journal d'audit, registre immuable, calibration de l'IA, recherche fondamentale, notifications."""
import datetime as dt
import json
import time
import pandas as pd
import pytest
import alertes
import approbations
import auditeur
import calibration
import config
import controle_donnees as CD
import disjoncteur as D
import equipe as E
import etat_risque
import gardien as G
import ledger
import main
import paliers
import recherche
import registre
from fausse_binance import FausseBinance


def _trade(pnl_usdt):
    p = {"entree": 100.0, "quantite": abs(pnl_usdt) or 1.0, "stop_initial": 99.0, "ouvert": time.time(), "votes": {}}
    auditeur.enregistrer("SOL/USDT", p, 101.0 if pnl_usdt > 0 else 99.0, "test")


@pytest.fixture
def messages(monkeypatch):
    recus = []
    for module in (main, G, etat_risque, D, paliers):
        if hasattr(module, "alerte"):
            monkeypatch.setattr(module, "alerte", lambda m, important=True: recus.append(m))
    monkeypatch.setattr(approbations, "boutons", lambda m, choix: recus.append(m))
    return recus


# ------------------------------ A. CONTRÔLE ------------------------------
def test_etats_de_risque_gradues():
    etat = G.charger_etat()
    assert etat_risque.evaluer(etat, "CALIBRÉ")[:2] == ("SÛR", 1.0)
    etat["pnl_jour"] = -20                                   # -2 % du capital autorisé (1 000)
    assert etat_risque.evaluer(etat, "CALIBRÉ")[:2] == ("PRUDENCE", 0.75)
    etat["pnl_jour"] = -35
    assert etat_risque.evaluer(etat, "CALIBRÉ")[:2] == ("RÉDUCTION", 0.5)
    etat["donnees_ko"] = "bougies périmées"
    assert etat_risque.evaluer(etat, "CALIBRÉ")[:2] == ("ARRÊT", 0.0) and not G.peut_acheter(etat)


def test_ia_mal_calibree_met_en_prudence():
    assert etat_risque.evaluer(G.charger_etat(), "NON FIABLE")[0] == "PRUDENCE"


def test_coupe_circuit_absolu_malgre_une_prevision_large():
    with open("champion.json", "w") as f:
        json.dump({"genome": {"id": "x"}, "unite": "15m", "date": "2020-01-01", "coffre": {"mc_dd95": 0.90}}, f)
    etat = G.charger_etat()
    for _ in range(4):
        _trade(-40)                                          # -160 USDT sur 1 000 = -16 %
    D.verifier(etat)
    assert "COUPE-CIRCUIT" in etat["disjoncteur"]["raison"]


def test_palier_propose_puis_approuve_uniquement_par_toi(monkeypatch, messages):
    monkeypatch.setattr(config, "CAPITAL_MAX_USDT", 5000.0)
    etat = G.charger_etat()
    etat["palier_depuis"] = time.time() - 20 * 86400
    for _ in range(30):
        _trade(+2)
    assert paliers.proposer(etat)
    assert paliers.capital_autorise(etat) == 1000             # rien ne bouge avant ta réponse
    main.traiter_approbation(etat, "palier-1", True)
    assert paliers.capital_autorise(etat) == 3000


def test_palier_refuse_ne_change_rien(monkeypatch, messages):
    monkeypatch.setattr(config, "CAPITAL_MAX_USDT", 5000.0)
    etat = G.charger_etat()
    etat["palier_depuis"] = time.time() - 20 * 86400
    for _ in range(30):
        _trade(+2)
    paliers.proposer(etat)
    main.traiter_approbation(etat, "palier-1", False)
    assert paliers.capital_autorise(etat) == 1000


def test_jamais_au_dela_du_plafond_absolu():
    etat = G.charger_etat()                                   # plafond .env : 1 000, palier suivant : 3 000
    etat["palier_depuis"] = time.time() - 20 * 86400
    for _ in range(30):
        _trade(+2)
    assert not paliers.proposer(etat)


def test_palier_pas_propose_trop_tot():
    etat = G.charger_etat()
    etat["palier_depuis"] = time.time() - 3 * 86400
    for _ in range(30):
        _trade(+2)
    assert not paliers.proposer(etat)


def test_disjoncteur_fait_redescendre_d_un_palier(messages):
    etat = G.charger_etat()
    etat["palier"] = 1
    D.declencher(etat, "test")
    assert etat["palier"] == 0


def test_donnees_perimees_eliminees():
    ex = FausseBinance()
    ex.retard_s = 3 * 3600                                    # tout a 3 h de retard
    cand = E.scout(ex)[0]
    assert not E.filtre(ex, cand)[0]


def test_bougies_et_ticker_frais_acceptes():
    ex = FausseBinance()
    df = pd.DataFrame(ex.fetch_ohlcv("SOL/USDT", "15m", limit=5), columns=["t", "o", "h", "l", "c", "v"])
    assert CD.bougies_fraiches(df, "15m") and CD.ticker_frais(ex.fetch_ticker("SOL/USDT"))


def test_horloge_decalee_detectee():
    ex = FausseBinance()
    ex.decalage_ms = 20_000
    assert not CD.horloge(ex)[0]


def test_btc_perime_bloque_tout_le_cycle(messages):
    ex, etat = FausseBinance(), G.charger_etat()
    ex.retard_s = 3 * 3600
    main.cycle_achat(ex, etat, 1000, 1.0)
    assert etat["donnees_ko"] and not etat["positions"]


# ------------------------------ B. TRAÇABILITÉ ------------------------------
def test_empreinte_deterministe_et_sensible():
    a = {"prix": 100.0, "rsi": 55.2, "vide": float("nan")}
    assert ledger.empreinte(a) == ledger.empreinte(dict(a))
    assert ledger.empreinte(a) != ledger.empreinte({**a, "rsi": 55.3})


def test_chaque_achat_a_sa_decision_et_son_glissement():
    ex, etat = FausseBinance(), G.charger_etat()
    did = ledger.decision("SOL/USDT", "champion", {"id": "g1"}, {"F": {"c": 100}}, 0.9, True, [], "SÛR")
    df = pd.DataFrame({"atr": [1.0] * 5, "c": [100.0] * 5})
    o = G.calculer_ordre(ex, "SOL/USDT", {"df": df}, 1000, stop_atr=1.5)
    G.acheter(ex, "SOL/USDT", o, etat, 0.9, {}, None, decision_id=did)
    c = ledger._cnx()
    ordres = c.execute("SELECT decision_id, type, prix_voulu, prix_obtenu, glissement_bps, politique FROM ordres").fetchall()
    assert {o[1] for o in ordres} == {"market", "stop_loss_limit"}
    achat = [o for o in ordres if o[1] == "market"][0]
    assert achat[0] == did and achat[4] is not None and achat[5] == config.POLITIQUE_VERSION
    assert c.execute("SELECT etat_hash FROM decisions WHERE decision_id=?", (did,)).fetchone()[0]


def test_registre_detecte_toute_retouche():
    registre.ajouter("test", {"a": 1})
    registre.ajouter("test", {"b": 2})
    assert registre.verifier()[0]
    lignes = open(registre.FICHIER, encoding="utf-8").read().splitlines()
    lignes[0] = lignes[0].replace('"a": 1', '"a": 999')
    open(registre.FICHIER, "w", encoding="utf-8").write("\n".join(lignes) + "\n")
    assert not registre.verifier()[0]


# ------------------------------ C. IA ------------------------------
def _paires(p_annonce, taux_reel, n=200, graine=1):
    import random
    rnd = random.Random(graine)
    return [(p_annonce, 1.0 if rnd.random() < taux_reel else 0.0) for _ in range(n)]


def test_calibration_reconnait_une_ia_honnete():
    paires = _paires(0.8, 0.8, 150) + _paires(0.2, 0.2, 150, 2)
    assert calibration.diagnostic(paires)["statut"] == "CALIBRÉ"


def test_calibration_reconnait_une_ia_surconfiante():
    paires = _paires(0.9, 0.6, 150) + _paires(0.7, 0.45, 150, 2)
    assert calibration.diagnostic(paires)["statut"] in ("SURCONFIANT", "NON FIABLE")


def test_calibration_reconnait_une_ia_inutile():
    paires = _paires(0.8, 0.5, 150) + _paires(0.2, 0.5, 150, 2)
    assert calibration.diagnostic(paires)["statut"] == "NON FIABLE"


def test_calibration_en_rodage_avec_peu_de_donnees():
    assert calibration.diagnostic(_paires(0.8, 0.8, 10))["statut"] == "EN RODAGE"


def test_passe_confiant_compte_comme_faible_chance_de_succes():
    assert calibration.probabilites_issues([("PASSE", 90, 1.2)])[0] == (pytest.approx(0.1), 1.0)


def test_ia_muette_avec_cle_configuree_aucun_trade(monkeypatch, messages):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "cle-test")
    monkeypatch.setattr(main.E, "contradicteur", lambda *a: (None, "IA indisponible"))
    _donnees_sans_reseau(monkeypatch)
    ex, etat = FausseBinance(), G.charger_etat()
    main.cycle_achat(ex, etat, 1000, 1.0)
    assert not etat["positions"]
    assert any("l'IA relectrice n'a pas répondu" in m for m in messages)


# ------------------------------ D. RECHERCHE ------------------------------
def _pieces():
    marche = lambda s, circ, total: {"id": s.lower(), "symbol": s.lower(), "name": s, "market_cap": 1e9,
                                     "fully_diluted_valuation": 3e9, "circulating_supply": circ,
                                     "total_supply": total, "max_supply": None}
    marches = [marche("AAA", 90, 100), marche("DIL", 20, 100), marche("TVL", 90, 100), marche("UNL", 90, 100)]
    protos = [{"gecko_id": "tvl", "name": "Tvl", "tvl": 1e8, "change_7d": -40},
              {"gecko_id": "aaa", "name": "Aaa", "tvl": 1e8, "change_7d": 2}]
    frais = {"aaa": {"total30d": 5e6}}
    debl = {"UNL": [(dt.date.today() + dt.timedelta(days=5), 4.0)]}
    return recherche.analyser(marches, protos, frais, frais, debl, dt.date.today())


def test_recherche_exclut_dilution_fuite_de_tvl_et_deblocage():
    f = _pieces()
    assert f["AAA"]["verdict"] == "RAS"
    assert f["DIL"]["verdict"] == "EXCLU" and "dilution" in f["DIL"]["raisons"][0]
    assert f["TVL"]["verdict"] == "EXCLU" and "TVL" in f["TVL"]["raisons"][0]
    assert f["UNL"]["verdict"] == "EXCLU" and "déblocage" in f["UNL"]["raisons"][0]
    assert "CoinGecko" in f["AAA"]["sources"]["marché"]


def test_recherche_ne_sert_que_de_veto_et_expire():
    json.dump({"date": dt.date.today().isoformat(), "fiches": _pieces()}, open("recherche_hebdo.json", "w"), default=str)
    assert E.recherche("DIL")[0] is False and E.recherche("AAA")[0] is True
    vieux = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    json.dump({"date": vieux, "fiches": _pieces()}, open("recherche_hebdo.json", "w"), default=str)
    assert E.recherche("DIL")[0] is True                        # trop ancienne : ignorée


# ------------------------------ NOTIFICATIONS ------------------------------
def _donnees_sans_reseau(monkeypatch):
    import donnees
    for nom, valeur in {"peur_avidite": lambda: 55, "fundings": lambda: {"SOLUSDT": 0.0001, "ETHUSDT": 0.001},
                        "open_interest": lambda s: [100, 101, 104], "actualites": lambda: [],
                        "tendances": lambda: set(), "annuaire": lambda: {}, "commits_4_semaines": lambda b: None,
                        "stablecoins_7j": lambda: 0.8, "macro": lambda: (True, False),
                        "positionnement": lambda s: (1.4, 1.9), "marches_mondiaux": lambda: (True, False, 17.0),
                        "attention": lambda: 1.1}.items():
        monkeypatch.setattr(donnees, nom, valeur)


def test_signal_bloque_notifie_une_fois_par_periode(messages):
    etat = G.charger_etat()
    main.notifier_bloque(etat, "ETH/USDT", 0.8, ["DERIVES_VETO"], "")
    main.notifier_bloque(etat, "ETH/USDT", 0.8, ["DERIVES_VETO"], "")
    assert sum(m.startswith("✋ ETH") for m in messages) == 1


def test_scan_juste_apres_chaque_nouvelle_bougie():
    etat = {}
    assert main.nouvelle_bougie(etat) and not main.nouvelle_bougie(etat)


def test_mauvaise_nouvelle_sur_position_vente_immediate(monkeypatch, messages):
    import donnees
    ex, etat = FausseBinance(), G.charger_etat()
    df = pd.DataFrame({"atr": [1.0] * 5, "c": [100.0] * 5})
    G.acheter(ex, "SOL/USDT", G.calculer_ordre(ex, "SOL/USDT", {"df": df}, 1000, stop_atr=1.5), etat, 0.9, {}, None)
    monkeypatch.setattr(donnees, "annuaire", lambda: {"SOL": ("solana", "Solana")})
    monkeypatch.setattr(donnees, "actualites", lambda: [{"titre": "Solana bridge hacked, funds drained", "ts": time.time()}])
    main.sortie_anticipee(ex, etat)
    assert "SOL/USDT" not in etat["positions"] and any("VENTE IMMÉDIATE" in m for m in messages)


def test_boutons_telegram_et_commandes_avec_argument(monkeypatch):
    monkeypatch.setattr(alertes, "_ACTIF", True)
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")

    class Rep:
        def json(self):
            return {"result": [
                {"update_id": 1, "callback_query": {"id": "c1", "data": "/approuver champion-ab12",
                                                   "message": {"chat": {"id": 42}}}},
                {"update_id": 2, "callback_query": {"id": "c2", "data": "/approuver champion-pirate",
                                                   "message": {"chat": {"id": 666}}}}]}
    monkeypatch.setattr(alertes.requests, "get", lambda *a, **k: Rep())
    monkeypatch.setattr(alertes.requests, "post", lambda *a, **k: None)
    assert alertes.commandes() == ["/approuver champion-ab12"]      # l'inconnu est ignoré
