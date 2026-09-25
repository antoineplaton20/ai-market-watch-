from dataclasses import dataclass
from typing import Dict

@dataclass
class EvalResult:
    bot_id: str
    correctness: float
    reliability: float
    latency_ms: float
    cost: float

class Evaluator:
    def score(self, r: EvalResult):
        # Transparent composite; callers may replace weights per domain.
        return 0.55*r.correctness + 0.25*r.reliability + 0.10*(1/(1+r.latency_ms/1000)) + 0.10*(1/(1+r.cost))
