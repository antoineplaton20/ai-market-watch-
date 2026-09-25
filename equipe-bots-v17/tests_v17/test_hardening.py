import math
import pytest
from v17_ops.core.portfolio import PaperPortfolio
from v17_ops.core.risk import RiskGate
from v17_ops.core.events import Intent
from v17_ops.core.config import Settings
from v17_ops.adapters.market import validate_candles
from v17_ops.adapters.ccxt_adapter import CCXTAdapter
from v17_ops.strategies.ensemble import Ensemble, StrategyVote
from v17_ops.workers.engine import OpsEngine
from trading_army.strategy_lab import StrategyLab
from outils_v17 import FakeMarket, hausse
from test_plateforme import FauxBinance


def test_round_trip_and_partial_sale_include_both_fees():
    book = PaperPortfolio(1000)
    book.execute('X', 'buy', 2, 100, .01)
    assert book.execute('X', 'sell', 1, 100, .01)['pnl'] == pytest.approx(-2)
    book = PaperPortfolio.from_dict(book.to_dict())
    assert book.entry_fees['X'] == pytest.approx(1)
    book.execute('X', 'sell', 1, 100, .01)
    assert book.realized_pnl == pytest.approx(book.cash - 1000)
    assert book.realized_pnl == pytest.approx(-4)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, 0])
def test_bad_price_never_mutates_cash(value):
    book = PaperPortfolio(1000)
    with pytest.raises(ValueError):
        book.execute('X', 'buy', 1, value)
    assert book.cash == 1000 and not book.positions
    intent = Intent('X', 'buy', 1, 'market', value, 'test', '')
    assert not RiskGate().check(intent, 1000, 0, 0).allowed


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, 0])
def test_invalid_capital_refused(value):
    with pytest.raises(ValueError):
        Settings(capital_max_usdt=value)


def test_feed_rejects_stale_duplicate_gap_and_future():
    good = [[0, 100, 100, 100, 100, 1], [60000, 100, 100, 100, 100, 1]]
    validate_candles(good, '1m', now_ms=120000)
    for bad, now in [(good, 900000), (good + [good[-1]], 120000),
                     ([good[0], [180000, 100, 100, 100, 100, 1]], 180000),
                     (good, 0)]:
        with pytest.raises(ValueError):
            validate_candles(bad, '1m', now_ms=now)


def test_tiny_agreement_not_high_confidence():
    agg = Ensemble().aggregate([StrategyVote('a', 'buy', .00001, ''), StrategyVote('b', 'buy', .00001, '')])
    assert agg[1] < .01


class Exchange:
    def __init__(self, result):
        self.result = result
    def load_markets(self):
        pass
    def amount_to_precision(self, symbol, qty):
        return str(qty)
    def create_order(self, *args):
        return self.result
    def fetch_order(self, *args):
        return self.result


@pytest.mark.parametrize('result', [
    {'id': '1', 'status': 'closed', 'filled': 0, 'average': 100},
    {'id': '1', 'status': 'open', 'filled': .5, 'average': 100},
    {'id': '1', 'status': 'closed', 'filled': 1},
    {'id': '1', 'status': 'closed', 'filled': math.nan, 'average': 100},
])
def test_never_invent_fill(result):
    with pytest.raises(RuntimeError):
        CCXTAdapter(exchange=Exchange(result)).market_order('X', 'buy', 1, 100)


def test_final_partial_fill_is_preserved():
    result = {'id': '1', 'status': 'canceled', 'filled': .4, 'cost': 40}
    fill = CCXTAdapter(exchange=Exchange(result)).market_order('X', 'buy', 1, 100)
    assert fill['qty'] == .4 and fill['price'] == 100


def test_timeout_latches_across_restart_and_never_retries(reglages):
    class TimeoutExchange(FauxBinance):
        calls = 0
        def market_order(self, *args, **kwargs):
            self.calls += 1
            raise TimeoutError('unknown exchange outcome')
    fx = TimeoutExchange(hausse())
    settings = reglages(mode='demo')
    e = OpsEngine(settings=settings, executor=fx)
    assert e.tick('BTC/USDT')['status'] == 'error'
    assert e.book.cash == 1000
    e2 = OpsEngine(settings=settings, executor=fx, store=e.store)
    assert e2.tick('BTC/USDT')['status'] == 'reconciliation_required'
    assert fx.calls == 1


def test_open_order_cap_enforced(reglages):
    fx = FauxBinance(hausse())
    fx.open_orders_count = lambda: 5
    e = OpsEngine(settings=reglages(mode='demo'), executor=fx)
    assert e.tick('BTC/USDT')['reason'] == 'open_orders_limit'
    assert not fx.ordres


def test_stale_feed_never_buys(reglages):
    market = FakeMarket(hausse())
    market.ts0 -= 900000 * 10
    e = OpsEngine(settings=reglages(), market=market)
    assert e.tick('BTC/USDT')['reason'] == 'stale_ohlcv'
    assert not e.book.open_positions()


def test_lab_delays_fill_and_applies_costs():
    # Price doubles before fill: cannot profit from a jump already observed.
    r = StrategyLab().backtest([100, 200, 200], lambda c: 'buy' if len(c) == 1 else 'sell', fee_rate=0, slippage_pct=0)
    assert r.pnl == 0
    r = StrategyLab().backtest([100, 100, 100], lambda c: 'buy' if len(c) == 1 else 'sell')
    assert r.pnl < 0 and r.trades == 2


def test_lab_winrate_is_per_trade_not_cumulative():
    # +100%, then -10%: cumulative cash still positive, second trade is a loser.
    prices = [100, 100, 200, 200, 200, 180]
    actions = ['buy', 'sell', 'hold', 'buy', 'sell', 'hold']
    r = StrategyLab().backtest(prices, lambda c: actions[len(c)-1], fee_rate=0, slippage_pct=0)
    assert r.win_rate == .5


def test_daily_loss_latch_does_not_reopen_after_rebound(reglages):
    import datetime as dt
    e = OpsEngine(settings=reglages())
    e.store.set('jour:paper', {'date': dt.datetime.now(dt.timezone.utc).date().isoformat(), 'equity': 10100})
    assert e.daily_pnl() <= -50
    e.book.cash = 11000
    assert e.daily_pnl() <= -50


def test_unconfirmed_marker_and_book_commit_atomically(reglages):
    e = OpsEngine(settings=reglages())
    e.store.set('pending:paper', {'id': 'x'})
    e.book.cash = 777
    e._finish_execution()
    assert e.store.get('pending:paper') is None
    assert e.store.get('portfolio:paper')['cash'] == 777


def test_research_checksum_parser_rejects_missing_month():
    import io
    import zipfile
    from research.validate import decode
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('sample.csv', '1704067200000,100,100,100,100,1\n')
    with pytest.raises(ValueError, match='missing'):
        decode(stream.getvalue(), '2024-01')


def test_backtest_cannot_reinvest_future_profit(monkeypatch):
    import backtest
    monkeypatch.setattr(backtest.config, 'POSITIONS_MAX', 3)
    monkeypatch.setattr(backtest.config, 'RISQUE_PAR_TRADE_PCT', 1)
    monkeypatch.setattr(backtest.config, 'POSITION_MAX_PCT', 100)
    trades = [{'t': 1, 't_sortie': 10, 'r': 1, 'pnl_pct': 1},
              {'t': 2, 't_sortie': 11, 'r': 1, 'pnl_pct': 1}]
    # Both were sized before either profit was realized; no compounding.
    assert backtest.portefeuille(trades)[0] == pytest.approx(1.02)


def test_slippage_gate_blocks_expensive_or_thin_book():
    ex = Exchange({})
    adapter = CCXTAdapter(exchange=ex)
    ex.fetch_order_book = lambda *a, **k: {'asks': [[101, 10]]}
    assert not adapter.check_buy_liquidity('X', 1, 100, .25)
    ex.fetch_order_book = lambda *a, **k: {'asks': [[100.1, .1]]}
    assert not adapter.check_buy_liquidity('X', 1, 100, .25)
    ex.fetch_order_book = lambda *a, **k: {'asks': [[100.1, 2]]}
    assert adapter.check_buy_liquidity('X', 1, 100, .25)


def test_injected_prices_cannot_trigger_exchange_orders(reglages):
    fx = FauxBinance(hausse())
    e = OpsEngine(settings=reglages(mode='demo'), executor=fx)
    assert e.tick('BTC/USDT', 1)['reason'] == 'injected_price_requires_paper'
    assert not fx.ordres
