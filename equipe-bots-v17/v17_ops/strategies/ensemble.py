"""Two correlated technical signals; score is strength, never a probability."""
import math
from dataclasses import dataclass

@dataclass
class StrategyVote:
    bot_id: str
    side: str
    score: float
    reason: str

class Ensemble:
    def votes(self, closes):
        if len(closes) < 30 or any(not math.isfinite(x) or x <= 0 for x in closes):
            return []
        fast = sum(closes[-8:]) / 8
        slow = sum(closes[-30:]) / 30
        momentum = closes[-1] / closes[-10] - 1
        return [StrategyVote('trend_sma_001', 'buy' if fast > slow else 'sell',
                             min(abs(fast / slow - 1) * 100, 1), 'SMA8_vs_SMA30'),
                StrategyVote('momentum_001', 'buy' if momentum > 0 else 'sell',
                             min(abs(momentum) * 20, 1), '10-bar momentum')]

    def aggregate(self, votes):
        if not votes:
            return None
        if any(not math.isfinite(v.score) or not 0 <= v.score <= 1 or v.side not in ('buy', 'sell') for v in votes):
            return None
        buy = sum(v.score for v in votes if v.side == 'buy')
        sell = sum(v.score for v in votes if v.side == 'sell')
        if buy == sell:
            return None
        # Agreement between two infinitesimal signals no longer produces 100%.
        return ('buy' if buy > sell else 'sell', abs(buy - sell) / len(votes))
