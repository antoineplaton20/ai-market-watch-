"""Configuration commune des tests : dossier temporaire, aucune connexion, aucun message Telegram."""
import os
import sys
import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def isolement(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                       # chaque test a ses propres fichiers (journal, état...)
    import config
    import alertes
    import gardien
    monkeypatch.setattr(alertes, "_ACTIF", False)     # jamais de message Telegram pendant les tests
    monkeypatch.setattr(config, "REEL", False)
    monkeypatch.setattr(config, "MODE", "testnet")              # indépendant du fichier .env de l'utilisateur
    for nom, valeur in {"VOLUME_24H_MIN": 0, "SPREAD_MAX_PCT": 1.0, "PROFONDEUR_MIN_USDT": 0,
                        "BALEINE_MIN_USDT": 1000, "PALIERS_CAPITAL": [1000, 3000], "ANTHROPIC_API_KEY": "",
                        "COINGECKO_API_KEY": ""}.items():
        monkeypatch.setattr(config, nom, valeur)
    monkeypatch.setattr(config, "CAPITAL_MAX_USDT", 1000.0)
    monkeypatch.setattr(config, "UNITE_BOUGIE", "15m")
    monkeypatch.setattr(config, "EXPLORATION_NIVEAU_DEFAUT", 0)      # tests du champion strict ; exploration testée à part
    monkeypatch.setattr(config, "EVENEMENTS_MACRO", [])               # les tests ne dépendent pas du calendrier réel
    monkeypatch.setattr(gardien.time, "sleep", lambda s: None)
    yield
