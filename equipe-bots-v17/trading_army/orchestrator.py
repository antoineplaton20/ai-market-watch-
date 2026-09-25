from .regime import RegimeDetector
from .risk import RiskEngine
from .execution import ExecutionEngine
from .schemas import TradeIntent

class TradingOrchestrator:
    def __init__(self, risk=None, execution=None):
        self.regime=RegimeDetector(); self.risk=risk or RiskEngine(); self.execution=execution or ExecutionEngine()
    def propose(self, symbol, side, quantity, price, strategy_id, reason=""):
        return TradeIntent(symbol,side,quantity,"limit",price,strategy_id,reason)
    def run(self, intent, equity_usdt, open_orders=0, daily_pnl_usdt=0):
        decision=self.risk.check(intent,equity_usdt,open_orders,daily_pnl_usdt)
        if not decision.allowed:
            from .schemas import TradeResult
            return TradeResult(intent.id,"risk_rejected",error=decision.reason)
        intent.risk_check_id=decision.risk_check_id
        return self.execution.execute(intent)
