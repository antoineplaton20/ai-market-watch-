"""Une fausse plateforme Binance, entièrement contrôlable, pour tester le bot sans risque ni réseau."""
import time
import numpy as np


class FausseBinance:
    def __init__(self, paires=("BTC", "SOL", "ETH"), usdt=1000.0):
        mk = lambda b: {"active": True, "spot": True, "quote": "USDT", "base": b, "limits": {"cost": {"min": 5}}}
        self.markets = {f"{b}/USDT": mk(b) for b in paires}
        self.prix = {s: 100.0 for s in self.markets}
        self.solde = {"USDT": usdt, **{b: 0.0 for b in paires}}
        self.ordres = {}
        self.options = {}
        self.n = 0
        self.stop_en_panne = False
        self.historique = []

    # --- lecture du marché ---
    retard_s = 0            # pour simuler des données périmées

    def fetch_tickers(self):
        ts = (time.time() - self.retard_s) * 1000
        return {s: {"bid": p * 0.999, "ask": p * 1.001, "last": p, "quoteVolume": 1e7, "percentage": 2,
                    "timestamp": ts} for s, p in self.prix.items()}

    def fetch_ticker(self, sym):
        p = self.prix[sym]
        return {"bid": p * 0.999, "ask": p * 1.001, "last": p, "timestamp": time.time() * 1000}

    def fetch_ohlcv(self, sym, unite, limit=250, since=None):
        pas = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000}[unite]
        fin = (time.time() - self.retard_s) * 1000
        rng = np.random.default_rng(len(sym))
        c = np.linspace(90, 100, limit) + rng.normal(0, 0.2, limit)
        return [[fin - (limit - 1 - i) * pas, x, x + 0.5, x - 0.5, x, 1000 + i * 5] for i, x in enumerate(c)]

    def fetch_time(self):
        return time.time() * 1000 + getattr(self, "decalage_ms", 0)

    def fetch_order_book(self, sym, limit=100):
        p = self.prix[sym]
        return {"bids": [[p * 0.998, 5000]], "asks": [[p * 1.002, 3000]]}

    def fetch_trades(self, sym, limit=1000):
        now = time.time() * 1000
        return [{"timestamp": now - i * 1000, "side": "buy" if i % 3 else "sell", "price": 100, "amount": 20,
                 "cost": 2000} for i in range(100)]

    def fetch_balance(self):
        return {"free": dict(self.solde), "total": dict(self.solde)}

    def amount_to_precision(self, sym, q):
        return f"{q:.4f}"

    def price_to_precision(self, sym, p):
        return f"{p:.4f}"

    def milliseconds(self):
        return int(time.time() * 1000)

    # --- ordres ---
    def create_order(self, sym, typ, cote, qte, prix=None, params=None):
        self.n += 1
        oid = str(self.n)
        base = sym.split("/")[0]
        p = self.prix[sym]
        self.historique.append((typ, cote, sym, qte))
        if typ == "market":
            if cote == "buy":
                self.solde["USDT"] -= qte * p
                self.solde[base] += qte
            else:
                self.solde[base] -= qte
                self.solde["USDT"] += qte * p
            return {"id": oid, "average": p, "filled": qte, "status": "closed"}
        if self.stop_en_panne:
            raise Exception("ordre stop refusé")
        cid = (params or {}).get("newClientOrderId", "")
        self.ordres[oid] = {"id": oid, "symbol": sym, "status": "open", "price": prix, "amount": qte,
                            "stopPrice": (params or {}).get("stopPrice"), "clientOrderId": cid, "type": typ}
        return {"id": oid}

    def fetch_order(self, oid, sym):
        return self.ordres[oid]

    def cancel_order(self, oid, sym):
        self.ordres[oid]["status"] = "canceled"

    def fetch_open_orders(self, sym=None):
        return [o for o in self.ordres.values() if o["status"] == "open"]

    # --- outils de test ---
    def executer_stop(self, oid, prix):
        """Simule le déclenchement du stop chez Binance."""
        o = self.ordres[oid]
        base = o["symbol"].split("/")[0]
        o.update(status="closed", average=prix)
        self.solde[base] -= o["amount"]
        self.solde["USDT"] += o["amount"] * prix
