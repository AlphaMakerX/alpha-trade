import math

import pandas as pd
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

from engine.data import (
    HIGHER_TIMEFRAME_CLOSE_COLUMN,
    HIGHER_TIMEFRAME_TREND_EMA_COLUMN,
)
from strategies.base import BaseStrategy


class TrendHoldingV3(BaseStrategy):
    """Long-only trend holding strategy for right-tail crypto moves."""

    # 第 1 步：把策略参数显式写在类上，保证回测、评估、优化和 walk-forward
    # 使用同一套默认值。
    trend_period = 150
    trend_slope_period = 24
    breakout_period = 120
    pullback_period = 55
    exit_period = 55
    atr_period = 20
    atr_multiplier = 3.0
    atr_percentile_period = 200
    min_atr_percentile = 0.30
    max_atr_percentile = 0.95
    use_breakout_entry = False
    use_pullback_entry = True
    use_higher_timeframe_filter = False
    higher_timeframe_slope_bars = 24
    max_holding_bars = 0
    trailing_atr_multiplier = 3.0

    @classmethod
    def bars_needed(cls) -> int:
        # 第 2 步：等所有滚动指标都有足够历史数据后，再开始做交易判断。
        return (
            max(
                cls.trend_period + cls.trend_slope_period,
                cls.breakout_period,
                cls.pullback_period,
                cls.exit_period,
                cls.atr_period + cls.atr_percentile_period,
            )
            + 2
        )

    @classmethod
    def optimize_params(cls) -> dict:
        # 第 3 步：只暴露核心研究参数给网格搜索。仓位和风控参数继续由
        # BaseStrategy 和配置统一管理。
        return {
            "trend_period": [150, 200, 300],
            "breakout_period": [55, 80, 120],
            "pullback_period": [21, 34, 55],
            "exit_period": [34, 55, 80],
            "atr_multiplier": [2.5, 3.0, 3.5],
            "min_atr_percentile": [0.10, 0.20, 0.30],
        }

    def init(self):
        # 第 4 步：初始化通用风控，包括最大回撤、冷却、按风险定仓和 ATR
        # 跟踪止损等能力。
        self.init_risk()

        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)

        # 长期 EMA 用来定义主趋势。只有价格在长期 EMA 上方，且长期 EMA
        # 本身向上时，策略才考虑做多。
        self.trend_ema = self.I(
            EMAIndicator(close, window=self.trend_period).ema_indicator,
        )
        # 较短 EMA 用来判断趋势中的回踩重站，以及趋势结构是否被破坏。
        self.pullback_ema = self.I(
            EMAIndicator(close, window=self.pullback_period).ema_indicator,
        )
        # Donchian 高点使用之前 N 根 K 线，shift(1) 用来避免把当前 K 线
        # 纳入突破判断，防止未来函数。
        self.donchian_high = self.I(
            lambda: high.rolling(self.breakout_period).max().shift(1),
        )
        # Donchian 低点是结构性退出位。跌破它，说明价格失去了近期支撑。
        self.donchian_low = self.I(
            lambda: low.rolling(self.exit_period).min().shift(1),
        )
        # ATR 衡量当前波动幅度，同时用于初始止损距离、仓位计算、跟踪止损
        # 和波动率过滤。
        atr = AverageTrueRange(high, low, close, window=self.atr_period)
        self.atr = self.I(atr.average_true_range)
        # ATR 分位数用来过滤死水行情和过度恐慌的极端波动。
        self.atr_percentile = self.I(
            lambda: atr.average_true_range()
            .rolling(self.atr_percentile_period)
            .rank(pct=True),
        )
        if self.use_higher_timeframe_filter:
            self._init_higher_timeframe_filter()

    @staticmethod
    def _finite(*values) -> bool:
        # 第 5 步：过滤不完整的指标值，避免在 NaN 上做交易判断。
        return all(
            value is not None and math.isfinite(float(value)) for value in values
        )

    def _trend_confirmed(self, price: float) -> bool:
        # 第 6 步：同时用价格位置和 EMA 斜率确认上涨趋势。
        trend_now = self.trend_ema[-1]
        trend_then = self.trend_ema[-self.trend_slope_period]
        return (
            self._finite(trend_now, trend_then)
            and price > trend_now
            and trend_now > trend_then
        )

    def _volatility_allowed(self) -> bool:
        # 第 7 步：只在波动足够活跃、但又没有极端过热时交易。
        # 波动太低容易没有延续，波动太高容易追在衰竭点。
        percentile = self.atr_percentile[-1]
        return (
            self._finite(percentile, self.atr[-1])
            and self.min_atr_percentile <= percentile <= self.max_atr_percentile
        )

    def _init_higher_timeframe_filter(self):
        columns = self.data.df.columns
        missing_columns = [
            column
            for column in (
                HIGHER_TIMEFRAME_CLOSE_COLUMN,
                HIGHER_TIMEFRAME_TREND_EMA_COLUMN,
            )
            if column not in columns
        ]
        if missing_columns:
            joined = ", ".join(missing_columns)
            raise ValueError(f"缺少高周期过滤数据列: {joined}")

        self.higher_timeframe_close = self.I(
            lambda: self.data.df[HIGHER_TIMEFRAME_CLOSE_COLUMN],
        )
        self.higher_timeframe_trend_ema = self.I(
            lambda: self.data.df[HIGHER_TIMEFRAME_TREND_EMA_COLUMN],
        )

    def _higher_timeframe_confirmed(self) -> bool:
        if not self.use_higher_timeframe_filter:
            return True

        close = self.higher_timeframe_close[-1]
        ema_now = self.higher_timeframe_trend_ema[-1]
        ema_then = self.higher_timeframe_trend_ema[-self.higher_timeframe_slope_bars]
        return self._finite(close, ema_now, ema_then) and close > ema_now > ema_then

    def _entry_signal(self, price: float) -> bool:
        # 第 8 步：在已确认的趋势里，等待突破前高或回踩重站信号。
        if not self._finite(
            self.donchian_high[-1],
            self.pullback_ema[-2],
            self.pullback_ema[-1],
        ):
            return False

        # 突破入场：价格突破前一段时间的 Donchian 高点。
        breakout = price > self.donchian_high[-1]
        # 回踩重站：上一根收盘在短 EMA 下方或附近，当前价格重新站上短 EMA，
        # 并且突破上一根 K 线高点。
        pullback_reclaim = (
            self.data.Close[-2] <= self.pullback_ema[-2]
            and price > self.pullback_ema[-1]
            and price > self.data.High[-2]
        )
        return (self.use_breakout_entry and breakout) or (
            self.use_pullback_entry and pullback_reclaim
        )

    def _exit_signal(self, price: float) -> bool:
        # 第 9 步：趋势结构破坏时退出，不等慢速均线交叉确认后才卖。
        if not self._finite(self.donchian_low[-1], self.pullback_ema[-1]):
            return False

        trend_now = self.trend_ema[-1]
        trend_then = self.trend_ema[-self.trend_slope_period]
        # 通道跌破：价格跌破近期结构低点。
        channel_break = price < self.donchian_low[-1]
        # 结构破坏：价格跌破短 EMA，同时长期 EMA 已经开始向下。
        structure_broken = (
            self._finite(trend_now, trend_then)
            and price < self.pullback_ema[-1]
            and trend_now < trend_then
        )
        return channel_break or structure_broken

    def next(self):
        # 第 10 步：每根 K 线先执行通用风控。这里可能因为止损、跟踪止损、
        # 最大回撤或时间止损而平仓。
        atr_value = self.atr[-1] if self._finite(self.atr[-1]) else None
        self.apply_risk_management(atr_value)

        price = self.data.Close[-1]

        # 第 11 步：如果已经持仓，再检查策略自己的趋势退出信号。
        if self.position and self._exit_signal(price):
            self.position.close()
            return

        # 第 12 步：如果风控处于冷却或其它禁止开仓状态，就不再开新仓。
        if not self.can_enter():
            return

        # 第 13 步：只有趋势、波动率和入场形态都满足时才做多。
        # 初始止损距离会参与仓位计算。
        if (
            self._trend_confirmed(price)
            and self._higher_timeframe_confirmed()
            and self._volatility_allowed()
            and self._entry_signal(price)
        ):
            sl = price - self.atr_multiplier * self.atr[-1]
            self.buy_with_risk(price, sl)
