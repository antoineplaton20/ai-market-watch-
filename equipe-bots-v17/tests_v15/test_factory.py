import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot_factory import BotFactory, Orchestrator, Task, PolicyEngine

def test_catalogue_is_large_enough():
    bots=BotFactory().list_bots()
    assert len(bots) >= 100
    assert len({b.id for b in bots}) == len(bots)

def test_policy_denies_side_effect_without_approval():
    assert not PolicyEngine().authorize(["read"], "shell", approved=False).allowed

def test_orchestrator_routes():
    bots=BotFactory().list_bots()
    registry={b.id:b for b in bots}
    plan=Orchestrator(registry).plan(Task("t1", "recherche web et fact check"))
    assert plan["candidates"]
