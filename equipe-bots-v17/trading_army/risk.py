from .config import TradingConfig
from .schemas import TradeIntent, RiskDecision
class RiskEngine:
    def __init__(self, config=None): self.config=config or TradingConfig()
    def check(self, intent: TradeIntent, equity_usdt: float, open_orders: int=0, daily_pnl_usdt: float=0):
        if intent.quantity <= 0: return RiskDecision(False,"quantity must be positive")
        notional=(intent.quantity*(intent.limit_price or 0))
        if notional > self.config.max_order_usdt: return RiskDecision(False,"order size limit")
        if notional > self.config.max_position_usdt: return RiskDecision(False,"position size limit")
        if open_orders >= self.config.max_open_orders: return RiskDecision(False,"too many open orders")
        if daily_pnl_usdt <= -self.config.max_daily_loss_usdt: return RiskDecision(False,"daily loss limit")
        if notional > equity_usdt*self.config.capital_max_usdt/max(self.config.capital_max_usdt,1): return RiskDecision(False,"equity constraint")
        return RiskDecision(True,"risk checks passed")
