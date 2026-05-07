# src/features/indicators.py
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple

def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """Calculate Relative Strength Index."""
    if len(prices) < period + 1:
        return 50.0  # Default neutral RSI if not enough data
    
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def calculate_momentum(prices: pd.Series, period: int = 10) -> float:
    """Calculate Momentum (Rate of Change)."""
    if len(prices) < period + 1:
        return 0.0
    
    momentum = (prices.iloc[-1] / prices.iloc[-period-1]) - 1
    return float(momentum * 100)

def compute_inline_signals(ticker: str, timestamp: Any, ohlcv_data: Dict[str, Any], history: List[float]) -> List[Tuple[Any, str, str, float, str]]:
    """
    Compute RSI and Momentum signals for a single ticker given its history.
    Returns: List of tuples (timestamp, ticker, signal_type, value, metadata_json)
    """
    prices = pd.Series(history + [ohlcv_data['close']])
    
    rsi_val = calculate_rsi(prices)
    mom_val = calculate_momentum(prices)
    
    import json
    signals = [
        (timestamp, ticker, 'RSI', rsi_val, json.dumps({'period': 14})),
        (timestamp, ticker, 'MOMENTUM', mom_val, json.dumps({'period': 10}))
    ]
    return signals
