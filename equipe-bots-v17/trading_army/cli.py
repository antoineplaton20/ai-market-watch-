import argparse
from .factory import TradingBotFactory
from .config import TradingConfig
from .exchanges import ExchangeFactory

def main():
    p=argparse.ArgumentParser(); p.add_argument("command",choices=["catalog","export","smoke"]); p.add_argument("--exchange",default="binance"); a=p.parse_args()
    if a.command in {"catalog","export"}:
        f=TradingBotFactory(); print(len(f.catalog));
        if a.command=="export": print(f.export())
    else:
        c=TradingConfig(); print({"mode":c.mode,"live_enabled":c.live_enabled,"can_trade_live":c.can_trade_live})
        if c.mode=="testnet": print(ExchangeFactory("testnet").create(a.exchange).id)
if __name__=="__main__": main()
