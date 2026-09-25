from dataclasses import dataclass
@dataclass
class BotScore:
    bot_id: str; pnl: float; drawdown: float; accuracy: float; robustness: float
    @property
    def score(self): return self.pnl - self.drawdown*2 + self.accuracy*100 + self.robustness*100
class BotTournament:
    def rank(self, scores): return sorted(scores, key=lambda x:x.score, reverse=True)
