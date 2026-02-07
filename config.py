"""
Configuration for the MT5 Scalping Bot.
All parameters can be adjusted via the GUI at runtime.
"""

# --- MT5 Connection ---
MT5_PATH = None  # Path to MT5 terminal (None = auto-detect)

# --- Symbol & Timeframes ---
SYMBOL = "EURUSD"
TIMEFRAME_ENTRY = "M3"       # Primary timeframe for entry signals
TIMEFRAME_CONFIRM = "M15"    # Confirmation timeframe

# --- Indicator Parameters ---
# Williams %R
WILLIAMS_PERIOD = 14
WILLIAMS_OVERSOLD = -80.0     # Below this = oversold (buy zone)
WILLIAMS_OVERBOUGHT = -20.0   # Above this = overbought (sell zone)
WILLIAMS_CONFIRM_ZONE = 15.0  # M15 WR must be within this distance of threshold

# Bollinger Bands
BOLLINGER_PERIOD = 20
BOLLINGER_STD_DEV = 2.0

# SMA for trend detection on M15
SMA_PERIOD = 20
SMA_LOOKBACK = 3              # Number of bars to check SMA slope

# --- Strategy Parameters ---
CANDLES_COUNT = 200

# --- Risk Management ---
LOT_SIZE = 0.03               # Total lot size (split across 3 TPs)
MAX_POSITIONS = 1             # Max simultaneous setups
SL_SWING_LOOKBACK = 10        # Bars to look back for swing low/high for SL
SL_MARGIN_POINTS = 30         # Extra margin below/above swing for SL (in points)
BREAKEVEN_AFTER_TP1 = True    # Move SL to entry after TP1 hit
MAX_SPREAD_POINTS = 30        # Max spread allowed to enter a trade
IGNORE_SPREAD = False         # If True, spread filter is disabled
COOLDOWN_SECONDS = 120        # Wait time after a losing trade
IGNORE_M15 = False            # If True, M15 confirmation is skipped (M3 only)

# --- Bot Behavior ---
CHECK_INTERVAL_SECONDS = 5    # How often to check for signals
MAGIC_NUMBER = 123456         # Unique identifier for bot orders
SLIPPAGE = 10                 # Max allowed slippage in points
