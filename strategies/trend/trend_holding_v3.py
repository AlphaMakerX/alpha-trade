import math

import pandas as pd
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

from strategies.base import BaseStrategy


class TrendHoldingV3(BaseStrategy):
    """Long-only trend holding strategy for right-tail crypto moves."""

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
    max_holding_bars = 0
    trailing_atr_multiplier = 3.0

    @classmethod
    def bars_needed(cls) -> int:
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
        return {
            "trend_period": [150, 200, 300],
            "breakout_period": [55, 80, 120],
            "pullback_period": [21, 34, 55],
            "exit_period": [34, 55, 80],
            "atr_multiplier": [2.5, 3.0, 3.5],
            "min_atr_percentile": [0.10, 0.20, 0.30],
        }

    def init(self):
        self.init_risk()

        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)

        self.trend_ema = self.I(
            EMAIndicator(close, window=self.trend_period).ema_indicator,
        )
        self.pullback_ema = self.I(
            EMAIndicator(close, window=self.pullback_period).ema_indicator,
        )
        self.donchian_high = self.I(
            lambda: high.rolling(self.breakout_period).max().shift(1),
        )
        self.donchian_low = self.I(
            lambda: low.rolling(self.exit_period).min().shift(1),
        )
        atr = AverageTrueRange(high, low, close, window=self.atr_period)
        self.atr = self.I(atr.average_true_range)
        self.atr_percentile = self.I(
            lambda: atr.average_true_range()
            .rolling(self.atr_percentile_period)
            .rank(pct=True),
        )

    @staticmethod
    def _finite(*values) -> bool:
        return all(
            value is not None and math.isfinite(float(value)) for value in values
        )

    def _trend_confirmed(self, price: float) -> bool:
        trend_now = self.trend_ema[-1]
        trend_then = self.trend_ema[-self.trend_slope_period]
        return (
            self._finite(trend_now, trend_then)
            and price > trend_now
            and trend_now > trend_then
        )

    def _volatility_allowed(self) -> bool:
        percentile = self.atr_percentile[-1]
        return (
            self._finite(percentile, self.atr[-1])
            and self.min_atr_percentile <= percentile <= self.max_atr_percentile
        )

    def _entry_signal(self, price: float) -> bool:
        if not self._finite(
            self.donchian_high[-1],
            self.pullback_ema[-2],
            self.pullback_ema[-1],
        ):
            return False

        breakout = price > self.donchian_high[-1]
        pullback_reclaim = (
            self.data.Close[-2] <= self.pullback_ema[-2]
            and price > self.pullback_ema[-1]
            and price > self.data.High[-2]
        )
        return breakout or pullback_reclaim

    def _exit_signal(self, price: float) -> bool:
        if not self._finite(self.donchian_low[-1], self.pullback_ema[-1]):
            return False

        trend_now = self.trend_ema[-1]
        trend_then = self.trend_ema[-self.trend_slope_period]
        channel_break = price < self.donchian_low[-1]
        structure_broken = (
            self._finite(trend_now, trend_then)
            and price < self.pullback_ema[-1]
            and trend_now < trend_then
        )
        return channel_break or structure_broken

    def next(self):
        atr_value = self.atr[-1] if self._finite(self.atr[-1]) else None
        self.apply_risk_management(atr_value)

        price = self.data.Close[-1]

        if self.position and self._exit_signal(price):
            self.position.close()
            return

        if not self.can_enter():
            return

        if (
            self._trend_confirmed(price)
            and self._volatility_allowed()
            and self._entry_signal(price)
        ):
            sl = price - self.atr_multiplier * self.atr[-1]
            self.buy_with_risk(price, sl)
