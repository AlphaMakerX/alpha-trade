import pandas as pd
from ta.trend import SMAIndicator

from strategies.base import BaseStrategy


class MaCross(BaseStrategy):
    """双均线交叉策略。

    金叉（快线上穿慢线）买入，死叉（快线下穿慢线）卖出。
    """

    fast_period = 10
    slow_period = 30

    def init(self):
        close = pd.Series(self.data.Close)
        self.fast_ma = self.I(
            SMAIndicator(close, window=self.fast_period).sma_indicator,
        )
        self.slow_ma = self.I(
            SMAIndicator(close, window=self.slow_period).sma_indicator,
        )

    def next(self):
        # 金叉：快线上穿慢线 → 买入
        if self.fast_ma[-2] <= self.slow_ma[-2] and self.fast_ma[-1] > self.slow_ma[-1]:
            if not self.position:
                self.buy()
        # 死叉：快线下穿慢线 → 平仓
        elif self.fast_ma[-2] >= self.slow_ma[-2] and self.fast_ma[-1] < self.slow_ma[-1]:
            if self.position:
                self.position.close()
