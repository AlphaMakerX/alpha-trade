from datetime import datetime, timezone

import pandas as pd
from loguru import logger
from ta.trend import SMAIndicator
from ta.volatility import AverageTrueRange

from data.feeds.binance import fetch_klines, _ms_to_dt

FAST = 45
SLOW = 200
TREND = 100
ATR_PERIOD = 16
ATR_MULT = 1.5
BARS_NEEDED = TREND + 2


def get_signal(pair: str, timeframe: str) -> str:
    """拉取最新 K线，计算指标，返回信号分析文本。"""
    now = datetime.now(tz=timezone.utc)
    since = _ms_to_dt(int((now.timestamp() - BARS_NEEDED * 3600) * 1000))

    logger.info(f"拉取最近 {BARS_NEEDED} 根 {timeframe} K线...")
    rows = fetch_klines(pair, timeframe, since, limit=BARS_NEEDED)

    if len(rows) < BARS_NEEDED:
        return f"K线数据不足（需要 {BARS_NEEDED}，只有 {len(rows)}）"

    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_buy_base", "taker_buy_quote",
    ])

    close = df["close"]
    high = df["high"]
    low = df["low"]

    fast_ma = SMAIndicator(close, window=FAST).sma_indicator()
    slow_ma = SMAIndicator(close, window=SLOW).sma_indicator()
    trend_ma = SMAIndicator(close, window=TREND).sma_indicator()
    atr = AverageTrueRange(high, low, close, window=ATR_PERIOD).average_true_range()

    price = close.iloc[-1]
    fast_now, fast_prev = fast_ma.iloc[-1], fast_ma.iloc[-2]
    slow_now, slow_prev = slow_ma.iloc[-1], slow_ma.iloc[-2]
    trend_now = trend_ma.iloc[-1]
    atr_now = atr.iloc[-1]

    golden_cross = fast_prev <= slow_prev and fast_now > slow_now
    death_cross = fast_prev >= slow_prev and fast_now < slow_now
    above_trend = price > trend_now

    lines = [
        f"\n{'='*40}",
        f"  {pair} {timeframe} 信号分析",
        f"  时间: {df['open_time'].iloc[-1]}",
        f"{'='*40}",
        f"  当前价格:   {price:.2f}",
        f"  快线(MA{FAST}): {fast_now:.2f}",
        f"  慢线(MA{SLOW}): {slow_now:.2f}",
        f"  趋势(MA{TREND}):{trend_now:.2f}",
        f"  ATR({ATR_PERIOD}):    {atr_now:.2f}",
        f"  趋势方向:   {'▲ 上方' if above_trend else '▼ 下方'}",
        f"  均线关系:   快线 {'>' if fast_now > slow_now else '<'} 慢线",
        f"{'='*40}",
    ]

    if golden_cross and above_trend:
        sl = price - ATR_MULT * atr_now
        lines.append(f"  ★ 信号: 买入")
        lines.append(f"  止损价: {sl:.2f} (ATR x{ATR_MULT})")
    elif death_cross:
        lines.append(f"  ★ 信号: 卖出 / 平仓")
    elif golden_cross and not above_trend:
        lines.append(f"  ★ 信号: 观望（金叉但价格在趋势线下方）")
    else:
        position = "多头持有中" if fast_now > slow_now and above_trend else "空仓等待"
        lines.append(f"  ★ 信号: 持有 ({position})")

    lines.append(f"{'='*40}\n")
    return "\n".join(lines)
