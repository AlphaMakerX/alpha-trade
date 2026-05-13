from dataclasses import dataclass

import pandas as pd
from ta.trend import SMAIndicator
from ta.volatility import AverageTrueRange

from strategies.base import BaseStrategy


SIGNAL_BUY = "buy"
SIGNAL_SELL = "sell"
SIGNAL_WATCH = "watch"
SIGNAL_HOLD = "hold"


@dataclass
class SignalResult:
    signal: str
    price: float
    fast_ma: float
    slow_ma: float
    trend_ma: float
    atr: float
    stop_loss: float | None


class MaCross(BaseStrategy):
    """双均线交叉策略 + 趋势过滤 + ATR 动态止损。

    金叉（快线上穿慢线）且价格在趋势线上方时买入，
    死叉（快线下穿慢线）时平仓。止损根据 ATR 动态调整。
    """

    fast_period = 45
    slow_period = 200
    trend_period = 100
    atr_period = 16
    atr_multiplier = 1.5

    @classmethod
    def optimize_params(cls) -> dict:
        return {
            "fast_period": range(10, 55, 5),
            "slow_period": range(30, 210, 10),
            "trend_period": range(100, 350, 50),
            "atr_period": range(10, 22, 2),
            "atr_multiplier": [i / 10 for i in range(15, 40, 5)],
        }

    @classmethod
    def compute_signal(cls, df: pd.DataFrame) -> SignalResult:
        """基于 DataFrame 计算当前信号，复用策略参数和判断逻辑。"""
        close, high, low = df["close"], df["high"], df["low"]

        fast = SMAIndicator(close, window=cls.fast_period).sma_indicator()
        slow = SMAIndicator(close, window=cls.slow_period).sma_indicator()
        trend = SMAIndicator(close, window=cls.trend_period).sma_indicator()
        atr = AverageTrueRange(high, low, close, window=cls.atr_period).average_true_range()

        price = close.iloc[-1]
        golden_cross = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]
        death_cross = fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]
        above_trend = price > trend.iloc[-1]

        if golden_cross and above_trend:
            signal = SIGNAL_BUY
            sl = price - cls.atr_multiplier * atr.iloc[-1]
        elif death_cross:
            signal = SIGNAL_SELL
            sl = None
        elif golden_cross and not above_trend:
            signal = SIGNAL_WATCH
            sl = None
        else:
            signal = SIGNAL_HOLD
            sl = None

        return SignalResult(
            signal=signal,
            price=price,
            fast_ma=fast.iloc[-1],
            slow_ma=slow.iloc[-1],
            trend_ma=trend.iloc[-1],
            atr=atr.iloc[-1],
            stop_loss=sl,
        )

    @classmethod
    def bars_needed(cls) -> int:
        return max(cls.fast_period, cls.slow_period, cls.trend_period) + 2

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
        golden_cross = self.fast_ma[-2] <= self.slow_ma[-2] and self.fast_ma[-1] > self.slow_ma[-1]
        death_cross = self.fast_ma[-2] >= self.slow_ma[-2] and self.fast_ma[-1] < self.slow_ma[-1]
        above_trend = price > self.trend_ma[-1]

        if golden_cross and above_trend and not self.position:
            sl = price - self.atr_multiplier * self.atr[-1]
            self.buy(sl=sl)
        elif death_cross and self.position:
            self.position.close()
