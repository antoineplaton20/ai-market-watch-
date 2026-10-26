"""Télécharge les historiques journaliers Yahoo des études (34 marchés + 10 marchés de R6.1), fenêtre fixe.

Usage : python etudes/telecharger_yahoo.py DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA
Les fichiers (format brut de l'API chart v8) restent hors du dépôt : usage personnel, conditions de Yahoo.
"""
import json
import os
import sys
import time
import urllib.request

DEBUT, FIN = 946_684_800, 1_792_800_000          # 01/01/2000 → 24/10/2026 (UTC), fixée pour la reproductibilité
SYMBOLES = {
    "EURUSDX": "EURUSD=X", "GBPUSDX": "GBPUSD=X", "JPYX": "JPY=X", "CHFX": "CHF=X", "AUDUSDX": "AUDUSD=X",
    "CADX": "CAD=X", "NZDUSDX": "NZDUSD=X", "EURGBPX": "EURGBP=X", "EURJPYX": "EURJPY=X", "GBPJPYX": "GBPJPY=X",
    "EURCHFX": "EURCHF=X", "AUDJPYX": "AUDJPY=X", "GCF": "GC=F", "SIF": "SI=F", "PLF": "PL=F", "HGF": "HG=F",
    "CLF": "CL=F", "BZF": "BZ=F", "NGF": "NG=F", "ZCF": "ZC=F", "ZWF": "ZW=F", "KCF": "KC=F", "SBF": "SB=F",
    "CCF": "CC=F", "GSPC": "^GSPC", "NDX": "^NDX", "DJI": "^DJI", "GDAXI": "^GDAXI", "FCHI": "^FCHI", "FTSE": "^FTSE",
    "N225": "^N225", "STOXX50E": "^STOXX50E", "BTC-USD": "BTC-USD", "ETH-USD": "ETH-USD"}
EXTRA = {"HSI": "^HSI", "AXJO": "^AXJO", "KS11": "^KS11", "STI": "^STI", "NSEI": "^NSEI", "000001SS": "000001.SS",
         "SSMI": "^SSMI", "IBEX": "^IBEX", "ZNF": "ZN=F", "ZBF": "ZB=F",
         "GLD": "GLD", "SLV": "SLV", "SPY": "SPY",               # R7 : or, argent, S&P 500 par leurs fonds cotés
         "QQQ": "QQQ", "VIX": "^VIX", "VIX3M": "^VIX3M", "NVDA": "NVDA", "AAPL": "AAPL", "MSFT": "MSFT",   # R8
         "AMZN": "AMZN", "GOOGL": "GOOGL", "META": "META", "TSLA": "TSLA"}


def telecharger(symbole):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbole)}"
           f"?period1={DEBUT}&period2={FIN}&interval=1d&events=div%2Csplit")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    for essai in range(5):
        try:
            return urllib.request.urlopen(req, timeout=60).read()
        except Exception:
            time.sleep(5 * (essai + 1))
    raise RuntimeError(f"{symbole} : téléchargement impossible")


if __name__ == "__main__":
    import urllib.parse
    for dossier, table in ((sys.argv[1], SYMBOLES), (sys.argv[2], EXTRA)):
        os.makedirs(dossier, exist_ok=True)
        for nom, symbole in table.items():
            brut = telecharger(symbole)
            r = json.loads(brut)["chart"]["result"][0]
            open(os.path.join(dossier, nom + ".json"), "wb").write(brut)
            print(f"{nom:9} {len(r['timestamp']):6} bougies")
            time.sleep(1.0)
