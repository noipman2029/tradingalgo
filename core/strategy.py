"""
Multi-timeframe scalping strategy engine.

Entry signals from M3 (Williams %R + Bollinger Bands),
confirmed by M15 and H1 trend filters.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from core.indicators import compute_all_indicators

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "NONE"
    entry_price: float
    sl: float
    tp: float
    reason: str


@dataclass
class TimeframeAnalysis:
    """Indicator snapshot for a single timeframe."""
    timeframe: str
    williams_r: float
    close: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_bandwidth: float
    bias: str  # "BULLISH", "BEARISH", "NEUTRAL"


def analyze_timeframe(
    df: pd.DataFrame,
    timeframe: str,
    williams_period: int,
    bb_period: int,
    bb_std: float,
    wr_oversold: float,
    wr_overbought: float,
) -> TimeframeAnalysis | None:
    """Compute indicators and determine bias for one timeframe."""
    if df is None or len(df) < max(williams_period, bb_period) + 5:
        return None

    data = compute_all_indicators(df, williams_period, bb_period, bb_std)
    last = data.iloc[-1]

    wr = last["williams_r"]
    close = last["close"]
    bb_upper = last["bb_upper"]
    bb_middle = last["bb_middle"]
    bb_lower = last["bb_lower"]
    bw = last["bb_bandwidth"]

    # Determine bias
    if wr < wr_oversold and close <= bb_lower:
        bias = "BULLISH"  # Oversold + at lower band = expect bounce up
    elif wr > wr_overbought and close >= bb_upper:
        bias = "BEARISH"  # Overbought + at upper band = expect drop
    elif close > bb_middle and wr > -50:
        bias = "BULLISH"
    elif close < bb_middle and wr < -50:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    return TimeframeAnalysis(
        timeframe=timeframe,
        williams_r=wr,
        close=close,
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
        bb_bandwidth=bw,
        bias=bias,
    )


class ScalpingStrategy:
    """
    Multi-timeframe scalping strategy.

    Entry on M3 when:
      BUY:  Williams %R < oversold AND close touches/crosses lower Bollinger Band
      SELL: Williams %R > overbought AND close touches/crosses upper Bollinger Band

    Confirmation from higher timeframes (M15 / H1):
      - strict mode: both must confirm
      - relaxed mode: at least one must confirm
    """

    def __init__(self, config):
        self.config = config

    def evaluate(
        self,
        df_entry: pd.DataFrame,
        df_mid: pd.DataFrame,
        df_high: pd.DataFrame,
    ) -> Signal:
        """
        Evaluate all timeframes and return a trading signal.
        """
        cfg = self.config

        # Analyze each timeframe
        entry_analysis = analyze_timeframe(
            df_entry, cfg.TIMEFRAME_ENTRY,
            cfg.WILLIAMS_PERIOD, cfg.BOLLINGER_PERIOD, cfg.BOLLINGER_STD_DEV,
            cfg.WILLIAMS_OVERSOLD, cfg.WILLIAMS_OVERBOUGHT,
        )
        mid_analysis = analyze_timeframe(
            df_mid, cfg.TIMEFRAME_MID,
            cfg.WILLIAMS_PERIOD, cfg.BOLLINGER_PERIOD, cfg.BOLLINGER_STD_DEV,
            cfg.WILLIAMS_OVERSOLD, cfg.WILLIAMS_OVERBOUGHT,
        )
        high_analysis = analyze_timeframe(
            df_high, cfg.TIMEFRAME_HIGH,
            cfg.WILLIAMS_PERIOD, cfg.BOLLINGER_PERIOD, cfg.BOLLINGER_STD_DEV,
            cfg.WILLIAMS_OVERSOLD, cfg.WILLIAMS_OVERBOUGHT,
        )

        if entry_analysis is None:
            return Signal("NONE", 0, 0, 0, "Insufficient entry TF data")

        # Store last analysis for GUI display
        self.last_entry = entry_analysis
        self.last_mid = mid_analysis
        self.last_high = high_analysis

        # Check entry conditions on M3
        entry_dir = self._check_entry_signal(entry_analysis)
        if entry_dir == "NONE":
            return Signal("NONE", 0, 0, 0, "No entry signal on M3")

        # Check higher-timeframe confirmation
        confirmed, reason = self._check_htf_confirmation(
            entry_dir, mid_analysis, high_analysis
        )
        if not confirmed:
            return Signal("NONE", 0, 0, 0, reason)

        # Calculate SL/TP
        sl, tp = self._calculate_sl_tp(entry_analysis, entry_dir)

        reason_parts = [
            f"{entry_dir} signal on {cfg.TIMEFRAME_ENTRY}",
            f"WR={entry_analysis.williams_r:.1f}",
        ]
        if mid_analysis:
            reason_parts.append(f"{cfg.TIMEFRAME_MID} bias={mid_analysis.bias}")
        if high_analysis:
            reason_parts.append(f"{cfg.TIMEFRAME_HIGH} bias={high_analysis.bias}")

        return Signal(
            direction=entry_dir,
            entry_price=entry_analysis.close,
            sl=sl,
            tp=tp,
            reason=" | ".join(reason_parts),
        )

    def _check_entry_signal(self, analysis: TimeframeAnalysis) -> str:
        """Check if M3 has a valid entry signal."""
        cfg = self.config
        wr = analysis.williams_r

        # BUY: oversold + price at/below lower band
        if wr < cfg.WILLIAMS_OVERSOLD and analysis.close <= analysis.bb_lower:
            return "BUY"

        # SELL: overbought + price at/above upper band
        if wr > cfg.WILLIAMS_OVERBOUGHT and analysis.close >= analysis.bb_upper:
            return "SELL"

        return "NONE"

    def _check_htf_confirmation(
        self,
        direction: str,
        mid: TimeframeAnalysis | None,
        high: TimeframeAnalysis | None,
    ) -> tuple[bool, str]:
        """Check if higher timeframes confirm the entry direction."""
        cfg = self.config

        required_bias = "BULLISH" if direction == "BUY" else "BEARISH"

        mid_ok = mid is not None and mid.bias in (required_bias, "NEUTRAL")
        high_ok = high is not None and high.bias in (required_bias, "NEUTRAL")

        if mid is None and high is None:
            return False, "No HTF data available"

        if cfg.MTF_MODE == "strict":
            # Both must confirm (if data available)
            if mid is not None and not mid_ok:
                return False, (
                    f"{cfg.TIMEFRAME_MID} bias={mid.bias} "
                    f"contradicts {direction}"
                )
            if high is not None and not high_ok:
                return False, (
                    f"{cfg.TIMEFRAME_HIGH} bias={high.bias} "
                    f"contradicts {direction}"
                )
            return True, "HTF confirmed (strict)"
        else:
            # At least one must confirm
            if mid_ok or high_ok:
                return True, "HTF confirmed (relaxed)"
            return False, "No HTF confirmation (relaxed mode)"

    def _calculate_sl_tp(
        self, analysis: TimeframeAnalysis, direction: str
    ) -> tuple[float, float]:
        """Calculate stop loss and take profit levels."""
        cfg = self.config

        if cfg.USE_BOLLINGER_SL:
            # SL based on Bollinger band distance
            band_width = analysis.bb_upper - analysis.bb_lower
            sl_distance = band_width / 2.0
        else:
            # Fallback: fixed distance based on bandwidth as proxy for volatility
            sl_distance = analysis.bb_bandwidth * analysis.close / 10000.0

        tp_distance = sl_distance * cfg.TP_RR_RATIO

        if direction == "BUY":
            sl = analysis.close - sl_distance
            tp = analysis.close + tp_distance
        else:
            sl = analysis.close + sl_distance
            tp = analysis.close - tp_distance

        return round(sl, 6), round(tp, 6)
