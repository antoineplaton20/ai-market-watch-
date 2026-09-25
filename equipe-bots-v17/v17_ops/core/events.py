from dataclasses import dataclass, field
import time, uuid

@dataclass
class Intent:
    symbol: str
    side: str
    quantity: float
    order_type: str
    limit_price: float | None
    strategy_id: str
    reason: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
