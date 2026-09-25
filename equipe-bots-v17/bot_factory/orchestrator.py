from dataclasses import dataclass
from typing import Dict, List
from .policy import PolicyEngine

@dataclass
class Task:
    id: str
    goal: str
    risk: str = "low"

class Orchestrator:
    def __init__(self, registry=None):
        self.registry = registry or {}
        self.policy = PolicyEngine()

    def route(self, task: Task):
        text=task.goal.lower()
        matches=[]
        for bot_id, spec in self.registry.items():
            score=0
            for token in (spec.department.lower(), spec.specialty.lower(), spec.name.lower()):
                if token.replace('_',' ') in text: score += 2
            if score: matches.append((score, bot_id))
        return [b for _,b in sorted(matches, reverse=True)[:8]]

    def plan(self, task: Task):
        return {"task": task.__dict__, "candidates": self.route(task), "requires_approval": task.risk in {"high","critical"}}
