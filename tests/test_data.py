from datetime import datetime, timezone

import pandas as pd

from data.feeds import binance
from data.feeds.cleaner import clean_klines

_T1 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
_T2 = datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc)
_T3 = datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc)


def test_clean_removes_duplicates():
    df = pd.DataFrame(
        {
            "open_time": [_T1, _T1, _T2],
            "open": [100, 101, 102],
            "high": [110, 111, 112],
            "low": [90, 91, 92],
            "close": [105, 106, 107],
            "volume": [1000, 1001, 1002],
        }
    )
    result = clean_klines(df)
    assert len(result) == 2


def test_clean_removes_zero_price():
    df = pd.DataFrame(
        {
            "open_time": [_T1, _T2, _T3],
            "open": [100, 0, 102],
            "high": [110, 110, 112],
            "low": [90, 90, 92],
            "close": [105, 105, 107],
            "volume": [1000, 1000, 1002],
        }
    )
    result = clean_klines(df)
    assert len(result) == 2
    assert _T2 not in result["open_time"].values


def test_clean_empty_dataframe():
    df = pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
    result = clean_klines(df)
    assert result.empty


def test_clean_sorted_by_open_time():
    df = pd.DataFrame(
        {
            "open_time": [_T3, _T1, _T2],
            "open": [100, 101, 102],
            "high": [110, 111, 112],
            "low": [90, 91, 92],
            "close": [105, 106, 107],
            "volume": [1000, 1001, 1002],
        }
    )
    result = clean_klines(df)
    assert list(result["open_time"]) == [_T1, _T2, _T3]


def test_fetch_all_backfills_when_existing_range_has_gaps(monkeypatch):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 3, tzinfo=timezone.utc)
    latest = datetime(2024, 1, 3, tzinfo=timezone.utc)
    calls = []

    monkeypatch.setattr(binance, "get_latest_open_time", lambda pair, timeframe: latest)
    monkeypatch.setattr(binance, "count_klines", lambda pair, timeframe, start, end: 1)
    monkeypatch.setattr(binance.time, "sleep", lambda seconds: None)

    def fake_fetch_klines(pair, timeframe, since, limit=1000, end=None):
        calls.append(since)
        return []

    monkeypatch.setattr(binance, "fetch_klines", fake_fetch_klines)

    total = binance.fetch_all_klines("ETH/USDT", "1h", start, end)

    assert total == 0
    assert calls == [start]


def test_fetch_all_skips_complete_existing_range(monkeypatch):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 3, tzinfo=timezone.utc)
    latest = datetime(2024, 1, 3, tzinfo=timezone.utc)
    calls = []

    monkeypatch.setattr(binance, "get_latest_open_time", lambda pair, timeframe: latest)
    monkeypatch.setattr(binance, "count_klines", lambda pair, timeframe, start, end: 49)
    monkeypatch.setattr(binance.time, "sleep", lambda seconds: None)

    def fake_fetch_klines(pair, timeframe, since, limit=1000, end=None):
        calls.append(since)
        return []

    monkeypatch.setattr(binance, "fetch_klines", fake_fetch_klines)

    total = binance.fetch_all_klines("ETH/USDT", "1h", start, end)

    assert total == 0
    assert calls == []
