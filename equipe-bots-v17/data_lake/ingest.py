"""Adaptateurs d'ingestion non intrusifs pour le Data Lake."""
from .store import DataLake


def ingest_ccxt_ohlcv(lake, exchange, symbols, timeframes, limit=1000, source=None):
    source = source or getattr(exchange, "id", "ccxt")
    n = 0
    for sym in symbols:
        for tf in timeframes:
            rows = exchange.fetch_ohlcv(sym, tf, limit=limit)
            lake.candles(source, sym, tf, rows)
            n += len(rows)
    return n


def ingest_ccxt_trades(lake, exchange, symbol, limit=1000, source=None):
    source = source or getattr(exchange, "id", "ccxt")
    rows = exchange.fetch_trades(symbol, limit=limit)
    for t in rows:
        lake.trade(source, symbol, t)
    return len(rows)


def ingest_ccxt_orderbook(lake, exchange, symbol, limit=100):
    ob = exchange.fetch_order_book(symbol, limit=limit)
    ts = ob.get("timestamp") or exchange.milliseconds()
    bid = ob["bids"][0][0] if ob.get("bids") else 0
    ask = ob["asks"][0][0] if ob.get("asks") else 0
    bid_depth = sum(p*q for p,q in ob.get("bids",[]) if p >= ((bid+ask)/2)*0.99) if bid and ask else 0
    ask_depth = sum(p*q for p,q in ob.get("asks",[]) if p <= ((bid+ask)/2)*1.01) if bid and ask else 0
    lake.orderbook(getattr(exchange,"id","ccxt"), symbol, ts, bid, ask, bid_depth, ask_depth)
    return ts
