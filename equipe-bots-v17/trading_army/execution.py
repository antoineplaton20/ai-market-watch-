from __future__ import annotations
from .schemas import TradeIntent, TradeResult
from .policy import PolicyEngine
from .config import TradingConfig

class ExecutionEngine:
    def __init__(self, exchange=None, config=None):
        self.config=config or TradingConfig(); self.exchange=exchange; self.policy=PolicyEngine(self.config)
    def execute(self, intent: TradeIntent):
        amount=(intent.quantity*(intent.limit_price or 0))
        ok,reason=self.policy.authorize(self.config.mode, "trade", amount)
        if not ok: return TradeResult(intent.id,"rejected",error=reason)
        if self.config.mode in {"paper","demo"}:
            return TradeResult(intent.id,"paper_filled",filled_quantity=intent.quantity,average_price=intent.limit_price)
        if self.exchange is None: return TradeResult(intent.id,"rejected",error="exchange adapter missing")
        try:
            order=self.exchange.create_order(intent.symbol,intent.order_type,intent.side,intent.quantity,intent.limit_price)
            return TradeResult(intent.id,"submitted",exchange_order_id=str(order.get("id")))
        except Exception as e:
            return TradeResult(intent.id,"error",error=str(e))
