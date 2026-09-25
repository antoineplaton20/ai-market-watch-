"""Moteur de coûts v11: frais, spread, slippage et coût aller-retour.

Les taux sont configurables par environnement et peuvent être remplacés par les
frais réellement observés dans l'historique du compte. Ne jamais coder un taux
comme vérité permanente: les barèmes des plateformes évoluent.
"""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class CostEstimate:
    platform: str
    notional: float
    entry_fee_pct: float
    exit_fee_pct: float
    spread_pct: float
    slippage_pct: float
    fixed_entry: float
    fixed_exit: float

    @property
    def total_pct(self):
        variable = self.entry_fee_pct + self.exit_fee_pct + self.spread_pct + self.slippage_pct
        fixed = (self.fixed_entry + self.fixed_exit) / max(self.notional, 1e-9) * 100
        return variable + fixed

    @property
    def total_amount(self):
        return self.notional * self.total_pct / 100


def _f(name, default):
    return float(os.getenv(name, str(default)))


def estimate(platform, notional, spread_pct=0.0, slippage_pct=0.0,
             entry_role="taker", exit_role=None):
    platform = platform.lower().replace(" ", "_")
    exit_role = exit_role or entry_role
    if platform == "binance":
        # Standard Spot: 0.10% maker / 0.10% taker; overrides support VIP/BNB/account fees.
        maker = _f("BINANCE_MAKER_FEE_PCT", 0.10)
        taker = _f("BINANCE_TAKER_FEE_PCT", 0.10)
        entry_fee = maker if entry_role == "maker" else taker
        exit_fee = maker if exit_role == "maker" else taker
        return CostEstimate("binance", notional, entry_fee, exit_fee,
                            spread_pct, slippage_pct, 0.0, 0.0)
    if platform in ("trade_republic", "traderepublic", "trade-republic"):
        # Trade Republic: single-trade settlement fee is configurable (default 1 EUR).
        fixed = _f("TRADE_REPUBLIC_SETTLEMENT_FEE_EUR", 1.0)
        direct = _f("TRADE_REPUBLIC_DIRECT_PRICE_FEE_EUR", 2.0)
        # Caller can select direct-price through TR_DIRECT_PRICE=1.
        fixed = direct if os.getenv("TR_DIRECT_PRICE", "0") == "1" else fixed
        return CostEstimate("trade_republic", notional, 0.0, 0.0,
                            spread_pct, slippage_pct, fixed, fixed)
    raise ValueError(f"plateforme inconnue: {platform}")


def break_even_pct(cost: CostEstimate, safety_margin_pct=0.0):
    return cost.total_pct + safety_margin_pct


def net_return_pct(gross_return_pct, cost: CostEstimate):
    return gross_return_pct - cost.total_pct
