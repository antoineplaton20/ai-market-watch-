from moteurs.instrument_registry import Instrument, InstrumentRegistry
from moteurs.universal_scanner import UniversalScanner
from moteurs.correlation_engine import pearson, veto_against_open


def test_registry_binance_and_trade_republic():
    r = InstrumentRegistry()
    assert r.add_binance_markets({"BTC/USDT": {"active": True, "spot": True, "type": "spot", "base": "BTC", "quote": "USDT", "limits": {"amount": {"min": 0.0001}}, "precision": {}}}) == 1
    assert r.add_trade_republic_rows([{"isin": "US123", "name": "Example", "kind": "stock", "currency": "EUR"}]) == 1
    assert len(r.active()) == 2


def test_scanner_rejects_wide_spread_and_low_volume():
    i = Instrument(platform="binance", symbol="AAA/USDT")
    s = UniversalScanner(min_volume_quote=1000, max_spread_pct=0.2)
    out = s.evaluate(i, {"bid": 99, "ask": 101, "quoteVolume": 10})
    assert not out["tradable"]
    assert "spread" in out["reasons"] and "volume" in out["reasons"]


def test_correlation_veto():
    a = [0.01, 0.02, -0.01, 0.03]
    assert pearson(a, a) > 0.99
    veto, reasons = veto_against_open("A", {"A": a, "B": a}, ["B"], 0.85)
    assert veto and reasons


def test_registry_ignore_futures_binance():
    r = InstrumentRegistry()
    n = r.add_binance_markets({
        "BTC/USDT": {"active": True, "spot": True, "type": "spot", "base": "BTC", "quote": "USDT"},
        "BTC/USDT:USDT": {"active": True, "spot": False, "type": "swap", "base": "BTC", "quote": "USDT"},
    })
    assert n == 1 and [i.symbol for i in r.all()] == ["BTC/USDT"]


def test_correlation_negative_pas_de_veto():
    a = [0.01, 0.02, -0.01, 0.03]
    b = [-x for x in a]
    veto, _ = veto_against_open("A", {"A": a, "B": b}, ["B"], 0.85)
    assert not veto
