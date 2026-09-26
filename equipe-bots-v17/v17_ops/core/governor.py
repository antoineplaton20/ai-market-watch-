"""Budget de risque V17 persistant ; contrôle des entrées seulement."""
import math


class RiskGovernor:
    def __init__(self, store, mode, settings):
        self.store, self.settings = store, settings
        self.key = f'governor:{mode}'

    def assess(self, equity, positions):
        s = self.settings
        if not math.isfinite(equity) or equity <= 0:
            return False, 'invalid_equity', 0.0
        state = self.store.get(self.key) or {'peak': equity, 'halted': False}
        peak = max(float(state['peak']), equity)
        # Idle paper cash does not dilute the allowed loss of the deployment budget.
        basis = min(s.capital_max_usdt, peak)
        drawdown = (peak - equity) / basis * 100
        if drawdown >= s.max_drawdown_pct:
            state['halted'] = True
        state.update(peak=peak, drawdown_pct=drawdown)
        self.store.set(self.key, state)
        if state['halted']:
            return False, 'portfolio_drawdown_limit', 0.0
        if positions >= s.max_positions:
            return False, 'portfolio_positions_limit', 0.0
        loss_fraction = s.stop_loss_pct / 100 + 2 * s.fee_rate + 2 * s.max_slippage_pct / 100
        if loss_fraction <= 0:
            return False, 'undefined_stop_risk', 0.0
        notional = min(s.capital_max_usdt, equity) * s.risk_per_trade_pct / 100 / loss_fraction
        return True, 'ok', notional
