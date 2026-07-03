from dataclasses import dataclass

import pandas as pd

from data.storage.postgres import query_klines
from engine.data import BASE_TIMEFRAME, parse_utc_date
from indicators.momentum import momentum


@dataclass
class QuantileStats:
    period: int
    horizon: int
    quantile: int  # 1..num_quantiles，1=动量最弱层，num=最强层
    count: int
    mean_return_pct: float
    up_rate_pct: float  # 之后 horizon 根上涨的比例


@dataclass
class FactorStats:
    period: int
    horizon: int
    ic: float  # 因子值与 forward-return 的秩相关（Spearman）
    quantiles: list[QuantileStats]
    long_short_pct: float  # 最强层 - 最弱层 的平均收益差


@dataclass
class MomentumEvalResult:
    pair: str
    start: str | None
    end: str | None
    total_bars: int
    periods: list[int]
    horizons: list[int]
    num_quantiles: int
    baseline: dict[int, tuple[float, float]]  # horizon -> (mean_return_pct, up_rate_pct)
    stats: list[FactorStats]


def _quantile_labels(values: pd.Series, num_quantiles: int) -> pd.Series:
    """按因子值排名等分为 num_quantiles 层，返回 0..num_quantiles-1 的整数标签。

    用排名分层而非按值分箱：分布再偏也能得到大小均匀的层，且不会因重复边界报错。
    """
    order = values.rank(method="first").astype(int)  # 1..N
    return (order - 1) * num_quantiles // len(values)


def evaluate_momentum(
    pair: str,
    start: str | None,
    end: str | None,
    periods: list[int],
    horizons: list[int],
    num_quantiles: int,
) -> MomentumEvalResult:
    """评估动量因子预测力：每根 K 线算各窗口动量，统计其后 horizon 根真实涨跌。

    对每个 (period, horizon)：算 IC、按动量分位分层的平均收益/上涨概率、多空价差；
    另给无条件 baseline（全样本前瞻收益），用于判断因子是否真的比「什么都不看」更好。
    """
    base_df = query_klines(
        pair, BASE_TIMEFRAME, parse_utc_date(start), parse_utc_date(end)
    )
    if base_df.empty:
        raise RuntimeError(f"{pair} 无 {BASE_TIMEFRAME} 数据，请先 fetch")

    frame = base_df[["open_time", "close"]].reset_index(drop=True)
    for p in periods:
        frame[f"mom_{p}"] = momentum(frame["close"], p)
    for n in horizons:
        frame[f"fwd_{n}"] = frame["close"].shift(-n) / frame["close"] - 1

    baseline: dict[int, tuple[float, float]] = {}
    for n in horizons:
        valid = frame.dropna(subset=[f"fwd_{n}"])
        baseline[n] = (
            float(valid[f"fwd_{n}"].mean() * 100),
            float((valid[f"fwd_{n}"] > 0).mean() * 100),
        )

    stats: list[FactorStats] = []
    for p in periods:
        for n in horizons:
            sub = frame.dropna(subset=[f"mom_{p}", f"fwd_{n}"])
            # Spearman IC = 因子秩与前瞻收益秩的 Pearson 相关（避免依赖 scipy）
            ic = float(sub[f"mom_{p}"].rank().corr(sub[f"fwd_{n}"].rank()))
            labels = _quantile_labels(sub[f"mom_{p}"], num_quantiles)

            qstats: list[QuantileStats] = []
            for q in range(num_quantiles):
                bucket = sub[labels == q]
                qstats.append(
                    QuantileStats(
                        period=p,
                        horizon=n,
                        quantile=q + 1,
                        count=len(bucket),
                        mean_return_pct=float(bucket[f"fwd_{n}"].mean() * 100),
                        up_rate_pct=float((bucket[f"fwd_{n}"] > 0).mean() * 100),
                    )
                )

            stats.append(
                FactorStats(
                    period=p,
                    horizon=n,
                    ic=ic,
                    quantiles=qstats,
                    long_short_pct=qstats[-1].mean_return_pct
                    - qstats[0].mean_return_pct,
                )
            )

    return MomentumEvalResult(
        pair=pair,
        start=start,
        end=end,
        total_bars=len(frame),
        periods=periods,
        horizons=horizons,
        num_quantiles=num_quantiles,
        baseline=baseline,
        stats=stats,
    )


def format_eval(result: MomentumEvalResult) -> str:
    lines = [
        f"\n{'=' * 64}",
        f"  Momentum 因子评估: {result.pair} {BASE_TIMEFRAME}",
        f"  区间: {result.start or '最早'} ~ {result.end or '最新'}，样本 {result.total_bars} 根",
        f"  回看窗口(根): {', '.join(map(str, result.periods))} | "
        f"前瞻(根): {', '.join(map(str, result.horizons))} | 分位: {result.num_quantiles} 层",
        f"{'=' * 64}",
    ]
    for p in result.periods:
        lines.append(f"\n  ══ 动量窗口 {p} 根（约 {p / 24:.0f} 天）══")
        for n in result.horizons:
            fs = next(s for s in result.stats if s.period == p and s.horizon == n)
            base_mean, base_up = result.baseline[n]
            lines.append(
                f"\n  ── 前瞻 {n} 根（约 {n / 24:.0f} 天）── "
                f"基准: 平均 {base_mean:+.2f}% | 上涨 {base_up:.1f}%"
            )
            lines.append(
                f"    IC(Spearman) = {fs.ic:+.3f}   多空价差(Q{result.num_quantiles}-Q1) = "
                f"{fs.long_short_pct:+.2f}%"
            )
            lines.append("    分位    样本    平均收益    上涨概率")
            for q in fs.quantiles:
                lines.append(
                    f"    Q{q.quantile:<5}{q.count:>6}   {q.mean_return_pct:>+7.2f}%   "
                    f"{q.up_rate_pct:>6.1f}%"
                )
    lines.append(f"\n{'=' * 64}")
    lines.append("  判读: IC 接近 0、分位收益不单调、多空价差 ≈ 0，说明动量在该窗口无预测力；")
    lines.append("        最强层收益要明显高于基准，才算比「什么都不看」多赚。")
    lines.append(f"{'=' * 64}\n")
    return "\n".join(lines)
