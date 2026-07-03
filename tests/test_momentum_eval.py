from datetime import datetime, timedelta, timezone

import pandas as pd

from analysis import momentum_eval
from indicators.momentum import momentum

_T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _make_df(closes):
    rows = []
    for i, c in enumerate(closes):
        rows.append({"open_time": _T0 + timedelta(hours=i), "close": float(c)})
    return pd.DataFrame(rows)


def _patch_klines(monkeypatch, closes):
    monkeypatch.setattr(
        momentum_eval, "query_klines", lambda *a, **k: _make_df(closes)
    )


# ── 因子函数 ──


def test_momentum_value():
    close = pd.Series([100.0, 110.0, 121.0])
    mom = momentum(close, 1)
    assert pd.isna(mom.iloc[0])  # 前 period 根不足
    assert mom.iloc[1] == 110 / 100 - 1
    assert mom.iloc[2] == 121 / 110 - 1


def test_momentum_only_looks_back():
    # 改动未来的收盘价不应影响当前及更早的因子值（无未来函数）
    base = momentum(pd.Series([100.0, 101.0, 102.0, 103.0]), 1)
    changed = momentum(pd.Series([100.0, 101.0, 102.0, 999.0]), 1)
    assert base.iloc[:3].equals(changed.iloc[:3])


# ── 评估框架 ──


def test_deterministic(monkeypatch):
    closes = [100 + i * 0.5 for i in range(400)]
    _patch_klines(monkeypatch, closes)
    r1 = momentum_eval.evaluate_momentum("ETH/USDT", None, None, [120], [24], 5)
    _patch_klines(monkeypatch, closes)
    r2 = momentum_eval.evaluate_momentum("ETH/USDT", None, None, [120], [24], 5)
    assert r1.stats[0].ic == r2.stats[0].ic


def test_quantile_counts_cover_valid_sample(monkeypatch):
    closes = [100 + i * 0.5 for i in range(400)]
    _patch_klines(monkeypatch, closes)
    result = momentum_eval.evaluate_momentum("ETH/USDT", None, None, [120], [24], 5)
    fs = result.stats[0]
    assert len(fs.quantiles) == 5
    # 分层样本合计 = 同时有因子值和前瞻收益的样本数（末尾 24 根无前瞻被排除）
    total = sum(q.count for q in fs.quantiles)
    assert total == result.total_bars - 120 - 24


def test_uptrend_positive_ic(monkeypatch):
    # 单调上升行情下动量与前瞻收益同向下降，IC 应为正
    closes = [100 + i for i in range(400)]
    _patch_klines(monkeypatch, closes)
    result = momentum_eval.evaluate_momentum("ETH/USDT", None, None, [120], [24], 5)
    assert result.stats[0].ic > 0


def test_baseline_present(monkeypatch):
    closes = [100 + i * 0.5 for i in range(400)]
    _patch_klines(monkeypatch, closes)
    result = momentum_eval.evaluate_momentum("ETH/USDT", None, None, [120], [24, 72], 5)
    assert set(result.baseline) == {24, 72}
