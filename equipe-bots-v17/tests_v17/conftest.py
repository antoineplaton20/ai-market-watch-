"""Tests V17 : dossier temporaire, aucun réseau, aucun message Telegram, indépendants du .env du serveur."""
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def isolement(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import outils_v17
    import v17_ops.adapters.market as market
    monkeypatch.setattr(market, 'time', SimpleNamespace(time=lambda: outils_v17.clock_ms / 1000))
    monkeypatch.chdir(tmp_path)
    for nom in list(os.environ):
        if nom.startswith("V17_") or nom in ("LIVE_TRADING_ENABLED", "KILL_SWITCH", "OPS_DB"):
            monkeypatch.delenv(nom, raising=False)
    # Réglages neutres : le .env du serveur (V17_MODE=demo, V17_DEMO_ONLY=1...) est lu à l'import
    # et ne doit jamais faire échouer les tests (sinon « bots mettre-a-jour » ferait un retour arrière).
    from v17_ops.core import config as C
    from v17_ops.workers import engine as W
    from v17_ops import rapport as R
    import v17_ops.cli as CLI
    neutres = C.Settings(ops_db=str(tmp_path / "runtime" / "v17_ops.db"), telegram=False)
    for module, nom in ((C, "settings"), (W, "SETTINGS"), (R, "SETTINGS"), (CLI, "settings")):
        monkeypatch.setattr(module, nom, neutres)
    try:
        import alertes
        monkeypatch.setattr(alertes, "_ACTIF", False)       # jamais de Telegram pendant les tests
    except Exception:
        pass
    yield


@pytest.fixture
def reglages(tmp_path):
    from v17_ops.core.config import Settings

    def fabrique(**kw):
        base = dict(ops_db=str(tmp_path / "runtime" / "v17.db"), telegram=False)
        base.update(kw)
        return Settings(**base)
    return fabrique
