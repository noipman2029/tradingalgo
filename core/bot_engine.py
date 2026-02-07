"""
Main bot engine: orchestrates MT5 data fetching, strategy evaluation,
order execution with 3 partial TPs, breakeven management, spread filter,
and cooldown after losing trades.
"""

import logging
import math
import threading
import time
from datetime import datetime

from core.mt5_connector import MT5Connector
from core.strategy import ScalpingStrategy, Signal, SetupState

logger = logging.getLogger(__name__)


class ActiveTrade:
    """Tracks a multi-TP trade (3 sub-positions)."""

    def __init__(self, direction: str, tickets: list[int], lots: list[float],
                 entry_price: float, sl: float,
                 tp1: float, tp2: float, tp3: float):
        self.direction = direction
        self.tickets = tickets          # [ticket_tp1, ticket_tp2, ticket_tp3]
        self.lots = lots                # [lot1, lot2, lot3]
        self.entry_price = entry_price
        self.sl = sl
        self.tps = [tp1, tp2, tp3]
        self.tp1_hit = False
        self.tp2_hit = False
        self.tp3_hit = False
        self.breakeven_applied = False


class BotEngine:
    """
    Core trading engine that runs in a background thread.
    Handles 3-TP partial closes, breakeven after TP1, spread filter,
    and cooldown after losing trades.
    """

    def __init__(self, config):
        self.config = config
        self.connector = MT5Connector(config.MT5_PATH)
        self.strategy = ScalpingStrategy(config)

        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Active trade tracking
        self.active_trade: ActiveTrade | None = None

        # Cooldown
        self._last_loss_time: float = 0

        # Callbacks set by the GUI
        self.on_log = None          # (str) -> None
        self.on_signal = None       # (Signal) -> None
        self.on_trade = None        # (dict) -> None
        self.on_status = None       # (dict) -> None
        self.on_positions = None    # (list[dict]) -> None
        self.on_indicators = None   # (dict) -> None
        self.on_state = None        # (str) -> None
        self.on_chart_data = None   # (pd.DataFrame) -> None

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
        self._log("Bot demarre - Strategie: WR reintegration + BB + M15 SMA")
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

            for _ in range(cfg.CHECK_INTERVAL_SECONDS * 10):
                if not self._running:
                    return
                time.sleep(0.1)

    def _tick(self):
        """Single iteration of the bot logic."""
        cfg = self.config

        # Update positions display and check if active trade is still open
        self._check_active_trade()

        # Publish state to GUI
        if self.on_state:
            self.on_state(self.strategy.state.value)

        # Fetch candles
        df_entry = self.connector.get_candles(
            cfg.SYMBOL, cfg.TIMEFRAME_ENTRY, cfg.CANDLES_COUNT
        )
        if cfg.IGNORE_M15:
            df_confirm = None
        else:
            df_confirm = self.connector.get_candles(
                cfg.SYMBOL, cfg.TIMEFRAME_CONFIRM, cfg.CANDLES_COUNT
            )

        if df_entry is None:
            self._log("Pas de donnees pour le timeframe d'entree")
            return

        # Evaluate strategy
        signal = self.strategy.evaluate(df_entry, df_confirm)

        # Publish indicators and chart data to GUI
        self._publish_indicators()
        self._publish_status()
        if self.on_chart_data:
            self.on_chart_data(df_entry)

        if self.on_signal:
            self.on_signal(signal)

        if signal.direction == "NONE":
            # Manage active trade (breakeven)
            if self.active_trade:
                self._manage_breakeven()
            return

        # ── We have a BUY or SELL signal ──────────────────────────

        self._log(f"SIGNAL: {signal.direction} | {signal.reason}")

        # Spread filter
        if not cfg.IGNORE_SPREAD:
            sym_info = self.connector.get_symbol_info(cfg.SYMBOL)
            if sym_info and sym_info["spread"] > cfg.MAX_SPREAD_POINTS:
                self._log(
                    f"Spread trop eleve: {sym_info['spread']} > {cfg.MAX_SPREAD_POINTS} | "
                    f"Signal ignore"
                )
                self.strategy.reset()
                return

        # Cooldown check
        if self._last_loss_time > 0:
            elapsed = time.time() - self._last_loss_time
            if elapsed < cfg.COOLDOWN_SECONDS:
                remaining = int(cfg.COOLDOWN_SECONDS - elapsed)
                self._log(f"Cooldown actif: {remaining}s restantes | Signal ignore")
                self.strategy.reset()
                return

        # Check no existing active trade
        if self.active_trade:
            self._log("Trade deja actif, signal ignore")
            return

        # Execute 3 sub-orders
        self._execute_multi_tp(signal)

    # ── Multi-TP Order Execution ──────────────────────────────────

    def _execute_multi_tp(self, signal: Signal):
        """Open 3 positions with different TPs for partial close."""
        cfg = self.config

        # Split lot into 3 parts
        sym_info = self.connector.get_symbol_info(cfg.SYMBOL)
        if sym_info is None:
            return

        vol_step = sym_info["volume_step"]
        vol_min = sym_info["volume_min"]
        total_lot = cfg.LOT_SIZE

        # Split: 33% / 33% / 34%
        lot1 = self._round_lot(total_lot / 3, vol_step, vol_min)
        lot2 = self._round_lot(total_lot / 3, vol_step, vol_min)
        lot3 = self._round_lot(total_lot - lot1 - lot2, vol_step, vol_min)

        lots = [lot1, lot2, lot3]
        tps = [signal.tp1, signal.tp2, signal.tp3]
        tickets = []

        for i, (lot, tp) in enumerate(zip(lots, tps), 1):
            if lot < vol_min:
                self._log(f"Lot TP{i} trop petit ({lot}), ignore")
                continue

            result = self.connector.send_order(
                symbol=cfg.SYMBOL,
                order_type=signal.direction,
                lot=lot,
                sl=signal.sl,
                tp=tp,
                magic=cfg.MAGIC_NUMBER,
                slippage=cfg.SLIPPAGE,
                comment=f"ScalpBot TP{i}",
            )

            if result and result.get("success"):
                tickets.append(result["ticket"])
                self._log(
                    f"  TP{i}: {lot:.2f} lots @ {result['price']:.5f} | "
                    f"SL={signal.sl:.5f} TP={tp:.5f} (#{result['ticket']})"
                )
            else:
                comment = result.get("comment", "?") if result else "None"
                self._log(f"  ECHEC TP{i}: {comment}")
                tickets.append(None)

        valid_tickets = [t for t in tickets if t is not None]
        if not valid_tickets:
            self._log("Aucun ordre execute, abandon")
            self.strategy.reset()
            return

        self.active_trade = ActiveTrade(
            direction=signal.direction,
            tickets=tickets,
            lots=lots,
            entry_price=signal.entry_price,
            sl=signal.sl,
            tp1=signal.tp1,
            tp2=signal.tp2,
            tp3=signal.tp3,
        )
        self.total_trades += 1
        self._log(
            f"TRADE OUVERT: {signal.direction} {total_lot:.2f} lots "
            f"(3 TPs: {signal.tp1:.5f} / {signal.tp2:.5f} / {signal.tp3:.5f})"
        )
        if self.on_trade:
            self.on_trade({"direction": signal.direction, "tickets": valid_tickets})

    def _round_lot(self, lot: float, step: float, minimum: float) -> float:
        """Round lot to volume step."""
        if step == 0:
            step = 0.01
        rounded = math.floor(lot / step) * step
        rounded = round(rounded, 8)
        return max(rounded, minimum)

    # ── Active Trade Management ───────────────────────────────────

    def _check_active_trade(self):
        """Check which TPs have been hit and if trade is fully closed."""
        if self.active_trade is None:
            # Check if we should be in position but lost it
            if self.strategy.state == SetupState.IN_POSITION:
                positions = self.connector.get_positions(
                    self.config.SYMBOL, self.config.MAGIC_NUMBER
                )
                if not positions:
                    self._log("Positions fermees (SL ou manuellement)")
                    self.losing_trades += 1
                    self._last_loss_time = time.time()
                    self._log(
                        f"Cooldown active pour {self.config.COOLDOWN_SECONDS}s"
                    )
                    self.strategy.reset()
            return

        cfg = self.config
        positions = self.connector.get_positions(cfg.SYMBOL, cfg.MAGIC_NUMBER)

        if self.on_positions:
            self.on_positions(positions)

        open_tickets = {p["ticket"] for p in positions}
        trade = self.active_trade

        # Check each TP sub-position
        closed_count = 0
        for i, ticket in enumerate(trade.tickets):
            if ticket is None:
                closed_count += 1
                continue
            if ticket not in open_tickets:
                closed_count += 1
                tp_num = i + 1
                if tp_num == 1 and not trade.tp1_hit:
                    trade.tp1_hit = True
                    self._log(f"TP1 touche! (#{ticket})")
                    self.winning_trades += 1
                elif tp_num == 2 and not trade.tp2_hit:
                    trade.tp2_hit = True
                    self._log(f"TP2 touche! (#{ticket})")
                elif tp_num == 3 and not trade.tp3_hit:
                    trade.tp3_hit = True
                    self._log(f"TP3 touche! (#{ticket})")

        # All sub-positions closed
        if closed_count == len(trade.tickets):
            self._log("Trade completement ferme")
            self.active_trade = None
            self.strategy.reset()

    def _manage_breakeven(self):
        """Move SL to entry price after TP1 is hit."""
        cfg = self.config
        trade = self.active_trade

        if trade is None or not cfg.BREAKEVEN_AFTER_TP1:
            return

        if not trade.tp1_hit or trade.breakeven_applied:
            return

        # Move SL of remaining positions to entry price
        positions = self.connector.get_positions(cfg.SYMBOL, cfg.MAGIC_NUMBER)
        be_price = trade.entry_price

        for pos in positions:
            if pos["ticket"] in trade.tickets:
                current_sl = pos["sl"]
                if trade.direction == "BUY" and current_sl < be_price:
                    ok = self.connector.modify_position_sl(
                        pos["ticket"], cfg.SYMBOL, be_price, pos["tp"]
                    )
                    if ok:
                        self._log(
                            f"Breakeven BUY #{pos['ticket']}: "
                            f"SL {current_sl:.5f} -> {be_price:.5f}"
                        )
                elif trade.direction == "SELL" and (
                    current_sl == 0 or current_sl > be_price
                ):
                    ok = self.connector.modify_position_sl(
                        pos["ticket"], cfg.SYMBOL, be_price, pos["tp"]
                    )
                    if ok:
                        self._log(
                            f"Breakeven SELL #{pos['ticket']}: "
                            f"SL {current_sl:.5f} -> {be_price:.5f}"
                        )

        trade.breakeven_applied = True
        self._log("Breakeven applique sur toutes les positions restantes")

    # ── Publishing to GUI ─────────────────────────────────────────

    def _publish_indicators(self):
        """Send latest indicator values to GUI."""
        if not self.on_indicators:
            return

        data = {}
        for attr, label in [
            ("last_entry", "Entry"),
            ("last_confirm", "Confirm"),
        ]:
            snap = getattr(self.strategy, attr, None)
            if snap:
                data[label] = {
                    "timeframe": snap.timeframe,
                    "williams_r": snap.williams_r,
                    "close": snap.close,
                    "bb_upper": snap.bb_upper,
                    "bb_middle": snap.bb_middle,
                    "bb_lower": snap.bb_lower,
                    "sma_value": snap.sma_value,
                    "sma_rising": snap.sma_rising,
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
