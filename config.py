"""
Configuration for the MT5 Scalping Bot.
All parameters can be adjusted via the GUI at runtime.
"""

# --- MT5 Connection ---
MT5_PATH = None  # Path to MT5 terminal (None = auto-detect)

# --- Symbol & Timeframes ---
SYMBOL = "EURUSD"
TIMEFRAME_ENTRY = "M3"       # Primary timeframe for entry signals
TIMEFRAME_MID = "M15"        # Mid-level confirmation
TIMEFRAME_HIGH = "H1"        # High-level trend filter

# --- Indicator Parameters ---
# Williams %R
WILLIAMS_PERIOD = 14
WILLIAMS_OVERSOLD = -80.0     # Below this = oversold (buy zone)
WILLIAMS_OVERBOUGHT = -20.0   # Above this = overbought (sell zone)

# Bollinger Bands
BOLLINGER_PERIOD = 20
BOLLINGER_STD_DEV = 2.0

# --- Strategy Parameters ---
# Number of candles to fetch for indicator calculation
CANDLES_COUNT = 200

# Multi-timeframe confirmation mode:
#   "strict"  = M15 AND H1 must confirm
#   "relaxed" = M15 OR H1 must confirm
MTF_MODE = "strict"

# --- Risk Management ---
LOT_SIZE = 0.01
MAX_POSITIONS = 3             # Max simultaneous positions
SL_ATR_MULTIPLIER = 1.5       # Stop loss = ATR * multiplier (fallback)
TP_RR_RATIO = 2.0             # Take profit = SL * ratio (risk/reward)
USE_BOLLINGER_SL = True       # Use Bollinger band width for SL calculation
TRAILING_STOP = True          # Enable trailing stop
TRAILING_STEP_POINTS = 50     # Trailing step in points

# --- Bot Behavior ---
CHECK_INTERVAL_SECONDS = 5    # How often to check for signals
MAGIC_NUMBER = 123456         # Unique identifier for bot orders
SLIPPAGE = 10                 # Max allowed slippage in points
