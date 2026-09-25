from __future__ import annotations

import os

ACTIONS_PAR_MODE = {'paper': 'paper_trade', 'demo': 'demo_trade', 'testnet': 'testnet_trade', 'live': 'live_trade'}


class Policy:
    """Barrière indépendante entre la stratégie et l'exécution. Les retraits sont toujours refusés."""

    def __init__(self, mode='paper', live_enabled=False, kill_switch=False):
        self.mode = mode
        self.live_enabled = live_enabled
        self.kill_switch = kill_switch

    def authorize(self, action):
        if action == 'withdraw':
            return False, 'withdrawals disabled'
        if self.kill_switch:
            return False, 'kill_switch'
        if action == 'live_trade':
            env_enabled = os.getenv('LIVE_TRADING_ENABLED', '0').lower() in {'1', 'true', 'yes', 'on'}
            if not (self.mode == 'live' and self.live_enabled and env_enabled):
                return False, 'live trading disabled'
        if action == 'testnet_trade' and self.mode != 'testnet':
            return False, 'testnet mode required'
        if action == 'demo_trade' and self.mode != 'demo':
            return False, 'demo mode required'
        if action == 'paper_trade' and self.mode != 'paper':
            return False, 'paper mode required'
        if action not in set(ACTIONS_PAR_MODE.values()) | {'read'}:
            return False, 'unknown action'
        return True, 'ok'
