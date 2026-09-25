"""Moteur multi-timeframe v11.

Règle: les décisions techniques utilisent uniquement la dernière bougie FERMÉE.
4h = régime, 1h = confirmation, 15m = signal, 5m = timing.
"""
import time
from dataclasses import dataclass
from typing import Dict, Optional

import config
from indicateurs import bougies, enrichir


@dataclass
class TFState:
    timeframe: str
    df: object
    closed_index: int = -2

    @property
    def closed(self):
        return self.df.iloc[self.closed_index]


def _load(ex, sym, tf, cache, limit=250):
    key = f"{sym}:{tf}"
    if key not in cache:
        df = enrichir(bougies(ex, sym, tf, limit))
        cache[key] = df
    return cache[key]


def snapshot(ex, sym, cache=None):
    cache = cache if cache is not None else {}
    out = {}
    for tf in (config.TIMEFRAME_REGIME, config.TIMEFRAME_TREND, config.TIMEFRAME_SIGNAL, config.TIMEFRAME_ENTRY):
        df = _load(ex, sym, tf, cache, 250)
        if df is None or len(df) < 60:
            raise ValueError(f"historique insuffisant {sym} {tf}")
        out[tf] = TFState(tf, df)
    return out


def bullish(state):
    d = state.closed
    return bool(d["c"] > d["ema50"] and d["ema20"] > d["ema50"])


def bearish(state):
    d = state.closed
    return bool(d["c"] < d["ema50"] and d["ema20"] < d["ema50"])


def score(states, direction="BUY"):
    f = bullish if direction == "BUY" else bearish
    checks = {tf: f(states[tf]) for tf in (config.TIMEFRAME_REGIME, config.TIMEFRAME_TREND,
                                            config.TIMEFRAME_SIGNAL, config.TIMEFRAME_ENTRY)}
    return (sum(checks.values()) / len(checks), checks)


def entry_confirmation(states, direction="BUY"):
    """Porte stricte: 4h/1h/15m/5m doivent confirmer la même direction."""
    score_tf, checks = score(states, direction)
    return score_tf == 1.0, checks


def clear_cache(cache, sym=None, timeframe=None):
    if sym is None and timeframe is None:
        cache.clear(); return
    for k in list(cache):
        s, tf = k.split(":", 1)
        if (sym is None or s == sym) and (timeframe is None or tf == timeframe):
            cache.pop(k, None)
