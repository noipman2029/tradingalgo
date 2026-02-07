"""
Technical indicators: Williams %R, Bollinger Bands, and SMA.
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


def sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Simple Moving Average on close price."""
    return df["close"].rolling(window=period).mean()


def sma_slope(sma_series: pd.Series, lookback: int = 3) -> float:
    """
    Return the slope direction of the SMA over the last `lookback` bars.
    Positive = rising, negative = falling.
    """
    if len(sma_series) < lookback + 1:
        return 0.0
    recent = sma_series.iloc[-lookback:]
    if recent.isna().any():
        return 0.0
    return float(recent.iloc[-1] - recent.iloc[0])


def compute_all_indicators(
    df: pd.DataFrame,
    williams_period: int = 14,
    bb_period: int = 20,
    bb_std: float = 2.0,
    sma_period: int = 20,
) -> pd.DataFrame:
    """
    Compute all indicators and add them as columns to the dataframe.
    Returns a copy with added columns:
        - williams_r
        - bb_upper, bb_middle, bb_lower
        - sma
    """
    result = df.copy()

    result["williams_r"] = williams_r(result, williams_period)

    upper, middle, lower = bollinger_bands(result, bb_period, bb_std)
    result["bb_upper"] = upper
    result["bb_middle"] = middle
    result["bb_lower"] = lower

    result["sma"] = sma(result, sma_period)

    return result
