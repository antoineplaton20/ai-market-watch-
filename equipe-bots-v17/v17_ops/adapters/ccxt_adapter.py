"""Adaptateur CCXT pour Binance Demo/Testnet/Live.

L'édition Termius dédiée active V17_DEMO_ONLY=1 et passe exclusivement par Binance Demo.
Les clés utilisées sont V17_API_KEY / V17_API_SECRET et ne doivent jamais être celles d'un compte réel.
"""
from __future__ import annotations

import os
import math


class CCXTAdapter:
    def __init__(self, exchange_id='binance', sandbox=True, *, mode=None, api_key=None, api_secret=None,
                 exchange=None):
        self.mode = mode or ('testnet' if sandbox else 'live')
        demo_only = os.getenv('V17_DEMO_ONLY', '0').lower() in {'1', 'true', 'yes', 'on'}
        if demo_only and self.mode != 'demo':
            raise RuntimeError('V17_DEMO_ONLY=1 : CCXTAdapter accepte uniquement mode=demo')
        if exchange is None:
            import ccxt
            cls = getattr(ccxt, exchange_id)
            params = {'enableRateLimit': True,
                      'options': {'defaultType': 'spot', 'adjustForTimeDifference': True, 'recvWindow': 10000,
                                  'fetchMarkets': {'types': ['spot']}}}
            key = api_key if api_key is not None else os.getenv('V17_API_KEY', '')
            secret = api_secret if api_secret is not None else os.getenv('V17_API_SECRET', '')
            if key:
                params['apiKey'] = key
            if secret:
                params['secret'] = secret
            exchange = cls(params)
            if self.mode == 'demo':
                exchange.enable_demo_trading(True)      # Binance Démo : vrais prix, argent fictif
            elif self.mode == 'testnet':
                exchange.set_sandbox_mode(True)         # ancien testnet : prix artificiels
        self.exchange = exchange
        self._markets = False

    def _load(self):
        if not self._markets:
            self.exchange.load_markets()
            self._markets = True

    # ------------------------------------------------------------- données
    def fetch_ticker(self, symbol):
        return self.exchange.fetch_ticker(symbol)

    def fetch_ohlcv(self, symbol, timeframe='15m', limit=120):
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def balance(self):
        return self.exchange.fetch_balance()

    def free(self, asset):
        b = self.exchange.fetch_balance()
        return float((b.get('free') or {}).get(asset, 0) or 0)

    # ------------------------------------------------------------- ordres
    def create_order(self, symbol, order_type, side, amount, price=None):
        return self.exchange.create_order(symbol, order_type, side, amount, price)

    def cancel_order(self, oid, symbol=None):
        return self.exchange.cancel_order(oid, symbol)

    def min_cost(self, symbol):
        self._load()
        lim = ((self.exchange.markets.get(symbol) or {}).get('limits') or {}).get('cost') or {}
        return float(lim.get('min') or 0)

    def check_buy_liquidity(self, symbol, qty, reference, max_slippage_pct):
        book = self.exchange.fetch_order_book(symbol, limit=20)
        remaining, cost = qty, 0.0
        previous = 0.0
        for price, amount, *_ in book.get('asks', []):
            price, amount = float(price), float(amount)
            if not all(math.isfinite(v) for v in (price, amount)) or price <= 0 or amount < 0 or price < previous:
                return False
            previous = price
            take = min(remaining, amount)
            cost += take * price
            remaining -= take
            if remaining <= qty * 1e-10:
                return cost / qty <= reference * (1 + max_slippage_pct / 100)
        return False

    def open_orders_count(self):
        return len(self.exchange.fetch_open_orders())

    def market_order(self, symbol, side, qty, ref_price, client_order_id=None):
        """Ordre au marché ; renvoie le remplissage réel (quantité, prix moyen)."""
        self._load()
        amount = float(self.exchange.amount_to_precision(symbol, qty))
        if amount <= 0:
            raise ValueError('quantité trop petite pour Binance')
        params = {'newClientOrderId': client_order_id} if client_order_id else {}
        o = self.exchange.create_order(symbol, 'market', side, amount, None, params)
        if o.get('status') not in ('closed', 'canceled', 'expired', 'rejected') and o.get('id'):
            o = self.exchange.fetch_order(o['id'], symbol)
        # An ACK, zero fill or an open partial fill is NOT a completed trade.
        filled = float(o.get('filled') or 0)
        average = float(o.get('average') or (float(o.get('cost') or 0) / filled if filled else 0))
        if (not o.get('id') or o.get('status') not in ('closed', 'canceled', 'expired')
                or not math.isfinite(filled) or not math.isfinite(average)
                or filled <= 0 or filled > amount * (1 + 1e-8) or average <= 0):
            raise RuntimeError('unconfirmed_execution: reconciliation required')
        return {'id': str(o['id']), 'qty': filled, 'price': average, 'raw': o}
