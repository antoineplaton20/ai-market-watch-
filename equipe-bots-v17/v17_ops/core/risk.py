import uuid
import math
from dataclasses import dataclass


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ''
    risk_check_id: str = ''


class RiskGate:
    """Contrôle chaque intention d'ACHAT avant exécution. Les ventes (sorties) ne passent pas par ici :
    on ne bloque jamais la sortie d'une position."""

    def __init__(self, max_order_usdt=100, max_position_usdt=250, max_daily_loss_usdt=50, max_slippage_pct=.25,
                 max_open_orders=5):
        self.max_order_usdt = max_order_usdt
        self.max_position_usdt = max_position_usdt
        self.max_daily_loss_usdt = max_daily_loss_usdt
        self.max_slippage_pct = max_slippage_pct
        self.max_open_orders = max_open_orders

    def check(self, intent, equity, open_orders, daily_pnl, position_usdt=0.0):
        rid = str(uuid.uuid4())
        values = (intent.quantity, intent.limit_price or 0, equity, daily_pnl, position_usdt, open_orders)
        if not all(math.isfinite(v) for v in values) or position_usdt < 0 or open_orders < 0:
            return RiskDecision(False, 'invalid_numeric_data', rid)
        if intent.quantity <= 0 or (intent.limit_price or 0) <= 0:
            return RiskDecision(False, 'order_notional_limit', rid)
        notional = intent.quantity * (intent.limit_price or 0)
        if notional <= 0 or notional > self.max_order_usdt + 1e-9:
            return RiskDecision(False, 'order_notional_limit', rid)
        if equity <= 0:
            return RiskDecision(False, 'invalid_equity', rid)
        if daily_pnl <= -self.max_daily_loss_usdt:
            return RiskDecision(False, 'daily_loss_limit', rid)
        if open_orders >= self.max_open_orders:
            return RiskDecision(False, 'open_orders_limit', rid)
        if position_usdt + notional > self.max_position_usdt + 1e-9:     # position DÉJÀ détenue + nouvel achat
            return RiskDecision(False, 'position_limit', rid)
        return RiskDecision(True, 'ok', rid)
