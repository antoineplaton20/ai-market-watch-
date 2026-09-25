"""Connexion à Binance (spot uniquement, jamais de levier)."""
import ccxt
import config


def connecter():
    ex = ccxt.binance({
        "apiKey": config.BINANCE_API_KEY,
        "secret": config.BINANCE_API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "spot", "adjustForTimeDifference": True, "recvWindow": 10000},
    })
    if config.MODE == "demo":
        ex.enable_demo_trading(True)   # Binance Démo : vrais prix, argent fictif (clés sur demo.binance.com)
    elif config.MODE == "testnet":
        ex.set_sandbox_mode(True)      # ancien testnet : prix artificiels, remis à zéro chaque mois
    ex.load_markets()
    return ex
