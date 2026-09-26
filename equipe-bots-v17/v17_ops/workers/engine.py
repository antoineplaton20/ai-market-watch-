"""Moteur V17 : bougies fermées -> votes de l'ensemble -> policy -> risque -> exécution -> stockage -> Telegram.

Règles de fonctionnement (spot, jamais de levier, jamais de vente à découvert) :
- une décision par bougie FERMÉE (pas à chaque tick) ;
- achat seulement si le symbole n'est pas déjà détenu ; taille = plus petit de : MAX_ORDER_USDT, place restante
  sous MAX_POSITION_USDT, place restante sous le plafond de capital, caisse disponible ;
- vente de toute la position sur signal de vente, ou si la protection (V17_STOP_LOSS_PCT) est touchée ;
- un signal de vente sans position ne fait rien (le spot ne permet pas de vendre ce qu'on n'a pas) ;
- /v17 stop (Telegram) bloque les achats ; les ventes et la protection continuent ; KILL_SWITCH=1 bloque tout ;
- le portefeuille et la dernière bougie traitée sont enregistrés : un redémarrage ne rejoue rien ;
- démo / testnet : un ordre au résultat incertain (coupure réseau pendant l'envoi) ou un solde incohérent est
  rapproché uniquement sur preuve explicite de Binance ; un solde incohérent exige une vérification.
  En argent réel, le rapprochement reste manuel.
"""
from __future__ import annotations

import datetime as dt
import time
import math

from ..adapters.ccxt_adapter import CCXTAdapter
from ..adapters.market import TF_MS, BinancePublic, closed_candles, validate_candles
from ..adapters.paper import PaperAdapter
from ..core.config import MODES, settings as SETTINGS
from ..core.events import Intent
from ..core.policy import ACTIONS_PAR_MODE, Policy
from ..core.portfolio import PaperPortfolio
from ..core.risk import RiskGate
from ..core.governor import RiskGovernor
from ..core.store import OpsStore
from ..format import MODES as NOMS_MODES, dollars, pct, prix
from ..notify import NullNotifier
from ..strategies.ensemble import Ensemble

HISTORIQUE = 300
BOUGIES_MIN = 30
RAPPROCHEMENT_PAUSE_S = 60        # au plus une interrogation de Binance par minute pendant un blocage
AGE_ORDRE_INCONNU_S = 120         # compatibilité ; ce délai ne prouve plus une non-exécution
AGE_SOLDE_S = 600                 # compatibilité ; aucun effacement de position sur un simple délai
MODES_AUTO_RAPPROCHEMENT = ('demo', 'testnet')

RAISONS = {
    'invalid_configuration': "réglage invalide : corriger .env avant de reprendre les achats",
    'stop_cooldown': "délai de repos après une perte",
    'portfolio_drawdown_limit': "perte cumulée du portefeuille : achats suspendus",
    'portfolio_positions_limit': "nombre maximal de positions atteint",
    'order_notional_limit': "montant hors limites (MAX_ORDER_USDT)",
    'invalid_equity': "valeur du portefeuille invalide",
    'daily_loss_limit': "perte maximale du jour atteinte (MAX_DAILY_LOSS_USDT)",
    'open_orders_limit': "trop d'ordres ouverts",
    'position_limit': "position maximale atteinte (MAX_POSITION_USDT)",
    'slippage_or_depth': "glissement estimé excessif ou profondeur insuffisante",
    'budget': "plus de budget disponible (plafond de capital ou caisse)",
    'renseignement': "nouvelle grave ou climat mondial très dégradé (armée de renseignement)",
    'kill_switch': "KILL_SWITCH=1 dans .env",
    'live trading disabled': "argent réel non autorisé",
}


class ConfigError(RuntimeError):
    """Réglage incompatible avec la plateforme : le service ne doit pas redémarrer en boucle."""


def cles_exchange(s, mode):
    """Clés Binance de la v17 pour un mode exchange -> (clé, secret, origine).

    - demo : V17_API_KEY / V17_API_SECRET, sinon les clés du bot principal SI celui-ci est en MODE=demo
      (même compte démo, argent fictif). La v17 ne vend que ce qu'elle a acheté et a son propre budget.
    - testnet : clés sandbox propres à la v17 obligatoires.
    - live : clés propres à la v17 obligatoires et DIFFÉRENTES de celles du bot principal (sous-compte).
    """
    cle, secret, origine = s.api_key, s.api_secret, "v17"
    if mode == 'demo' and not (cle and secret) and s.main_mode == 'demo' and s.main_api_key and s.main_api_secret:
        cle, secret, origine = s.main_api_key, s.main_api_secret, "bot principal (même compte démo)"
    if not (cle and secret):
        if mode == 'demo':
            raise ConfigError("V17_MODE=demo : aucune clé démo trouvée. Mets V17_API_KEY / V17_API_SECRET "
                              "(clés de demo.binance.com), ou laisse-les vides si le bot principal est en MODE=demo.")
        raise ConfigError(f"V17_MODE={mode} exige des clés propres à la v17 (V17_API_KEY et V17_API_SECRET "
                          "dans .env). Sans elles : V17_MODE=paper.")
    if mode == 'live' and s.main_api_key and cle == s.main_api_key:
        raise ConfigError("Argent réel : V17_API_KEY est la clé du bot principal. Utilise un sous-compte "
                          "Binance dédié à la v17, ou V17_MODE=paper.")
    return cle, secret, origine


class OpsEngine:
    def __init__(self, mode=None, symbols=None, store=None, *, settings=None, market=None, executor=None,
                 notifier=None):
        self.settings = settings or SETTINGS
        self.mode = (mode or self.settings.mode).lower()
        self.origine_cles = None
        if self.settings.demo_only and self.mode != 'demo':
            raise ConfigError('V17_DEMO_ONLY=1 : seul le mode Binance Demo est autorisé')
        if self.mode not in MODES:
            raise ConfigError(f"V17_MODE inconnu : {self.mode} (paper, demo, testnet ou live)")
        if self.settings.timeframe not in TF_MS:
            raise ConfigError(f"V17_TIMEFRAME inconnu : {self.settings.timeframe} ({', '.join(TF_MS)})")
        if self.mode == 'live' and not self.settings.live_trading_enabled:
            raise RuntimeError('LIVE_TRADING_ENABLED=1 is required for live mode')
        self.symbols = list(symbols or self.settings.symbols)
        if any(not sym.endswith('/USDT') or sym.count('/') != 1 for sym in self.symbols):
            raise ConfigError('V17 OPS prend en charge uniquement le spot coté en USDT')
        self.store = store or OpsStore(self.settings.ops_db)
        self.notifier = notifier or NullNotifier()
        self.strategy = Ensemble()
        s = self.settings
        self.risk = RiskGate(s.max_order_usdt, s.max_position_usdt, s.max_daily_loss_usdt, s.max_slippage_pct,
                             s.max_open_orders)
        self.policy = Policy(self.mode, live_enabled=s.live_trading_enabled, kill_switch=s.kill_switch)

        cle_book = f'portfolio:{self.mode}'
        depart = s.paper_cash_usdt if self.mode == 'paper' else s.capital_max_usdt
        self.book = PaperPortfolio.from_dict(self.store.get(cle_book), default_cash=depart)
        self._cle_book = cle_book
        self.governor = RiskGovernor(self.store, self.mode, s)

        if self.mode == 'paper':
            if executor is not None and hasattr(executor, 'portfolio'):
                self.book = executor.portfolio
            self.adapter = executor or PaperAdapter(fee_rate=s.fee_rate, slippage_pct=s.paper_slippage_pct,
                                                    portfolio=self.book)
            self._market = market                     # créé à la première utilisation (aucun réseau ici)
        else:
            if executor is None:
                cle, secret, self.origine_cles = cles_exchange(s, self.mode)
                executor = CCXTAdapter(mode=self.mode, api_key=cle, api_secret=secret)
            self.adapter = executor
            self._market = market or executor

        self.closes = {sym: [] for sym in self.symbols}
        hb = self.store.get('heartbeat') or {}
        saved_prices = hb.get('prices', {}) if hb.get('mode') == self.mode else {}
        self.prices = {k: float(v) for k, v in saved_prices.items()
                       if isinstance(v, (int, float)) and math.isfinite(v) and v > 0}
        self.governor.assess(self.equity(), len(self.book.open_positions()))
        self._rejets = {}
        self._prochain_rapprochement = 0.0
        self.last_candle = dict(self.store.get(f'last_candle:{self.mode}', {}) or {})
        self.store.event('engine_started', {'mode': self.mode, 'symbols': self.symbols,
                                            'timeframe': self.settings.timeframe})

    # ------------------------------------------------------------------ outils
    @property
    def market(self):
        if self._market is None:
            self._market = BinancePublic()
        return self._market

    def paused(self):
        if self.store.get('pause', False):                     # /v17 stop : jusqu'à /v17 reprise
            return True
        return time.time() < float(self.store.get('pause_until', 0) or 0)   # pause automatique temporaire

    def _save_book(self):
        self.store.set(self._cle_book, self.book.to_dict())

    def _set_price(self, symbol, price):
        self.prices[symbol] = price
        if self.mode == 'paper':
            self.adapter.update_price(symbol, price)

    def equity(self):
        return self.book.equity(self.prices)

    def daily_pnl(self):
        aujourdhui = dt.datetime.now(dt.timezone.utc).date().isoformat()
        cle = f'jour:{self.mode}'
        jour = self.store.get(cle) or {}
        eq = self.equity()
        if jour.get('date') != aujourdhui:
            jour = {'date': aujourdhui, 'equity': eq}
            self.store.set(cle, jour)
        pnl = eq - float(jour['equity'])
        if pnl <= -self.settings.max_daily_loss_usdt and not jour.get('tripped'):
            jour['tripped'] = True
            self.store.set(cle, jour)
        return min(pnl, -self.settings.max_daily_loss_usdt) if jour.get('tripped') else pnl

    def heartbeat(self, extra=None):
        self.governor.assess(self.equity(), len(self.book.open_positions()))
        self.daily_pnl()                     # bascule de journée dès le premier tour après minuit
        self.store.set('heartbeat', {'ts': time.time(), 'mode': self.mode, 'symbols': self.symbols,
                                     'timeframe': self.settings.timeframe, 'prices': self.prices,
                                     'equity': self.equity(), **(extra or {})})

    def state(self):
        return {'mode': self.mode, 'symbols': self.symbols, 'kill_switch': self.policy.kill_switch,
                'paused': self.paused(),
                'balance': {'cash': self.book.cash, 'equity': self.equity(),
                            'positions': self.book.open_positions(), 'avg_cost': dict(self.book.avg_cost),
                            'realized_pnl': self.book.realized_pnl}}

    # ------------------------------------------------------------------ boucle
    def tick(self, symbol, price=None):
        if symbol not in self.symbols:
            return {'status': 'rejected', 'reason': 'unknown_symbol'}
        if self.store.get(f'pending:{self.mode}') and not self.rapprocher():
            return {'status': 'reconciliation_required', 'reason': 'uncertain_execution'}
        if price is not None and self.mode != 'paper':
            return {'status': 'invalid_data', 'reason': 'injected_price_requires_paper'}
        if price is not None:          # prix injecté (tests, --price) : chaque appel = une bougie fermée
            price = float(price)
            if not math.isfinite(price) or price <= 0:
                return {'status': 'invalid_data', 'reason': 'invalid_price'}
            closes = self.closes.setdefault(symbol, [])
            closes.append(price)
            del closes[:-HISTORIQUE]
            nouvelle = True
            bougie = None
        else:
            rows = self.market.fetch_ohlcv(symbol, timeframe=self.settings.timeframe, limit=120)
            if not rows:
                return {'status': 'no_data'}
            try:
                validate_candles(rows, self.settings.timeframe)
            except ValueError as error:
                return {'status': 'invalid_data', 'reason': str(error)}
            price = float(rows[-1][4])                                    # dernier prix (bougie en cours)
            fermees = closed_candles(rows, self.settings.timeframe)
            self.closes[symbol] = [float(r[4]) for r in fermees][-HISTORIQUE:]
            bougie = int(fermees[-1][0]) if fermees else None
            nouvelle = bougie is not None and bougie > int(self.last_candle.get(symbol, 0))
        self._set_price(symbol, price)

        protection = self._protect(symbol, price)
        if protection:
            if bougie is not None and protection.get('status') == 'filled':
                self.last_candle[symbol] = bougie
                self.store.set(f'last_candle:{self.mode}', self.last_candle)
            return protection
        if not nouvelle:
            return {'status': 'waiting', 'price': price}
        if bougie is not None:
            self.last_candle[symbol] = bougie
            self.store.set(f'last_candle:{self.mode}', self.last_candle)
        self.store.snapshot(symbol, {'price': price, 'timestamp': time.time(), 'mode': self.mode,
                                     'equity': self.equity()})
        closes = self.closes[symbol]
        if len(closes) < BOUGIES_MIN:
            return {'status': 'warming', 'price': price}

        votes = self.strategy.votes(closes)
        agg = self.strategy.aggregate(votes)
        self.store.signal(symbol, agg[0] if agg else 'hold', agg[1] if agg else 0,
                          {'votes': [v.__dict__ for v in votes], 'timeframe': self.settings.timeframe})
        if not agg or agg[1] < self.settings.score_min:
            return {'status': 'no_trade', 'price': price, 'score': agg[1] if agg else 0}
        side, score = agg
        if side == 'buy':
            return self._buy(symbol, price, score)
        return self._sell(symbol, price, 'signal', score)

    # --------------------------------------------------------------- décisions
    def _protect(self, symbol, price):
        qte = self.book.positions.get(symbol, 0.0)
        pru = self.book.avg_cost.get(symbol)
        if qte <= 0 or not pru or self.settings.stop_loss_pct <= 0:
            return None
        if price <= pru * (1 - self.settings.stop_loss_pct / 100):
            return self._sell(symbol, price, 'stop')
        return None

    @staticmethod
    def _renseignement_defavorable(symbol):
        """Lecture seule de l'armée de renseignement (0,3 s max). Toute panne = pas d'avis = achat possible."""
        try:
            import lecture_renseignement as LR
            return bool(LR.alerte_grave([LR.cle_actif(symbol)]) or LR.risque_global())
        except Exception:
            return False

    def _rejet(self, intent, statut, raison, notifier=True):
        cle = (raison, intent.symbol, intent.side)
        if time.time() - self._rejets.get(cle, 0) >= 900:   # journal : au plus une ligne / 15 min / cas
            self._rejets[cle] = time.time()
            self.store.order(intent.id, intent.symbol, intent.side, intent.quantity, intent.limit_price, statut,
                             payload={'reason': raison})
        if notifier:                   # au plus un message toutes les 6 h par symbole et par raison
            self.notifier.erreur(f'rejet-{raison}-{intent.symbol}',
                                 f"⚠️ Signal d'{'achat' if intent.side == 'buy' else 'vente'} "
                                 f"{intent.symbol.split('/')[0]} non exécuté : {RAISONS.get(raison, raison)}",
                                 fenetre_s=6 * 3600)
        return {'status': 'rejected' if statut == 'policy_rejected' else statut, 'reason': raison}

    def _buy(self, symbol, price, score):
        if self.store.get(f'pending:{self.mode}'):
            return {'status': 'reconciliation_required', 'reason': 'uncertain_execution'}
        s = self.settings
        if s.entries_blocked:
            return {'status': 'risk_rejected', 'reason': 'invalid_configuration'}
        if time.time() < float(self.store.get(f'cooldown:{self.mode}:{symbol}', 0)):
            return {'status': 'risk_rejected', 'reason': 'stop_cooldown'}
        detenu = self.book.position_value(symbol, price)
        if detenu >= s.min_order_usdt:
            return {'status': 'hold', 'reason': 'already_in_position', 'price': price}
        if self.paused():
            return {'status': 'paused', 'price': price}
        intent = Intent(symbol, 'buy', 0.0, 'market', price, 'ensemble_v1', f'score {score:.2f}')
        ok, raison = self.policy.authorize(ACTIONS_PAR_MODE[self.mode])
        if not ok:
            return self._rejet(intent, 'policy_rejected', raison)
        if s.renseignement and self._renseignement_defavorable(symbol):
            return self._rejet(intent, 'risk_rejected', 'renseignement')

        marge = 1 + s.fee_rate + s.paper_slippage_pct / 100 + 0.002
        caisse = self.book.cash / marge
        if self.mode != 'paper':
            caisse = min(caisse, self.adapter.free('USDT') / marge)
        allowed, reason, risk_notional = self.governor.assess(self.equity(), len(self.book.open_positions()))
        if not allowed:
            return self._rejet(intent, 'risk_rejected', reason)
        montant = min(risk_notional, s.max_order_usdt, s.max_position_usdt - detenu,
                      s.capital_max_usdt - self.book.invested(), caisse)
        minimum = s.min_order_usdt
        if self.mode != 'paper':
            minimum = max(minimum, self.adapter.min_cost(symbol))
        intent.quantity = max(montant, 0.0) / price
        if montant < minimum:
            return self._rejet(intent, 'risk_rejected', 'budget')
        open_orders = self.adapter.open_orders_count() if self.mode != 'paper' else 0
        rd = self.risk.check(intent, self.equity(), open_orders, self.daily_pnl(), position_usdt=detenu)
        if not rd.allowed:
            return self._rejet(intent, 'risk_rejected', rd.reason)

        if self.mode == 'paper':
            liquidity_ok = s.paper_slippage_pct <= s.max_slippage_pct
        else:
            liquidity_ok = self.adapter.check_buy_liquidity(symbol, intent.quantity, price, s.max_slippage_pct)
        if not liquidity_ok:
            return self._rejet(intent, 'risk_rejected', 'slippage_or_depth')

        try:
            if self.mode == 'paper':
                o = self.adapter.create_order(symbol, 'market', 'buy', intent.quantity, price)
                qte, px, oid = intent.quantity, float(o['price']), o['id']
            else:
                f = self._exchange_order(intent, intent.quantity, price)
                qte, px, oid = f['qty'], f['price'], f['id']
                self.book.execute(symbol, 'buy', qte, px, fee_rate=s.fee_rate, strict=False)
        except Exception as e:
            self.store.order(intent.id, symbol, 'buy', intent.quantity, price, 'error', payload={'error': str(e)})
            self.notifier.erreur(f'achat-{symbol}', f"❗ Achat {symbol} impossible : {e}")
            return {'status': 'error', 'error': str(e)}
        self._finish_execution()
        if (px / price - 1) * 100 > s.max_slippage_pct:
            if s.slippage_pause_min > 0:                        # pause temporaire : les achats reprennent seuls
                self.store.set('pause_until', time.time() + s.slippage_pause_min * 60)
            else:
                self.store.set('pause', True)
            self.store.event('slippage_breach', {'symbol': symbol, 'reference': price, 'fill': px})
        self.store.order(intent.id, symbol, 'buy', qte, px, 'filled', oid,
                         {'score': score, 'risk_check_id': rd.risk_check_id, 'notional': qte * px})
        stop = px * (1 - s.stop_loss_pct / 100) if s.stop_loss_pct > 0 else None
        self.notifier.send(f"🟢 ACHAT {symbol.split('/')[0]} à {prix(px)} $ · {dollars(qte * px)} · "
                           f"score {score * 100:.0f} % · {NOMS_MODES[self.mode]}"
                           + (f"\nProtection à {prix(stop)} $ ({pct(-s.stop_loss_pct)})" if stop else ""))
        return {'status': 'filled', 'price': px, 'side': 'buy', 'qty': qte, 'order_id': oid}

    def _exchange_order(self, intent, qty, price):
        key = f'pending:{self.mode}'
        if self.store.get(key):
            raise RuntimeError('reconciliation required')
        self.store.set(key, {'intent_id': intent.id, 'symbol': intent.symbol,
                             'side': intent.side, 'qty': qty, 'reference_price': price,
                             'created_at': time.time(), 'reason': intent.reason})
        return self.adapter.market_order(intent.symbol, intent.side, qty, price,
                                         client_order_id=intent.id.replace('-', '')[:32])

    def _finish_execution(self):
        self.store.finish_execution(self._cle_book, self.book.to_dict(), f'pending:{self.mode}')

    def _disparue(self, intent, symbol, qte, price):
        # A missing/free balance may be locked, transferred or manually sold.
        # Do not invent sale proceeds or erase inventory.
        self.store.set(f'pending:{self.mode}', {'symbol': symbol, 'side': 'reconcile',
                                              'reason': 'balance_mismatch', 'qty': qte,
                                              'created_at': time.time()})
        self.store.event('reconciliation_required', {'symbol': symbol, 'qty': qte})
        auto = self.mode in MODES_AUTO_RAPPROCHEMENT and self.settings.auto_reconcile
        self.notifier.erreur(f'balance-{symbol}',
                            f"⚠️ Solde {symbol} incohérent : rapprochement requis, carnet conservé."
                            + (" Les positions restent conservées jusqu’au rapprochement." if auto else ""))
        return {'status': 'reconciliation_required', 'reason': 'balance_mismatch', 'price': price}

    def _sell(self, symbol, price, motif, score=None):
        if self.store.get(f'pending:{self.mode}'):
            return {'status': 'reconciliation_required', 'reason': 'uncertain_execution'}
        s = self.settings
        qte = self.book.positions.get(symbol, 0.0)
        if qte <= 0 or qte * price < 1:
            return {'status': 'hold', 'reason': 'no_position', 'price': price}
        intent = Intent(symbol, 'sell', qte, 'market', price, 'ensemble_v1', motif)
        ok, raison = self.policy.authorize(ACTIONS_PAR_MODE[self.mode])
        if not ok:
            return self._rejet(intent, 'policy_rejected', raison)
        pru = self.book.avg_cost.get(symbol, price)
        try:
            if self.mode == 'paper':
                o = self.adapter.create_order(symbol, 'market', 'sell', qte, price)
                px, oid, pnl = float(o['price']), o['id'], float(o['pnl'])
            else:
                base = symbol.split('/')[0]
                a_vendre = min(qte, self.adapter.free(base))
                if a_vendre * price < max(1.0, self.adapter.min_cost(symbol)):
                    return self._disparue(intent, symbol, qte, price)
                f = self._exchange_order(intent, a_vendre, price)
                px, oid = f['price'], f['id']
                qte = f['qty']
                pnl = self.book.execute(symbol, 'sell', qte, px, fee_rate=s.fee_rate)['pnl']
        except Exception as e:
            self.store.order(intent.id, symbol, 'sell', qte, price, 'error', payload={'error': str(e)})
            self.notifier.erreur(f'vente-{symbol}', f"❗ Vente {symbol} impossible : {e}")
            return {'status': 'error', 'error': str(e)}
        self._finish_execution()
        if motif == 'stop':
            self.store.set(f'cooldown:{self.mode}:{symbol}', time.time() + s.cooldown_bars * TF_MS[s.timeframe] / 1000)
        self.governor.assess(self.equity(), len(self.book.open_positions()))
        self.store.order(intent.id, symbol, 'sell', qte, px, 'filled', oid,
                         {'pnl': pnl, 'reason': motif, 'score': score, 'entry': pru})
        texte_motif = "protection touchée" if motif == 'stop' else f"signal de vente (score {score * 100:.0f} %)"
        self.notifier.send(f"🔴 VENTE {symbol.split('/')[0]} à {prix(px)} $ · résultat {dollars(pnl, True)} "
                           f"({pct((px / pru - 1) * 100)}) · {texte_motif} · {NOMS_MODES[self.mode]}")
        return {'status': 'filled', 'price': px, 'side': 'sell', 'qty': qte, 'order_id': oid, 'pnl': pnl}

    # ------------------------------------------------------ rapprochement auto
    def rapprocher(self):
        """Lève un blocage « rapprochement requis » en interrogeant Binance (démo / testnet uniquement).

        Renvoie True si plus rien ne bloque. Toute erreur (réseau...) laisse le blocage en place : nouvel essai
        une minute plus tard. En argent réel, rien n'est fait automatiquement."""
        cle = f'pending:{self.mode}'
        p = self.store.get(cle)
        if not p:
            return True
        if self.mode not in MODES_AUTO_RAPPROCHEMENT or not self.settings.auto_reconcile:
            return False
        maintenant = time.time()
        if maintenant < self._prochain_rapprochement:
            return False
        self._prochain_rapprochement = maintenant + RAPPROCHEMENT_PAUSE_S
        try:
            # Rebuild from durable state so a failed database commit cannot double-book a fill.
            depart = self.settings.capital_max_usdt
            self.book = PaperPortfolio.from_dict(self.store.get(self._cle_book), default_cash=depart)
            issue = self._resoudre(p, maintenant)
        except Exception as ex:
            self.store.event('auto_reconcile_error', {'pending': p, 'error': f"{type(ex).__name__}: {ex}"[:300]})
            return False
        if issue is None:
            return False
        self.store.event('auto_reconciled', {'pending': p, 'issue': issue})
        self.notifier.send(f"🔓 Blocage levé automatiquement : {issue}. La v17 reprend.", important=False)
        return True

    def _resoudre(self, p, maintenant):
        """-> texte de l'issue si le blocage est levé, None s'il faut attendre."""
        symbole = p.get('symbol')
        if symbole not in self.book.positions and symbole not in self.symbols:
            return None
        base = symbole.split('/')[0]
        age = maintenant - float(p.get('created_at') or 0)
        cote = p.get('side')
        if cote in ('buy', 'sell') and p.get('intent_id'):
            lookup = getattr(self.adapter, 'lookup_order', None)
            if lookup is None:
                return None
            o = lookup(symbole, p['intent_id'].replace('-', '')[:32])
            if o is None:
                # An absent response is not proof that an order never executed.
                return None
            if o['status'] not in ('closed', 'canceled', 'expired', 'rejected'):
                return None
            if not o.get('id') or not all(math.isfinite(float(o[k])) for k in ('qty', 'price')):
                return None
            if o['qty'] < 0 or o['qty'] > float(p.get('qty', 0)) * (1 + 1e-8):
                return None
            if o['qty'] == 0:
                self._finish_execution()
                return f"ordre {base} clos par Binance sans exécution"
            if o['price'] <= 0:
                return None
            fee = self.settings.fee_rate
            if cote == 'buy':
                qte, pnl = o['qty'], None
                self.book.execute(symbole, 'buy', qte, o['price'], fee_rate=fee, strict=False)
            else:
                if o['qty'] > self.book.positions.get(symbole, 0.0) + 1e-12:
                    return None
                qte = o['qty']
                pnl = self.book.execute(symbole, 'sell', qte, o['price'], fee_rate=fee)['pnl'] if qte > 0 else 0.0
            if cote == 'sell' and p.get('reason') == 'stop':
                self.store.set(f'cooldown:{self.mode}:{symbole}', maintenant + self.settings.cooldown_bars * TF_MS[self.settings.timeframe] / 1000)
            self._finish_execution()
            self.store.order(p['intent_id'], symbole, cote, qte, o['price'], 'filled', o['id'],
                             {'reason': 'auto_reconcile', 'pnl': pnl})
            return (f"{'achat' if cote == 'buy' else 'vente'} {base} confirmé par Binance "
                    f"({qte:.8g} à {prix(o['price'])} $), carnet mis à jour")
        if cote == 'reconcile':
            # Free balance can be locked by an order or reserved elsewhere.
            # Neither time nor the free balance proves ownership or a realized loss.
            return None
        return None
