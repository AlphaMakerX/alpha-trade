import pandas as pd
from ta.trend import SMAIndicator
from ta.volatility import AverageTrueRange

from strategies.base import BaseStrategy


class MaCross(BaseStrategy):
    """双均线交叉策略 + 趋势过滤 + ATR 动态止损。

    金叉（快线上穿慢线）且价格在趋势线上方时买入，
    死叉（快线下穿慢线）时平仓。止损根据 ATR 动态调整。
    """

    fast_period = 35
    slow_period = 50
    trend_period = 200
    atr_period = 14
    atr_multiplier = 2.0

    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)

        self.fast_ma = self.I(
            SMAIndicator(close, window=self.fast_period).sma_indicator,
        )
        self.slow_ma = self.I(
            SMAIndicator(close, window=self.slow_period).sma_indicator,
        )
        self.trend_ma = self.I(
            SMAIndicator(close, window=self.trend_period).sma_indicator,
        )
        self.atr = self.I(
            AverageTrueRange(high, low, close, window=self.atr_period).average_true_range,
        )

    def next(self):
        price = self.data.Close[-1]

        # 金叉 + 趋势过滤：快线上穿慢线，且价格在趋势线上方
        if (
            self.fast_ma[-2] <= self.slow_ma[-2]
            and self.fast_ma[-1] > self.slow_ma[-1]
            and price > self.trend_ma[-1]
        ):
            if not self.position:
                sl = price - self.atr_multiplier * self.atr[-1]
                self.buy(sl=sl)

        # 死叉 → 平仓
        elif self.fast_ma[-2] >= self.slow_ma[-2] and self.fast_ma[-1] < self.slow_ma[-1]:
            if self.position:
                self.position.close()
