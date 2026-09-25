from trading_army.config import TradingConfig
from trading_army.risk import RiskEngine
from trading_army.execution import ExecutionEngine
from trading_army.schemas import TradeIntent

def test_risk_rejects_large_order():
    c=TradingConfig(mode='paper', max_order_usdt=100); r=RiskEngine(c)
    x=TradeIntent('BTC/USDT','buy',2,limit_price=100)
    assert not r.check(x,1000).allowed

def test_paper_execution():
    c=TradingConfig(mode='paper', max_order_usdt=1000); e=ExecutionEngine(config=c)
    x=TradeIntent('BTC/USDT','buy',0.001,limit_price=50000)
    assert e.execute(x).status=='paper_filled'
