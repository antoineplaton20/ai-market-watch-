from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any

class SourceError(RuntimeError): pass

class BinanceSource:
    def __init__(self, exchange=None): self.exchange = exchange
    def ticker(self, symbol: str) -> Dict[str, Any]:
        if self.exchange is None: raise SourceError("ccxt exchange not configured")
        return self.exchange.fetch_ticker(symbol)
    def order_book(self, symbol: str, limit=50):
        if self.exchange is None: raise SourceError("ccxt exchange not configured")
        return self.exchange.fetch_order_book(symbol, limit)
    def ohlcv(self, symbol: str, timeframe="1h", limit=500):
        if self.exchange is None: raise SourceError("ccxt exchange not configured")
        return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

class YahooSource:
    def __init__(self):
        try: import yfinance as yf
        except ImportError: yf = None
        self.yf = yf
    def history(self, ticker: str, period="1y", interval="1d"):
        if self.yf is None: raise SourceError("yfinance not installed")
        return self.yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)

class SourceFusion:
    def merge(self, *observations):
        return [o for o in observations if o is not None]


def utc_now(): return datetime.now(timezone.utc).isoformat()
