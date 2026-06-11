from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

MA_FAST_PERIOD = 20
MA_SLOW_PERIOD = 50
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ATR_PERIOD = 14
VOLUME_MA_PERIOD = 20
HIGHER_TREND_EMA_PERIOD = 200
RECENT_BARS = 36
RECENT_RANGE_BARS = 48


@dataclass
class RecentBar:
    open_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Snapshot:
    pair: str
    timeframe: str
    as_of: str
    price: float
    ma_fast: float
    ma_slow: float
    rsi: float
    macd_dif: float
    macd_dea: float
    macd_hist: float
    bb_upper: float
    bb_lower: float
    bb_pct: float
    atr: float
    volume: float
    volume_ma: float
    higher_close: float | None
    higher_trend_ema: float | None
    recent_high: float
    recent_low: float
    recent_bars: list[RecentBar]


def _last(series: pd.Series) -> float:
    return float(series.iloc[-1])


def _higher_trend_ema(higher_df: pd.DataFrame) -> float | None:
    """4h 趋势 EMA200，样本不足 200 根时返回 None（真实缺失，不兜底）。"""
    close = higher_df["close"]
    ema = close.ewm(
        span=HIGHER_TREND_EMA_PERIOD,
        adjust=False,
        min_periods=HIGHER_TREND_EMA_PERIOD,
    ).mean()
    value = ema.iloc[-1]
    return None if pd.isna(value) else float(value)


def compute_snapshot(
    base_df: pd.DataFrame,
    higher_df: pd.DataFrame,
    pair: str,
    timeframe: str,
) -> Snapshot:
    """在基础周期 K线上计算指标快照，higher_df 提供高周期趋势参考。

    base_df / higher_df 为 query_klines 返回格式（小写列名，按 open_time 升序）。
    指标在全量序列上计算后取末值，保证长周期指标准确。
    """
    close, high, low, volume = (
        base_df["close"],
        base_df["high"],
        base_df["low"],
        base_df["volume"],
    )

    ma_fast = SMAIndicator(close, window=MA_FAST_PERIOD).sma_indicator()
    ma_slow = SMAIndicator(close, window=MA_SLOW_PERIOD).sma_indicator()
    rsi = RSIIndicator(close, window=RSI_PERIOD).rsi()
    macd = MACD(close, window_fast=MACD_FAST, window_slow=MACD_SLOW, window_sign=MACD_SIGNAL)
    bb = BollingerBands(close, window=BB_PERIOD, window_dev=BB_STD)
    atr = AverageTrueRange(high, low, close, window=ATR_PERIOD).average_true_range()
    volume_ma = SMAIndicator(volume, window=VOLUME_MA_PERIOD).sma_indicator()

    bb_upper = _last(bb.bollinger_hband())
    bb_lower = _last(bb.bollinger_lband())
    price = _last(close)
    bb_width = bb_upper - bb_lower
    bb_pct = (price - bb_lower) / bb_width if bb_width > 0 else 0.5

    recent = base_df.tail(RECENT_BARS)
    recent_bars = [
        RecentBar(
            open_time=str(row.open_time),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in recent.itertuples()
    ]

    range_window = base_df.tail(RECENT_RANGE_BARS)
    higher_close = float(higher_df["close"].iloc[-1]) if not higher_df.empty else None

    return Snapshot(
        pair=pair,
        timeframe=timeframe,
        as_of=str(base_df["open_time"].iloc[-1]),
        price=price,
        ma_fast=_last(ma_fast),
        ma_slow=_last(ma_slow),
        rsi=_last(rsi),
        macd_dif=_last(macd.macd()),
        macd_dea=_last(macd.macd_signal()),
        macd_hist=_last(macd.macd_diff()),
        bb_upper=bb_upper,
        bb_lower=bb_lower,
        bb_pct=bb_pct,
        atr=_last(atr),
        volume=_last(volume),
        volume_ma=_last(volume_ma),
        higher_close=higher_close,
        higher_trend_ema=_higher_trend_ema(higher_df) if not higher_df.empty else None,
        recent_high=float(range_window["high"].max()),
        recent_low=float(range_window["low"].min()),
        recent_bars=recent_bars,
    )
