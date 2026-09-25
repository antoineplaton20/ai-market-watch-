"""Porte d'autorisation v11.

Aucune entrée si une condition obligatoire n'est pas positive. Le profit attendu
est évalué NET des coûts estimés. Ce moteur ne remplace jamais le moteur de risque.
"""
from dataclasses import dataclass, asdict
from typing import Dict

from moteurs.cost_engine import CostEstimate, break_even_pct, net_return_pct


@dataclass
class Opportunity:
    allowed: bool
    direction: str
    gross_potential_pct: float
    cost_pct: float
    net_potential_pct: float
    min_net_pct: float
    conditions: Dict[str, bool]
    reasons: list

    def to_dict(self):
        return asdict(self)


def evaluate(direction, timeframe_checks, risk_ok, data_ok, liquidity_ok,
             spread_ok, cost: CostEstimate, gross_potential_pct,
             min_net_pct=0.15, safety_margin_pct=0.05):
    conditions = {
        "regime_4h": bool(timeframe_checks.get("4h", False)),
        "trend_1h": bool(timeframe_checks.get("1h", False)),
        "signal_15m": bool(timeframe_checks.get("15m", False)),
        "entry_5m": bool(timeframe_checks.get("5m", False)),
        "risk": bool(risk_ok),
        "data": bool(data_ok),
        "liquidity": bool(liquidity_ok),
        "spread": bool(spread_ok),
        "cost_margin": bool(gross_potential_pct >= break_even_pct(cost, safety_margin_pct) + min_net_pct),
    }
    reasons = [name for name, ok in conditions.items() if not ok]
    net = net_return_pct(gross_potential_pct, cost)
    return Opportunity(not reasons, direction, gross_potential_pct, cost.total_pct,
                       net, min_net_pct, conditions, reasons)
