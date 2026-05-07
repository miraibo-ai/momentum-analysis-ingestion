-- 001_initial_timescale_schema.sql
-- Initialize TimescaleDB hypertables for Market Momentum Ingestion

-- Extension setup (Assumes user has SUPERUSER or has pre-installed TimescaleDB)
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 0. Tickers Metadata
CREATE TABLE IF NOT EXISTS tickers (
    symbol           TEXT              PRIMARY KEY,
    market_region    TEXT              NOT NULL, -- 'KR', 'JP', 'US', etc.
    is_active        BOOLEAN           DEFAULT TRUE,
    name             TEXT,
    created_at       TIMESTAMPTZ       DEFAULT NOW()
);

-- 1. KR Market Real-time Ticks (1-minute intervals or raw ticks)
CREATE TABLE IF NOT EXISTS market_ticks (
    timestamp        TIMESTAMPTZ       NOT NULL,
    ticker           TEXT              NOT NULL,
    open             DOUBLE PRECISION,
    high             DOUBLE PRECISION,
    low              DOUBLE PRECISION,
    close            DOUBLE PRECISION,
    volume           BIGINT,
    accumulated_value DOUBLE PRECISION,
    PRIMARY KEY (timestamp, ticker)
);

-- Convert to hypertable with 1-day chunks for KR ticks
SELECT create_hypertable('market_ticks', 'timestamp', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);

-- 2. JP/Global Market Daily OHLCV
CREATE TABLE IF NOT EXISTS market_daily (
    timestamp        TIMESTAMPTZ       NOT NULL,
    ticker           TEXT              NOT NULL,
    region           TEXT              NOT NULL,
    open             DOUBLE PRECISION,
    high             DOUBLE PRECISION,
    low              DOUBLE PRECISION,
    close            DOUBLE PRECISION,
    adj_close        DOUBLE PRECISION,
    volume           BIGINT,
    PRIMARY KEY (timestamp, ticker)
);

-- Convert to hypertable with 30-day chunks for daily data
SELECT create_hypertable('market_daily', 'timestamp', chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);

-- 3. Momentum & RSI Signals
CREATE TABLE IF NOT EXISTS signals (
    timestamp        TIMESTAMPTZ       NOT NULL,
    ticker           TEXT              NOT NULL,
    signal_type      TEXT              NOT NULL, -- e.g., 'RSI', 'MOMENTUM'
    value            DOUBLE PRECISION  NOT NULL,
    metadata         JSONB,                     -- For flexible signal context
    PRIMARY KEY (timestamp, ticker, signal_type)
);

-- Convert to hypertable with 7-day chunks for signals
SELECT create_hypertable('signals', 'timestamp', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);

-- Indices for common lookups
CREATE INDEX IF NOT EXISTS idx_market_ticks_ticker ON market_ticks (ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_market_daily_ticker ON market_daily (ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals (ticker, timestamp DESC);
