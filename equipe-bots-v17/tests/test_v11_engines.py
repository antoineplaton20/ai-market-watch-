import os
from moteurs.cost_engine import estimate
from moteurs.opportunity_engine import evaluate


def test_binance_standard_roundtrip_cost():
    c = estimate("binance", 1000, spread_pct=0.10, slippage_pct=0.05)
    assert round(c.entry_fee_pct, 3) == 0.10
    assert c.total_pct > 0.30


def test_trade_republic_fixed_fee_scales_with_notional():
    c50 = estimate("trade_republic", 50, spread_pct=0, slippage_pct=0)
    c5000 = estimate("trade_republic", 5000, spread_pct=0, slippage_pct=0)
    assert c50.total_pct > c5000.total_pct


def test_opportunity_requires_all_timeframes():
    checks = {"4h": True, "1h": True, "15m": True, "5m": False}
    c = estimate("binance", 1000, spread_pct=0.02, slippage_pct=0.02)
    o = evaluate("BUY", checks, True, True, True, True, c, 2.0)
    assert not o.allowed
    assert "entry_5m" in o.reasons


def test_opportunity_is_net_positive_after_costs():
    checks = {"4h": True, "1h": True, "15m": True, "5m": True}
    c = estimate("binance", 1000, spread_pct=0.10, slippage_pct=0.05)
    o = evaluate("BUY", checks, True, True, True, True, c, 0.1, min_net_pct=0.15)
    assert not o.allowed
    assert "cost_margin" in o.reasons


def test_opportunity_allows_clean_setup():
    checks = {"4h": True, "1h": True, "15m": True, "5m": True}
    c = estimate("binance", 1000, spread_pct=0.02, slippage_pct=0.01)
    o = evaluate("BUY", checks, True, True, True, True, c, 2.0)
    assert o.allowed
    assert o.net_potential_pct > 0
