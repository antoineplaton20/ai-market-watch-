"""V17 branchée sur la plateforme (serveur Hetzner, .env partagé, Telegram, service systemd) — sans réseau."""
import os
import subprocess

import pytest

from outils_v17 import FakeMarket, baisse, hausse
from v17_ops.core.config import Settings
from v17_ops.core.store import OpsStore
from v17_ops.notify import NullNotifier
from v17_ops.workers.engine import ConfigError, OpsEngine
from v17_ops import rapport

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def moteur(reglages, market, symbols=("BTC/USDT",), notifier=None, store=None, **kw):
    s = reglages(**kw)
    return OpsEngine('paper', list(symbols), store or OpsStore(s.ops_db), settings=s, market=market,
                     notifier=notifier or NullNotifier())


def ordres(e, statut='filled'):
    return [o for o in e.store.recent('orders', 500) if o['status'] == statut]


# ------------------------------------------------------------ réglages / .env
def test_mode_demo_du_bot_principal_n_est_pas_lu(monkeypatch):
    monkeypatch.setenv("MODE", "demo")                     # .env du serveur : appartient au bot principal
    assert Settings.from_env().mode == "paper"


def test_symboles_et_mode_v17_depuis_env(monkeypatch):
    monkeypatch.setenv("V17_SYMBOLS", "btcusdt, ETH/USDT,ETH/USDT")
    monkeypatch.setenv("V17_MODE", "n_importe_quoi")
    s = Settings.from_env()
    assert s.symbols == ("BTC/USDT", "ETH/USDT") and s.mode == "paper" and s.symbol == "BTC/USDT"


def test_cles_des_modes_exchange(reglages):
    from v17_ops.workers.engine import cles_exchange
    # démo sans clé v17 : clés du bot principal SEULEMENT s'il est lui-même en démo
    s = reglages(mode='demo', main_api_key='P', main_api_secret='PS', main_mode='demo')
    assert cles_exchange(s, 'demo') == ('P', 'PS', 'bot principal (même compte démo)')
    with pytest.raises(ConfigError):
        cles_exchange(reglages(mode='demo', main_api_key='P', main_api_secret='PS', main_mode='reel'), 'demo')
    with pytest.raises(ConfigError):
        OpsEngine('demo', ['BTC/USDT'], settings=reglages(mode='demo'))
    # clés v17 prioritaires
    assert cles_exchange(reglages(api_key='K', api_secret='S', main_api_key='P', main_mode='demo'), 'demo')[0] == 'K'
    # testnet : jamais les clés du bot principal
    with pytest.raises(ConfigError):
        cles_exchange(reglages(main_api_key='P', main_api_secret='PS', main_mode='demo'), 'testnet')
    # argent réel : clés propres ET différentes du bot principal
    with pytest.raises(ConfigError, match="sous-compte"):
        cles_exchange(reglages(api_key='P', api_secret='S', main_api_key='P'), 'live')


def test_verrou_demo_uniquement(reglages):
    with pytest.raises(ConfigError, match="V17_DEMO_ONLY"):
        OpsEngine('paper', ['BTC/USDT'], settings=reglages(demo_only=True))


def test_mode_demo_du_env_utilise_les_cles_demo_du_bot_principal(monkeypatch):
    for k, v in {"MODE": "demo", "BINANCE_API_KEY": "P", "BINANCE_API_SECRET": "PS", "V17_MODE": "demo",
                 "V17_DEMO_ONLY": "1"}.items():
        monkeypatch.setenv(k, v)
    s = Settings.from_env()
    assert s.mode == "demo" and s.demo_only and s.main_mode == "demo" and s.main_api_secret == "PS"


def test_unite_de_bougie_inconnue_refusee(reglages):
    with pytest.raises(ConfigError):
        OpsEngine('paper', ['BTC/USDT'], settings=reglages(timeframe='7m'))


def test_argent_reel_verrouille(reglages):
    with pytest.raises(RuntimeError):
        OpsEngine('live', ['BTC/USDT'], settings=reglages(mode='live'))


# ------------------------------------------------------------ mode paper
def test_paper_lit_les_bougies_fermees_et_achete_sans_attendre(reglages):
    m = FakeMarket(hausse())
    n = NullNotifier()
    e = moteur(reglages, m, notifier=n)
    r = e.tick('BTC/USDT')
    assert r['status'] == 'filled' and r['side'] == 'buy'
    assert 99 <= r["qty"] * r["price"] <= 100.1        # MAX_ORDER_USDT (+ glissement simulé), pas 0,001 BTC en dur
    assert any("ACHAT BTC" in msg and important for msg, important in n.messages)


def test_une_seule_decision_par_bougie_et_pas_de_rejeu_au_redemarrage(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m)
    e.tick('BTC/USDT')
    assert e.tick('BTC/USDT')['status'] == 'waiting'                  # même bougie : rien
    e2 = moteur(reglages, m, store=e.store)                           # redémarrage du service
    assert e2.tick('BTC/USDT')['status'] == 'waiting'
    assert e2.book.positions['BTC/USDT'] > 0                          # portefeuille retrouvé
    assert len(ordres(e2)) == 1


def test_pas_d_achat_en_boucle_tant_que_le_signal_reste_a_l_achat(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m)
    e.tick('BTC/USDT')
    for i in range(5):
        m.ajouter(m.closes[-1] + 0.5)
        assert e.tick('BTC/USDT')['status'] == 'hold'
    assert len(ordres(e)) == 1


def test_signal_de_vente_sans_position_ne_fait_rien(reglages):
    n = NullNotifier()
    e = moteur(reglages, FakeMarket(baisse()), notifier=n)
    assert e.tick('BTC/USDT')['status'] == 'hold'
    assert not ordres(e) and not n.messages


def test_signal_de_vente_solde_la_position(reglages):
    m = FakeMarket(hausse())
    n = NullNotifier()
    e = moteur(reglages, m, notifier=n, stop_loss_pct=0)
    e.tick('BTC/USDT')
    r = None
    for _ in range(30):
        m.ajouter(m.closes[-1] - 1.5)
        r = e.tick('BTC/USDT')
        if r['status'] == 'filled':
            break
    assert r['side'] == 'sell' and r['pnl'] < 0
    assert e.book.open_positions() == {}
    vente = [o for o in ordres(e) if o['side'] == 'sell'][0]
    assert '"reason": "signal"' in vente['payload']
    assert any("VENTE BTC" in msg for msg, _ in n.messages)


def test_protection_declenchee_sur_le_prix_en_cours(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m, stop_loss_pct=3.0)
    achat = e.tick('BTC/USDT')
    m.forming = achat['price'] * 0.96                               # -4 % dans la bougie en cours
    r = e.tick('BTC/USDT')
    assert r['status'] == 'filled' and r['side'] == 'sell'
    assert '"reason": "stop"' in [o for o in ordres(e) if o['side'] == 'sell'][0]['payload']


def test_pause_telegram_bloque_les_achats_pas_la_protection(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m)
    rapport.commande_telegram("stop", store=e.store, settings=e.settings)
    assert e.tick('BTC/USDT')['status'] == 'paused'
    rapport.commande_telegram("reprise", store=e.store, settings=e.settings)
    m.ajouter(m.closes[-1] + 0.5)
    achat = e.tick('BTC/USDT')
    assert achat['status'] == 'filled'
    rapport.commande_telegram("stop", store=e.store, settings=e.settings)
    m.forming = achat['price'] * 0.9
    assert e.tick('BTC/USDT')['side'] == 'sell'


def test_plafond_de_capital_et_budget(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m, symbols=("BTC/USDT", "ETH/USDT", "SOL/USDT"), capital_max_usdt=150, risk_per_trade_pct=5)
    assert e.tick('BTC/USDT')['status'] == 'filled'
    r = e.tick('ETH/USDT')
    assert r['status'] == 'filled' and r['qty'] * r['price'] == pytest.approx(50, rel=0.01)
    assert e.tick('SOL/USDT') == {'status': 'risk_rejected', 'reason': 'budget'}


def test_perte_du_jour_bloque_les_nouveaux_achats(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m, max_daily_loss_usdt=50)
    e.store.set('jour:paper', {'date': __import__('datetime').date.today().isoformat(), 'equity': 10100})
    assert e.tick('BTC/USDT') == {'status': 'risk_rejected', 'reason': 'daily_loss_limit'}


def test_kill_switch_bloque_tout(reglages):
    e = moteur(reglages, FakeMarket(hausse()), kill_switch=True)
    assert e.tick('BTC/USDT')['status'] == 'rejected'
    assert not ordres(e)


def test_refus_repetes_sans_remplir_la_base(reglages):
    m = FakeMarket(hausse())
    n = NullNotifier()
    e = moteur(reglages, m, notifier=n, kill_switch=True)
    for _ in range(20):
        m.ajouter(m.closes[-1] + 0.5)
        e.tick('BTC/USDT')
    assert len(ordres(e, 'policy_rejected')) == 1


# ------------------------------------------------------------ mode exchange (faux Binance)
class FauxBinance(FakeMarket):
    def __init__(self, closes):
        super().__init__(closes)
        self.ordres = []
        self.usdt = 500.0
        self.btc = 0.0

    def free(self, asset):
        return self.usdt if asset == 'USDT' else self.btc

    def min_cost(self, symbol):
        return 5.0

    def check_buy_liquidity(self, *args):
        return True

    def open_orders_count(self):
        return 0

    def market_order(self, symbol, side, qty, ref_price, client_order_id=None):
        self.ordres.append((side, qty))
        if side == 'buy':
            self.btc += qty
        else:
            self.btc -= qty
        return {'id': f'x{len(self.ordres)}', 'qty': qty, 'price': ref_price * 1.001, 'raw': {}}


def test_mode_demo_avec_ses_propres_cles(reglages):
    fx = FauxBinance(hausse())
    s = reglages(mode='demo', api_key='V17', api_secret='S', main_api_key='PRINCIPAL', stop_loss_pct=3)
    e = OpsEngine('demo', ['BTC/USDT'], OpsStore(s.ops_db), settings=s, executor=fx, notifier=NullNotifier())
    achat = e.tick('BTC/USDT')
    assert achat['status'] == 'filled' and fx.ordres[0][0] == 'buy'
    fx.forming = achat['price'] * 0.9
    assert e.tick('BTC/USDT')['side'] == 'sell' and fx.ordres[-1][0] == 'sell'
    assert e.book.open_positions() == {}


def test_mode_demo_position_disparue_du_compte(reglages):
    fx = FauxBinance(hausse())
    s = reglages(mode='demo', api_key='V17', api_secret='S', stop_loss_pct=3)
    n = NullNotifier()
    e = OpsEngine('demo', ['BTC/USDT'], OpsStore(s.ops_db), settings=s, executor=fx, notifier=n)
    achat = e.tick('BTC/USDT')
    fx.btc = 0.0                                                     # vendue à la main / compte démo remis à zéro
    fx.forming = achat['price'] * 0.9
    r = e.tick('BTC/USDT')
    assert r['status'] == 'reconciliation_required' and e.book.open_positions()
    assert [o for o in fx.ordres if o[0] == 'sell'] == []           # aucun ordre de vente envoyé
    assert any("rapprochement requis" in m for m, _ in n.messages)


def test_mode_demo_ne_vend_que_ce_qui_reste(reglages):
    fx = FauxBinance(hausse())
    s = reglages(mode='demo', api_key='V17', api_secret='S', stop_loss_pct=3)
    e = OpsEngine('demo', ['BTC/USDT'], OpsStore(s.ops_db), settings=s, executor=fx, notifier=NullNotifier())
    achat = e.tick('BTC/USDT')
    fx.btc = achat['qty'] / 2                                        # la moitié a disparu du compte
    fx.forming = achat['price'] * 0.9
    assert e.tick('BTC/USDT')['status'] == 'filled'
    assert fx.ordres[-1] == ('sell', pytest.approx(achat['qty'] / 2))
    assert e.book.positions['BTC/USDT'] == pytest.approx(achat['qty'] / 2)


class FauxDemo:
    def __init__(self, erreur=None):
        self.erreur = erreur

    def _load(self):
        if self.erreur:
            raise Exception(self.erreur)

    def fetch_ticker(self, symbol):
        return {'last': 64000.0}

    def free(self, asset):
        return 5000.0


def test_verification_du_compte_demo(capsys, reglages):
    from v17_ops import verif_demo
    s = reglages(main_api_key='P', main_api_secret='PS', main_mode='demo')
    assert verif_demo.main(s, FauxDemo()) == 0
    sortie = capsys.readouterr().out
    assert "✔ Compte démo Binance joignable" in sortie and "bot principal" in sortie
    assert verif_demo.main(s, FauxDemo('binance {"code":-2015,"msg":"Invalid API-key"}')) == 1
    assert "demo.binance.com" in capsys.readouterr().out
    assert verif_demo.main(reglages(), FauxDemo()) == 1                  # aucune clé démo


def test_une_seule_v17_a_la_fois(monkeypatch, reglages):
    import v17_ops.cli as C
    s = reglages()
    monkeypatch.setattr(C, "settings", s)
    premier = C._verrou(s.ops_db)
    assert premier is not None
    assert C.main(["--once", "--price", "50000"]) == C.CODE_VERROU   # le service tourne déjà : refus
    premier.close()
    assert C.main(["--once", "--price", "50000"]) == 0


# ------------------------------------------------------------ Telegram /v17, API, CLI
def test_rapport_v17(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m)
    assert "pas encore démarrée" in rapport.texte_statut(e.store, e.settings)
    e.tick('BTC/USDT')
    e.heartbeat()
    texte = rapport.texte_statut(e.store, e.settings)
    assert "v17" in texte and "BTC" in texte and "1 achat" in texte


def test_commande_v17_dans_le_bot_principal(monkeypatch, reglages):
    import main
    from v17_ops.core import config as C
    s = reglages()
    monkeypatch.setattr(C, "settings", s)
    import v17_ops.rapport as R
    monkeypatch.setattr(R, "SETTINGS", s)
    envoyes = []
    monkeypatch.setattr(main, "commandes", lambda: ["/v17", "/v17 stop"])
    monkeypatch.setattr(main, "alerte", lambda m, important=True: envoyes.append(m))
    main.traiter_commandes(None, {"positions": {}})
    assert "v17" in envoyes[0] and "pause" in envoyes[1]
    assert OpsStore(s.ops_db).get('pause') is True


def test_api_lecture_seule(monkeypatch, reglages):
    from v17_ops.api import app as A
    s = reglages()
    m = FakeMarket(hausse())
    e = moteur(reglages, m)
    e.tick('BTC/USDT')
    e.heartbeat()
    monkeypatch.setattr(A, "store", e.store)
    import v17_ops.rapport as R
    monkeypatch.setattr(R, "SETTINGS", s)
    assert A.health()['status'] == 'ok'
    assert A.state()['positions'][0]['symbol'] == 'BTC/USDT'
    assert A.orders(1000)[0]['side'] == 'buy'


def test_cli_passage_unique_avec_prix_injecte(capsys, monkeypatch, reglages):
    import v17_ops.cli as C
    monkeypatch.setattr(C, "settings", reglages())                   # indépendant du .env du serveur
    cli = C.main
    assert cli(["--once", "--price", "50000", "--mode", "paper"]) == 0
    assert "warming" in capsys.readouterr().out


def test_cli_reglage_invalide_code_2_sans_boucle(monkeypatch, reglages):
    import v17_ops.cli as C
    monkeypatch.setattr(C, "settings", reglages())
    cli = C.main
    assert cli(["--once", "--mode", "demo"]) == 2                   # pas de clés v17 : arrêt net, pas de boucle


def test_cli_coupure_reseau_un_seul_message_puis_retour(monkeypatch, reglages):
    import ccxt
    import v17_ops.cli as C
    from v17_ops import notify
    from v17_ops.workers import engine as W
    monkeypatch.setattr(C, "settings", reglages(interval=10))
    envoyes = []
    monkeypatch.setattr(notify.Notifier, "send", lambda self, msg, important=True: envoyes.append(msg))
    tours = {"n": 0}

    def faux_tick(self, symbol, price=None):
        if tours["n"] < 7:
            raise ccxt.NetworkError("binance GET https://api.binance.com/api/v3/klines")
        return {"status": "waiting"}

    def fausse_pause(s):
        tours["n"] += 1
        if tours["n"] > 8:
            raise KeyboardInterrupt
    monkeypatch.setattr(W.OpsEngine, "tick", faux_tick)
    monkeypatch.setattr(C.time, "sleep", fausse_pause)
    monkeypatch.setattr(C, "_journal", lambda f: None)
    assert C.main([]) == 0
    reseau = [m for m in envoyes if "Binance ne répond" in m or "Connexion à Binance" in m]
    assert len(reseau) == 2 and "ne répond plus" in reseau[0] and "revenue" in reseau[1]


# ------------------------------------------------------------ déploiement
def test_verifier_couvre_la_v17():
    texte = open(os.path.join(RACINE, "verifier.py"), encoding="utf-8").read()
    assert "tests_v17" in texte


def test_telecommande_connait_la_v17():
    texte = open(os.path.join(RACINE, "bots"), encoding="utf-8").read()
    for cmd in ("v17-etat", "v17-demarrer", "v17-arreter", "v17-journal", "v17-symboles", "v17-demo)",
                "v17-fictif)", "v17-demo-test)"):
        assert cmd in texte
    assert "RestartPreventExitStatus" not in texte                    # jamais d'abandon : réglage invalide = attente
    assert "StartLimitIntervalSec=0" in texte and "StartLimitBurst" not in texte
    assert "Restart=always" in texte and "Restart=on-failure" not in texte
    assert "WatchdogSec=900" in texte and "service_principal" in texte and "increvable)" in texte
    assert subprocess.run(["bash", "-n", os.path.join(RACINE, "bots")]).returncode == 0


@pytest.mark.parametrize("script,commande", [("termius_demo_install.sh", "v17-demo-test"),
                                             ("termius_demo_check.sh", "v17-demo-test"),
                                             ("termius_demo_start.sh", "v17-demo"),
                                             ("termius_demo_stop.sh", "v17-arreter"),
                                             ("termius_demo_status.sh", "v17-etat")])
def test_scripts_termius_passent_par_la_plateforme_sur_le_serveur(script, commande):
    texte = open(os.path.join(RACINE, script), encoding="utf-8").read()
    assert f"exec bots {commande}" in texte and "equipe-bots.service" in texte
    assert subprocess.run(["bash", "-n", os.path.join(RACINE, script)]).returncode == 0


def test_ccxt_installable_et_compatible_demo():
    for f in ("requirements.txt", os.path.join("v17_ops", "requirements.txt")):
        lignes = open(os.path.join(RACINE, f), encoding="utf-8").read().split()
        assert "ccxt>=4.5.6" in lignes                                  # 4.6.0 n'existe pas ; démo depuis 4.5.6


def test_api_jamais_exposee_sur_internet():
    for f in ("run_api_v17.sh", "docker-compose.v17.yml", "bots"):
        texte = open(os.path.join(RACINE, f), encoding="utf-8").read()
        assert "0.0.0.0:8080" not in texte and '"8080:8080"' not in texte


def test_blocage_visible_et_deblocage_confirme(reglages):
    s = reglages()
    st = OpsStore(s.ops_db)
    st.set('heartbeat', {'ts': __import__('time').time(), 'mode': 'demo', 'symbols': ['BTC/USDT']})
    st.set('pending:demo', {'symbol': 'BTC/USDT', 'side': 'buy', 'intent_id': 'x'})
    assert "BLOQUÉE" in rapport.texte_statut(st, s)
    assert "demo.binance.com" in rapport.rapprochement(st, s)
    assert "Blocage retiré" in rapport.debloquer(st, s)
    assert st.get('pending:demo') is None and st.get('pause') is True
    st.set('heartbeat', {'ts': 0, 'mode': 'live'})
    st.set('pending:live', {'symbol': 'BTC/USDT'})
    assert "Argent réel" in rapport.debloquer(st, s) and st.get('pending:live')


def test_telecommande_blocage():
    texte = open(os.path.join(RACINE, "bots"), encoding="utf-8").read()
    assert "v17-rapprochement)" in texte and "v17-debloquer)" in texte and "JE CONFIRME" in texte


def test_v17_consulte_le_renseignement_avant_d_acheter(reglages):
    import renseignement as RS
    b = RS.Base()                                                    # runtime/renseignement.db du dossier de test
    b.ajouter("test", [{"titre": "Bitcoin exchange collapses", "source": "x", "themes": ["crypto"],
                        "actifs": ["BTC"], "ton": -2, "importance": 3}], {})
    e = moteur(reglages, FakeMarket(hausse()))
    assert e.tick('BTC/USDT') == {'status': 'risk_rejected', 'reason': 'renseignement'}
    e2 = moteur(reglages, FakeMarket(hausse()), symbols=("ETH/USDT",))
    assert e2.tick('ETH/USDT')['status'] == 'filled'                  # autre actif : achat normal
    e3 = moteur(reglages, FakeMarket(hausse()), symbols=("SOL/USDT",), renseignement=False)
    assert e3.tick('SOL/USDT')['status'] == 'filled'
