from datetime import datetime, timezone

import pandas as pd

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
