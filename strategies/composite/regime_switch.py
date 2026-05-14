import math

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

from strategies.base import BaseStrategy


class RegimeSwitch(BaseStrategy):
    """Single-position strategy that switches between trend and range logic."""

    breakout_period = 80
    trend_exit_period = 20
    trend_period = 200
    trend_slope_period = 24
    adx_period = 14
    trend_adx_threshold = 26
    range_adx_threshold = 18
    atr_period = 20
    trend_atr_multiplier = 2.5
    mean_atr_multiplier = 1.5
    volume_period = 20
    volume_multiplier = 1.0
    rsi_period = 14
    oversold = 35
    exit_rsi = 50
    bb_period = 20
    bb_std = 1.8

    @classmethod
    def bars_needed(cls) -> int:
        return max(
            cls.breakout_period,
            cls.trend_exit_period,
            cls.trend_period + cls.trend_slope_period,
            cls.adx_period,
            cls.atr_period,
            cls.volume_period,
            cls.rsi_period,
            cls.bb_period,
        ) + 2

    @classmethod
    def optimize_params(cls) -> dict:
        return {
            "breakout_period": [40, 55, 80],
            "trend_adx_threshold": [18, 22, 26],
            "range_adx_threshold": [16, 18, 22],
            "oversold": [30, 35, 40],
            "bb_std": [1.8, 2.0, 2.2],
            "trend_atr_multiplier": [2.0, 2.5, 3.0],
            "mean_atr_multiplier": [1.2, 1.5, 2.0],
        }

    def init(self):
        self.init_risk()
        self._entry_mode = None

        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)
        volume = pd.Series(self.data.Volume)

        self.donchian_high = self.I(
            lambda: high.rolling(self.breakout_period).max().shift(1),
        )
        self.trend_exit_ema = self.I(
            EMAIndicator(close, window=self.trend_exit_period).ema_indicator,
        )
        self.trend_ema = self.I(
            EMAIndicator(close, window=self.trend_period).ema_indicator,
        )
        self.adx = self.I(ADXIndicator(high, low, close, window=self.adx_period).adx)
        self.atr = self.I(
            AverageTrueRange(high, low, close, window=self.atr_period).average_true_range,
        )
        self.volume_ma = self.I(lambda: volume.rolling(self.volume_period).mean())

        bands = BollingerBands(close, window=self.bb_period, window_dev=self.bb_std)
        self.bb_low = self.I(bands.bollinger_lband)
        self.bb_mid = self.I(bands.bollinger_mavg)
        self.rsi = self.I(RSIIndicator(close, window=self.rsi_period).rsi)

    @staticmethod
    def _finite(*values) -> bool:
        return all(value is not None and math.isfinite(float(value)) for value in values)

    def _trend_entry(self, price: float, trend_now: float, trend_then: float) -> bool:
        if not self._finite(
            self.donchian_high[-1],
            trend_now,
            trend_then,
            self.adx[-1],
            self.atr[-1],
            self.volume_ma[-1],
        ):
            return False

        trend_up = price > trend_now and trend_now > trend_then
        strength_ok = self.adx[-1] >= self.trend_adx_threshold
        volume_ok = self.data.Volume[-1] >= self.volume_ma[-1] * self.volume_multiplier
        breakout = price > self.donchian_high[-1]
        return breakout and trend_up and strength_ok and volume_ok

    def _range_entry(self, price: float, trend_now: float, trend_then: float) -> bool:
        if not self._finite(
            self.bb_low[-1],
            self.bb_mid[-1],
            self.rsi[-1],
            self.adx[-1],
            trend_now,
            trend_then,
            self.atr[-1],
        ):
            return False

        range_regime = self.adx[-1] <= self.range_adx_threshold
        not_strong_downtrend = price > trend_now or trend_now >= trend_then
        oversold_touch = price <= self.bb_low[-1] and self.rsi[-1] <= self.oversold
        return range_regime and not_strong_downtrend and oversold_touch

    def _close_active_position(self, price: float, trend_now: float, trend_then: float) -> bool:
        if not self.position:
            self._entry_mode = None
            return False

        if self._entry_mode == "trend":
            trend_reversed = (
                self._finite(trend_now, trend_then)
                and price < trend_now
                and trend_now < trend_then
            )
            exit_cross = self._finite(self.trend_exit_ema[-1]) and price < self.trend_exit_ema[-1]
            if trend_reversed or exit_cross:
                self.position.close()
                self._entry_mode = None
                return True

        if self._entry_mode == "mean":
            mean_recovered = self._finite(self.bb_mid[-1], self.rsi[-1]) and (
                price >= self.bb_mid[-1] or self.rsi[-1] >= self.exit_rsi
            )
            if mean_recovered:
                self.position.close()
                self._entry_mode = None
                return True

        return False

    def next(self):
        atr_value = self.atr[-1] if self._finite(self.atr[-1]) else None
        self.apply_risk_management(atr_value)

        price = self.data.Close[-1]
        trend_now = self.trend_ema[-1]
        trend_then = self.trend_ema[-self.trend_slope_period]

        if not self.position:
            self._entry_mode = None

        if self._close_active_position(price, trend_now, trend_then):
            return

        if not self.can_enter():
            return

        if self._trend_entry(price, trend_now, trend_then):
            sl = price - self.trend_atr_multiplier * self.atr[-1]
            if self.buy_with_risk(price, sl) is not None:
                self._entry_mode = "trend"
            return

        if self._range_entry(price, trend_now, trend_then):
            sl = price - self.mean_atr_multiplier * self.atr[-1]
            if self.buy_with_risk(price, sl) is not None:
                self._entry_mode = "mean"
