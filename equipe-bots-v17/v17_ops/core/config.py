"""Réglages V17 OPS, lus dans le .env de la plateforme (même fichier que le bot principal).

Les variables propres à la v17 commencent par V17_ : elles ne se mélangent pas avec celles du bot
principal. En particulier MODE (demo / reel) appartient au bot principal et n'est PAS lu ici.
"""
from __future__ import annotations

import os
import math
from dataclasses import dataclass, field

try:                                     # le .env du dossier du bot (comme config.py à la racine)
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:                      # pragma: no cover - python-dotenv est dans requirements.txt
    pass

MODES = ("paper", "demo", "testnet", "live")
MODES_EXCHANGE = ("demo", "testnet", "live")


def _txt(*noms: str, defaut: str = "") -> str:
    for nom in noms:
        v = os.getenv(nom)
        if v is not None and v.strip() != "":
            return v.strip()
    return defaut


def _float(*noms: str, defaut: float) -> float:
    try:
        return float(_txt(*noms, defaut=str(defaut)).replace(",", "."))
    except ValueError:
        return float(defaut)


def _int(*noms: str, defaut: int) -> int:
    try:
        return int(float(_txt(*noms, defaut=str(defaut))))
    except ValueError:
        return int(defaut)


def _bool(*noms: str, defaut: bool = False) -> bool:
    return _txt(*noms, defaut="1" if defaut else "0").lower() in {"1", "true", "yes", "on", "oui"}


def _symboles(texte: str) -> tuple[str, ...]:
    out = []
    for s in texte.replace(";", ",").split(","):
        s = s.strip().upper()
        if not s:
            continue
        if "/" not in s and s.endswith("USDT"):          # BTCUSDT -> BTC/USDT
            s = s[:-4] + "/USDT"
        if s not in out:
            out.append(s)
    return tuple(out) or ("BTC/USDT",)


@dataclass(frozen=True)
class Settings:
    mode: str = "paper"
    symbols: tuple[str, ...] = ("BTC/USDT",)
    timeframe: str = "15m"
    interval: float = 60.0
    ops_db: str = "runtime/v17_ops.db"
    log_file: str = "v17.log"
    live_trading_enabled: bool = False
    kill_switch: bool = False
    capital_max_usdt: float = 1000.0
    max_order_usdt: float = 100.0
    max_position_usdt: float = 250.0
    max_daily_loss_usdt: float = 50.0
    max_slippage_pct: float = 0.25
    max_open_orders: int = 5
    paper_cash_usdt: float = 10000.0
    paper_slippage_pct: float = 0.05
    fee_rate: float = 0.001
    score_min: float = 0.65
    stop_loss_pct: float = 3.0
    min_order_usdt: float = 10.0
    api_key: str = field(default="", repr=False)
    api_secret: str = field(default="", repr=False)
    main_api_key: str = field(default="", repr=False)
    main_api_secret: str = field(default="", repr=False)
    main_mode: str = ""                  # MODE du bot principal (demo / testnet / reel), lu pour les clés de repli
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    telegram: bool = True
    demo_only: bool = False
    renseignement: bool = True           # consulter l'armée de renseignement avant chaque achat

    def __post_init__(self):
        positive = ('capital_max_usdt', 'max_order_usdt', 'max_position_usdt',
                    'max_daily_loss_usdt', 'paper_cash_usdt', 'min_order_usdt', 'interval')
        for name in positive:
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} doit être fini et strictement positif')
        for name, upper in (('fee_rate', 1), ('paper_slippage_pct', 100),
                            ('max_slippage_pct', 100), ('stop_loss_pct', 100)):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value < upper:
                raise ValueError(f'{name} hors limites')
        if not math.isfinite(self.score_min) or not 0 <= self.score_min <= 1:
            raise ValueError('score_min hors limites')
        if self.max_open_orders < 1 or self.min_order_usdt > self.max_order_usdt:
            raise ValueError('limites d’ordre incohérentes')

    # Compatibilité V17 d'origine : un seul symbole
    @property
    def symbol(self) -> str:
        return self.symbols[0]

    @property
    def exchange_mode(self) -> bool:
        return self.mode in MODES_EXCHANGE

    @classmethod
    def from_env(cls) -> "Settings":
        mode = _txt("V17_MODE", defaut="paper").lower()
        return cls(
            mode=mode if mode in MODES else "paper",
            symbols=_symboles(_txt("V17_SYMBOLS", "SYMBOL", defaut="BTC/USDT")),
            timeframe=_txt("V17_TIMEFRAME", defaut="15m"),
            interval=max(10.0, _float("V17_INTERVAL_SECONDS", "INTERVAL_SECONDS", defaut=60)),
            ops_db=_txt("OPS_DB", defaut="runtime/v17_ops.db"),
            log_file=_txt("V17_LOG", defaut="v17.log"),
            live_trading_enabled=_bool("LIVE_TRADING_ENABLED"),
            kill_switch=_bool("KILL_SWITCH"),
            capital_max_usdt=_float("V17_CAPITAL_MAX_USDT", "CAPITAL_MAX_USDT", defaut=1000),
            max_order_usdt=_float("MAX_ORDER_USDT", defaut=100),
            max_position_usdt=_float("MAX_POSITION_USDT", defaut=250),
            max_daily_loss_usdt=_float("MAX_DAILY_LOSS_USDT", defaut=50),
            max_slippage_pct=_float("MAX_SLIPPAGE_PCT", defaut=0.25),
            max_open_orders=_int("MAX_OPEN_ORDERS", defaut=5),
            paper_cash_usdt=_float("PAPER_CASH_USDT", defaut=10000),
            paper_slippage_pct=_float("V17_PAPER_SLIPPAGE_PCT", defaut=0.05),
            fee_rate=_float("V17_FEE_RATE", defaut=0.001),
            min_order_usdt=_float("V17_MIN_ORDER_USDT", defaut=10),
            score_min=_float("V17_SCORE_MIN", defaut=0.65),
            stop_loss_pct=_float("V17_STOP_LOSS_PCT", defaut=3.0),
            api_key=_txt("V17_API_KEY"),
            api_secret=_txt("V17_API_SECRET"),
            main_api_key=_txt("BINANCE_API_KEY"),
            main_api_secret=_txt("BINANCE_API_SECRET"),
            main_mode=_txt("MODE").lower(),
            api_host=_txt("V17_API_HOST", "API_HOST", defaut="127.0.0.1"),
            api_port=_int("V17_API_PORT", "API_PORT", defaut=8080),
            telegram=_bool("V17_TELEGRAM", defaut=True),
            demo_only=_bool("V17_DEMO_ONLY", defaut=False),
            renseignement=_bool("V17_RENSEIGNEMENT", defaut=True),
        )


settings = Settings.from_env()
