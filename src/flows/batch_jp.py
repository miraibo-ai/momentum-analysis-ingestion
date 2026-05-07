# src/flows/batch_jp.py
import asyncio
import logging
import pandas as pd
from typing import List
from prefect import flow, task, get_run_logger
from src.fetchers.yfinance import YFBaseFetcher
from src.db.repositories import repo
from src.features.indicators import calculate_rsi, calculate_momentum
import json

logger = logging.getLogger(__name__)

@task(name="process_ticker_batch")
async def process_ticker_batch(ticker: str, region: str, fetcher: YFBaseFetcher):
    """Fetch daily data and prepare records."""
    df = await fetcher.fetch_with_latency(ticker, period="3mo")
    if df is None or df.empty:
        return None, None

    # Prepare daily records
    daily_records = []
    signal_records = []
    
    for _, row in df.iterrows():
        ts = row['Date'].to_pydatetime()
        daily_records.append((
            ts, ticker, region, 
            float(row['Open']), float(row['High']), 
            float(row['Low']), float(row['Close']), 
            float(row['Close']), int(row['Volume'])
        ))
    
    # Compute signals for the latest date
    latest_close = df['Close']
    rsi = calculate_rsi(latest_close)
    mom = calculate_momentum(latest_close)
    
    latest_ts = df.iloc[-1]['Date'].to_pydatetime()
    signal_records.append((latest_ts, ticker, 'RSI', rsi, json.dumps({'period': 14})))
    signal_records.append((latest_ts, ticker, 'MOMENTUM', mom, json.dumps({'period': 10})))
    
    return daily_records, signal_records

@flow(name="batch-jp-ingestion", log_prints=True)
async def batch_jp_ingestion():
    """Main flow for JP/Global market batch ingestion."""
    log = get_run_logger()
    log.info("Starting JP/Global batch ingestion cycle...")
    
    tickers = await repo.fetch_active_tickers(region="JP")
    if not tickers:
        # Fallback for testing
        tickers = ["7203.T", "9984.T"] # Toyota, SoftBank
        log.warning(f"No active JP tickers found in DB. Using fallback: {tickers}")
        
    fetcher = YFBaseFetcher()
    
    # We can run these in parallel but maybe more conservatively than real-time
    results = await asyncio.gather(*[process_ticker_batch(t, "JP", fetcher) for t in tickers])
    
    all_daily = []
    all_signals = []
    
    for daily, signals in results:
        if daily:
            all_daily.extend(daily)
        if signals:
            all_signals.extend(signals)
            
    if all_daily:
        await repo.upsert_market_daily(all_daily)
        log.info(f"Upserted {len(all_daily)} daily records.")
        
    if all_signals:
        await repo.insert_signals(all_signals)
        log.info(f"Inserted {len(all_signals)} signal records.")

    log.info("JP/Global batch ingestion cycle complete.")

if __name__ == "__main__":
    asyncio.run(batch_jp_ingestion())
