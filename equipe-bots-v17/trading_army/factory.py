import json
from pathlib import Path
from .bot_catalog import build_trading_army_catalog
class TradingBotFactory:
    def __init__(self, root=None): self.root=Path(root or Path(__file__).resolve().parents[1]); self.catalog=build_trading_army_catalog()
    def export(self):
        p=self.root/"catalogue"/"trading_army_v16.json"; p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(self.catalog,ensure_ascii=False,indent=2)); return p
    def scaffold(self, bot):
        d=self.root/"runtime"/"generated"/bot["id"]; d.mkdir(parents=True,exist_ok=True)
        (d/"SPEC.json").write_text(json.dumps(bot,ensure_ascii=False,indent=2));
        (d/"agent.py").write_text("class Agent:\n    def plan(self, task): return {'status':'planned','task':task}\n")
        return d
