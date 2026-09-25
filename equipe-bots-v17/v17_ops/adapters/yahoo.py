class YahooAdapter:
    def __init__(self):
        import yfinance as yf; self.yf=yf
    def history(self,symbol,period='1mo',interval='1h'):
        return self.yf.Ticker(symbol).history(period=period,interval=interval,auto_adjust=False)
