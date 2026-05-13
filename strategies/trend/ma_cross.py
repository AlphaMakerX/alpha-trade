import pandas as pd
from ta.trend import SMAIndicator

from strategies.base import BaseStrategy


class MaCross(BaseStrategy):
    """双均线交叉策略 + 趋势过滤 + 止损止盈。

    金叉（快线上穿慢线）且价格在趋势线上方时买入，
    死叉（快线下穿慢线）时平仓。
    """

    fast_period = 35
    slow_period = 50
    trend_period = 200
    stop_loss = 0.08
    take_profit = 0.05

    def init(self):
        close = pd.Series(self.data.Close)
        self.fast_ma = self.I(
            SMAIndicator(close, window=self.fast_period).sma_indicator,
        )
        self.slow_ma = self.I(
            SMAIndicator(close, window=self.slow_period).sma_indicator,
        )
        self.trend_ma = self.I(
            SMAIndicator(close, window=self.trend_period).sma_indicator,
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
                sl = price * (1 - self.stop_loss) if self.stop_loss else None
                tp = price * (1 + self.take_profit) if self.take_profit else None
                self.buy(sl=sl, tp=tp)

        # 死叉 → 平仓
        elif self.fast_ma[-2] >= self.slow_ma[-2] and self.fast_ma[-1] < self.slow_ma[-1]:
            if self.position:
                self.position.close()
