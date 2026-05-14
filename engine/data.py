from datetime import datetime, timezone

import pandas as pd

from data.storage.postgres import query_klines


def parse_utc_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def load_ohlcv(
    pair: str,
    timeframe: str,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    """Load Kline data from DB and convert it to Backtesting.py OHLCV format."""
    df = query_klines(
        pair,
        timeframe,
        parse_utc_date(start),
        parse_utc_date(end),
    )
    if df.empty:
        return df

    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    return df.set_index("open_time").sort_index()
