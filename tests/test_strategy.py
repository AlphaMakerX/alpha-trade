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
    """金叉+死叉场景：用小参数验证，应产生至少一笔完整交易。"""
    prices = [100.0 - i * 0.5 for i in range(35)]  # 下跌
    prices += [prices[-1] + i * 1.5 for i in range(1, 40)]  # 反弹
    prices += [prices[-1] - i * 1.5 for i in range(1, 40)]  # 再跌

    df = _make_ohlcv(prices)
    # 用小 trend_period 让测试数据量够用，关闭止损止盈
    bt = Backtest(df, MaCross, cash=10000, commission=0.001)
    stats = bt.run(fast_period=5, slow_period=15, trend_period=20, stop_loss=0, take_profit=0)

    assert stats["# Trades"] > 0


def test_ma_cross_no_trade_in_flat_market():
    """横盘场景：价格不变，均线重合，不应产生交易。"""
    prices = [100.0] * 80

    df = _make_ohlcv(prices)
    bt = Backtest(df, MaCross, cash=10000, commission=0.001)
    stats = bt.run(fast_period=5, slow_period=15, trend_period=20, stop_loss=0, take_profit=0)

    assert stats["# Trades"] == 0


def test_ma_cross_trend_filter_blocks_downtrend():
    """趋势过滤：价格在趋势线下方时，金叉不应买入。"""
    # 持续下跌中有小反弹（金叉），但整体在趋势线下方
    prices = [200.0 - i * 0.8 for i in range(60)]  # 持续下跌
    prices += [prices[-1] + i * 0.3 for i in range(1, 20)]  # 小反弹（不足以突破趋势线）
    prices += [prices[-1] - i * 0.5 for i in range(1, 30)]  # 继续跌

    df = _make_ohlcv(prices)
    bt = Backtest(df, MaCross, cash=10000, commission=0.001)
    stats = bt.run(fast_period=5, slow_period=15, trend_period=30, stop_loss=0, take_profit=0)

    # 趋势过滤应阻止在下跌趋势中开仓
    assert stats["# Trades"] == 0
