import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass
class TradingConfig:
    mode: str = os.getenv("MODE", "paper").lower()
    capital_max_usdt: float = float(os.getenv("CAPITAL_MAX_USDT", "1000"))
    live_enabled: bool = os.getenv("LIVE_TRADING_ENABLED", "0") == "1"
    allow_withdrawals: bool = False
    max_order_usdt: float = float(os.getenv("MAX_ORDER_USDT", "100"))
    max_daily_loss_usdt: float = float(os.getenv("MAX_DAILY_LOSS_USDT", "25"))
    max_position_usdt: float = float(os.getenv("MAX_POSITION_USDT", "100"))
    max_slippage_pct: float = float(os.getenv("MAX_SLIPPAGE_PCT", "0.25"))
    max_open_orders: int = int(os.getenv("MAX_OPEN_ORDERS", "10"))
    kill_switch: bool = os.getenv("KILL_SWITCH", "0") == "1"

    @property
    def can_trade_live(self):
        return self.mode == "live" and self.live_enabled and not self.kill_switch
