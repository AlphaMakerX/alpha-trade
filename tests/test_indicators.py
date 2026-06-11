from datetime import datetime, timedelta, timezone

import pandas as pd

from indicators.snapshot import RECENT_BARS, compute_snapshot

_T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_df(closes, step_hours):
    rows = []
    for i, close in enumerate(closes):
        open_time = _T0 + timedelta(hours=step_hours * i)
        rows.append(
            {
                "open_time": open_time,
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000.0,
            }
        )
    return pd.DataFrame(rows)


def test_uptrend_snapshot_alignment():
    closes = [100 + i for i in range(260)]  # 持续上升
    base_df = make_df(closes, step_hours=1)
    higher_df = make_df([100 + i for i in range(260)], step_hours=4)

    s = compute_snapshot(base_df, higher_df, "ETH/USDT", "1h")

    assert s.price == closes[-1]
    assert s.ma_fast > s.ma_slow  # 上升趋势下快线在慢线上方
    assert s.rsi > 50
    assert s.higher_trend_ema is not None
    assert s.bb_lower < s.price


def test_recent_bars_capped():
    closes = [100 + i for i in range(260)]
    base_df = make_df(closes, step_hours=1)
    higher_df = make_df(closes, step_hours=4)

    s = compute_snapshot(base_df, higher_df, "ETH/USDT", "1h")
    assert len(s.recent_bars) == RECENT_BARS
    assert s.recent_bars[-1].close == closes[-1]


def test_higher_ema_none_when_insufficient():
    closes = [100 + i for i in range(60)]
    base_df = make_df(closes, step_hours=1)
    higher_df = make_df([100 + i for i in range(50)], step_hours=4)  # < 200 根

    s = compute_snapshot(base_df, higher_df, "ETH/USDT", "1h")
    assert s.higher_trend_ema is None
