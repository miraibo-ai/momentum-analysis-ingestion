"""
Data fetcher module using yfinance.
Fetches market data for stocks.
"""
 
import logging
from datetime import datetime, timezone

import httpx
import pandas as pd
import pytz
import yfinance as yf

logger = logging.getLogger(__name__)

class DataFetcher:
    """Fetches market data using yfinance."""
    def __init__(self, ticker: str):
        """
        Initialize DataFetcher.
        Args:
            ticker: Stock ticker symbol
        """
        self.ticker = ticker
        self.yf_ticker = yf.Ticker(ticker)
    def fetch_realtime_data(self) -> dict | None:
        """
        Fetch current/realtime data for the ticker.
        Returns:
            Dictionary with current price data or None if failed
        """
        try:
            # Get latest intraday data
            data = self.yf_ticker.history(period='1d', interval='1m')
            if data.empty:
                logger.warning(f"No realtime data available for {self.ticker}")
                return None
            latest = data.iloc[-1]
            # yfinance returns a timezone-aware index (e.g., America/New_York).
            # We convert it to UTC immediately to be safe for Postgres.
            timestamp = data.index[-1].to_pydatetime()
            if timestamp.tzinfo is None:
                # If yfinance somehow returns a naive timestamp, force it to UTC
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                # Convert whatever timezone yfinance gave us (e.g. EST) to UTC
                timestamp = timestamp.astimezone(timezone.utc)
            return {
                'ticker': self.ticker,
                'timestamp': timestamp,  # <--- Now safely UTC
                'open': float(latest['Open']),
                'high': float(latest['High']),
                'low': float(latest['Low']),
                'close': float(latest['Close']),
                'volume': int(latest['Volume'])
            }
        except Exception as e:
            logger.error(f"Failed to fetch realtime data: {e}")
            return None
    def fetch_daily_data(self, period: str = "1y") -> pd.DataFrame | None:
        """
        Fetch daily historical data.
        Args:
            period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        Returns:
            DataFrame with daily price data or None if failed
        """
        try:
            data = self.yf_ticker.history(period=period)
            if data.empty:
                logger.warning(f"No daily data available for {self.ticker}")
                return None
            # Reset index to make date a column
            data = data.reset_index()
            data['ticker'] = self.ticker
            return data
        except Exception as e:
            logger.error(f"Failed to fetch daily data for {self.ticker}: {e}")
            return None
    def get_info(self) -> dict | None:
        """
        Get ticker information.
        Returns:
            Dictionary with ticker information or None if failed
        """
        try:
            return self.yf_ticker.info
        except Exception as e:
            logger.error(f"Failed to get info for {self.ticker}: {e}")
            return None
class KISFetcher:
    def __init__(self, api_key: str, api_secret: str, token: str):
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": api_key,
            "appsecret": api_secret,
            "tr_id": "FHKST03010200" # TR_ID strictly returns 1-minute data
        }
        self.kst_tz = pytz.timezone('Asia/Seoul')
    def fetch_minute_data(self, ticker: str, interval_min: int = 1) -> pd.DataFrame:
        try:
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
            # 1. Enforce KST for the request regardless of NAS server time
            current_kst_time = datetime.now(self.kst_tz).strftime("%H%M%00")
            params = {
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_HOUR_1": current_kst_time,
                "FID_PW_DATA_INCU_YN": "N"
            }
            response = httpx.get(url, headers=self.headers, params=params, timeout=10.0)
            response.raise_for_status()
            candles = response.json().get("output2", [])
            df = pd.DataFrame(candles)
            if df.empty:
                logger.warning(f"No minute data returned from KIS for {ticker}")
                return df
            # Parse strings and apply KST timezone
            df['datetime_str'] = df['stck_bsop_date'] + df['stck_cntg_hour']
            df['timestamp'] = pd.to_datetime(df['datetime_str'], 
                                             format='%Y%m%d%H%M%S').dt.tz_localize('Asia/Seoul')
            df = df.rename(columns={
                'stck_oprc': 'open_price',
                'stck_hgpr': 'high_price',
                'stck_lwpr': 'low_price',
                'stck_prpr': 'close_price',
                'cntg_vol': 'volume',
                'acml_tr_pbmn': 'accumulated_value'
            })
            numeric_cols = ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'accumulated_value']
            df[numeric_cols] = df[numeric_cols].astype(float)
            # 2. Resample the 1-minute API data into the requested timeframe (e.g., 3-min or 5-min)
            df = df.set_index('timestamp').sort_index()
            df = df.resample(f'{interval_min}min').agg({
                'open_price': 'first',
                'high_price': 'max',
                'low_price': 'min',
                'close_price': 'last',
                'volume': 'sum',
                'accumulated_value': 'sum'
            }).dropna().reset_index()
            # 3. Convert to UTC to match DataFetcher (yfinance) logic before Postgres insertion
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            df['ticker'] = ticker
            df['interval_min'] = interval_min
            return df[['ticker', 'interval_min', 'timestamp'] + numeric_cols]
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching KIS data for {ticker}: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Unexpected error processing KIS data for {ticker}: {e}")
            return pd.DataFrame()