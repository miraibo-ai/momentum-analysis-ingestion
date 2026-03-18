import yfinance as yf
from dotenv import load_dotenv
from prefect import flow, get_run_logger, task

from common.database import check_health, get_connection

load_dotenv()

DEFAULT_TICKER = "AAPL"

@task
def fetch_price_data(ticker):
    logger = get_run_logger()
    data = yf.download(ticker, period="5d")
    if data.empty:
        return None
    row = data
    logger.info(str(row))
    # return {
    #     "ticker": ticker,
    #     "date": row.name.date(),
    #     "open": row["Open"],
    #     "high": row["High"],
    #     "low": row["Low"],
    #     "close": row["Close"],
    #     "adj_close": row.get("Adj Close", row["Close"]),
    #     "volume": int(row["Volume"]),
    #     "region": "US"
    # }
    return None

@task
def save_to_db(price_data):
    if not price_data:
        return
    # with get_connection() as conn, conn.cursor() as cur:
    #     cur.execute("""
    #             INSERT INTO price_daily (ticker, region, date, open, high, low, close, adj_close, volume)
    #             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    #             ON CONFLICT (ticker, date) DO NOTHING;
    # """, (
    #     price_data["ticker"],
    #     price_data["region"],
    #     price_data["date"],
    #     price_data["open"],
    #     price_data["high"],
    #     price_data["low"],
    #     price_data["close"],
    #     price_data["adj_close"],
    #     price_data["volume"]
    # ))
    # conn.commit()
    check_health()  # Ensure DB is healthy before attempting to save

@flow
def daily_batch():
    price_data = fetch_price_data(DEFAULT_TICKER)
    save_to_db(price_data)
    return None


if __name__ == "__main__":
    daily_batch()
