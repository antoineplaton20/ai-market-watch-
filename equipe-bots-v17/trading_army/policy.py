from .config import TradingConfig

class PolicyEngine:
    """Barrière indépendante entre intelligence et action."""
    READ = "read"
    PAPER = "paper_trade"
    TESTNET = "testnet_trade"
    LIVE = "live_trade"

    def __init__(self, config=None): self.config = config or TradingConfig()

    def authorize(self, mode: str, action: str, amount_usdt: float = 0) -> tuple[bool, str]:
        if action == "withdraw": return False, "withdrawals disabled by design"
        if self.config.kill_switch: return False, "global kill switch active"
        if amount_usdt > self.config.max_order_usdt: return False, "order exceeds max_order_usdt"
        if mode == "live" and not self.config.can_trade_live: return False, "live trading is not enabled"
        if mode not in {"paper", "testnet", "live", "demo"}: return False, "unknown execution mode"
        return True, "authorized"
