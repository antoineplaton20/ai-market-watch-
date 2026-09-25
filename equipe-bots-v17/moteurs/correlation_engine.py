"""Contrôle d'exposition par corrélation des rendements."""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple
import math


def pearson(a: Iterable[float], b: Iterable[float]) -> float:
    x, y = list(a), list(b)
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x, y = x[-n:], y[-n:]
    mx, my = sum(x) / n, sum(y) / n
    num = sum((u - mx) * (v - my) for u, v in zip(x, y))
    dx = math.sqrt(sum((u - mx) ** 2 for u in x))
    dy = math.sqrt(sum((v - my) ** 2 for v in y))
    return num / (dx * dy) if dx and dy else 0.0


def veto_against_open(candidate: str, returns: Dict[str, List[float]], open_symbols: Iterable[str], threshold: float = 0.85) -> Tuple[bool, List[str]]:
    reasons = []
    if candidate not in returns:
        return False, reasons
    for symbol in open_symbols:
        if symbol not in returns:
            continue
        corr = pearson(returns[candidate], returns[symbol])
        # Achat seul (spot) : une corrélation NÉGATIVE diversifie, seul le « même sens » est redondant
        if corr >= threshold:
            reasons.append(f"correlation:{symbol}:{corr:.3f}")
    return bool(reasons), reasons
