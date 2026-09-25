"""Market Data Lake local v11.

Stockage append-only SQLite pour bougies, trades, snapshots de carnet et événements.
La couche n'essaie pas de scraper des sites protégés: elle accepte des données
provenant d'APIs/licences autorisées et conserve source + timestamp pour la traçabilité.
"""
import json, os, sqlite3, time

DEFAULT_DB = os.getenv("DATA_LAKE_DB", "market_data.db")

class DataLake:
    def __init__(self, path=DEFAULT_DB):
        self.path = path
        self._init()

    def _cnx(self):
        return sqlite3.connect(self.path)

    def _init(self):
        c = self._cnx()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS candles(
          source TEXT, symbol TEXT, timeframe TEXT, ts INTEGER,
          o REAL, h REAL, l REAL, c REAL, v REAL, extra TEXT,
          PRIMARY KEY(source,symbol,timeframe,ts));
        CREATE TABLE IF NOT EXISTS trades(
          source TEXT, symbol TEXT, ts INTEGER, price REAL, amount REAL,
          side TEXT, cost REAL, extra TEXT,
          PRIMARY KEY(source,symbol,ts,price,amount));
        CREATE TABLE IF NOT EXISTS orderbook(
          source TEXT, symbol TEXT, ts INTEGER, bid REAL, ask REAL,
          bid_depth REAL, ask_depth REAL, extra TEXT,
          PRIMARY KEY(source,symbol,ts));
        CREATE TABLE IF NOT EXISTS events(
          source TEXT, event_id TEXT, ts INTEGER, category TEXT, payload TEXT,
          PRIMARY KEY(source,event_id));
        CREATE INDEX IF NOT EXISTS idx_candles ON candles(symbol,timeframe,ts);
        CREATE INDEX IF NOT EXISTS idx_trades ON trades(symbol,ts);
        CREATE INDEX IF NOT EXISTS idx_events ON events(category,ts);
        """)
        c.close()

    def candle(self, source, symbol, timeframe, row, extra=None):
        vals = (source, symbol, timeframe, int(row[0]), *map(float, row[1:6]), json.dumps(extra or {}))
        with self._cnx() as c:
            c.execute("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)", vals)

    def candles(self, source, symbol, timeframe, rows):
        with self._cnx() as c:
            c.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)",
                          [(source, symbol, timeframe, int(r[0]), *map(float, r[1:6]), json.dumps({})) for r in rows])

    def trade(self, source, symbol, t):
        ts = int(t.get("timestamp") or time.time()*1000)
        price, amount = float(t.get("price") or 0), float(t.get("amount") or 0)
        cost = float(t.get("cost") or price*amount)
        with self._cnx() as c:
            c.execute("INSERT OR REPLACE INTO trades VALUES (?,?,?,?,?,?,?,?)",
                      (source,symbol,ts,price,amount,t.get("side"),cost,json.dumps(t)))

    def orderbook(self, source, symbol, ts, bid, ask, bid_depth, ask_depth, extra=None):
        with self._cnx() as c:
            c.execute("INSERT OR REPLACE INTO orderbook VALUES (?,?,?,?,?,?,?,?)",
                      (source,symbol,int(ts),float(bid),float(ask),float(bid_depth),float(ask_depth),json.dumps(extra or {})))

    def event(self, source, event_id, ts, category, payload):
        with self._cnx() as c:
            c.execute("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)",
                      (source,str(event_id),int(ts),category,json.dumps(payload, ensure_ascii=False)))

    def stats(self):
        with self._cnx() as c:
            return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("candles","trades","orderbook","events")}
