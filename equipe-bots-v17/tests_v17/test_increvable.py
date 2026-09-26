"""V17 increvable : rapprochement automatique (démo), pauses temporaires, réglages tolérants, boucle sans arrêt."""
import time

import pytest

from v17_ops.adapters.ccxt_adapter import CCXTAdapter
from v17_ops.core.config import CORRECTIONS, Settings
from v17_ops.core.store import OpsStore
from v17_ops.notify import NullNotifier
from v17_ops.workers import engine as W
from v17_ops.workers.engine import OpsEngine
from outils_v17 import hausse
from test_plateforme import FauxBinance


class BinanceCoupee(FauxBinance):
    """L'envoi de l'ordre part en délai dépassé ; Binance, lui, l'a peut-être exécuté."""

    def __init__(self, closes, issue):
        super().__init__(closes)
        self.issue = issue                  # ce que Binance répondra au rapprochement (None = ordre inconnu)
        self.recherches = []

    def market_order(self, symbol, side, qty, ref_price, client_order_id=None):
        self.ordres.append((side, qty))
        self.client_id = client_order_id
        raise TimeoutError('unknown exchange outcome')

    def lookup_order(self, symbol, client_order_id):
        self.recherches.append(client_order_id)
        return self.issue


def _moteur(fx, reglages, **kw):
    s = reglages(mode='demo', api_key='V17', api_secret='S', **kw)
    n = NullNotifier()
    return OpsEngine('demo', ['BTC/USDT'], OpsStore(s.ops_db), settings=s, executor=fx, notifier=n), n


def _vieillir(e, secondes):
    p = e.store.get('pending:demo')
    p['created_at'] = time.time() - secondes
    e.store.set('pending:demo', p)
    e._prochain_rapprochement = 0


def test_achat_incertain_confirme_par_binance_puis_reprise(reglages):
    fx = BinanceCoupee(hausse(), {'id': '42', 'status': 'closed', 'qty': 0.5, 'price': 130.0})
    e, n = _moteur(fx, reglages)
    assert e.tick('BTC/USDT')['status'] == 'error'
    assert e.store.get('pending:demo')
    e._prochain_rapprochement = 0
    r = e.tick('BTC/USDT')
    assert r['status'] != 'reconciliation_required'
    assert e.store.get('pending:demo') is None
    assert fx.recherches == [fx.client_id]                            # recherche par identifiant client
    assert e.book.positions['BTC/USDT'] == pytest.approx(0.5) and e.book.avg_cost['BTC/USDT'] == 130.0
    assert any("Blocage levé automatiquement" in m for m, _ in n.messages)
    assert len(fx.ordres) == 1                                        # jamais de second envoi à l'aveugle


def test_ordre_inconnu_de_binance_reste_bloque_apres_2_min(reglages):
    fx = BinanceCoupee(hausse(), None)
    e, _ = _moteur(fx, reglages)
    e.tick('BTC/USDT')
    e._prochain_rapprochement = 0
    assert e.tick('BTC/USDT')['status'] == 'reconciliation_required'   # trop tôt : on attend
    _vieillir(e, W.AGE_ORDRE_INCONNU_S + 1)
    assert e.rapprocher() is False
    assert e.store.get('pending:demo') and not e.book.open_positions() and e.book.cash == 1000


def test_ordre_clos_sans_execution(reglages):
    fx = BinanceCoupee(hausse(), {'id': '9', 'status': 'expired', 'qty': 0.0, 'price': 0.0})
    e, _ = _moteur(fx, reglages)
    e.tick('BTC/USDT')
    e._prochain_rapprochement = 0
    assert e.rapprocher() is True and not e.book.open_positions()


def test_panne_pendant_le_rapprochement_garde_le_blocage(reglages):
    fx = BinanceCoupee(hausse(), None)
    e, _ = _moteur(fx, reglages)
    e.tick('BTC/USDT')
    fx.lookup_order = lambda *a: (_ for _ in ()).throw(TimeoutError('réseau'))
    _vieillir(e, 3600)
    assert e.rapprocher() is False and e.store.get('pending:demo')
    assert e.rapprocher() is False                                    # au plus un essai par minute


def test_solde_indisponible_conserve_le_carnet_apres_10_min(reglages):
    fx = FauxBinance(hausse())
    e, n = _moteur(fx, reglages, stop_loss_pct=3)
    achat = e.tick('BTC/USDT')
    fx.btc = 0.0                                                      # compte démo remis à zéro
    fx.forming = achat['price'] * 0.9
    assert e.tick('BTC/USDT')['status'] == 'reconciliation_required'
    cash = e.book.cash
    _vieillir(e, W.AGE_SOLDE_S + 1)
    assert e.rapprocher() is False
    assert e.book.open_positions() and e.book.cash == cash        # aucune recette inventée
    assert [o for o in fx.ordres if o[0] == 'sell'] == []
    assert e.store.get('pending:demo')


def test_argent_reel_jamais_debloque_automatiquement(reglages):
    s = reglages(mode='live', live_trading_enabled=True, api_key='V17', api_secret='S')
    fx = BinanceCoupee(hausse(), {'id': '1', 'status': 'closed', 'qty': 1.0, 'price': 100.0})
    e = OpsEngine('live', ['BTC/USDT'], OpsStore(s.ops_db), settings=s, executor=fx, notifier=NullNotifier())
    e.store.set('pending:live', {'intent_id': 'abc', 'symbol': 'BTC/USDT', 'side': 'buy', 'created_at': 0})
    assert e.rapprocher() is False
    assert e.tick('BTC/USDT')['status'] == 'reconciliation_required' and fx.recherches == []
    assert e.store.get('pending:live')


def test_rapprochement_auto_desactivable(reglages):
    fx = BinanceCoupee(hausse(), {'id': '1', 'status': 'closed', 'qty': 1.0, 'price': 100.0})
    e, _ = _moteur(fx, reglages, auto_reconcile=False)
    e.tick('BTC/USDT')
    e._prochain_rapprochement = 0
    assert e.tick('BTC/USDT')['status'] == 'reconciliation_required' and fx.recherches == []


def test_pause_de_glissement_temporaire(reglages):
    e, _ = _moteur(FauxBinance(hausse()), reglages)
    e.store.set('pause_until', time.time() + 60)
    assert e.paused()
    e.store.set('pause_until', time.time() - 1)
    assert not e.paused()
    from v17_ops import rapport
    e.store.set('pause_until', time.time() + 60)
    rapport.regler_pause(False, e.store, e.settings)                  # /v17 reprise lève aussi la pause auto
    assert not e.paused()


def test_glissement_excessif_pause_temporaire_seulement(reglages):
    class Glisse(FauxBinance):
        def market_order(self, symbol, side, qty, ref_price, client_order_id=None):
            f = super().market_order(symbol, side, qty, ref_price, client_order_id)
            f['price'] = ref_price * 1.05
            return f
    e, _ = _moteur(Glisse(hausse()), reglages)
    assert e.tick('BTC/USDT')['status'] == 'filled'
    assert e.store.get('pause') in (None, False) and e.paused()
    assert e.store.get('pause_until') > time.time() + 30 * 60


# ------------------------------------------------------------------ adaptateur
class ExchangeRapprochement:
    def __init__(self, reponses, inconnu=False):
        self.reponses = list(reponses)
        self.inconnu = inconnu
        self.annules = []

    def load_markets(self):
        pass

    def fetch_order(self, oid, symbol, params=None):
        if self.inconnu:
            import ccxt
            raise ccxt.OrderNotFound('binance {"code":-2013,"msg":"Order does not exist."}')
        return self.reponses.pop(0)

    def cancel_order(self, oid, symbol):
        self.annules.append(oid)


def test_adaptateur_lookup_order():
    ex = ExchangeRapprochement([{'id': '5', 'status': 'closed', 'filled': 2, 'cost': 200}])
    assert CCXTAdapter(exchange=ex).lookup_order('BTC/USDT', 'abc') == {'id': '5', 'status': 'closed',
                                                                        'qty': 2.0, 'price': 100.0}
    ex = ExchangeRapprochement([{'id': '6', 'status': 'open', 'filled': 1},
                                {'id': '6', 'status': 'canceled', 'filled': 1, 'average': 99}])
    r = CCXTAdapter(exchange=ex).lookup_order('BTC/USDT', 'abc')
    assert ex.annules == ['6'] and r['status'] == 'canceled' and r['qty'] == 1.0
    assert CCXTAdapter(exchange=ExchangeRapprochement([], inconnu=True)).lookup_order('BTC/USDT', 'x') is None


# ------------------------------------------------------------------ réglages
def test_reglage_invalide_remplace_par_defaut():
    CORRECTIONS.clear()
    s = Settings.tolerant(mode='demo', max_order_usdt=float('nan'), stop_loss_pct=250.0, symbols=('ETH/USDT',))
    assert s.mode == 'demo' and s.symbols == ('ETH/USDT',)
    assert s.max_order_usdt == Settings().max_order_usdt and s.stop_loss_pct == Settings().stop_loss_pct
    assert len(CORRECTIONS) == 2
    CORRECTIONS.clear()


def test_from_env_ne_plante_jamais(monkeypatch):
    CORRECTIONS.clear()
    monkeypatch.setenv('MAX_ORDER_USDT', '-5')
    monkeypatch.setenv('V17_SCORE_MIN', '7')
    s = Settings.from_env()
    assert s.max_order_usdt == 100 and s.score_min == 0.65 and len(CORRECTIONS) == 2
    CORRECTIONS.clear()


# ------------------------------------------------------------------ boucle
def test_cli_reglage_invalide_attend_au_lieu_de_s_arreter(monkeypatch, reglages):
    import v17_ops.cli as C
    monkeypatch.setattr(C, "settings", reglages(demo_only=True))       # demo_only + paper = ConfigError
    monkeypatch.setattr(C, "_journal", lambda f: None)
    attentes, envoyes = [], []
    monkeypatch.setattr(C, "dormir", attentes.append)
    from v17_ops import notify
    monkeypatch.setattr(notify.Notifier, "send", lambda self, msg, important=True: envoyes.append(msg))
    assert C.main([]) == 2 and attentes == [C.ATTENTE_CONFIG_S]
    assert C.main([]) == 2 and len(envoyes) == 1                      # une seule alerte, même après redémarrage


def test_cli_repli_si_aucun_symbole_valable(monkeypatch, reglages):
    import ccxt
    import v17_ops.cli as C
    from v17_ops import notify
    monkeypatch.setattr(C, "settings", reglages(interval=10, symbols=('XXX/USDT',)))
    monkeypatch.setattr(C, "_journal", lambda f: None)
    envoyes, vus = [], []
    monkeypatch.setattr(notify.Notifier, "send", lambda self, msg, important=True: envoyes.append(msg))

    def faux_tick(self, symbol, price=None):
        vus.append(symbol)
        if symbol == 'XXX/USDT':
            raise ccxt.BadSymbol('binance does not have market symbol XXX/USDT')
        raise KeyboardInterrupt
    monkeypatch.setattr(W.OpsEngine, "tick", faux_tick)
    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    assert C.main([]) == 0
    assert vus == ['XXX/USDT', C.SYMBOLE_REPLI] and any("continue sur BTC/USDT" in m for m in envoyes)


def test_cli_redemarrage_a_neuf_apres_une_heure_d_echecs(monkeypatch, reglages):
    import v17_ops.cli as C
    from v17_ops import notify
    monkeypatch.setattr(C, "settings", reglages(interval=10))
    monkeypatch.setattr(C, "_journal", lambda f: None)
    monkeypatch.setattr(notify.Notifier, "send", lambda self, msg, important=True: None)
    tours = []
    monkeypatch.setattr(W.OpsEngine, "tick", lambda self, s, p=None: (_ for _ in ()).throw(RuntimeError("panne")))
    monkeypatch.setattr(C.time, "sleep", tours.append)
    assert C.main([]) == C.CODE_REDEMARRAGE
    assert len(tours) == C.tours_avant_redemarrage(10) - 1 and sum(tours) >= C.DUREE_KO_AVANT_REDEMARRAGE_S - 10


def test_cli_coupure_reseau_longue_pas_de_redemarrage(monkeypatch, reglages):
    import ccxt
    import v17_ops.cli as C
    from v17_ops import notify
    monkeypatch.setattr(C, "settings", reglages(interval=10))
    monkeypatch.setattr(C, "_journal", lambda f: None)
    monkeypatch.setattr(notify.Notifier, "send", lambda self, msg, important=True: None)
    monkeypatch.setattr(W.OpsEngine, "tick",
                        lambda self, s, p=None: (_ for _ in ()).throw(ccxt.NetworkError("binance down")))
    n = {"tours": 0}

    def pause(s):
        n["tours"] += 1
        if n["tours"] > 2 * C.tours_avant_redemarrage(10):
            raise KeyboardInterrupt
    monkeypatch.setattr(C.time, "sleep", pause)
    assert C.main([]) == 0                                            # il attend Binance, il ne redémarre pas


def test_cli_signe_de_vie_en_panne_ne_tue_pas_la_boucle(monkeypatch, reglages):
    import v17_ops.cli as C
    monkeypatch.setattr(C, "settings", reglages(interval=10))
    monkeypatch.setattr(C, "_journal", lambda f: None)
    monkeypatch.setattr(W.OpsEngine, "heartbeat", lambda self, extra=None: 1 / 0)
    monkeypatch.setattr(W.OpsEngine, "tick", lambda self, s, p=None: {'status': 'waiting'})
    n = {"tours": 0}

    def pause(s):
        n["tours"] += 1
        if n["tours"] >= 3:
            raise KeyboardInterrupt
    monkeypatch.setattr(C.time, "sleep", pause)
    assert C.main([]) == 0 and n["tours"] == 3


def test_sd_notify_sans_systemd_ne_fait_rien(monkeypatch):
    import v17_ops.cli as C
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    C.sd_notify("WATCHDOG=1")
    monkeypatch.setenv("NOTIFY_SOCKET", "/chemin/inexistant")
    C.sd_notify("WATCHDOG=1")                                         # socket absent : ignoré, jamais d'erreur
