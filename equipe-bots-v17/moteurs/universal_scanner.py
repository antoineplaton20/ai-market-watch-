"""Scanner universel d'instruments.

Le scanner ne prédit pas les prix : il réduit l'univers aux instruments réellement
analysables et tradables avant d'envoyer les candidats au moteur MTF.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List
import math


class UniversalScanner:
    def __init__(self, *, min_volume_quote: float = 0.0, max_spread_pct: float = 1.0,
                 excluded: Iterable[str] = ()):
        self.min_volume_quote = float(min_volume_quote)
        self.max_spread_pct = float(max_spread_pct)
        self.excluded = {str(x).upper() for x in excluded}

    @staticmethod
    def _spread_pct(ticker: Dict[str, Any]) -> float:
        bid, ask = ticker.get("bid"), ticker.get("ask")
        if not bid or not ask or ask <= 0:
            return math.inf
        return (ask - bid) / ((ask + bid) / 2) * 100

    def evaluate(self, instrument: Any, ticker: Dict[str, Any] | None = None) -> Dict[str, Any]:
        ticker = ticker or {}
        symbol = str(getattr(instrument, "symbol", ""))
        spread = self._spread_pct(ticker)
        volume = float(ticker.get("quoteVolume") or ticker.get("quote_volume") or 0)
        reasons: List[str] = []
        if not getattr(instrument, "active", True):
            reasons.append("inactive")
        if symbol.upper() in self.excluded:
            reasons.append("excluded")
        if self.min_volume_quote and volume < self.min_volume_quote:
            reasons.append("volume")
        if spread > self.max_spread_pct:
            reasons.append("spread")
        if not ticker.get("bid") or not ticker.get("ask"):
            reasons.append("no_quote")
        return {
            "platform": getattr(instrument, "platform", "unknown"),
            "symbol": symbol,
            "tradable": not reasons,
            "reasons": reasons,
            "spread_pct": spread,
            "quote_volume": volume,
        }

    def scan(self, instruments: Iterable[Any], tickers: Dict[str, Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
        tickers = tickers or {}
        results = []
        for instrument in instruments:
            key = getattr(instrument, "symbol", "")
            results.append(self.evaluate(instrument, tickers.get(key, {})))
        return results
