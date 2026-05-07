# src/fetchers/base.py
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)

class AbstractFetcher(ABC):
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    async def fetch(self, ticker: str, **kwargs) -> Any:
        """Fetch data for a single ticker."""
        pass

    async def fetch_with_latency(self, ticker: str, **kwargs) -> Any:
        """Fetch data and log latency."""
        start_time = time.perf_counter()
        try:
            result = await self.fetch(ticker, **kwargs)
            latency = time.perf_counter() - start_time
            self.logger.info(f"Fetched {ticker} from {self.name} in {latency:.4f}s")
            return result
        except Exception as e:
            latency = time.perf_counter() - start_time
            self.logger.error(f"Error fetching {ticker} from {self.name} after {latency:.4f}s: {e}")
            return None
