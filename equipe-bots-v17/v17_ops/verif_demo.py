"""Test de connexion de la v17 au compte démo Binance (aucun ordre) : python -m v17_ops.verif_demo
Utilisé par « bots v17-demo » et « bots v17-demo-test » avant de passer la v17 en mode démo."""
from __future__ import annotations

import sys

from .adapters.ccxt_adapter import CCXTAdapter
from .core.config import Settings
from .workers.engine import ConfigError, cles_exchange

CLES_REFUSEES = ("-2015", "-2014", "-2008", "Invalid API-key", "API-key format")


def main(settings=None, adapter=None):
    s = settings or Settings.from_env()
    try:
        cle, secret, origine = cles_exchange(s, 'demo')
    except ConfigError as e:
        print(f"✖ {e}")
        return 1
    try:
        a = adapter or CCXTAdapter(mode='demo', api_key=cle, api_secret=secret)
        a._load()
        dernier = a.fetch_ticker(s.symbols[0]).get('last')
        usdt = a.free('USDT')                      # appel privé : vérifie que les clés sont acceptées
    except Exception as e:
        texte = str(e)
        print(f"✖ Compte démo Binance injoignable : {texte[:200]}")
        if any(c in texte for c in CLES_REFUSEES):
            print("  → Clé fausse, ou clé du mauvais environnement : il faut des clés créées sur demo.binance.com.")
        return 1
    print(f"✔ Compte démo Binance joignable (clés : {origine}). Aucun ordre passé pendant ce test.")
    print(f"  {s.symbols[0]} : {dernier} · USDT disponibles sur le compte (argent fictif) : {usdt:.2f}")
    print(f"  Budget de la v17 : {s.capital_max_usdt:.0f} USDT maximum, {s.max_order_usdt:.0f} USDT par achat.")
    if usdt < s.min_order_usdt:
        print("  ⚠️ Pas assez d'USDT libres sur le compte démo : la v17 ne pourra rien acheter.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
