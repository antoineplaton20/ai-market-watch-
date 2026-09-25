"""Conservative close-only research simulator. Signals execute one bar later.

This is not a fill model for live trading; open positions are marked to their
estimated liquidation value, with exit fees and slippage included.
"""
import math
from dataclasses import dataclass
from typing import List

@dataclass
class BacktestResult:
    trades: int
    pnl: float
    max_drawdown: float
    win_rate: float
    score: float

class StrategyLab:
    def backtest(self, closes: List[float], signal_fn, *, fee_rate=0.001, slippage_pct=0.05):
        if not math.isfinite(fee_rate) or not 0 <= fee_rate < 1:
            raise ValueError('fee_rate')
        if not math.isfinite(slippage_pct) or not 0 <= slippage_pct < 100:
            raise ValueError('slippage_pct')
        if any(not math.isfinite(p) or p <= 0 for p in closes):
            raise ValueError('invalid price')
        cash = peak = 10000.0
        pos = dd = entry_cost = 0.0
        pnls = []
        trades = 0
        pending = None
        slip = slippage_pct / 100
        equity = cash
        for i, price in enumerate(closes):
            if pending == 'buy' and pos == 0:
                entry_cost = cash
                pos = cash / (price * (1 + slip) * (1 + fee_rate))
                cash = 0.0
                trades += 1
            elif pending == 'sell' and pos > 0:
                cash = pos * price * (1 - slip) * (1 - fee_rate)
                pos = 0.0
                pnls.append(cash - entry_cost)
                trades += 1
            equity = cash + pos * price * (1 - slip) * (1 - fee_rate)
            peak = max(peak, equity)
            dd = max(dd, (peak - equity) / peak)
            pending = signal_fn(closes[:i + 1])
        pnl = equity - 10000.0
        return BacktestResult(trades, pnl, dd,
                              sum(p > 0 for p in pnls) / len(pnls) if pnls else 0.0,
                              pnl - 10000.0 * dd)
