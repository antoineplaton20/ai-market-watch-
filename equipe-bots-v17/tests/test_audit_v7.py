"""Tests de non-régression des corrections de l'audit v7 : chaque erreur trouvée a son test."""
import time
import pandas as pd
import pytest
import alertes
import auditeur
import config
import equipe as E
import gardien as G
import historique as H
import strategie as S
from reconciliation import reconcilier
from fausse_binance import FausseBinance


def _position(ex, etat):
    df = pd.DataFrame({"atr": [1.0] * 5, "c": [100.0] * 5})
    o = G.calculer_ordre(ex, "SOL/USDT", {"df": df}, 1000, stop_atr=1.5)
    G.acheter(ex, "SOL/USDT", o, etat, 0.9, {}, None)
    return etat["positions"]["SOL/USDT"]


def test_fantomes_rejoues_dans_l_unite_tradee(monkeypatch):
    monkeypatch.setattr(config, "UNITE_BOUGIE", "1h")
    monkeypatch.setattr(config, "DUREE_MAX_H", 48)
    ex = FausseBinance()
    appels = []
    reel = ex.fetch_ohlcv
    ex.fetch_ohlcv = lambda sym, u, since=None, limit=250: appels.append((u, limit)) or reel(sym, u, limit=limit)
    auditeur.fantome("SOL/USDT", 100.0, 1.0, ["ANTI_HYPE"])
    c = auditeur._cnx()
    c.execute("UPDATE fantomes SET ts = ?", (time.time() - 60 * 3600,))
    c.commit()
    auditeur.resoudre_fantomes(ex)
    assert appels == [("1h", 53)]


def test_stop_partiellement_execute_compte_dans_le_resultat():
    ex, etat = FausseBinance(), G.charger_etat()
    p = _position(ex, etat)
    q = p["quantite"]
    ordre = ex.ordres[p["id_stop"]]
    moitie = float(f"{q / 2:.4f}")
    ordre.update(filled=moitie, average=98.0)
    ex.solde["SOL"] -= moitie
    ex.solde["USDT"] += moitie * 98.0
    ex.prix["SOL/USDT"] = 97.0
    G.vendre(ex, "SOL/USDT", etat, "test")
    r, pnl = auditeur.trades_depuis(0)[0]
    e = p["entree"]
    attendu = (98.0 - e) * moitie + (97.0 - e) * (q - moitie) - q * e * config.FRAIS_ALLER_RETOUR_PCT / 100
    assert pnl == pytest.approx(attendu, abs=0.02)


def test_reconciliation_stop_execute_malgre_crypto_detenue_a_cote():
    ex, etat = FausseBinance(), G.charger_etat()
    p = _position(ex, etat)
    ex.executer_stop(p["id_stop"], p["stop"])
    ex.solde["SOL"] += 5.0                       # tu détiens toi-même du SOL en dehors du bot
    reconcilier(ex, etat)
    assert "SOL/USDT" not in etat["positions"]


def test_fichier_champion_abime_ne_fait_pas_planter():
    open("champion.json", "w").write('{"genome": {"espece": "MAC')
    assert S.champion()["id"] == "defaut"


def test_message_telegram_trop_long_tronque(monkeypatch):
    envoyes = []
    monkeypatch.setattr(alertes, "_ACTIF", True)
    monkeypatch.setattr(alertes.requests, "post", lambda url, json, timeout: envoyes.append(json["text"]))
    alertes.alerte("x" * 10000)
    assert len(envoyes[0]) <= 4096


def test_commande_avec_nom_du_bot(monkeypatch):
    monkeypatch.setattr(alertes, "_ACTIF", True)
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")

    class Rep:
        def json(self):
            return {"result": [{"update_id": 1, "message": {"chat": {"id": 42}, "text": "/stop@MonBot"}}]}
    monkeypatch.setattr(alertes.requests, "get", lambda *a, **k: Rep())
    assert alertes.commandes() == ["/stop"]


def test_carnet_du_genome_identique_au_backtest():
    trades = [{"side": "buy", "cost": 60}, {"side": "sell", "cost": 40}]
    df = pd.DataFrame({c: [1.0] * 260 for c in ("o", "h", "l", "c", "v", "ema20", "rsi", "atr", "vol_moy")})
    d = {"df": df, "hausse24h": 0.0}
    votes = {"CARNET": E.carnet({"carnet": {"achat": 1, "vente": 5}}, trades)}
    F = S.caracteristiques_live(d, votes, [], {}, E.flux_seul(trades))
    assert F["vote_CARNET"] == 1.0              # 60 % d'achats exécutés, comme en backtest


def test_achat_protege_meme_si_le_solde_tarde():
    ex, etat = FausseBinance(), G.charger_etat()
    vrai = ex.fetch_balance
    ex.fetch_balance = lambda: {"free": {**vrai()["free"], "SOL": 0.0}, "total": vrai()["total"]}
    df = pd.DataFrame({"atr": [1.0] * 5, "c": [100.0] * 5})
    o = G.calculer_ordre(ex, "SOL/USDT", {"df": df}, 1000, stop_atr=1.5)
    ex.fetch_balance = lambda: {"free": {**vrai()["free"], "SOL": 0.0}, "total": vrai()["total"]}
    G.acheter(ex, "SOL/USDT", o, etat, 0.9, {}, None)
    p = etat["positions"]["SOL/USDT"]
    assert ex.ordres[p["id_stop"]]["status"] == "open"


def test_bougies_aberrantes_retirees():
    df = pd.DataFrame({"t": [0, 900000, 1800000, 2700000], "o": [100, 100, 100, 100], "h": [101, 101, 900, 101],
                       "l": [99, 99, 99, 99], "c": [100, 100, 850, 100], "v": [1, 1, 1, 1], "v_achat": [0.5] * 4})
    propre = H.controler(df, "TEST")
    assert len(propre) == 3 and H.QUALITE["TEST"]["retirees"] == 1


def test_horloge_synchronisee_avec_binance(monkeypatch):
    import exchange
    vus = {}

    class FauxCcxt:
        def __init__(self, params):
            vus.update(params)

        def set_sandbox_mode(self, x):
            pass

        def enable_demo_trading(self, x):
            pass

        def load_markets(self):
            pass
    monkeypatch.setattr(exchange.ccxt, "binance", FauxCcxt)
    exchange.connecter()
    assert vus["options"]["adjustForTimeDifference"] is True


def test_panne_totale_a_l_achat_position_quand_meme_suivie():
    ex, etat = FausseBinance(), G.charger_etat()
    df = pd.DataFrame({"atr": [1.0] * 5, "c": [100.0] * 5})
    o = G.calculer_ordre(ex, "SOL/USDT", {"df": df}, 1000, stop_atr=1.5)
    ex.stop_en_panne = True
    vrai = ex.create_order

    def panne_vente(sym, typ, cote, *a, **k):
        if typ == "market" and cote == "sell":
            raise Exception("Binance indisponible")
        return vrai(sym, typ, cote, *a, **k)
    ex.create_order = panne_vente
    G.acheter(ex, "SOL/USDT", o, etat, 0.9, {}, None)
    assert etat["positions"]["SOL/USDT"]["id_stop"] == "aucun"      # jamais perdue de vue
    ex.stop_en_panne = False
    ex.create_order = vrai
    G.surveiller(ex, etat)
    p = etat["positions"]["SOL/USDT"]
    assert ex.ordres[p["id_stop"]]["status"] == "open"              # protégée dès que Binance répond


def test_mode_demo_binance(monkeypatch):
    import exchange
    appels = []

    class FauxCcxt:
        def __init__(self, params):
            pass

        def enable_demo_trading(self, x):
            appels.append("demo")

        def set_sandbox_mode(self, x):
            appels.append("testnet")

        def load_markets(self):
            pass
    monkeypatch.setattr(exchange.ccxt, "binance", FauxCcxt)
    monkeypatch.setattr(config, "MODE", "demo")
    exchange.connecter()
    assert appels == ["demo"]


def test_testnet_reinitialise_ne_fausse_pas_le_journal(monkeypatch):
    monkeypatch.setattr(config, "MODE", "testnet")
    ex, etat = FausseBinance(), G.charger_etat()
    p = _position(ex, etat)
    del ex.ordres[p["id_stop"]]                  # Binance a tout effacé
    reconcilier(ex, etat)
    assert "SOL/USDT" not in etat["positions"] and auditeur.trades_depuis(0) == []


def test_vente_au_marche_partielle_terminee():
    ex, etat = FausseBinance(), G.charger_etat()
    _position(ex, etat)
    vrai = ex.create_order
    compteur = {"n": 0}

    def partielle(sym, typ, cote, qte, *a, **k):
        if typ == "market" and cote == "sell" and compteur["n"] == 0:
            compteur["n"] += 1
            r = vrai(sym, typ, cote, float(f"{qte / 2:.4f}"), *a, **k)   # Binance n'en exécute que la moitié
            return r
        return vrai(sym, typ, cote, qte, *a, **k)
    ex.create_order = partielle
    G.vendre(ex, "SOL/USDT", etat, "test")
    assert ex.solde["SOL"] < 0.001 and "SOL/USDT" not in etat["positions"]
