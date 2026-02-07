"""
MT5 Scalping Bot - Entry point.

Multi-timeframe scalping strategy using Williams %R and Bollinger Bands.
Trades on M3 with M15/H1 confirmation, managed via a Tkinter GUI.

Usage:
    python main.py
"""

import logging
import sys

import config
from core.bot_engine import BotEngine
from gui.app import ScalpBotGUI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("scalp_bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def main():
    logger.info("Starting MT5 Scalping Bot")

    engine = BotEngine(config)
    gui = ScalpBotGUI(config, engine)
    gui.run()

    logger.info("MT5 Scalping Bot closed")


if __name__ == "__main__":
    main()
