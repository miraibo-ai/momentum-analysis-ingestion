from prefect import flow, task
import yfinance as yf
import psycopg
from dotenv import load_dotenv
import os

load_dotenv()

DEFAULT_TICKER = "AAPL"

@task
def fetch_price_data(ticker):
    data = yf.download(ticker, period="1d")
    if data.empty:
        return None
    row = data.iloc[0]
    return {
        "ticker": ticker,
        "date": row.name.date(),
        "open": row["Open"],
        "high": row["High"],
        "low": row["Low"],
        "close": row["Close"],
        "adj_close": row["Adj Close"],
        "volume": int(row["Volume"]),
        "region": "US"
    }

@task
def save_to_db(price_data):
    if not price_data:
        return
    conn = psycopg.connect("dbname=your_db user=your_user password=your_password host=localhost")
    cur = conn.cursor()
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
    cur.close()
    conn.close()

@flow
def daily_batch():
    price_data = fetch_price_data(DEFAULT_TICKER)
    save_to_db(price_data)

if __name__ == "__main__":
    daily_batch()
