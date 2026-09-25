"""Calculs techniques en code pur (gratuits, instantanés)."""
import pandas as pd


def bougies(ex, symbole, unite, limite=250):
    donnees = ex.fetch_ohlcv(symbole, unite, limit=limite)
    return pd.DataFrame(donnees, columns=["t", "o", "h", "l", "c", "v"])


def ema(serie, n):
    return serie.ewm(span=n, adjust=False).mean()


def rsi(serie, n=14):
    delta = serie.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    perte = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / perte.replace(0, 1e-12)
    return 100 - 100 / (1 + rs)


def atr(df, n=14):
    prec = df["c"].shift(1)
    tr = pd.concat([df["h"] - df["l"], (df["h"] - prec).abs(), (df["l"] - prec).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def enrichir(df):
    df = df.copy()
    df["ema20"] = ema(df["c"], 20)
    df["ema50"] = ema(df["c"], 50)
    df["rsi"] = rsi(df["c"])
    df["atr"] = atr(df)
    df["vol_moy"] = df["v"].rolling(20).mean()
    return df
