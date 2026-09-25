from ..core.portfolio import PaperPortfolio


class PaperAdapter:
    """Exécution fictive : remplissage au dernier prix connu, frais Binance (0,1 %) et glissement simulé."""

    def __init__(self, cash=10000, fee_rate=0.001, slippage_pct=0.0, portfolio=None):
        self.portfolio = portfolio or PaperPortfolio(cash=cash)
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct
        self.last_prices = {}
        self.orders = {}

    def update_price(self, symbol, price):
        self.last_prices[symbol] = price

    def balance(self):
        return {'cash': self.portfolio.cash, 'equity': self.portfolio.equity(self.last_prices),
                'positions': self.portfolio.open_positions(), 'realized_pnl': self.portfolio.realized_pnl}

    def create_order(self, symbol, order_type, side, amount, price=None):
        ref = price or self.last_prices[symbol]
        glisse = self.slippage_pct / 100
        p = ref * (1 + glisse) if side == 'buy' else ref * (1 - glisse)
        r = self.portfolio.execute(symbol, side, amount, p, fee_rate=self.fee_rate)
        oid = 'paper-' + str(len(self.orders) + 1)
        self.orders[oid] = {'id': oid, 'symbol': symbol, 'side': side, 'amount': amount, 'price': p,
                            'status': 'closed', **r}
        return self.orders[oid]

    def fetch_ticker(self, symbol):
        return {'symbol': symbol, 'last': self.last_prices[symbol]}
