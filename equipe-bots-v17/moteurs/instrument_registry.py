"""Registre unifié des instruments Binance / Trade Republic.

Le registre sépare la découverte des instruments de la stratégie. Il accepte des
marchés CCXT (Binance) et des lignes externes Trade Republic normalisées depuis
un CSV/JSON fourni par l'utilisateur ou une source autorisée.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional
import csv
import json
from pathlib import Path


@dataclass
class Instrument:
    platform: str
    symbol: str
    kind: str = "unknown"
    base: str = ""
    quote: str = ""
    currency: str = ""
    active: bool = True
    min_order: float = 0.0
    tick_size: float = 0.0
    step_size: float = 0.0
    maker_fee_pct: Optional[float] = None
    taker_fee_pct: Optional[float] = None
    fixed_fee: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InstrumentRegistry:
    def __init__(self) -> None:
        self._items: Dict[str, Instrument] = {}

    @staticmethod
    def key(platform: str, symbol: str) -> str:
        return f"{platform.upper()}:{symbol.upper()}"

    def add(self, instrument: Instrument) -> Instrument:
        self._items[self.key(instrument.platform, instrument.symbol)] = instrument
        return instrument

    def add_binance_markets(self, markets: Dict[str, Dict[str, Any]]) -> int:
        n = 0
        for symbol, m in markets.items():
            # Spot uniquement : ccxt charge aussi les futures / marges / options de Binance
            if not m or m.get("spot") is False or m.get("type", "spot") != "spot":
                continue
            info = m.get("info") or {}
            limits = m.get("limits") or {}
            amount = limits.get("amount") or {}
            precision = m.get("precision") or {}
            self.add(Instrument(
                platform="binance",
                symbol=symbol,
                kind=m.get("type", "spot"),
                base=m.get("base", ""),
                quote=m.get("quote", ""),
                currency=m.get("quote", ""),
                active=bool(m.get("active", True)),
                min_order=float(amount.get("min") or 0),
                tick_size=float(precision.get("price") or 0) if isinstance(precision.get("price"), (int, float)) else 0.0,
                step_size=float(precision.get("amount") or 0) if isinstance(precision.get("amount"), (int, float)) else 0.0,
                metadata={"status": info.get("status"), "permissions": info.get("permissions")},
            ))
            n += 1
        return n

    def add_trade_republic_rows(self, rows: Iterable[Dict[str, Any]]) -> int:
        n = 0
        for row in rows:
            symbol = str(row.get("symbol") or row.get("isin") or row.get("name") or "").strip()
            if not symbol:
                continue
            self.add(Instrument(
                platform="trade_republic",
                symbol=symbol,
                kind=str(row.get("kind") or row.get("type") or "unknown").lower(),
                base=str(row.get("base") or ""),
                quote=str(row.get("quote") or row.get("currency") or "EUR"),
                currency=str(row.get("currency") or "EUR"),
                active=str(row.get("active", "true")).lower() not in {"false", "0", "no"},
                min_order=float(row.get("min_order") or 0),
                fixed_fee=float(row.get("fixed_fee") or 0),
                metadata={k: v for k, v in row.items() if k not in {"symbol", "isin", "name", "kind", "type", "base", "quote", "currency", "active", "min_order", "fixed_fee"}},
            ))
            n += 1
        return n

    def load_trade_republic_file(self, path: str | Path) -> int:
        p = Path(path)
        if p.suffix.lower() == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else data.get("instruments", [])
            return self.add_trade_republic_rows(rows)
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            return self.add_trade_republic_rows(csv.DictReader(f))

    def all(self) -> List[Instrument]:
        return list(self._items.values())

    def active(self, platform: Optional[str] = None) -> List[Instrument]:
        return [x for x in self.all() if x.active and (platform is None or x.platform == platform)]

    def export_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps([x.to_dict() for x in self.all()], ensure_ascii=False, indent=2), encoding="utf-8")
