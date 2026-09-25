import math
from dataclasses import dataclass, field
from typing import Dict

POUSSIERE = 1e-12


@dataclass
class PaperPortfolio:
    """Carnet de positions de la V17. En mode paper c'est aussi la « caisse » fictive ; en mode exchange il
    suit ce que la V17 a elle-même acheté (jamais les avoirs du bot principal)."""
    cash: float = 10000.0
    positions: Dict[str, float] = field(default_factory=dict)
    avg_cost: Dict[str, float] = field(default_factory=dict)
    realized_pnl: float = 0.0

    entry_fees: Dict[str, float] = field(default_factory=dict)

    def equity(self, prices):
        return self.cash + sum(q * prices.get(s, self.avg_cost.get(s, 0)) for s, q in self.positions.items())

    def position_value(self, symbol, price):
        return self.positions.get(symbol, 0.0) * price

    def invested(self):
        return sum(q * self.avg_cost.get(s, 0) for s, q in self.positions.items())

    def open_positions(self):
        return {s: q for s, q in self.positions.items() if q > POUSSIERE}

    def execute(self, symbol, side, qty, price, fee_rate=0.001, strict=True):
        """strict=False : l'ordre a DÉJÀ eu lieu sur l'exchange, on l'enregistre même si le budget est dépassé."""
        if not all(math.isfinite(x) for x in (qty, price, fee_rate)) or qty <= 0 or price <= 0 or not 0 <= fee_rate < 1:
            raise ValueError("invalid execution values")
        notional = qty * price
        fee = notional * fee_rate
        pnl = 0.0
        if side == 'buy':
            if strict and self.cash < notional + fee:
                raise ValueError('insufficient paper cash')
            old = self.positions.get(symbol, 0)
            new = old + qty
            self.avg_cost[symbol] = ((old * self.avg_cost.get(symbol, price)) + (qty * price)) / new
            self.positions[symbol] = new
            self.cash -= notional + fee
            self.entry_fees[symbol] = self.entry_fees.get(symbol, 0.0) + fee
        elif side == 'sell':
            old = self.positions.get(symbol, 0)
            if old + 1e-12 < qty:
                raise ValueError('insufficient paper position')
            allocated_fee = self.entry_fees.get(symbol, 0.0) * min(qty / old, 1.0)
            self.entry_fees[symbol] = max(0.0, self.entry_fees.get(symbol, 0.0) - allocated_fee)
            pnl = qty * (price - self.avg_cost.get(symbol, price)) - fee - allocated_fee
            self.realized_pnl += pnl
            self.positions[symbol] = old - qty
            self.cash += notional - fee
            if self.positions[symbol] <= POUSSIERE:          # position soldée (clé gardée à 0)
                self.positions[symbol] = 0.0
        else:
            raise ValueError('side')
        return {'notional': notional, 'fee': fee, 'cash': self.cash, 'position': self.positions.get(symbol, 0),
                'pnl': pnl}

    def to_dict(self):
        return {'cash': self.cash, 'positions': dict(self.positions), 'avg_cost': dict(self.avg_cost),
                'realized_pnl': self.realized_pnl, 'entry_fees': dict(self.entry_fees)}

    @classmethod
    def from_dict(cls, d, default_cash=10000.0):
        if not d:
            return cls(cash=default_cash)
        return cls(cash=float(d.get('cash', default_cash)),
                   positions={k: float(v) for k, v in (d.get('positions') or {}).items()},
                   avg_cost={k: float(v) for k, v in (d.get('avg_cost') or {}).items()},
                   realized_pnl=float(d.get('realized_pnl', 0.0)),
                   entry_fees={k: float(v) for k, v in (d.get('entry_fees') or {}).items()})
