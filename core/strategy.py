"""
Multi-timeframe scalping strategy engine.

Logic (example for BUY):
  1. M3: Price goes below lower Bollinger Band AND Williams %R < -80
  2. M3: Wait for Williams %R to reintegrate above -80 (confirmation of bounce)
  3. M15: Williams %R is near oversold zone AND SMA is rising (trend filter)
  4. Entry with 3 TPs spread across the Bollinger range

Mirror logic for SELL.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from core.indicators import compute_all_indicators, sma_slope

logger = logging.getLogger(__name__)


class SetupState(Enum):
    """State machine for the entry setup."""
    IDLE = "IDLE"                    # No setup detected
    WATCHING_BUY = "WATCHING_BUY"    # WR was < -80 & below BB, waiting reintegration
    WATCHING_SELL = "WATCHING_SELL"   # WR was > -20 & above BB, waiting reintegration
    IN_POSITION = "IN_POSITION"      # Trade active


@dataclass
class Signal:
    direction: str         # "BUY", "SELL", or "NONE"
    entry_price: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    reason: str


@dataclass
class TimeframeSnapshot:
    """Indicator snapshot for a single timeframe."""
    timeframe: str
    williams_r: float
    close: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    sma_value: float
    sma_rising: bool       # True if SMA slope > 0


class ScalpingStrategy:
    """
    Multi-timeframe scalping strategy with reintegration logic.

    State machine flow (BUY example):
      IDLE -> price < BB lower AND WR < -80 -> WATCHING_BUY
      WATCHING_BUY -> WR crosses back above -80 + M15 confirms -> SIGNAL BUY
      WATCHING_BUY -> price moves too far from BB / timeout -> IDLE (setup invalidated)
    """

    def __init__(self, config):
        self.config = config
        self.state = SetupState.IDLE
        self._setup_entry_wr = None   # WR value when setup was first detected

        # For GUI display
        self.last_entry: TimeframeSnapshot | None = None
        self.last_confirm: TimeframeSnapshot | None = None

    def reset(self):
        """Reset the state machine (e.g. after a trade closes)."""
        self.state = SetupState.IDLE
        self._setup_entry_wr = None

    def evaluate(
        self,
        df_entry: pd.DataFrame,
        df_confirm: pd.DataFrame,
    ) -> Signal:
        """
        Evaluate the strategy and return a signal.
        Called every tick interval by the bot engine.
        """
        cfg = self.config
        no_signal = Signal("NONE", 0, 0, 0, 0, 0, "")

        # Compute indicators on M3
        entry_data = self._analyze(df_entry, cfg.TIMEFRAME_ENTRY)
        if entry_data is None:
            return Signal("NONE", 0, 0, 0, 0, 0, "Donnees M3 insuffisantes")
        self.last_entry = entry_data

        # Compute indicators on M15
        confirm_data = self._analyze(df_confirm, cfg.TIMEFRAME_CONFIRM)
        self.last_confirm = confirm_data

        wr = entry_data.williams_r
        close = entry_data.close

        # ── State machine ────────────────────────────────────────

        if self.state == SetupState.IDLE:
            return self._check_setup(entry_data, cfg)

        elif self.state == SetupState.WATCHING_BUY:
            return self._check_reintegration_buy(
                entry_data, confirm_data, df_entry, cfg
            )

        elif self.state == SetupState.WATCHING_SELL:
            return self._check_reintegration_sell(
                entry_data, confirm_data, df_entry, cfg
            )

        elif self.state == SetupState.IN_POSITION:
            # Do nothing, managed by bot engine
            return Signal("NONE", 0, 0, 0, 0, 0, "En position")

        return no_signal

    # ── Step 1: Detect initial setup ──────────────────────────────

    def _check_setup(self, entry: TimeframeSnapshot, cfg) -> Signal:
        """Look for price below BB + WR oversold (or mirror for sell)."""
        wr = entry.williams_r
        close = entry.close

        # BUY setup: price at/below lower BB AND WR in oversold zone
        if close <= entry.bb_lower and wr < cfg.WILLIAMS_OVERSOLD:
            self.state = SetupState.WATCHING_BUY
            self._setup_entry_wr = wr
            logger.info(
                "Setup BUY detecte: close=%.5f <= BB_low=%.5f, WR=%.1f",
                close, entry.bb_lower, wr,
            )
            return Signal(
                "NONE", 0, 0, 0, 0, 0,
                f"SETUP BUY detecte | WR={wr:.1f} | Attente reintegration..."
            )

        # SELL setup: price at/above upper BB AND WR in overbought zone
        if close >= entry.bb_upper and wr > cfg.WILLIAMS_OVERBOUGHT:
            self.state = SetupState.WATCHING_SELL
            self._setup_entry_wr = wr
            logger.info(
                "Setup SELL detecte: close=%.5f >= BB_up=%.5f, WR=%.1f",
                close, entry.bb_upper, wr,
            )
            return Signal(
                "NONE", 0, 0, 0, 0, 0,
                f"SETUP SELL detecte | WR={wr:.1f} | Attente reintegration..."
            )

        return Signal("NONE", 0, 0, 0, 0, 0, "Pas de setup")

    # ── Step 2: Wait for WR reintegration + M15 confirm ───────────

    def _check_reintegration_buy(
        self,
        entry: TimeframeSnapshot,
        confirm: TimeframeSnapshot | None,
        df_entry: pd.DataFrame,
        cfg,
    ) -> Signal:
        """
        BUY: Wait for WR to cross back above -80.
        If it does, check M15 confirmation then enter.
        """
        wr = entry.williams_r

        # Invalidate if price went too far above BB middle (setup expired)
        if entry.close > entry.bb_middle:
            self.state = SetupState.IDLE
            return Signal(
                "NONE", 0, 0, 0, 0, 0,
                "Setup BUY invalide: prix au-dessus de BB middle"
            )

        # WR has NOT yet reintegrated
        if wr < cfg.WILLIAMS_OVERSOLD:
            return Signal(
                "NONE", 0, 0, 0, 0, 0,
                f"SETUP BUY actif | WR={wr:.1f} < {cfg.WILLIAMS_OVERSOLD} | "
                f"Attente reintegration..."
            )

        # WR has crossed back above -80 -> check M15 confirmation
        if cfg.IGNORE_M15:
            confirmed, reason = True, "M15 ignore (desactive)"
        else:
            confirmed, reason = self._check_m15_buy(confirm, cfg)
        if not confirmed:
            # Still keep watching - M15 might align on next tick
            return Signal("NONE", 0, 0, 0, 0, 0,
                          f"Reintegration WR OK | M15: {reason}")

        # All conditions met -> generate BUY signal
        sl = self._compute_sl_buy(df_entry, entry, cfg)
        tp1, tp2, tp3 = self._compute_tps_buy(entry)

        self.state = SetupState.IN_POSITION

        m15_info = "M15 ignore" if cfg.IGNORE_M15 else (
            f"M15 WR={confirm.williams_r:.1f} SMA {'UP' if confirm.sma_rising else 'DOWN'}"
            if confirm else "M15 N/A"
        )
        return Signal(
            direction="BUY",
            entry_price=entry.close,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            reason=f"BUY M3 | WR reintegre={wr:.1f} | {m15_info}",
        )

    def _check_reintegration_sell(
        self,
        entry: TimeframeSnapshot,
        confirm: TimeframeSnapshot | None,
        df_entry: pd.DataFrame,
        cfg,
    ) -> Signal:
        """
        SELL: Wait for WR to cross back below -20.
        If it does, check M15 confirmation then enter.
        """
        wr = entry.williams_r

        # Invalidate if price went too far below BB middle
        if entry.close < entry.bb_middle:
            self.state = SetupState.IDLE
            return Signal(
                "NONE", 0, 0, 0, 0, 0,
                "Setup SELL invalide: prix en-dessous de BB middle"
            )

        # WR has NOT yet reintegrated
        if wr > cfg.WILLIAMS_OVERBOUGHT:
            return Signal(
                "NONE", 0, 0, 0, 0, 0,
                f"SETUP SELL actif | WR={wr:.1f} > {cfg.WILLIAMS_OVERBOUGHT} | "
                f"Attente reintegration..."
            )

        # WR crossed back below -20 -> check M15
        if cfg.IGNORE_M15:
            confirmed, reason = True, "M15 ignore (desactive)"
        else:
            confirmed, reason = self._check_m15_sell(confirm, cfg)
        if not confirmed:
            return Signal("NONE", 0, 0, 0, 0, 0,
                          f"Reintegration WR OK | M15: {reason}")

        sl = self._compute_sl_sell(df_entry, entry, cfg)
        tp1, tp2, tp3 = self._compute_tps_sell(entry)

        self.state = SetupState.IN_POSITION

        m15_info = "M15 ignore" if cfg.IGNORE_M15 else (
            f"M15 WR={confirm.williams_r:.1f} SMA {'DOWN' if not confirm.sma_rising else 'UP'}"
            if confirm else "M15 N/A"
        )
        return Signal(
            direction="SELL",
            entry_price=entry.close,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            reason=f"SELL M3 | WR reintegre={wr:.1f} | {m15_info}",
        )

    # ── M15 Confirmation ─────────────────────────────────────────

    def _check_m15_buy(
        self, confirm: TimeframeSnapshot | None, cfg
    ) -> tuple[bool, str]:
        """
        M15 must confirm BUY:
          1. WR is near oversold zone (< oversold + confirm_zone)
          2. SMA is rising (trend not bearish)
        """
        if confirm is None:
            return False, "Donnees M15 indisponibles"

        wr_threshold = cfg.WILLIAMS_OVERSOLD + cfg.WILLIAMS_CONFIRM_ZONE
        if confirm.williams_r > wr_threshold:
            return False, (
                f"WR M15={confirm.williams_r:.1f} trop haut "
                f"(seuil={wr_threshold:.0f})"
            )

        if not confirm.sma_rising:
            return False, "SMA M15 descendante (contre-tendance)"

        return True, "OK"

    def _check_m15_sell(
        self, confirm: TimeframeSnapshot | None, cfg
    ) -> tuple[bool, str]:
        """
        M15 must confirm SELL:
          1. WR is near overbought zone (> overbought - confirm_zone)
          2. SMA is falling (trend not bullish)
        """
        if confirm is None:
            return False, "Donnees M15 indisponibles"

        wr_threshold = cfg.WILLIAMS_OVERBOUGHT - cfg.WILLIAMS_CONFIRM_ZONE
        if confirm.williams_r < wr_threshold:
            return False, (
                f"WR M15={confirm.williams_r:.1f} trop bas "
                f"(seuil={wr_threshold:.0f})"
            )

        if confirm.sma_rising:
            return False, "SMA M15 croissante (contre-tendance)"

        return True, "OK"

    # ── SL Calculation: Swing Low/High ────────────────────────────

    def _compute_sl_buy(
        self, df: pd.DataFrame, entry: TimeframeSnapshot, cfg
    ) -> float:
        """SL = recent swing low - margin."""
        lookback = min(cfg.SL_SWING_LOOKBACK, len(df) - 1)
        recent_lows = df["low"].iloc[-lookback:]
        swing_low = float(recent_lows.min())

        # Get point value for margin
        margin = cfg.SL_MARGIN_POINTS * 0.00001  # Approximate for forex
        sl = swing_low - margin
        return round(sl, 6)

    def _compute_sl_sell(
        self, df: pd.DataFrame, entry: TimeframeSnapshot, cfg
    ) -> float:
        """SL = recent swing high + margin."""
        lookback = min(cfg.SL_SWING_LOOKBACK, len(df) - 1)
        recent_highs = df["high"].iloc[-lookback:]
        swing_high = float(recent_highs.max())

        margin = cfg.SL_MARGIN_POINTS * 0.00001
        sl = swing_high + margin
        return round(sl, 6)

    # ── TP Calculation: 3 levels across BB range ──────────────────

    def _compute_tps_buy(
        self, entry: TimeframeSnapshot
    ) -> tuple[float, float, float]:
        """
        BUY TPs spread from entry to BB upper:
          TP1 = BB middle (33% of the distance, quick profit)
          TP2 = 75% of distance to BB upper
          TP3 = BB upper (full target)
        """
        tp1 = entry.bb_middle
        distance = entry.bb_upper - entry.close
        tp2 = entry.close + distance * 0.75
        tp3 = entry.bb_upper
        return round(tp1, 6), round(tp2, 6), round(tp3, 6)

    def _compute_tps_sell(
        self, entry: TimeframeSnapshot
    ) -> tuple[float, float, float]:
        """
        SELL TPs spread from entry to BB lower:
          TP1 = BB middle
          TP2 = 75% of distance to BB lower
          TP3 = BB lower (full target)
        """
        tp1 = entry.bb_middle
        distance = entry.close - entry.bb_lower
        tp2 = entry.close - distance * 0.75
        tp3 = entry.bb_lower
        return round(tp1, 6), round(tp2, 6), round(tp3, 6)

    # ── Analyze a timeframe ───────────────────────────────────────

    def _analyze(
        self, df: pd.DataFrame, timeframe: str
    ) -> TimeframeSnapshot | None:
        """Compute indicators and return a snapshot."""
        cfg = self.config
        min_bars = max(cfg.WILLIAMS_PERIOD, cfg.BOLLINGER_PERIOD,
                       cfg.SMA_PERIOD) + 5

        if df is None or len(df) < min_bars:
            return None

        data = compute_all_indicators(
            df, cfg.WILLIAMS_PERIOD, cfg.BOLLINGER_PERIOD,
            cfg.BOLLINGER_STD_DEV, cfg.SMA_PERIOD,
        )
        last = data.iloc[-1]

        slope = sma_slope(data["sma"], cfg.SMA_LOOKBACK)

        return TimeframeSnapshot(
            timeframe=timeframe,
            williams_r=last["williams_r"],
            close=last["close"],
            bb_upper=last["bb_upper"],
            bb_middle=last["bb_middle"],
            bb_lower=last["bb_lower"],
            sma_value=last["sma"],
            sma_rising=slope > 0,
        )
