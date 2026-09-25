"""Prix publics Binance (aucune clé, aucun ordre) : c'est la source de prix du mode paper."""
from __future__ import annotations

import time
import math

TF_MS = {'1m': 60_000, '3m': 180_000, '5m': 300_000, '15m': 900_000, '30m': 1_800_000, '1h': 3_600_000,
         '2h': 7_200_000, '4h': 14_400_000, '6h': 21_600_000, '8h': 28_800_000, '12h': 43_200_000,
         '1d': 86_400_000}


def closed_candles(rows, timeframe, now_ms=None):
    """Garde uniquement les bougies FERMÉES (la dernière renvoyée par Binance est en cours de formation)."""
    now_ms = now_ms if now_ms is not None else time.time() * 1000
    duree = TF_MS[timeframe]
    return [r for r in rows if r[0] + duree <= now_ms]


class BinancePublic:
    def __init__(self, exchange=None):
        if exchange is None:
            import ccxt
            exchange = ccxt.binance({
                'enableRateLimit': True,
                # spot uniquement : ne charge pas les marchés futures (moins de poids sur la limite d'IP
                # partagée avec le bot principal)
                'options': {'defaultType': 'spot', 'fetchMarkets': {'types': ['spot']}},
            })
        self.exchange = exchange

    def fetch_ohlcv(self, symbol, timeframe='15m', limit=120):
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def fetch_ticker(self, symbol):
        return self.exchange.fetch_ticker(symbol)


def validate_candles(rows, timeframe, now_ms=None):
    """Reject corrupt, unordered, gapped or stale feeds before any decision."""
    now = time.time() * 1000 if now_ms is None else now_ms
    step = TF_MS[timeframe]
    previous = None
    for row in rows:
        if len(row) < 6 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in row[:6]):
            raise ValueError('invalid_ohlcv')
        ts, op, high, low, close, vol = row[:6]
        if ts < 0 or ts > now or ts % step or min(op, high, low, close) <= 0 or vol < 0:
            raise ValueError('invalid_ohlcv')
        if low > min(op, close) or high < max(op, close) or low > high:
            raise ValueError('invalid_ohlcv')
        if previous is not None and ts - previous != step:
            raise ValueError('non_contiguous_ohlcv')
        previous = ts
    if rows and now - rows[-1][0] > 2 * step:
        raise ValueError('stale_ohlcv')
    return rows
