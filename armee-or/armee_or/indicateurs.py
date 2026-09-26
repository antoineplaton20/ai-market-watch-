"""Indicateurs techniques (numpy), calculés comme TradingView (moyennes de Wilder pour RSI, ATR, ADX).
Copie autonome : l'armée de l'or ne dépend d'aucun fichier des autres bots."""
from __future__ import annotations

import numpy as np


def ema(x, n):
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if n < 1 or len(x) < n:
        return out
    a = 2.0 / (n + 1)
    out[n - 1] = x[:n].mean()                      # départ = moyenne simple, comme ta.ema
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def sma(x, n):
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if n < 1 or len(x) < n:
        return out
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def rma(x, n):
    """Moyenne de Wilder (ta.rma)."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if n < 1 or len(x) < n:
        return out
    out[n - 1] = np.nanmean(x[:n])
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def true_range(h, l, c):
    pc = np.concatenate(([np.nan], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    return tr


def atr(h, l, c, n=14):
    return rma(true_range(h, l, c), n)


def rsi(c, n=14):
    d = np.diff(c, prepend=np.nan)
    gain, perte = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    gain[0] = perte[0] = np.nan
    g, p = rma(gain[1:], n), rma(perte[1:], n)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(p == 0, 100.0, 100 - 100 / (1 + g / p))
    return np.concatenate(([np.nan], r))


def macd_hist(c, rapide=12, lente=26, signal=9):
    m = ema(c, rapide) - ema(c, lente)
    debut = np.argmax(~np.isnan(m)) if np.any(~np.isnan(m)) else len(m)
    s = np.full(len(m), np.nan)
    s[debut:] = ema(m[debut:], signal)
    return m - s


def adx(h, l, c, n=14):
    haut, bas = np.diff(h, prepend=np.nan), -np.diff(l, prepend=np.nan)
    plus = np.where((haut > bas) & (haut > 0), haut, 0.0)
    moins = np.where((bas > haut) & (bas > 0), bas, 0.0)
    tr = rma(true_range(h, l, c)[1:], n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100 * rma(plus[1:], n) / tr
        mdi = 100 * rma(moins[1:], n) / tr
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    debut = np.argmax(~np.isnan(dx)) if np.any(~np.isnan(dx)) else len(dx)
    a = np.full(len(dx), np.nan)
    a[debut:] = rma(np.nan_to_num(dx[debut:]), n)
    return np.concatenate(([np.nan], a))


def supertrend_haussier(h, l, c, n=10, mult=3.0):
    """True quand le Supertrend est haussier (direction < 0 dans ta.supertrend)."""
    a = atr(h, l, c, n)
    mid = (h + l) / 2
    haut_b, bas_b = mid + mult * a, mid - mult * a
    fh, fb = np.copy(haut_b), np.copy(bas_b)
    hausse = np.zeros(len(c), dtype=bool)
    for i in range(1, len(c)):
        if np.isnan(a[i]):
            continue
        if not np.isnan(fb[i - 1]):
            fb[i] = max(bas_b[i], fb[i - 1]) if c[i - 1] > fb[i - 1] else bas_b[i]
            fh[i] = min(haut_b[i], fh[i - 1]) if c[i - 1] < fh[i - 1] else haut_b[i]
        if np.isnan(a[i - 1]):
            hausse[i] = c[i] > fh[i]
        elif hausse[i - 1]:
            hausse[i] = c[i] >= fb[i]
        else:
            hausse[i] = c[i] > fh[i]
    return hausse


def plus_haut_precedent(h, n):
    """Plus haut des n bougies PRÉCÉDENTES (ta.highest(high, n)[1])."""
    h = np.asarray(h, dtype=float)
    out = np.full(len(h), np.nan)
    if len(h) > n:
        out[n:] = np.lib.stride_tricks.sliding_window_view(h, n).max(axis=1)[:-1]
    return out


def bollinger_bas(c, n=20, k=2.0):
    """Bande basse de Bollinger (écart-type de population, comme ta.bb)."""
    c = np.asarray(c, dtype=float)
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        fen = np.lib.stride_tricks.sliding_window_view(c, n)
        out[n - 1:] = fen.mean(axis=1) - k * fen.std(axis=1)
    return out


def ecart_type_glissant(x, n):
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = np.lib.stride_tricks.sliding_window_view(x, n).std(axis=1)
    return out


def percentile_glissant(x, n):
    """Rang (0 à 1) de la dernière valeur parmi les n précédentes : 0,9 = plus haut que 90 % du passé récent."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) > n:
        fen = np.lib.stride_tricks.sliding_window_view(x, n + 1)
        out[n:] = (fen[:, :-1] < fen[:, -1:]).mean(axis=1)
    return out
