from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands

from data.storage.postgres import query_klines
from engine.data import (
    HIGHER_TIMEFRAME,
    HIGHER_TIMEFRAME_TREND_PERIOD,
    parse_utc_date,
)
from indicators.bias import BIAS_LONG, BIAS_RANGE, BIAS_SHORT, classify_bias
from indicators.snapshot import (
    BB_PERIOD,
    BB_STD,
    MA_FAST_PERIOD,
    MA_SLOW_PERIOD,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    RSI_PERIOD,
    VOLUME_MA_PERIOD,
    Snapshot,
)


@dataclass
class HorizonStats:
    horizon: int
    bias: str
    count: int
    mean_return_pct: float
    up_rate_pct: float  # 之后 N 根上涨的比例
    hit_rate_pct: float  # 方向命中率（偏多=涨, 偏空=跌, 震荡留空）


@dataclass
class BiasEvalResult:
    pair: str
    start: str | None
    end: str | None
    total_bars: int
    bias_counts: dict[str, int]
    stats: list[HorizonStats]
    baseline: dict[int, tuple[float, float]]  # horizon -> (mean_return_pct, up_rate_pct)


def _indicator_frame(base_df: pd.DataFrame, higher_df: pd.DataFrame) -> pd.DataFrame:
    """在全量序列上一次性算好各指标（均为因果/向后看，无未来函数）。"""
    close, volume = base_df["close"], base_df["volume"]
    macd = MACD(close, window_fast=MACD_FAST, window_slow=MACD_SLOW, window_sign=MACD_SIGNAL)
    bb = BollingerBands(close, window=BB_PERIOD, window_dev=BB_STD)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    bb_width = bb_upper - bb_lower

    frame = pd.DataFrame(
        {
            "open_time": base_df["open_time"],
            "close": close,
            "volume": volume,
            "ma_fast": SMAIndicator(close, window=MA_FAST_PERIOD).sma_indicator(),
            "ma_slow": SMAIndicator(close, window=MA_SLOW_PERIOD).sma_indicator(),
            "rsi": RSIIndicator(close, window=RSI_PERIOD).rsi(),
            "macd_dif": macd.macd(),
            "macd_dea": macd.macd_signal(),
            "macd_hist": macd.macd_diff(),
            "bb_pct": (close - bb_lower) / bb_width.where(bb_width > 0),
            "volume_ma": SMAIndicator(volume, window=VOLUME_MA_PERIOD).sma_indicator(),
        }
    )

    higher = higher_df[["open_time", "close"]].copy()
    higher["higher_ema"] = (
        higher["close"]
        .ewm(
            span=HIGHER_TIMEFRAME_TREND_PERIOD,
            adjust=False,
            min_periods=HIGHER_TIMEFRAME_TREND_PERIOD,
        )
        .mean()
    )
    higher = higher.rename(columns={"close": "higher_close"})

    merged = pd.merge_asof(
        frame.sort_values("open_time"),
        higher.sort_values("open_time"),
        on="open_time",
        direction="backward",
    )
    return merged.dropna(
        subset=["ma_slow", "rsi", "macd_hist", "bb_pct", "volume_ma"]
    ).reset_index(drop=True)


def _row_to_snapshot(row, pair: str) -> Snapshot:
    """用预算好的指标行构造最小 Snapshot，复用真实打分逻辑。未用字段填中性值。"""
    higher_ema = None if pd.isna(row.higher_ema) else float(row.higher_ema)
    higher_close = None if pd.isna(row.higher_close) else float(row.higher_close)
    return Snapshot(
        pair=pair,
        timeframe="1h",
        as_of=str(row.open_time),
        price=float(row.close),
        ma_fast=float(row.ma_fast),
        ma_slow=float(row.ma_slow),
        rsi=float(row.rsi),
        macd_dif=float(row.macd_dif),
        macd_dea=float(row.macd_dea),
        macd_hist=float(row.macd_hist),
        bb_upper=0.0,
        bb_lower=0.0,
        bb_pct=float(row.bb_pct),
        atr=0.0,
        volume=float(row.volume),
        volume_ma=float(row.volume_ma),
        higher_close=higher_close,
        higher_trend_ema=higher_ema,
        recent_high=0.0,
        recent_low=0.0,
        recent_bars=[],
    )


def evaluate_bias(
    pair: str,
    start: str | None,
    end: str | None,
    horizons: list[int],
) -> BiasEvalResult:
    """回测 bias 信号：每根 K线算出当时倾向，统计其后 N 根的真实涨跌。"""
    base_df = query_klines(pair, "1h", parse_utc_date(start), parse_utc_date(end))
    higher_df = query_klines(
        pair, HIGHER_TIMEFRAME, parse_utc_date(start), parse_utc_date(end)
    )
    if base_df.empty:
        raise RuntimeError(f"{pair} 无 1h 数据，请先 fetch")

    frame = _indicator_frame(base_df, higher_df)
    frame["bias"] = [
        classify_bias(_row_to_snapshot(row, pair)).bias for row in frame.itertuples()
    ]
    for n in horizons:
        frame[f"fwd_{n}"] = frame["close"].shift(-n) / frame["close"] - 1

    bias_counts = {
        b: int((frame["bias"] == b).sum())
        for b in (BIAS_LONG, BIAS_SHORT, BIAS_RANGE)
    }

    stats: list[HorizonStats] = []
    baseline: dict[int, tuple[float, float]] = {}
    for n in horizons:
        col = f"fwd_{n}"
        valid = frame.dropna(subset=[col])
        baseline[n] = (
            float(valid[col].mean() * 100),
            float((valid[col] > 0).mean() * 100),
        )
        for b in (BIAS_LONG, BIAS_SHORT, BIAS_RANGE):
            sub = valid[valid["bias"] == b]
            if sub.empty:
                stats.append(HorizonStats(n, b, 0, 0.0, 0.0, 0.0))
                continue
            up_rate = float((sub[col] > 0).mean() * 100)
            if b == BIAS_LONG:
                hit = up_rate
            elif b == BIAS_SHORT:
                hit = float((sub[col] < 0).mean() * 100)
            else:
                hit = 0.0
            stats.append(
                HorizonStats(
                    horizon=n,
                    bias=b,
                    count=len(sub),
                    mean_return_pct=float(sub[col].mean() * 100),
                    up_rate_pct=up_rate,
                    hit_rate_pct=hit,
                )
            )

    return BiasEvalResult(
        pair=pair,
        start=start,
        end=end,
        total_bars=len(frame),
        bias_counts=bias_counts,
        stats=stats,
        baseline=baseline,
    )


def format_eval(result: BiasEvalResult) -> str:
    lines = [
        f"\n{'=' * 60}",
        f"  Bias 信号回测: {result.pair} 1h",
        f"  区间: {result.start or '最早'} ~ {result.end or '最新'}，有效样本 {result.total_bars} 根",
        f"  倾向分布: 偏多 {result.bias_counts[BIAS_LONG]} / "
        f"偏空 {result.bias_counts[BIAS_SHORT]} / 震荡 {result.bias_counts[BIAS_RANGE]}",
        f"{'=' * 60}",
    ]
    horizons = sorted({s.horizon for s in result.stats})
    for n in horizons:
        base_mean, base_up = result.baseline[n]
        lines.append(f"\n  ── 未来 {n} 根（约 {n / 24:.0f} 天）──")
        lines.append(f"  基准(全样本): 平均收益 {base_mean:+.2f}% | 上涨概率 {base_up:.1f}%")
        lines.append("  倾向    样本    平均收益    上涨概率    方向命中率")
        for s in [x for x in result.stats if x.horizon == n]:
            hit = f"{s.hit_rate_pct:.1f}%" if s.bias != BIAS_RANGE else "  -"
            lines.append(
                f"  {s.bias}   {s.count:>6}   {s.mean_return_pct:>+7.2f}%   "
                f"{s.up_rate_pct:>6.1f}%   {hit:>8}"
            )
    lines.append(f"\n{'=' * 60}")
    lines.append("  判读: 若「偏多」平均收益/上涨概率 ≈ 基准，「偏空」≈ 基准，")
    lines.append("        说明当前等权打分没有预测力，需要调整（如趋势门控）。")
    lines.append(f"{'=' * 60}\n")
    return "\n".join(lines)
