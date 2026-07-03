import pandas as pd


def momentum(close: pd.Series, period: int) -> pd.Series:
    """时序动量因子：过去 period 根 K 线的累计收益 close_t / close_{t-period} - 1。

    只回看过去（shift 为正），无未来函数；前 period 根不足，返回 NaN。
    """
    return close / close.shift(period) - 1
