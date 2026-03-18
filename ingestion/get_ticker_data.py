import yfinance as yf
from dotenv import load_dotenv
from prefect import flow, get_run_logger, task

from common.database import check_health, get_connection

load_dotenv()

DEFAULT_TICKER = "QQQ"

@task
def fetch_price_data(ticker):
    logger = get_run_logger()
    data = yf.download(ticker, period="5d")
    if data.empty:
        return None
    row = data.iloc[0]
    logger.info(str(row))
    def get_value(val):
        if hasattr(val, 'item'):
            return val.item()
        elif hasattr(val, 'iloc'):
            return val.iloc[0]
        else:
            return val

    return {
        "ticker": ticker,
        "date": row.name.date(),
        "open": get_value(row["Open"]),
        "high": get_value(row["High"]),
        "low": get_value(row["Low"]),
        "close": get_value(row["Close"]),
        "adj_close": get_value(row.get("Adj Close", row["Close"])),
        "volume": int(get_value(row["Volume"])),
        "region": "US"
    }

@task
def save_to_db(price_data):
    if not price_data:
        return
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""
                INSERT INTO price_daily (ticker, region, date, open, high, low, close, adj_close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, date) DO NOTHING;
    """, (
        price_data["ticker"],
        price_data["region"],
        price_data["date"],
        price_data["open"],
        price_data["high"],
        price_data["low"],
        price_data["close"],
        price_data["adj_close"],
        price_data["volume"]
    ))
    conn.commit()


@flow
def daily_batch():
    price_data = fetch_price_data(DEFAULT_TICKER)
    save_to_db(price_data)
    return None


if __name__ == "__main__":
    daily_batch()
