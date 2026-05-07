# src/db/repositories.py
import logging
import asyncpg
from typing import List, Tuple, Any
from src.config import settings

logger = logging.getLogger(__name__)

class MarketRepository:
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            logger.info("Initializing asyncpg connection pool...")
            self._pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
        return self._pool

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def insert_market_ticks(self, records: List[Tuple[Any, ...]]):
        """
        Efficiently batch insert KR market ticks using copy_records_to_table.
        records: List of tuples (timestamp, ticker, open, high, low, close, volume, accumulated_value)
        """
        if not records:
            return
            
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            try:
                # Use copy_records_to_table for high performance
                # Columns order must match the tuple order
                await conn.copy_records_to_table(
                    'market_ticks',
                    records=records,
                    columns=['timestamp', 'ticker', 'open', 'high', 'low', 'close', 'volume', 'accumulated_value']
                )
                logger.debug(f"Successfully inserted {len(records)} ticks into market_ticks")
            except Exception as e:
                logger.error(f"Failed to copy records to market_ticks: {e}")
                # Fallback to executemany if needed or re-raise
                raise

    async def upsert_market_daily(self, records: List[Tuple[Any, ...]]):
        """
        Upsert daily records. Since daily data might need updates (e.g., adj_close),
        we use executemany with ON CONFLICT.
        """
        if not records:
            return

        query = """
            INSERT INTO market_daily (timestamp, ticker, region, open, high, low, close, adj_close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (timestamp, ticker) DO UPDATE SET
                region = EXCLUDED.region,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                adj_close = EXCLUDED.adj_close,
                volume = EXCLUDED.volume;
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            try:
                await conn.executemany(query, records)
                logger.debug(f"Upserted {len(records)} daily records into market_daily")
            except Exception as e:
                logger.error(f"Failed to upsert market_daily: {e}")
                raise

    async def insert_signals(self, records: List[Tuple[Any, ...]]):
        """
        Batch insert signals.
        records: List of tuples (timestamp, ticker, signal_type, value, metadata_json)
        """
        if not records:
            return

        pool = await self.get_pool()
        async with pool.acquire() as conn:
            try:
                await conn.copy_records_to_table(
                    'signals',
                    records=records,
                    columns=['timestamp', 'ticker', 'signal_type', 'value', 'metadata']
                )
                logger.debug(f"Inserted {len(records)} signals into signals table")
            except Exception as e:
                logger.error(f"Failed to insert signals: {e}")
                raise

    async def fetch_active_tickers(self, region: str) -> List[str]:
        """Fetch list of active tickers for a given region."""
        # This assumes a 'tickers' table exists as in the original code.
        # If it doesn't exist in our migration, we should add it or use a default list.
        # For now, we'll try to query it.
        query = "SELECT symbol FROM tickers WHERE is_active = true AND market_region = $1"
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(query, region)
                return [r['symbol'] for r in rows]
            except Exception as e:
                logger.warning(f"Failed to fetch active tickers from DB: {e}. Using empty list.")
                return []

    async def fetch_recent_history(self, ticker: str, limit: int = 30) -> List[float]:
        """Fetch recent close prices for a ticker to compute indicators."""
        query = """
            SELECT close FROM market_ticks 
            WHERE ticker = $1 
            ORDER BY timestamp DESC 
            LIMIT $2
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(query, ticker, limit)
                # Reverse to get chronological order
                return [float(r['close']) for r in reversed(rows)]
            except Exception as e:
                logger.error(f"Failed to fetch history for {ticker}: {e}")
                return []

# Global repository instance
repo = MarketRepository()
