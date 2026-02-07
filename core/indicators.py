"""
Technical indicators: Williams %R and Bollinger Bands.
Pure numpy/pandas implementations (no TA-Lib dependency).
"""

import numpy as np
import pandas as pd


def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Williams %R.

    Formula: %R = (Highest High - Close) / (Highest High - Lowest Low) * (-100)

    Returns values in range [-100, 0]:
        -100 to -80 : oversold
        -20 to 0    : overbought
    """
    high_roll = df["high"].rolling(window=period).max()
    low_roll = df["low"].rolling(window=period).min()

    hl_range = high_roll - low_roll
    # Avoid division by zero
    hl_range = hl_range.replace(0, np.nan)

    wr = (high_roll - df["close"]) / hl_range * (-100.0)
    return wr


def bollinger_bands(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Bollinger Bands.

    Returns: (upper_band, middle_band, lower_band)
    """
    middle = df["close"].rolling(window=period).mean()
    std = df["close"].rolling(window=period).std()

    upper = middle + std_dev * std
    lower = middle - std_dev * std

    return upper, middle, lower


def bollinger_bandwidth(upper: pd.Series, lower: pd.Series,
                        middle: pd.Series) -> pd.Series:
    """
    Bollinger Bandwidth = (Upper - Lower) / Middle * 100
    Useful for dynamic SL/TP calculation.
    """
    return (upper - lower) / middle * 100.0


def compute_all_indicators(
    df: pd.DataFrame,
    williams_period: int = 14,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> pd.DataFrame:
    """
    Compute all indicators and add them as columns to the dataframe.
    Returns a copy with added columns:
        - williams_r
        - bb_upper, bb_middle, bb_lower
        - bb_bandwidth
    """
    result = df.copy()

    result["williams_r"] = williams_r(result, williams_period)

    upper, middle, lower = bollinger_bands(result, bb_period, bb_std)
    result["bb_upper"] = upper
    result["bb_middle"] = middle
    result["bb_lower"] = lower
    result["bb_bandwidth"] = bollinger_bandwidth(upper, lower, middle)

    return result
