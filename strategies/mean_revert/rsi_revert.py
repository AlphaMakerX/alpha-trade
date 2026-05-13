import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from ta.volatility import AverageTrueRange

from strategies.base import BaseStrategy


class RsiRevert(BaseStrategy):
    """RSI 均值回归策略 + 趋势过滤 + ATR 动态止损。

    RSI 进入超卖区且价格在趋势线上方时买入（预期反弹），
    RSI 进入超买区时平仓。
    """

    rsi_period = 14
    oversold = 30
    overbought = 70
    trend_period = 100
    atr_period = 16
    atr_multiplier = 1.5

    @classmethod
    def bars_needed(cls) -> int:
        return max(cls.rsi_period, cls.trend_period) + 2

    @classmethod
    def optimize_params(cls) -> dict:
        return {
            "rsi_period": range(10, 22, 2),
            "oversold": range(20, 40, 5),
            "overbought": range(60, 85, 5),
            "trend_period": range(50, 250, 50),
            "atr_period": range(10, 22, 2),
            "atr_multiplier": [i / 10 for i in range(15, 40, 5)],
        }

    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)

        self.rsi = self.I(
            RSIIndicator(close, window=self.rsi_period).rsi,
        )
        self.trend_ma = self.I(
            SMAIndicator(close, window=self.trend_period).sma_indicator,
        )
        self.atr = self.I(
            AverageTrueRange(high, low, close, window=self.atr_period).average_true_range,
        )

    def next(self):
        price = self.data.Close[-1]
        above_trend = price > self.trend_ma[-1]

        # RSI 超卖 + 趋势确认 → 买入
        if self.rsi[-1] < self.oversold and above_trend and not self.position:
            sl = price - self.atr_multiplier * self.atr[-1]
            self.buy(sl=sl)

        # RSI 超买 → 平仓
        elif self.rsi[-1] > self.overbought and self.position:
            self.position.close()
