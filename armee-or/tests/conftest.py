"""Tests de l'armée de l'or : base temporaire, aucun Telegram, aucun réseau."""
import os
import shutil
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)


@pytest.fixture(scope="session")
def base_historique(tmp_path_factory):
    """Base importée UNE fois (historique livré complet), recopiée pour chaque test qui la demande."""
    from armee_or import config, donnees
    chemin = tmp_path_factory.mktemp("hist") / "or.db"
    ancien = config.BASE
    config.BASE = chemin
    try:
        donnees.importer_tout()
    finally:
        config.BASE = ancien
    return chemin


@pytest.fixture(autouse=True)
def isolement(tmp_path, monkeypatch):
    from armee_or import config
    monkeypatch.setattr(config, "BASE", tmp_path / "or.db")
    monkeypatch.setattr(config, "RACINE", tmp_path)
    monkeypatch.setattr(config, "TELEGRAM_JETON", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT", "")
    monkeypatch.setattr(config, "TELEGRAM_COMMANDES", False)
    monkeypatch.setattr(config, "MT5_ACTIF", False)          # jamais le vrai compte MT5 pendant les tests
    (tmp_path / "runtime").mkdir()
    yield


@pytest.fixture
def historique(base_historique, tmp_path, monkeypatch):
    from armee_or import config
    copie = tmp_path / "hist.db"
    shutil.copy(base_historique, copie)
    monkeypatch.setattr(config, "BASE", copie)
    return copie
