"""
Shared feature engineering module for the directional-probability pipeline.

This module is the SINGLE SOURCE OF TRUTH for all feature calculations used by
both the local training script (`scripts/train_local.py`) and the server-side
inference path (`ingestion/scheduler.py`).  Any change here must be reflected
in both environments to avoid training/serving skew.

Features
--------
* RSI (14)              – Relative Strength Index (Wilder smoothing)
* MACD (12, 26, 9)      – Moving Average Convergence/Divergence + histogram
* Bollinger Bands (20,2) – Upper / mid / lower bands and %B
* ATR (14)              – Average True Range (volatility proxy)
* Rolling volatility     – 20-day standard deviation of 1-day log returns
* Lagged log-returns     – 1, 2, 3, 5, 10-day

Target (training only)
----------------------
Binary label: 1 if close price 5 trading days in the future exceeds today's
close by at least the hurdle rate (default 1.5 %), else 0.  This separates
genuine momentum from the market's natural upward drift.
"""

import logging
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — keep in sync across train/inference
# ---------------------------------------------------------------------------
RSI_WINDOW = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_WINDOW = 20
BB_STD = 2
ATR_WINDOW = 14
ROLLING_VOL_WINDOW = 20
RETURN_LAGS: List[int] = [1, 2, 3, 5, 10]
FORWARD_WINDOW = 5  # look-ahead horizon for binary target (legacy default)
HURDLE = 0.015       # 1.5 % minimum move to count as "Up" (legacy default)

# ---------------------------------------------------------------------------
# Multi-horizon configuration
# ---------------------------------------------------------------------------
# Each entry maps a human-readable label to (trading_days, hurdle_rate).
# Hurdle rates scale roughly with sqrt(horizon) to account for the
# fact that price dispersion grows sub-linearly over time.
HORIZONS: dict[str, tuple[int, float]] = {
    "1d":  (1,   0.005),   # 0.5 %
    "1w":  (5,   0.015),   # 1.5 %
    "1mo": (21,  0.030),   # 3.0 %
    "6mo": (126, 0.075),   # 7.5 %
    "1y":  (252, 0.100),   # 10.0 %
}

# Ordered list of horizon keys (used throughout the codebase)
HORIZON_KEYS: list[str] = list(HORIZONS.keys())

# Ordered list of feature column names produced by `engineer_features`.
# Both training and inference MUST use this exact list for the model.
FEATURE_COLUMNS: List[str] = [
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "bb_pctb",
    "logret_1",
    "logret_2",
    "logret_3",
    "logret_5",
    "logret_10",
    "atr_14",
    "rolling_vol_20",
]


# ---------------------------------------------------------------------------
# Individual indicator helpers (pure pandas / numpy)
# ---------------------------------------------------------------------------

def _compute_rsi(close: pd.Series, window: int = RSI_WINDOW) -> pd.Series:
    """
    Relative Strength Index using Wilder's exponential smoothing.

    Parameters
    ----------
    close : pd.Series
        Closing price series.
    window : int
        Look-back period (default 14).

    Returns
    -------
    pd.Series
        RSI values in [0, 100].  First ``window`` values will be NaN.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothed averages (equivalent to EWM with alpha = 1/window)
    avg_gain = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _compute_macd(
    close: pd.Series,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD line, signal line, and histogram.

    Parameters
    ----------
    close : pd.Series
    fast, slow, signal : int
        EMA windows.

    Returns
    -------
    (macd_line, signal_line, histogram) — each a pd.Series.
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _compute_bollinger(
    close: pd.Series,
    window: int = BB_WINDOW,
    num_std: float = BB_STD,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands — upper, middle, lower, and %B.

    Parameters
    ----------
    close : pd.Series
    window : int
        Rolling window for the SMA (default 20).
    num_std : float
        Number of standard deviations for the bands (default 2).

    Returns
    -------
    (upper, middle, lower, pctb) — each a pd.Series.
    """
    middle = close.rolling(window=window).mean()
    rolling_std = close.rolling(window=window).std(ddof=1)
    upper = middle + num_std * rolling_std
    lower = middle - num_std * rolling_std
    # %B: position of close relative to the bands (0 = lower, 1 = upper)
    band_width = upper - lower
    pctb = (close - lower) / band_width.replace(0, np.nan)
    return upper, middle, lower, pctb


def _compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = ATR_WINDOW,
) -> pd.Series:
    """
    Average True Range — a volatility measure that accounts for gaps.

    Uses Wilder's exponential smoothing (same alpha as RSI).

    Parameters
    ----------
    high, low, close : pd.Series
        OHLC price components.
    window : int
        Smoothing period (default 14).

    Returns
    -------
    pd.Series
        ATR values.  First ``window`` rows will be NaN.
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    return atr


def _compute_rolling_volatility(
    close: pd.Series,
    window: int = ROLLING_VOL_WINDOW,
) -> pd.Series:
    """
    Rolling standard deviation of 1-day log returns.

    Parameters
    ----------
    close : pd.Series
    window : int
        Look-back window (default 20).

    Returns
    -------
    pd.Series
        Annualised daily vol (not annualised — raw rolling std).
    """
    logret = np.log(close / close.shift(1))
    return logret.rolling(window=window).std(ddof=1)


def _compute_lagged_returns(
    close: pd.Series, lags: list[int] = RETURN_LAGS
) -> pd.DataFrame:
    """
    Log-returns over several look-back periods.

    Parameters
    ----------
    close : pd.Series
    lags : list[int]
        List of day-offsets (e.g. [1, 2, 3, 5, 10]).

    Returns
    -------
    pd.DataFrame
        Columns named ``logret_{lag}``.
    """
    log_close = np.log(close)
    parts: dict[str, pd.Series] = {}
    for lag in lags:
        parts[f"logret_{lag}"] = log_close - log_close.shift(lag)
    return pd.DataFrame(parts, index=close.index)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all model features from a DataFrame of daily OHLCV data.

    The DataFrame **must** contain ``Close``, ``High``, and ``Low`` columns
    (case-sensitive).  The returned DataFrame has exactly the columns listed
    in ``FEATURE_COLUMNS`` and is indexed identically to the input.

    Parameters
    ----------
    df : pd.DataFrame
        Daily OHLCV data, sorted chronologically (oldest first).

    Returns
    -------
    pd.DataFrame
        Feature matrix.  Rows with insufficient look-back will contain NaN
        and should be dropped before training or inference.
    """
    close: pd.Series = df["Close"].astype(float)
    high: pd.Series = df["High"].astype(float)
    low: pd.Series = df["Low"].astype(float)

    # Decompose results from tuple-returning functions
    macd_line, macd_signal, macd_hist = _compute_macd(close)
    bb_upper, bb_middle, bb_lower, bb_pctb = _compute_bollinger(close)
    lag_df = _compute_lagged_returns(close)

    # Use .assign() for single-column features
    features = pd.DataFrame(index=df.index).assign(
        rsi_14=_compute_rsi(close),
        macd_line=macd_line,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
        bb_pctb=bb_pctb,
        atr_14=_compute_atr(high, low, close),
        rolling_vol_20=_compute_rolling_volatility(close),
    )

    # Combine with features that produce multiple columns at once
    features = pd.concat([features, lag_df], axis=1)

    # Enforce column order to guarantee model compatibility
    features = features[FEATURE_COLUMNS]

    logger.debug(
        "Engineered %d features for %d rows (%d NaN rows)",
        len(FEATURE_COLUMNS),
        len(features),
        features.isna().any(axis=1).sum(),
    )
    return features


def make_target(
    df: pd.DataFrame,
    horizon: int = FORWARD_WINDOW,
    hurdle: float = HURDLE,
) -> pd.Series:
    """
    Create the binary classification target with a hurdle rate.

    Label = 1 if ``Close[t + horizon] > Close[t] * (1 + hurdle)``, else 0.
    The hurdle separates genuine momentum from the market's natural upward
    drift (~0.04 % per day for the S&P 500).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain a ``Close`` column.
    horizon : int
        Number of trading days to look ahead (default 5).
    hurdle : float
        Minimum fractional price increase to count as "Up" (default 0.015
        i.e. 1.5 %).

    Returns
    -------
    pd.Series
        Binary labels.  The final ``horizon`` rows will be NaN (no future data).
    """
    close = df["Close"].astype(float)
    future_close = close.shift(-horizon)
    target = (future_close > close * (1.0 + hurdle)).astype(float)
    # Mark rows where we can't compute the target as NaN
    target.iloc[-horizon:] = np.nan
    target.name = "target"
    return target
