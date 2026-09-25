import json
from pathlib import Path
from .catalogue import build_catalogue
from .models import BotSpec

class BotFactory:
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[1])
        self.catalogue = build_catalogue()

    def list_bots(self):
        return self.catalogue

    def export_json(self, path=None):
        path = Path(path or self.root / "catalogue" / "bots_v15.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([b.__dict__ for b in self.catalogue], ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def scaffold(self, spec: BotSpec):
        d=self.root / "runtime" / "generated" / spec.id
        d.mkdir(parents=True, exist_ok=True)
        (d/"SPEC.json").write_text(json.dumps(spec.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
        (d/"README.md").write_text(f"# {spec.name}\n\nMission: {spec.mission}\n\nEtat: {spec.status}\n", encoding="utf-8")
        (d/"agent.py").write_text("""class Agent:\n    def __init__(self, spec):\n        self.spec = spec\n\n    def plan(self, task):\n        return {\"bot\": self.spec.id, \"task\": task, \"status\": \"planned\"}\n\n    def execute(self, task):\n        raise NotImplementedError(\"Connecter un runtime LLM/outils après validation de la policy.\")\n""", encoding="utf-8")
        return d
