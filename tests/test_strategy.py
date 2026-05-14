import pandas as pd
from backtesting import Backtest

from strategies.base import BaseStrategy
from strategies.registry import get_strategy, list_strategies
from strategies.trend.ma_cross import MaCross
from strategies.mean_revert.rsi_revert import RsiRevert


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


class RiskSizingStrategy(BaseStrategy):
    risk_per_trade = 0.01
    max_position_pct = 1.0
    cooldown_losses = 10
    cooldown_bars = 0
    max_holding_bars = 0
    trailing_atr_multiplier = 0
    max_drawdown_pct = 0

    def init(self):
        self.init_risk()

    def next(self):
        if not self.position and self.current_bar == 1:
            self.buy_with_risk(self.data.Close[-1], self.data.Close[-1] - 10)
        elif self.position and self.current_bar >= 3:
            self.position.close()


class MaxPositionStrategy(RiskSizingStrategy):
    risk_per_trade = 0.50
    max_position_pct = 0.10


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


def test_rsi_revert_oversold_buys():
    """RSI 超卖后反弹应产生交易。"""
    # 长期上涨建立高趋势线，然后急跌让 RSI 进入超卖但价格仍在趋势线上方
    prices = [50.0 + i * 2.0 for i in range(50)]  # 上涨到 148
    prices += [prices[-1] - i * 3.0 for i in range(1, 8)]  # 急跌 21 点（148→127）
    prices += [prices[-1] + i * 3 for i in range(1, 20)]  # 强反弹

    df = _make_ohlcv(prices)
    bt = Backtest(df, RsiRevert, cash=10000, commission=0.001)
    stats = bt.run(rsi_period=7, oversold=40, overbought=65, trend_period=40, atr_period=10, atr_multiplier=3.0)

    assert stats["# Trades"] > 0


def test_rsi_revert_no_trade_in_flat_market():
    """横盘场景：RSI 在中间区域，不应交易。"""
    prices = [100.0] * 80

    df = _make_ohlcv(prices)
    bt = Backtest(df, RsiRevert, cash=10000, commission=0.001)
    stats = bt.run(rsi_period=10, oversold=30, overbought=70, trend_period=20, atr_period=10, atr_multiplier=2.0)

    assert stats["# Trades"] == 0


def test_strategy_registry_lists_available_strategies():
    assert list_strategies() == ["ma_cross", "rsi_revert"]
    assert get_strategy("ma_cross") is MaCross
    assert get_strategy("rsi_revert") is RsiRevert


def test_strategy_registry_rejects_unknown_strategy():
    try:
        get_strategy("missing")
    except KeyError as exc:
        assert "ma_cross" in str(exc)
        assert "rsi_revert" in str(exc)
    else:
        raise AssertionError("Expected KeyError")


def test_risk_sizing_uses_stop_distance():
    df = _make_ohlcv([100.0] * 8)
    bt = Backtest(df, RiskSizingStrategy, cash=10000, commission=0, finalize_trades=True)

    stats = bt.run()

    assert stats["_trades"]["Size"].iloc[0] == 10


def test_risk_sizing_caps_max_position():
    df = _make_ohlcv([100.0] * 8)
    bt = Backtest(df, MaxPositionStrategy, cash=10000, commission=0, finalize_trades=True)

    stats = bt.run()

    assert stats["_trades"]["Size"].iloc[0] == 10
