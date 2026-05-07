# src/fetchers/yfinance.py
import logging
import asyncio
import pandas as pd
import yfinance as yf
from typing import Optional, Dict, Any
from src.fetchers.base import AbstractFetcher

logger = logging.getLogger(__name__)

class YFBaseFetcher(AbstractFetcher):
    def __init__(self):
        super().__init__(name="YFinance")

    async def fetch(self, ticker: str, **kwargs) -> Optional[pd.DataFrame]:
        """Fetch daily historical data using yfinance."""
        period = kwargs.get("period", "1mo")
        # yfinance is synchronous, so we run it in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        try:
            df = await loop.run_in_executor(None, self._fetch_sync, ticker, period)
            return df
        except Exception as e:
            self.logger.error(f"YFinance fetch failed for {ticker}: {e}")
            return None

    def _fetch_sync(self, ticker: str, period: str) -> Optional[pd.DataFrame]:
        yf_ticker = yf.Ticker(ticker)
        df = yf_ticker.history(period=period)
        if df.empty:
            return None
        df = df.reset_index()
        df["ticker"] = ticker
        return df
