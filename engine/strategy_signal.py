from dataclasses import dataclass

import pandas as pd
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

from strategies.trend.trend_holding_v3 import TrendHoldingV3


@dataclass
class ConditionRow:
    name: str
    passed: bool
    detail: str


@dataclass
class StrategySignal:
    strategy: str
    price: float
    buy: bool
    sell: bool
    entry_rows: list[ConditionRow]
    exit_rows: list[ConditionRow]

    @property
    def verdict(self) -> str:
        if self.buy:
            return "★ 买入信号（开多）"
        if self.sell:
            return "无买入；若持仓则平仓（趋势退出）"
        return "无信号（空仓观望 / 持仓继续持有）"


def format_console(sig: StrategySignal, pair: str, timeframe: str, as_of: str) -> str:
    def block(title, rows):
        lines = [f"  {title}:"]
        for r in rows:
            lines.append(f"    {'✅' if r.passed else '❌'} {r.name}  {r.detail}")
        return "\n".join(lines)

    bar = "=" * 48
    return "\n".join(
        [
            f"\n{bar}",
            f"  {pair} {timeframe}  最优策略信号（{sig.strategy}）",
            f"  时间: {as_of}",
            f"  现价: {sig.price:.2f}",
            bar,
            f"  ★ 信号: {sig.verdict}",
            "",
            block("买入（开多）条件", sig.entry_rows),
            block("卖出/平仓条件（仅持仓时有效）", sig.exit_rows),
            f"{bar}\n",
        ]
    )


def evaluate_trend_holding_v3(base_df: pd.DataFrame) -> StrategySignal:
    """在最新一根已闭合 K线上复算 trend_holding_v3 的入场/出场条件。

    base_df 为 query_klines 返回格式（小写列名，按 open_time 升序）。
    参数从策略类读取，保持与回测同一套默认值。
    """
    s = TrendHoldingV3
    close, high, low = base_df["close"], base_df["high"], base_df["low"]

    trend_ema = EMAIndicator(close, window=s.trend_period).ema_indicator()
    pullback_ema = EMAIndicator(close, window=s.pullback_period).ema_indicator()
    donchian_high = high.rolling(s.breakout_period).max().shift(1)
    donchian_low = low.rolling(s.exit_period).min().shift(1)
    atr = AverageTrueRange(high, low, close, window=s.atr_period).average_true_range()
    atr_pct = atr.rolling(s.atr_percentile_period).rank(pct=True)

    i = len(base_df) - 1
    price = float(close.iloc[i])
    trend_now = trend_ema.iloc[i]
    trend_then = trend_ema.iloc[i - s.trend_slope_period]
    pull_now = pullback_ema.iloc[i]
    pull_prev = pullback_ema.iloc[i - 1]
    pct = atr_pct.iloc[i]
    dch_high = donchian_high.iloc[i]
    dch_low = donchian_low.iloc[i]

    trend_ok = price > trend_now and trend_now > trend_then
    vol_ok = s.min_atr_percentile <= pct <= s.max_atr_percentile
    breakout = price > dch_high
    pullback = (
        close.iloc[i - 1] <= pull_prev
        and price > pull_now
        and price > high.iloc[i - 1]
    )
    entry_form = (s.use_breakout_entry and breakout) or (s.use_pullback_entry and pullback)
    buy = bool(trend_ok and vol_ok and entry_form)

    channel_break = price < dch_low
    structure_broken = price < pull_now and trend_now < trend_then
    sell = bool(channel_break or structure_broken)

    entry_rows = [
        ConditionRow(
            "趋势确认",
            bool(trend_ok),
            f"价 {price:.2f} {'>' if price > trend_now else '<'} EMA{s.trend_period}({trend_now:.2f})，"
            f"长期 EMA {'上行' if trend_now > trend_then else '下行'}",
        ),
        ConditionRow(
            "波动过滤",
            bool(vol_ok),
            f"ATR 分位 {pct:.3f} ∈ [{s.min_atr_percentile}, {s.max_atr_percentile}]",
        ),
        ConditionRow(
            "入场形态",
            bool(entry_form),
            f"回踩重站={'是' if pullback else '否'}"
            + (f"；突破前高({dch_high:.2f})={'是' if breakout else '否'}" if s.use_breakout_entry else "（突破入场已关闭）"),
        ),
    ]
    exit_rows = [
        ConditionRow("通道跌破", bool(channel_break), f"价 {price:.2f} {'<' if channel_break else '≥'} Donchian 低({dch_low:.2f})"),
        ConditionRow("结构破坏", bool(structure_broken), "价跌破短 EMA 且长期 EMA 下行" if structure_broken else "未同时满足"),
    ]
    return StrategySignal("trend_holding_v3", price, buy, sell, entry_rows, exit_rows)
