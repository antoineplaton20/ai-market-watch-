from v17_ops.core.policy import Policy
from v17_ops.core.portfolio import PaperPortfolio
from v17_ops.core.risk import RiskGate
from v17_ops.adapters.paper import PaperAdapter

def test_withdrawal_denied(): assert Policy().authorize('withdraw')[0] is False

def test_paper_buy_sell():
    p=PaperPortfolio(1000); p.execute('BTC/USDT','buy',.01,50000); assert p.positions['BTC/USDT']==.01; p.execute('BTC/USDT','sell',.01,51000); assert p.positions['BTC/USDT']==0

def test_risk_caps():
    class I: quantity=1; limit_price=200
    assert RiskGate(max_order_usdt=100).check(I(),1000,0,0).allowed is False

def test_paper_adapter():
    a=PaperAdapter(1000); a.update_price('BTC/USDT',50000); o=a.create_order('BTC/USDT','market','buy',.001); assert o['status']=='closed'
