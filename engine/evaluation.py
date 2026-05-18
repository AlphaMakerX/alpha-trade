from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from dateutil.relativedelta import relativedelta

from analysis.data_quality import validate_ohlcv_data
from engine.data import load_ohlcv, parse_utc_date
from engine.factory import make_backtest
from engine.params import format_strategy_params
from strategies.registry import get_strategy
from utils.config import get_settings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REPORT_DIR = _PROJECT_ROOT / "artifacts" / "evaluations"

_REPORT_COLUMNS = [
    "group",
    "label",
    "start",
    "end",
    "bars",
    "commission",
    "slippage",
    "return_pct",
    "buy_hold_return_pct",
    "sharpe",
    "max_drawdown_pct",
    "trades",
    "win_rate_pct",
    "profit_factor",
    "exposure_time_pct",
]


@dataclass(frozen=True)
class EvaluationSegment:
    label: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class EvaluationReportPaths:
    markdown_path: Path
    summary_path: Path


def _segments(
    start: datetime, end: datetime, months: int, prefix: str
) -> list[EvaluationSegment]:
    current = start
    result = []
    index = 1
    while current < end:
        segment_end = min(current + relativedelta(months=months), end)
        label = f"{prefix}{index}: {current.date()} ~ {segment_end.date()}"
        result.append(EvaluationSegment(label, current, segment_end))
        current = segment_end
        index += 1
    return result


def annual_segments(start: datetime, end: datetime) -> list[EvaluationSegment]:
    return _segments(start, end, 12, "Y")


def quarterly_segments(start: datetime, end: datetime) -> list[EvaluationSegment]:
    return _segments(start, end, 3, "Q")


def _settings_with_costs(settings: dict, commission: float, slippage: float) -> dict:
    adjusted = deepcopy(settings)
    trading = adjusted.setdefault("trading", {})
    trading["commission"] = commission
    trading["slippage"] = slippage
    return adjusted


def _metric(stats: pd.Series, name: str):
    value = stats.get(name)
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _summary_row(
    *,
    group: str,
    label: str,
    start: datetime,
    end: datetime,
    bars: int,
    commission: float,
    slippage: float,
    stats: pd.Series,
) -> dict:
    return {
        "group": group,
        "label": label,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "bars": bars,
        "commission": commission,
        "slippage": slippage,
        "return_pct": _metric(stats, "Return [%]"),
        "buy_hold_return_pct": _metric(stats, "Buy & Hold Return [%]"),
        "sharpe": _metric(stats, "Sharpe Ratio"),
        "max_drawdown_pct": _metric(stats, "Max. Drawdown [%]"),
        "trades": _metric(stats, "# Trades"),
        "win_rate_pct": _metric(stats, "Win Rate [%]"),
        "profit_factor": _metric(stats, "Profit Factor"),
        "exposure_time_pct": _metric(stats, "Exposure Time [%]"),
    }


def _slice_segment(df: pd.DataFrame, segment: EvaluationSegment) -> pd.DataFrame:
    if not df.empty and segment.end >= df.index.max():
        return df[(df.index >= segment.start) & (df.index <= segment.end)]
    return df[(df.index >= segment.start) & (df.index < segment.end)]


def _run_row(
    *,
    df: pd.DataFrame,
    strategy_cls,
    settings: dict,
    strategy_params: dict[str, object],
    group: str,
    label: str,
    start: datetime,
    end: datetime,
) -> dict:
    stats = make_backtest(df, strategy_cls, settings).run(**strategy_params)
    trading = settings.get("trading", {})
    return _summary_row(
        group=group,
        label=label,
        start=start,
        end=end,
        bars=len(df),
        commission=float(trading.get("commission", 0.0)),
        slippage=float(trading.get("slippage", 0.0)),
        stats=stats,
    )


def _format_value(value) -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "NaN"
    except TypeError:
        pass
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _markdown_table(rows: list[dict], columns: list[str]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(_format_value(row.get(column)) for column in columns)
            + " |"
        )
    return "\n".join(lines)


def _write_evaluation_report(
    *,
    strategy_name: str,
    pair: str,
    timeframe: str,
    start: str,
    end: str,
    data_quality,
    strategy_params: dict[str, object],
    rows: list[dict],
) -> EvaluationReportPaths:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_pair = pair.replace("/", "-")
    base_name = f"{timestamp}_{strategy_name}_{safe_pair}_{timeframe}_{start}_{end}"
    markdown_path = _REPORT_DIR / f"{base_name}.md"
    summary_path = _REPORT_DIR / f"{base_name}_summary.csv"

    summary = pd.DataFrame(rows, columns=_REPORT_COLUMNS)
    summary.to_csv(summary_path, index=False)

    baseline = [row for row in rows if row["group"] == "full"]
    segments = [row for row in rows if row["group"] in {"annual", "quarterly"}]
    costs = [row for row in rows if row["group"] == "cost"]

    lines = [
        "# Strategy Evaluation",
        "",
        "## Run",
        "",
        f"- Strategy: `{strategy_name}`",
        f"- Pair: `{pair}`",
        f"- Timeframe: `{timeframe}`",
        f"- Range: `{start}` ~ `{end}`",
        f"- Param overrides: `{format_strategy_params(strategy_params)}`",
        f"- Generated at: `{timestamp}`",
        "- Cash benchmark: `0%`",
        "",
        "## Data Quality",
        "",
        data_quality.markdown_table(),
        "",
        "## Baseline",
        "",
        _markdown_table(baseline, _REPORT_COLUMNS),
        "",
        "## Annual And Quarterly Segments",
        "",
        _markdown_table(segments, _REPORT_COLUMNS),
        "",
        "## Cost Stress",
        "",
        _markdown_table(costs, _REPORT_COLUMNS),
        "",
        "## Artifacts",
        "",
        f"- Summary CSV: `{summary_path}`",
        "",
    ]
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return EvaluationReportPaths(markdown_path=markdown_path, summary_path=summary_path)


def run_strategy_evaluation(
    strategy_name: str,
    pair: str,
    timeframe: str,
    start: str,
    end: str,
    strategy_params: dict[str, object],
) -> str:
    """Evaluate default strategy parameters across segments and cost assumptions."""
    settings = get_settings()
    bt_cfg = settings.get("backtest", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")

    start_dt = parse_utc_date(start)
    end_dt = parse_utc_date(end)
    if start_dt is None or end_dt is None:
        return "评估必须提供 start 和 end，或在配置中设置 backtest.start_date/end_date"

    df = load_ohlcv(pair, timeframe, start, end)
    if df.empty:
        return "无数据，请先运行 fetch 拉取数据"

    strategy_cls = get_strategy(strategy_name)
    data_quality = validate_ohlcv_data(df, pair, timeframe, start, end)

    rows = [
        _run_row(
            df=df,
            strategy_cls=strategy_cls,
            settings=settings,
            strategy_params=strategy_params,
            group="full",
            label="full",
            start=start_dt,
            end=end_dt,
        )
    ]

    for segment in annual_segments(start_dt, end_dt):
        segment_df = _slice_segment(df, segment)
        if segment_df.empty:
            continue
        rows.append(
            _run_row(
                df=segment_df,
                strategy_cls=strategy_cls,
                settings=settings,
                strategy_params=strategy_params,
                group="annual",
                label=segment.label,
                start=segment.start,
                end=segment.end,
            )
        )

    for segment in quarterly_segments(start_dt, end_dt):
        segment_df = _slice_segment(df, segment)
        if segment_df.empty:
            continue
        rows.append(
            _run_row(
                df=segment_df,
                strategy_cls=strategy_cls,
                settings=settings,
                strategy_params=strategy_params,
                group="quarterly",
                label=segment.label,
                start=segment.start,
                end=segment.end,
            )
        )

    for commission in (0.0005, 0.0010, 0.0020):
        for slippage in (0.0005, 0.0010, 0.0020):
            cost_settings = _settings_with_costs(settings, commission, slippage)
            rows.append(
                _run_row(
                    df=df,
                    strategy_cls=strategy_cls,
                    settings=cost_settings,
                    strategy_params=strategy_params,
                    group="cost",
                    label=f"commission={commission:.4f}, slippage={slippage:.4f}",
                    start=start_dt,
                    end=end_dt,
                )
            )

    report_paths = _write_evaluation_report(
        strategy_name=strategy_name,
        pair=pair,
        timeframe=timeframe,
        start=start,
        end=end,
        data_quality=data_quality,
        strategy_params=strategy_params,
        rows=rows,
    )

    summary = pd.DataFrame(rows)
    selected = summary[
        [
            "group",
            "label",
            "return_pct",
            "buy_hold_return_pct",
            "sharpe",
            "max_drawdown_pct",
            "trades",
            "profit_factor",
        ]
    ]
    return "\n".join(
        [
            "=== 策略稳定性评估 ===",
            (
                f"参数覆盖: {format_strategy_params(strategy_params)}"
                if strategy_params
                else "参数覆盖: 无"
            ),
            selected.to_string(index=False),
            "",
            "=== 数据质量 ===",
            *data_quality.summary_lines(),
            "",
            f"报告已生成: {report_paths.markdown_path}",
            f"汇总 CSV: {report_paths.summary_path}",
        ]
    )
