import pandas as pd
from backtesting import Backtest

from strategies.base import BaseStrategy
from strategies.composite.regime_switch import RegimeSwitch
from strategies.registry import get_strategy, list_strategies
from strategies.trend.ma_cross import MaCross
from strategies.trend.trend_breakout import TrendBreakout
from strategies.trend.trend_holding_v3 import TrendHoldingV3
from strategies.mean_revert.bollinger_revert import BollingerRevert
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
    assert list_strategies() == [
        "bollinger_revert",
        "ma_cross",
        "regime_switch",
        "rsi_revert",
        "trend_breakout",
        "trend_holding_v3",
    ]
    assert get_strategy("bollinger_revert") is BollingerRevert
    assert get_strategy("ma_cross") is MaCross
    assert get_strategy("regime_switch") is RegimeSwitch
    assert get_strategy("rsi_revert") is RsiRevert
    assert get_strategy("trend_breakout") is TrendBreakout
    assert get_strategy("trend_holding_v3") is TrendHoldingV3


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


def test_trend_breakout_buys_on_confirmed_breakout():
    prices = [100.0] * 30
    prices += [101.0 + i * 2.0 for i in range(30)]
    prices += [prices[-1] - i * 1.0 for i in range(1, 20)]

    df = _make_ohlcv(prices)
    bt = Backtest(df, TrendBreakout, cash=10000, commission=0.001, finalize_trades=True)
    stats = bt.run(
        breakout_period=10,
        exit_period=5,
        trend_period=10,
        trend_slope_period=3,
        adx_period=5,
        adx_threshold=0,
        atr_period=5,
        atr_multiplier=2.0,
        volume_period=5,
        volume_multiplier=0.0,
        max_holding_bars=0,
        trailing_atr_multiplier=2.0,
        max_drawdown_pct=0,
    )

    assert stats["# Trades"] > 0


def test_trend_holding_v3_buys_and_holds_breakout():
    prices = [100.0 + i * 0.05 for i in range(80)]
    prices += [104.0 + i * 1.5 for i in range(40)]
    prices += [prices[-1] - i * 0.5 for i in range(1, 20)]

    df = _make_ohlcv(prices)
    bt = Backtest(
        df, TrendHoldingV3, cash=10000, commission=0.001, finalize_trades=True
    )
    stats = bt.run(
        trend_period=20,
        trend_slope_period=3,
        breakout_period=10,
        pullback_period=5,
        exit_period=10,
        atr_period=5,
        atr_multiplier=3.0,
        atr_percentile_period=20,
        min_atr_percentile=0.0,
        max_atr_percentile=1.0,
        use_breakout_entry=True,
        max_holding_bars=0,
        trailing_atr_multiplier=3.0,
        max_drawdown_pct=0,
    )

    assert stats["# Trades"] > 0


def test_bollinger_revert_buys_in_range_oversold_touch():
    prices = [100.0 + i * 0.1 for i in range(60)]
    prices += [105.0, 103.0, 101.0, 100.0, 101.0, 103.0, 105.0]
    prices += [105.0 + i * 0.1 for i in range(20)]

    df = _make_ohlcv(prices)
    bt = Backtest(df, BollingerRevert, cash=10000, commission=0.001, finalize_trades=True)
    stats = bt.run(
        rsi_period=5,
        oversold=45,
        exit_rsi=50,
        bb_period=10,
        bb_std=1.5,
        adx_period=5,
        max_adx=100,
        trend_period=10,
        trend_slope_period=3,
        atr_period=5,
        atr_multiplier=2.0,
        max_holding_bars=20,
        trailing_atr_multiplier=0,
        max_drawdown_pct=0,
    )

    assert stats["# Trades"] > 0


def test_regime_switch_buys_trend_breakout():
    prices = [100.0] * 30
    prices += [101.0 + i * 2.0 for i in range(30)]
    prices += [prices[-1] - i * 1.0 for i in range(1, 20)]

    df = _make_ohlcv(prices)
    bt = Backtest(df, RegimeSwitch, cash=10000, commission=0.001, finalize_trades=True)
    stats = bt.run(
        breakout_period=10,
        trend_exit_period=5,
        trend_period=10,
        trend_slope_period=3,
        adx_period=5,
        trend_adx_threshold=0,
        range_adx_threshold=0,
        atr_period=5,
        trend_atr_multiplier=2.0,
        mean_atr_multiplier=2.0,
        volume_period=5,
        volume_multiplier=0.0,
        rsi_period=5,
        oversold=30,
        exit_rsi=50,
        bb_period=10,
        bb_std=2.0,
        max_holding_bars=0,
        trailing_atr_multiplier=2.0,
        max_drawdown_pct=0,
    )

    assert stats["# Trades"] > 0


def test_regime_switch_buys_range_reversion():
    prices = [100.0 + i * 0.1 for i in range(60)]
    prices += [105.0, 103.0, 101.0, 100.0, 101.0, 103.0, 105.0]
    prices += [105.0 + i * 0.1 for i in range(20)]

    df = _make_ohlcv(prices)
    bt = Backtest(df, RegimeSwitch, cash=10000, commission=0.001, finalize_trades=True)
    stats = bt.run(
        breakout_period=10,
        trend_exit_period=5,
        trend_period=10,
        trend_slope_period=3,
        adx_period=5,
        trend_adx_threshold=1000,
        range_adx_threshold=100,
        atr_period=5,
        trend_atr_multiplier=2.0,
        mean_atr_multiplier=2.0,
        volume_period=5,
        volume_multiplier=0.0,
        rsi_period=5,
        oversold=45,
        exit_rsi=50,
        bb_period=10,
        bb_std=1.5,
        max_holding_bars=20,
        trailing_atr_multiplier=0,
        max_drawdown_pct=0,
    )

    assert stats["# Trades"] > 0
