from datetime import datetime, timedelta, timezone

import pandas as pd

from analysis import bias_eval
from indicators.bias import BIAS_LONG, BIAS_RANGE, BIAS_SHORT

_T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_df(closes, step_hours):
    rows = []
    for i, c in enumerate(closes):
        t = _T0 + timedelta(hours=step_hours * i)
        rows.append(
            {
                "open_time": t,
                "open": c - 1,
                "high": c + 2,
                "low": c - 2,
                "close": c,
                "volume": 1000.0,
            }
        )
    return pd.DataFrame(rows)


def _patch_klines(monkeypatch, base_closes, higher_closes):
    def fake_query(pair, timeframe, start=None, end=None):
        if timeframe == "1h":
            return _make_df(base_closes, 1)
        return _make_df(higher_closes, 4)

    monkeypatch.setattr(bias_eval, "query_klines", fake_query)


def test_bias_counts_sum_to_total(monkeypatch):
    closes = [100 + i for i in range(300)]
    _patch_klines(monkeypatch, closes, closes)

    result = bias_eval.evaluate_bias("ETH/USDT", None, None, [24])

    assert result.total_bars > 0
    assert sum(result.bias_counts.values()) == result.total_bars
    assert set(result.bias_counts) == {BIAS_LONG, BIAS_SHORT, BIAS_RANGE}


def test_uptrend_long_forward_return_positive(monkeypatch):
    closes = [100 + i for i in range(300)]  # 单调上升
    _patch_klines(monkeypatch, closes, closes)

    result = bias_eval.evaluate_bias("ETH/USDT", None, None, [24])

    long_stats = [s for s in result.stats if s.bias == BIAS_LONG and s.horizon == 24]
    assert long_stats and long_stats[0].count > 0
    # 持续上升中，偏多之后的前瞻收益应为正
    assert long_stats[0].mean_return_pct > 0


def test_forward_return_excludes_tail(monkeypatch):
    # 前瞻 N 根会让末尾 N 根没有 forward return，应被排除而非报错
    closes = [100 + i for i in range(120)]
    _patch_klines(monkeypatch, closes, closes)

    result = bias_eval.evaluate_bias("ETH/USDT", None, None, [24])
    total_stats = sum(s.count for s in result.stats if s.horizon == 24)
    assert total_stats == result.total_bars - 24
