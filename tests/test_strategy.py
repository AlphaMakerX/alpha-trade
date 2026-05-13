import pandas as pd
from backtesting import Backtest

from strategies.trend.ma_cross import MaCross


def _make_ohlcv(prices: list[float]) -> pd.DataFrame:
    """用收盘价序列构造 OHLCV DataFrame。"""
    df = pd.DataFrame({
        "Open": prices,
        "High": [p * 1.01 for p in prices],
        "Low": [p * 0.99 for p in prices],
        "Close": prices,
        "Volume": [1000.0] * len(prices),
    })
    df.index = pd.date_range("2024-01-01", periods=len(prices), freq="h")
    return df


def test_ma_cross_golden_cross_buys():
    """金叉+死叉场景：先跌后涨再跌，应产生至少一笔完整交易。"""
    prices = [100.0 - i * 0.5 for i in range(35)]
    prices += [prices[-1] + i * 1.5 for i in range(1, 40)]
    prices += [prices[-1] - i * 1.5 for i in range(1, 40)]

    df = _make_ohlcv(prices)
    bt = Backtest(df, MaCross, cash=10000, commission=0.001)
    stats = bt.run(fast_period=5, slow_period=15, trend_period=20, atr_period=10, atr_multiplier=2.0)

    assert stats["# Trades"] > 0


def test_ma_cross_no_trade_in_flat_market():
    """横盘场景：价格不变，均线重合，不应产生交易。"""
    prices = [100.0] * 80

    df = _make_ohlcv(prices)
    bt = Backtest(df, MaCross, cash=10000, commission=0.001)
    stats = bt.run(fast_period=5, slow_period=15, trend_period=20, atr_period=10, atr_multiplier=2.0)

    assert stats["# Trades"] == 0


def test_ma_cross_trend_filter_blocks_downtrend():
    """趋势过滤：价格在趋势线下方时，金叉不应买入。"""
    prices = [200.0 - i * 0.8 for i in range(60)]
    prices += [prices[-1] + i * 0.3 for i in range(1, 20)]
    prices += [prices[-1] - i * 0.5 for i in range(1, 30)]

    df = _make_ohlcv(prices)
    bt = Backtest(df, MaCross, cash=10000, commission=0.001)
    stats = bt.run(fast_period=5, slow_period=15, trend_period=30, atr_period=10, atr_multiplier=2.0)

    assert stats["# Trades"] == 0
