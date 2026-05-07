# src/flows/realtime_kr.py
import asyncio
import logging
from typing import List
from prefect import flow, task, get_run_logger
from src.fetchers.kis import KISFetcher
from src.db.repositories import repo
from src.features.indicators import compute_inline_signals

# Configure logging for Prefect
logger = logging.getLogger(__name__)

@task(name="process_ticker_realtime")
async def process_ticker_realtime(ticker: str, fetcher: KISFetcher):
    """Fetch, process, and prepare records for a single ticker."""
    # 1. Fetch data
    data = await fetcher.fetch_with_latency(ticker)
    if not data:
        return None, None

    # 2. Fetch history for indicators
    history = await repo.fetch_recent_history(ticker, limit=20)
    
    # 3. Compute signals
    signals = compute_inline_signals(ticker, data['timestamp'], data, history)
    
    # 4. Prepare records for DB
    tick_record = (
        data['timestamp'], data['ticker'], data['open'], 
        data['high'], data['low'], data['close'], 
        data['volume'], data['accumulated_value']
    )
    
    return tick_record, signals

@flow(name="realtime-kr-ingestion", log_prints=True)
async def realtime_kr_ingestion():
    """Main flow for KR market real-time ingestion."""
    log = get_run_logger()
    log.info("Starting KR realtime ingestion cycle...")
    
    # Get active KR tickers
    tickers = await repo.fetch_active_tickers(region="KR")
    if not tickers:
        # Fallback for testing if DB is empty
        tickers = ["005930", "000660"] # Samsung, SK Hynix
        log.warning(f"No active KR tickers found in DB. Using fallback: {tickers}")
    
    fetcher = KISFetcher()
    
    # Run concurrent tasks for each ticker
    results = await asyncio.gather(*[process_ticker_realtime(t, fetcher) for t in tickers])
    
    # Collect all records
    tick_records = []
    all_signals = []
    
    for tick, signals in results:
        if tick:
            tick_records.append(tick)
        if signals:
            all_signals.extend(signals)
            
    # Batch insert into DB
    if tick_records:
        await repo.insert_market_ticks(tick_records)
        log.info(f"Inserted {len(tick_records)} tick records.")
        
    if all_signals:
        await repo.insert_signals(all_signals)
        log.info(f"Inserted {len(all_signals)} signal records.")

    log.info("KR realtime ingestion cycle complete.")

if __name__ == "__main__":
    asyncio.run(realtime_kr_ingestion())
