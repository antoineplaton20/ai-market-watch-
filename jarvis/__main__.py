# -*- coding: utf-8 -*-
"""python -m jarvis [telegram|terminal|demande "question"]"""
import logging
import sys

from .config import DONNEES


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "terminal"
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(DONNEES / "jarvis.log", encoding="utf-8")]
        + ([logging.StreamHandler()] if mode == "telegram" else []),
    )
    if mode == "telegram":
        from .telegram import BotTelegram
        BotTelegram().lancer()
    elif mode == "terminal":
        from .terminal import lancer
        lancer()
    elif mode == "demande":
        from .cerveau import Jarvis
        print(Jarvis().repondre("terminal", " ".join(sys.argv[2:]), confirmer=lambda q: False))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
