import math

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

from strategies.base import BaseStrategy


class BollingerRevert(BaseStrategy):
    """Regime-filtered mean reversion strategy.

    The strategy only buys oversold lower-band touches when ADX indicates a
    non-trending market and the long trend filter is not strongly bearish.
    """

    rsi_period = 14
    oversold = 35
    exit_rsi = 50
    bb_period = 20
    bb_std = 2.0
    adx_period = 14
    max_adx = 22
    trend_period = 200
    trend_slope_period = 24
    atr_period = 14
    atr_multiplier = 1.5

    @classmethod
    def bars_needed(cls) -> int:
        return max(
            cls.rsi_period,
            cls.bb_period,
            cls.adx_period,
            cls.trend_period + cls.trend_slope_period,
            cls.atr_period,
        ) + 2

    @classmethod
    def optimize_params(cls) -> dict:
        return {
            "rsi_period": [10, 14, 18],
            "oversold": [30, 35, 40],
            "exit_rsi": [50, 55],
            "bb_period": [20, 30],
            "bb_std": [1.8, 2.0, 2.2],
            "max_adx": [18, 22, 26],
            "atr_multiplier": [1.2, 1.5, 2.0],
        }

    def init(self):
        self.init_risk()

        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)

        bands = BollingerBands(close, window=self.bb_period, window_dev=self.bb_std)
        self.bb_low = self.I(bands.bollinger_lband)
        self.bb_mid = self.I(bands.bollinger_mavg)
        self.rsi = self.I(RSIIndicator(close, window=self.rsi_period).rsi)
        self.adx = self.I(ADXIndicator(high, low, close, window=self.adx_period).adx)
        self.trend_ema = self.I(EMAIndicator(close, window=self.trend_period).ema_indicator)
        self.atr = self.I(
            AverageTrueRange(high, low, close, window=self.atr_period).average_true_range,
        )

    @staticmethod
    def _finite(*values) -> bool:
        return all(value is not None and math.isfinite(float(value)) for value in values)

    def next(self):
        self.apply_risk_management(self.atr[-1])

        price = self.data.Close[-1]
        trend_now = self.trend_ema[-1]
        trend_then = self.trend_ema[-self.trend_slope_period]

        if self.position and (price >= self.bb_mid[-1] or self.rsi[-1] >= self.exit_rsi):
            self.position.close()
            return

        if not self._finite(
            self.bb_low[-1],
            self.bb_mid[-1],
            self.rsi[-1],
            self.adx[-1],
            trend_now,
            trend_then,
            self.atr[-1],
        ):
            return

        range_regime = self.adx[-1] <= self.max_adx
        not_strong_downtrend = price > trend_now or trend_now >= trend_then
        oversold_touch = price <= self.bb_low[-1] and self.rsi[-1] <= self.oversold

        if range_regime and not_strong_downtrend and oversold_touch and self.can_enter():
            sl = price - self.atr_multiplier * self.atr[-1]
            self.buy_with_risk(price, sl)
