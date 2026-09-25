import statistics
class RegimeDetector:
    def detect(self, closes):
        if len(closes) < 20: return {"regime":"unknown","confidence":0.0}
        returns=[(b/a)-1 for a,b in zip(closes[:-1],closes[1:]) if a]
        vol=statistics.pstdev(returns) if len(returns)>1 else 0
        trend=(closes[-1]/closes[-20])-1
        if vol > 0.04: regime="high_volatility"
        elif trend > 0.03: regime="trend_up"
        elif trend < -0.03: regime="trend_down"
        else: regime="range"
        return {"regime":regime,"confidence":min(1.0, abs(trend)*10+vol*5)}
