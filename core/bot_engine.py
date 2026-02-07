"""
Main bot engine: orchestrates MT5 data fetching, strategy evaluation,
order execution, and trade management (trailing stop).
"""

import logging
import threading
import time
from datetime import datetime

from core.mt5_connector import MT5Connector
from core.strategy import ScalpingStrategy, Signal

logger = logging.getLogger(__name__)


class BotEngine:
    """
    Core trading engine that runs in a background thread.
    Communicates state changes via callbacks for the GUI.
    """

    def __init__(self, config):
        self.config = config
        self.connector = MT5Connector(config.MT5_PATH)
        self.strategy = ScalpingStrategy(config)

        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Callbacks set by the GUI
        self.on_log = None          # (str) -> None
        self.on_signal = None       # (Signal) -> None
        self.on_trade = None        # (dict) -> None
        self.on_status = None       # (dict) -> None
        self.on_positions = None    # (list[dict]) -> None
        self.on_indicators = None   # (dict) -> None

        # Stats
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0

    def _log(self, msg: str):
        logger.info(msg)
        if self.on_log:
            try:
                self.on_log(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            except Exception:
                pass

    def start(self) -> bool:
        """Start the bot. Returns True if started successfully."""
        if self._running:
            return True

        if not self.connector.connect():
            self._log("ERREUR: Impossible de se connecter a MT5")
            return False

        account = self.connector.get_account_info()
        if account:
            self._log(
                f"Connecte: {account['login']} @ {account['server']} | "
                f"Balance: {account['balance']} {account['currency']}"
            )

        sym_info = self.connector.get_symbol_info(self.config.SYMBOL)
        if sym_info is None:
            self._log(f"ERREUR: Symbole {self.config.SYMBOL} introuvable")
            self.connector.disconnect()
            return False

        self._log(f"Symbole {self.config.SYMBOL} OK (spread={sym_info['spread']})")

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._log("Bot demarre")
        return True

    def stop(self):
        """Stop the bot gracefully."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self.connector.disconnect()
        self._log("Bot arrete")

    @property
    def is_running(self) -> bool:
        return self._running

    def _loop(self):
        """Main bot loop running in a background thread."""
        cfg = self.config

        while self._running:
            try:
                self._tick()
            except Exception as e:
                self._log(f"Erreur dans la boucle: {e}")
                logger.exception("Bot loop error")

            # Wait for next check
            for _ in range(cfg.CHECK_INTERVAL_SECONDS * 10):
                if not self._running:
                    return
                time.sleep(0.1)

    def _tick(self):
        """Single iteration of the bot logic."""
        cfg = self.config

        # Fetch candles for all timeframes
        df_entry = self.connector.get_candles(
            cfg.SYMBOL, cfg.TIMEFRAME_ENTRY, cfg.CANDLES_COUNT
        )
        df_mid = self.connector.get_candles(
            cfg.SYMBOL, cfg.TIMEFRAME_MID, cfg.CANDLES_COUNT
        )
        df_high = self.connector.get_candles(
            cfg.SYMBOL, cfg.TIMEFRAME_HIGH, cfg.CANDLES_COUNT
        )

        if df_entry is None:
            self._log("Pas de donnees pour le timeframe d'entree")
            return

        # Evaluate strategy
        signal = self.strategy.evaluate(df_entry, df_mid, df_high)

        # Send indicator data to GUI
        self._publish_indicators()

        # Update account/positions status
        self._publish_status()

        if signal.direction == "NONE":
            if self.on_signal:
                self.on_signal(signal)
            # Still manage existing positions (trailing stop)
            self._manage_positions()
            return

        self._log(f"SIGNAL: {signal.direction} | {signal.reason}")
        if self.on_signal:
            self.on_signal(signal)

        # Check position limit
        positions = self.connector.get_positions(
            cfg.SYMBOL, cfg.MAGIC_NUMBER
        )
        if len(positions) >= cfg.MAX_POSITIONS:
            self._log(
                f"Max positions atteint ({cfg.MAX_POSITIONS}), signal ignore"
            )
            return

        # Check no duplicate direction
        for p in positions:
            if p["type"] == signal.direction:
                self._log(
                    f"Position {signal.direction} deja ouverte, signal ignore"
                )
                return

        # Execute trade
        result = self.connector.send_order(
            symbol=cfg.SYMBOL,
            order_type=signal.direction,
            lot=cfg.LOT_SIZE,
            sl=signal.sl,
            tp=signal.tp,
            magic=cfg.MAGIC_NUMBER,
            slippage=cfg.SLIPPAGE,
            comment=f"ScalpBot {signal.direction}",
        )

        if result and result.get("success"):
            self.total_trades += 1
            self._log(
                f"TRADE EXECUTE: {signal.direction} {cfg.LOT_SIZE} lots "
                f"@ {result['price']:.5f} | SL={signal.sl:.5f} TP={signal.tp:.5f}"
            )
            if self.on_trade:
                self.on_trade(result)
        else:
            comment = result.get("comment", "Unknown") if result else "None"
            self._log(f"ECHEC ORDRE: {comment}")

        # Manage trailing stop on existing positions
        self._manage_positions()

    def _manage_positions(self):
        """Apply trailing stop to open positions."""
        cfg = self.config

        if not cfg.TRAILING_STOP:
            return

        positions = self.connector.get_positions(
            cfg.SYMBOL, cfg.MAGIC_NUMBER
        )

        if self.on_positions:
            self.on_positions(positions)

        sym_info = self.connector.get_symbol_info(cfg.SYMBOL)
        if sym_info is None:
            return
        point = sym_info["point"]
        trail_distance = cfg.TRAILING_STEP_POINTS * point

        tick = self.connector.get_tick(cfg.SYMBOL)
        if tick is None:
            return

        for pos in positions:
            current_sl = pos["sl"]
            tp = pos["tp"]

            if pos["type"] == "BUY":
                # For buy: trail SL up as price rises
                new_sl = tick["bid"] - trail_distance
                if new_sl > current_sl and new_sl > pos["open_price"]:
                    self.connector.modify_position_sl(
                        pos["ticket"], cfg.SYMBOL, new_sl, tp
                    )
                    self._log(
                        f"Trailing SL BUY #{pos['ticket']}: "
                        f"{current_sl:.5f} -> {new_sl:.5f}"
                    )
            else:
                # For sell: trail SL down as price falls
                new_sl = tick["ask"] + trail_distance
                if (current_sl == 0 or new_sl < current_sl) and \
                        new_sl < pos["open_price"]:
                    self.connector.modify_position_sl(
                        pos["ticket"], cfg.SYMBOL, new_sl, tp
                    )
                    self._log(
                        f"Trailing SL SELL #{pos['ticket']}: "
                        f"{current_sl:.5f} -> {new_sl:.5f}"
                    )

    def _publish_indicators(self):
        """Send latest indicator values to GUI."""
        if not self.on_indicators:
            return

        data = {}
        for attr, label in [
            ("last_entry", "Entry"),
            ("last_mid", "Mid"),
            ("last_high", "High"),
        ]:
            analysis = getattr(self.strategy, attr, None)
            if analysis:
                data[label] = {
                    "timeframe": analysis.timeframe,
                    "williams_r": analysis.williams_r,
                    "close": analysis.close,
                    "bb_upper": analysis.bb_upper,
                    "bb_middle": analysis.bb_middle,
                    "bb_lower": analysis.bb_lower,
                    "bias": analysis.bias,
                }

        self.on_indicators(data)

    def _publish_status(self):
        """Send account status to GUI."""
        if not self.on_status:
            return

        account = self.connector.get_account_info()
        if account:
            account["total_trades"] = self.total_trades
            account["winning"] = self.winning_trades
            account["losing"] = self.losing_trades
            self.on_status(account)
