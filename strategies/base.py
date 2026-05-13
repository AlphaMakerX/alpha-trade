from backtesting import Strategy


class BaseStrategy(Strategy):
    """策略基类，继承 Backtesting.py 的 Strategy。

    子类需实现 init() 和 next()。
    """
