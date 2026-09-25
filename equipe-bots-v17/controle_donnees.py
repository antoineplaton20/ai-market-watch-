"""FRAÎCHEUR DES DONNÉES : données périmées, horloge décalée ou connexion incertaine = aucun nouveau risque."""
import time
import config

UNITE_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000}


def bougies_fraiches(df, unite):
    """La dernière bougie (en cours) doit avoir commencé il y a moins de 2 unités de temps."""
    if df is None or len(df) == 0:
        return False
    age = time.time() * 1000 - float(df["t"].iloc[-1])
    return age <= config.DONNEES_AGE_MAX_BOUGIES * UNITE_MS[unite]


def ticker_frais(t):
    ts = (t or {}).get("timestamp")
    return ts is not None and time.time() * 1000 - float(ts) <= config.TICKER_AGE_MAX_S * 1000


def horloge(ex):
    """Écart entre l'horloge du serveur Binance et celle du bot. Renvoie (ok, écart en ms)."""
    try:
        ecart = abs(float(ex.fetch_time()) - time.time() * 1000)
    except Exception:
        return False, None
    return ecart <= config.HORLOGE_ECART_MAX_MS, ecart
