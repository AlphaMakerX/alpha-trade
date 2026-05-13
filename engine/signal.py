from datetime import datetime, timezone

import pandas as pd
from loguru import logger

from data.feeds.binance import fetch_klines, _ms_to_dt
from strategies.trend.ma_cross import MaCross, SIGNAL_BUY, SIGNAL_SELL, SIGNAL_WATCH

_SIGNAL_TEXT = {
    SIGNAL_BUY: "买入",
    SIGNAL_SELL: "卖出 / 平仓",
    SIGNAL_WATCH: "观望（金叉但价格在趋势线下方）",
}


def get_signal(pair: str, timeframe: str) -> str:
    """拉取最新 K线，复用 MaCross 策略计算信号。"""
    bars = MaCross.bars_needed()
    now = datetime.now(tz=timezone.utc)
    since = _ms_to_dt(int((now.timestamp() - bars * 3600) * 1000))

    logger.info(f"拉取最近 {bars} 根 {timeframe} K线...")
    rows = fetch_klines(pair, timeframe, since, limit=bars)

    if len(rows) < bars:
        return f"K线数据不足（需要 {bars}，只有 {len(rows)}）"

    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_buy_base", "taker_buy_quote",
    ])

    s = MaCross.compute_signal(df)

    above = s.price > s.trend_ma
    lines = [
        f"\n{'='*40}",
        f"  {pair} {timeframe} 信号分析",
        f"  时间: {df['open_time'].iloc[-1]}",
        f"{'='*40}",
        f"  当前价格:   {s.price:.2f}",
        f"  快线(MA{MaCross.fast_period}): {s.fast_ma:.2f}",
        f"  慢线(MA{MaCross.slow_period}): {s.slow_ma:.2f}",
        f"  趋势(MA{MaCross.trend_period}):{s.trend_ma:.2f}",
        f"  ATR({MaCross.atr_period}):    {s.atr:.2f}",
        f"  趋势方向:   {'▲ 上方' if above else '▼ 下方'}",
        f"  均线关系:   快线 {'>' if s.fast_ma > s.slow_ma else '<'} 慢线",
        f"{'='*40}",
    ]

    if s.signal in _SIGNAL_TEXT:
        lines.append(f"  ★ 信号: {_SIGNAL_TEXT[s.signal]}")
        if s.stop_loss is not None:
            lines.append(f"  止损价: {s.stop_loss:.2f} (ATR x{MaCross.atr_multiplier})")
    else:
        position = "多头持有中" if s.fast_ma > s.slow_ma and above else "空仓等待"
        lines.append(f"  ★ 信号: 持有 ({position})")

    lines.append(f"{'='*40}\n")
    return "\n".join(lines)
