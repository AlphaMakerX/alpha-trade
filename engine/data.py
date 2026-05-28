from datetime import datetime, timezone

import pandas as pd

from data.storage.postgres import query_klines

BASE_TIMEFRAME = "1h"
HIGHER_TIMEFRAME = "4h"
HIGHER_TIMEFRAME_CLOSE_COLUMN = "HigherTimeframeClose"
HIGHER_TIMEFRAME_TREND_EMA_COLUMN = "HigherTimeframeTrendEma"
HIGHER_TIMEFRAME_TREND_PERIOD = 200


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
    df = df.set_index("open_time").sort_index()
    if timeframe == BASE_TIMEFRAME:
        df = _append_higher_timeframe_columns(df, pair, start, end)
    return df


def _append_higher_timeframe_columns(
    df: pd.DataFrame,
    pair: str,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    higher = query_klines(
        pair,
        HIGHER_TIMEFRAME,
        parse_utc_date(start),
        parse_utc_date(end),
    )
    if higher.empty:
        return df

    higher = higher[["open_time", "close"]].copy()
    higher[HIGHER_TIMEFRAME_TREND_EMA_COLUMN] = (
        higher["close"]
        .ewm(
            span=HIGHER_TIMEFRAME_TREND_PERIOD,
            adjust=False,
            min_periods=HIGHER_TIMEFRAME_TREND_PERIOD,
        )
        .mean()
    )
    higher = higher.rename(columns={"close": HIGHER_TIMEFRAME_CLOSE_COLUMN})

    left = df.reset_index().sort_values("open_time")
    right = higher.sort_values("open_time")
    merged = pd.merge_asof(
        left,
        right,
        on="open_time",
        direction="backward",
    )
    return merged.set_index("open_time").sort_index()
