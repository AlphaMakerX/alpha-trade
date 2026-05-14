import math

import pandas as pd
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange

from strategies.base import BaseStrategy


class TrendBreakout(BaseStrategy):
    """Trend-following breakout strategy with volatility-aware risk controls.

    The strategy enters long positions when price breaks the prior Donchian high
    while trend, trend strength, and volume filters agree.
    """

    breakout_period = 55
    exit_period = 20
    trend_period = 200
    trend_slope_period = 24
    adx_period = 14
    adx_threshold = 18
    atr_period = 20
    atr_multiplier = 2.5
    volume_period = 20
    volume_multiplier = 1.0

    @classmethod
    def bars_needed(cls) -> int:
        return max(
            cls.breakout_period,
            cls.exit_period,
            cls.trend_period + cls.trend_slope_period,
            cls.adx_period,
            cls.atr_period,
            cls.volume_period,
        ) + 2

    @classmethod
    def optimize_params(cls) -> dict:
        return {
            "breakout_period": [40, 55, 80],
            "exit_period": [15, 20, 30],
            "trend_period": [100, 200],
            "adx_threshold": [15, 20, 25],
            "atr_multiplier": [2.0, 2.5, 3.0],
            "volume_multiplier": [0.8, 1.0, 1.2],
        }

    def init(self):
        self.init_risk()

        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)
        volume = pd.Series(self.data.Volume)

        self.donchian_high = self.I(
            lambda: high.rolling(self.breakout_period).max().shift(1),
        )
        self.exit_ema = self.I(
            EMAIndicator(close, window=self.exit_period).ema_indicator,
        )
        self.trend_ema = self.I(
            EMAIndicator(close, window=self.trend_period).ema_indicator,
        )
        self.adx = self.I(
            ADXIndicator(high, low, close, window=self.adx_period).adx,
        )
        self.atr = self.I(
            AverageTrueRange(high, low, close, window=self.atr_period).average_true_range,
        )
        self.volume_ma = self.I(
            lambda: volume.rolling(self.volume_period).mean(),
        )

    @staticmethod
    def _finite(*values) -> bool:
        return all(value is not None and math.isfinite(float(value)) for value in values)

    def next(self):
        self.apply_risk_management(self.atr[-1])

        price = self.data.Close[-1]
        trend_now = self.trend_ema[-1]
        trend_then = self.trend_ema[-self.trend_slope_period]
        trend_up = price > trend_now and trend_now > trend_then
        strength_ok = self.adx[-1] >= self.adx_threshold
        volume_ok = self.data.Volume[-1] >= self.volume_ma[-1] * self.volume_multiplier
        breakout = price > self.donchian_high[-1]

        if self.position and price < self.exit_ema[-1]:
            self.position.close()
            return

        if not self._finite(
            self.donchian_high[-1],
            self.exit_ema[-1],
            trend_now,
            trend_then,
            self.adx[-1],
            self.atr[-1],
            self.volume_ma[-1],
        ):
            return

        if breakout and trend_up and strength_ok and volume_ok and self.can_enter():
            sl = price - self.atr_multiplier * self.atr[-1]
            self.buy_with_risk(price, sl)
