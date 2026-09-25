from __future__ import annotations
import os

class ExchangeFactory:
    """Crée un adaptateur CCXT. Par défaut: lecture seule / sandbox quand possible."""
    def __init__(self, mode="paper"):
        self.mode = mode

    def create(self, exchange_id="binance"):
        try: import ccxt
        except ImportError as e: raise RuntimeError("Installer ccxt") from e
        klass = getattr(ccxt, exchange_id)
        params = {"enableRateLimit": True}
        key = os.getenv("BINANCE_API_KEY")
        secret = os.getenv("BINANCE_API_SECRET")
        if self.mode in {"testnet", "live"} and exchange_id == "binance" and key and secret:
            params.update(apiKey=key, secret=secret)
        ex = klass(params)
        if self.mode == "testnet" and hasattr(ex, "set_sandbox_mode"):
            ex.set_sandbox_mode(True)
        return ex
