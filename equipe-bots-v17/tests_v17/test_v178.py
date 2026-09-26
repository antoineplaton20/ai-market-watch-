"""Régressions financières et de reprise : aucun ordre externe."""
from dataclasses import replace
import time
import pytest
from outils_v17 import FakeMarket, hausse
from test_plateforme import moteur
from test_increvable import BinanceCoupee, _moteur, _vieillir
from v17_ops.core.config import Settings, CORRECTIONS
from v17_ops.core.governor import RiskGovernor
from v17_ops.core.store import OpsStore
from v17_ops import rapport


def test_risque_taille_position_et_capital_inactif(reglages):
    s = reglages(capital_max_usdt=1000, stop_loss_pct=3, fee_rate=.001,
                 max_slippage_pct=.25, risk_per_trade_pct=.5)
    g = RiskGovernor(OpsStore(s.ops_db), 'paper', s)
    ok, _, nominal = g.assess(10000, 0)
    assert ok and nominal * .037 == pytest.approx(5)
    # 100 USDT perdus = 10 % du budget de 1000, même avec 10000 de cash fictif.
    assert g.assess(9899, 0)[1] == 'portfolio_drawdown_limit'


def test_arret_persistant_et_reprise_ne_le_contourne_pas(reglages):
    s = reglages()
    store = OpsStore(s.ops_db)
    RiskGovernor(store, 'paper', s).assess(1000, 0)
    assert not RiskGovernor(store, 'paper', s).assess(899, 0)[0]
    rapport.regler_pause(False, store, s)
    assert not RiskGovernor(OpsStore(s.ops_db), 'paper', s).assess(1200, 0)[0]
    assert rapport.etat(store, s)['governor']['halted']


def test_nombre_positions_limite_achats(reglages):
    e = moteur(reglages, FakeMarket(hausse()), symbols=('BTC/USDT','ETH/USDT'), max_positions=1)
    assert e.tick('BTC/USDT')['status'] == 'filled'
    assert e.tick('ETH/USDT')['reason'] == 'portfolio_positions_limit'


def test_redemarrage_conserve_la_derniere_valorisation(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m, max_drawdown_pct=5)
    e.tick('BTC/USDT')
    e._set_price('BTC/USDT', 260)
    e.heartbeat()
    other = moteur(reglages, m, store=e.store, max_drawdown_pct=5)
    assert not other.store.get('governor:paper')['halted']
    assert other.equity() == pytest.approx(e.equity())


@pytest.mark.parametrize('value', ['abc', 'nan', '-2', 'inf'])
def test_configuration_invalide_bloque_achats(monkeypatch, value):
    CORRECTIONS.clear()
    monkeypatch.setenv('V17_RISK_PER_TRADE_PCT', value)
    assert Settings.from_env().entries_blocked
    CORRECTIONS.clear()


def test_configuration_bloquee_garde_les_sorties(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m)
    entry = e.tick('BTC/USDT')
    e.settings = replace(e.settings, entries_blocked=True)
    assert e._buy('ETH/USDT', 100, 1)['reason'] == 'invalid_configuration'
    m.forming = entry['price'] * .9
    assert e.tick('BTC/USDT')['side'] == 'sell'


def test_stop_declenche_repos_persistant(reglages):
    m = FakeMarket(hausse())
    e = moteur(reglages, m, cooldown_bars=4)
    entry = e.tick('BTC/USDT')
    m.forming = entry['price'] * .96
    assert e.tick('BTC/USDT')['side'] == 'sell'
    other = moteur(reglages, m, store=e.store, cooldown_bars=4)
    assert other._buy('BTC/USDT', entry['price'], 1)['reason'] == 'stop_cooldown'
    other.store.set('cooldown:paper:BTC/USDT', time.time()-1)
    assert other._buy('BTC/USDT', entry['price'], 1)['status'] == 'filled'


def test_rapprochement_refuse_quantite_superieure(reglages):
    fx = BinanceCoupee(hausse(), {'id':'1', 'status':'closed','qty':100,'price':130})
    e, _ = _moteur(fx, reglages)
    e.tick('BTC/USDT')
    _vieillir(e, 3600)
    assert not e.rapprocher() and e.store.get('pending:demo')
    assert not e.book.open_positions()


def test_echec_commit_rapprochement_ne_double_pas_achat(reglages, monkeypatch):
    fx = BinanceCoupee(hausse(), {'id':'1', 'status':'closed','qty':.5,'price':130})
    e, _ = _moteur(fx, reglages)
    e.tick('BTC/USDT')
    save = e.store.finish_execution
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr(e.store, 'finish_execution', fail)
    _vieillir(e, 3600)
    assert not e.rapprocher() and e.store.get('pending:demo')
    monkeypatch.setattr(e.store, 'finish_execution', save)
    _vieillir(e, 3600)
    assert e.rapprocher()
    assert e.book.positions['BTC/USDT'] == pytest.approx(.5)
    assert e.book.cash == pytest.approx(1000 - 65 * 1.001)
    assert len(fx.ordres) == 1


def test_validation_reste_sans_position_si_aucun_avantage():
    from research.walk_forward_ops import choose
    from research.validate import STEP
    rows = [[i*STEP,100,100,100,100,1] for i in range(500)]
    chosen, results = choose(rows)
    assert chosen == 'cash' and results['cash']['base']['orders'] == 0


def test_selection_ne_recoit_pas_le_futur(monkeypatch):
    from research import walk_forward_ops as w
    monthly = {f'2025-{i:02}': [[i,100,100,100,100,1]] for i in range(1,10)}
    seen = []
    def select(rows):
        seen.extend(r[0] for r in rows)
        return 'cash', {}
    monkeypatch.setattr(w, 'choose', select)
    monkeypatch.setattr(w, 'run', lambda *args: {'pnl_usdt':0})
    r = w.evaluate(monthly)
    assert seen == [1,2,3,4,5,6]
    assert r['windows'][0]['test_months'] == ['2025-07','2025-08','2025-09']
