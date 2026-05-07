# src/fetchers/kis.py
import asyncio
import logging
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from src.config import settings
from src.fetchers.base import AbstractFetcher

logger = logging.getLogger(__name__)

class KISTokenManager:
    """Async-safe manager for KIS OAuth tokens."""
    def __init__(self):
        self._token: Optional[str] = None
        self._expiry: Optional[datetime] = None
        self._lock = asyncio.Lock()

    async def get_token(self, client: httpx.AsyncClient) -> str:
        async with self._lock:
            if self._token and self._expiry and datetime.now() < self._expiry - timedelta(minutes=5):
                return self._token
            
            logger.info("Refreshing KIS OAuth token...")
            url = f"{settings.KIS_REST_BASE_URL}/oauth2/tokenP"
            payload = {
                "grant_type": "client_credentials",
                "appkey": settings.KIS_APP_KEY,
                "appsecret": settings.KIS_APP_SECRET
            }
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            self._token = data["access_token"]
            # Typically valid for 24 hours, but we parse it or set a safe default
            expires_in = int(data.get("expires_in", 86400))
            self._expiry = datetime.now() + timedelta(seconds=expires_in)
            logger.info(f"New KIS token acquired. Expires at {self._expiry}")
            return self._token

token_manager = KISTokenManager()

class KISFetcher(AbstractFetcher):
    def __init__(self):
        super().__init__(name="KIS")
        self.base_url = settings.KIS_REST_BASE_URL

    async def fetch(self, ticker: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Implementation of AbstractFetcher's fetch. For KIS, we mostly want minute data."""
        return await self.fetch_minute_data(ticker)

    async def fetch_minute_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch 1-minute OHLCV data for KR market."""
        async with httpx.AsyncClient(http2=True) as client:
            try:
                token = await token_manager.get_token(client)
                url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
                
                # Using KST for the request
                now_kst = datetime.now() # Simplified, should ideally be KST
                time_str = now_kst.strftime("%H%M%00")
                
                headers = {
                    "Content-Type": "application/json",
                    "authorization": f"Bearer {token}",
                    "appkey": settings.KIS_APP_KEY,
                    "appsecret": settings.KIS_APP_SECRET,
                    "tr_id": "FHKST03010200"
                }
                params = {
                    "FID_ETC_CLS_CODE": "",
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": ticker,
                    "FID_INPUT_HOUR_1": time_str,
                    "FID_PW_DATA_INCU_YN": "N"
                }
                
                resp = await client.get(url, headers=headers, params=params, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                
                candles = data.get("output2", [])
                if not candles:
                    return None
                    
                # We return the latest candle for real-time ingestion
                latest = candles[0] 
                
                # Parsing timestamp (stck_bsop_date: YYYYMMDD, stck_cntg_hour: HHMMSS)
                ts_str = f"{latest['stck_bsop_date']}{latest['stck_cntg_hour']}"
                ts = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
                
                return {
                    "timestamp": ts,
                    "ticker": ticker,
                    "open": float(latest["stck_oprc"]),
                    "high": float(latest["stck_hgpr"]),
                    "low": float(latest["stck_lwpr"]),
                    "close": float(latest["stck_prpr"]),
                    "volume": int(latest["cntg_vol"]),
                    "accumulated_value": float(latest["acml_tr_pbmn"])
                }
            except Exception as e:
                self.logger.error(f"KIS fetch failed for {ticker}: {e}")
                return None
