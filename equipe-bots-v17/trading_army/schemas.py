from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid

@dataclass
class Observation:
    source: str
    symbol: str
    timestamp: str
    kind: str
    value: Any
    confidence: float = 0.5
    provenance: Dict[str, Any] = field(default_factory=dict)
    latency_ms: Optional[float] = None

@dataclass
class TradeIntent:
    symbol: str
    side: str
    quantity: float
    order_type: str = "limit"
    limit_price: Optional[float] = None
    strategy_id: str = "unknown"
    reason: str = ""
    max_slippage_pct: float = 0.25
    expires_at: Optional[str] = None
    risk_check_id: Optional[str] = None
    authorization_id: Optional[str] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self): return asdict(self)

@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    risk_check_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    limits: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TradeResult:
    intent_id: str
    status: str
    exchange_order_id: Optional[str] = None
    filled_quantity: float = 0.0
    average_price: Optional[float] = None
    fees: float = 0.0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
