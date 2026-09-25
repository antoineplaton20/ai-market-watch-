import json, sqlite3
from pathlib import Path
from .schemas import Observation, TradeResult

class MarketDataLake:
    def __init__(self, path="market_data_v16.db"):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY, source TEXT, symbol TEXT, timestamp TEXT, kind TEXT, value TEXT, confidence REAL, provenance TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS trade_results (id INTEGER PRIMARY KEY, payload TEXT)")
    def write_observation(self, o: Observation):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO observations(source,symbol,timestamp,kind,value,confidence,provenance) VALUES(?,?,?,?,?,?,?)", (o.source,o.symbol,o.timestamp,o.kind,json.dumps(o.value,default=str),o.confidence,json.dumps(o.provenance)))
    def write_trade_result(self, r: TradeResult):
        with sqlite3.connect(self.path) as db: db.execute("INSERT INTO trade_results(payload) VALUES(?)", (json.dumps(r.__dict__),))
