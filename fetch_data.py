#!/usr/bin/env python3

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pandas as pd
import yfinance as yf

DATA_DIR = Path("./data")
DEFAULT_TICKERS = ["SNDK", "QQQ", "NVDA"]
MAX_HISTORY_DAYS = 30
RATE_LIMIT_PER_MIN = 5
CHUNK_DAYS = 7


class RateLimiter:
    def __init__(self, max_per_minute: int):
        self._max = max_per_minute
        self._timestamps: list[float] = []

    def throttle(self):
        now = time.monotonic()
        self._timestamps = [t for t in self._timestamps if now - t < 60]
        if len(self._timestamps) >= self._max:
            wait = 60 - (now - self._timestamps[0]) + 0.1
            print(f"  Rate limit reached, waiting {wait:.1f}s...")
            time.sleep(wait)
        self._timestamps.append(time.monotonic())


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _compute_vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    tp_vol = typical_price * df["Volume"]
    if df.index.tz is not None:
        day = df.index.tz_convert("America/New_York").floor("D")
    else:
        day = df.index.floor("D")
    cum_tp_vol = tp_vol.groupby(day).cumsum()
    cum_vol = df["Volume"].groupby(day).cumsum()
    return cum_tp_vol / cum_vol


def load_records(ticker: str) -> dict[str, list]:
    filepath = DATA_DIR / f"{ticker}.records"
    if not filepath.exists():
        return {}
    records: dict[str, list] = {}
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sep = line.index(": ")
            records[line[:sep]] = json.loads(line[sep + 2:])
    return records


def save_records(ticker: str, records: dict[str, list], mode: str = "w"):
    DATA_DIR.mkdir(exist_ok=True)
    filepath = DATA_DIR / f"{ticker}.records"
    with open(filepath, mode) as f:
        for date_str in sorted(records.keys()):
            f.write(f"{date_str}: {json.dumps(records[date_str])}\n")


def fetch_chunks(
    ticker: str, start: datetime, end: datetime, rate_limiter: RateLimiter
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=CHUNK_DAYS), end)
        rate_limiter.throttle()
        print(f"  [{ticker}] fetching {current.date()} ~ {chunk_end.date()}")
        df = yf.download(
            ticker,
            start=current.strftime("%Y-%m-%d"),
            end=chunk_end.strftime("%Y-%m-%d"),
            interval="1m",
            progress=False,
            auto_adjust=True,
        )
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            frames.append(df)
        current = chunk_end

    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames).sort_index()
    return combined[~combined.index.duplicated()]


def build_indicator_df(new_df: pd.DataFrame, prefix_closes: list[float]) -> pd.DataFrame:
    n = len(new_df)
    if prefix_closes:
        all_closes = pd.Series(prefix_closes + list(new_df["Close"].values))
    else:
        all_closes = pd.Series(list(new_df["Close"].values))

    rsi = _compute_rsi(all_closes)
    ema10 = _compute_ema(all_closes, 10)
    ema20 = _compute_ema(all_closes, 20)

    result = new_df.copy()
    result["RSI_14"] = rsi.iloc[-n:].values
    result["EMA_10"] = ema10.iloc[-n:].values
    result["EMA_20"] = ema20.iloc[-n:].values
    result["VWAP"] = _compute_vwap(new_df).values
    return result


def df_to_records(df: pd.DataFrame) -> dict[str, list]:
    records: dict[str, list] = {}
    for ts, row in df.iterrows():
        if df.index.tz is not None:
            local_ts = ts.tz_convert("America/New_York")
        else:
            local_ts = ts
        date_str = local_ts.strftime("%Y-%m-%d")

        def _val(v: float):
            return None if pd.isna(v) else round(float(v), 4)

        bar = {
            "time": local_ts.strftime("%H:%M"),
            "open": _val(row["Open"]),
            "high": _val(row["High"]),
            "low": _val(row["Low"]),
            "close": _val(row["Close"]),
            "volume": int(row["Volume"]),
            "RSI_14": _val(row["RSI_14"]),
            "EMA_10": _val(row["EMA_10"]),
            "EMA_20": _val(row["EMA_20"]),
            "VWAP": _val(row["VWAP"]),
        }
        records.setdefault(date_str, []).append(bar)
    return records


def process_ticker(ticker: str, init_mode: bool, rate_limiter: RateLimiter):
    print(f"\n=== {ticker} ===")
    filepath = DATA_DIR / f"{ticker}.records"

    if init_mode:
        if filepath.exists():
            filepath.unlink()
            print("  Deleted existing data.")
        existing_data: dict[str, list] = {}
        start = datetime.now() - timedelta(days=MAX_HISTORY_DAYS)
    else:
        existing_data = load_records(ticker)
        last_date = max(existing_data.keys()) if existing_data else None
        if last_date:
            print(f"  Last recorded date: {last_date}")
            start = datetime.strptime(last_date, "%Y-%m-%d")
            existing_data.pop(last_date)
        else:
            start = datetime.now() - timedelta(days=MAX_HISTORY_DAYS)

    end = datetime.now() + timedelta(days=1)

    new_df = fetch_chunks(ticker, start, end, rate_limiter)
    if new_df.empty:
        print("  No data fetched.")
        return

    prefix_closes: list[float] = [
        bar["close"]
        for date_str in sorted(existing_data.keys())
        for bar in existing_data[date_str]
        if bar["close"] is not None
    ]

    result_df = build_indicator_df(new_df, prefix_closes)
    new_records = df_to_records(result_df)

    if existing_data:
        save_records(ticker, existing_data, mode="w")
        save_records(ticker, new_records, mode="a")
    else:
        save_records(ticker, new_records, mode="w")

    print(f"  Saved {len(new_records)} trading days ({len(new_df)} bars).")


def main():
    parser = argparse.ArgumentParser(description="Fetch US stock 1-min historical data")
    parser.add_argument("tickers", nargs="*", default=DEFAULT_TICKERS, metavar="TICKER")
    parser.add_argument(
        "--init",
        action="store_true",
        help="Delete existing data and fetch full history (up to 90 days)",
    )
    args = parser.parse_args()

    rate_limiter = RateLimiter(RATE_LIMIT_PER_MIN)
    for ticker in args.tickers:
        process_ticker(ticker.upper(), args.init, rate_limiter)

    print("\nDone.")


if __name__ == "__main__":
    main()
