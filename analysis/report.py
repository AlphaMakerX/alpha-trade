from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

import pandas as pd

from analysis.data_quality import DataQualityReport


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REPORT_DIR = _PROJECT_ROOT / "artifacts" / "backtests"

_CORE_METRICS = [
    "Start",
    "End",
    "Duration",
    "Exposure Time [%]",
    "Equity Final [$]",
    "Equity Peak [$]",
    "Return [%]",
    "Buy & Hold Return [%]",
    "Return (Ann.) [%]",
    "CAGR [%]",
    "Volatility (Ann.) [%]",
    "Sharpe Ratio",
    "Sortino Ratio",
    "Calmar Ratio",
    "Max. Drawdown [%]",
    "Max. Drawdown Duration",
    "Avg. Drawdown [%]",
    "Avg. Drawdown Duration",
    "# Trades",
    "Win Rate [%]",
    "Best Trade [%]",
    "Worst Trade [%]",
    "Avg. Trade [%]",
    "Max. Trade Duration",
    "Avg. Trade Duration",
    "Profit Factor",
    "Expectancy [%]",
    "SQN",
    "Kelly Criterion",
]


@dataclass
class BacktestReportPaths:
    markdown_path: Path
    trades_path: Path | None


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")


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


def _metric_table(stats: pd.Series) -> str:
    lines = ["| Metric | Value |", "| --- | ---: |"]
    for metric in _CORE_METRICS:
        if metric in stats:
            lines.append(f"| {metric} | {_format_value(stats[metric])} |")
    return "\n".join(lines)


def _trades(stats: pd.Series) -> pd.DataFrame:
    trades = stats.get("_trades")
    if isinstance(trades, pd.DataFrame):
        return trades.copy()
    return pd.DataFrame()


def _count_final_bar_exits(stats: pd.Series) -> int:
    trades = _trades(stats)
    if trades.empty or "ExitTime" not in trades.columns or "End" not in stats:
        return 0
    end_text = str(stats["End"])
    return int((trades["ExitTime"].astype(str) == end_text).sum())


def write_backtest_report(
    *,
    stats: pd.Series,
    strategy_name: str,
    pair: str,
    timeframe: str,
    start: str | None,
    end: str | None,
    backtest_options: dict,
    data_quality: DataQualityReport,
) -> BacktestReportPaths:
    """Persist a compact Markdown report and the trade list for one backtest."""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = _safe_name(
        f"{timestamp}_{strategy_name}_{pair}_{timeframe}_{start or 'na'}_{end or 'na'}"
    )
    markdown_path = _REPORT_DIR / f"{base_name}.md"
    trades_path = _REPORT_DIR / f"{base_name}_trades.csv"

    trades = _trades(stats)
    if not trades.empty:
        trades.to_csv(trades_path, index=False)
    else:
        trades_path = None

    commission = backtest_options.get("commission", 0.0)
    spread = backtest_options.get("spread", 0.0)
    final_bar_exits = _count_final_bar_exits(stats)
    commissions_paid = stats.get("Commissions [$]", 0.0)

    lines = [
        "# Backtest Report",
        "",
        "## Run",
        "",
        f"- Strategy: `{strategy_name}`",
        f"- Pair: `{pair}`",
        f"- Timeframe: `{timeframe}`",
        f"- Requested range: `{start or '-'}` ~ `{end or '-'}`",
        f"- Generated at: `{timestamp}`",
        "",
        "## Backtest Settings",
        "",
        "| Setting | Value |",
        "| --- | ---: |",
        f"| cash | {_format_value(backtest_options.get('cash'))} |",
        f"| commission | {_format_value(commission)} |",
        f"| spread/slippage | {_format_value(spread)} |",
        f"| trade_on_close | {backtest_options.get('trade_on_close')} |",
        f"| exclusive_orders | {backtest_options.get('exclusive_orders')} |",
        f"| finalize_trades | {backtest_options.get('finalize_trades')} |",
        "",
        "## Data Quality",
        "",
        data_quality.markdown_table(),
        "",
        "## Key Metrics",
        "",
        _metric_table(stats),
        "",
        "## Benchmark And Costs",
        "",
        "| Item | Value |",
        "| --- | ---: |",
        f"| Strategy Return [%] | {_format_value(stats.get('Return [%]'))} |",
        f"| Buy & Hold Return [%] | {_format_value(stats.get('Buy & Hold Return [%]'))} |",
        "| Cash Benchmark Return [%] | 0.0000 |",
        f"| Commissions [$] | {_format_value(commissions_paid)} |",
        f"| Configured commission | {_format_value(commission)} |",
        f"| Configured spread/slippage | {_format_value(spread)} |",
        "",
        "## Trade Finalization",
        "",
        f"- `finalize_trades`: `{backtest_options.get('finalize_trades')}`",
        f"- Trades exiting on final bar: `{final_bar_exits}`",
        "- Note: final-bar exits may include trades closed by Backtesting.py finalization.",
        "",
        "## Artifacts",
        "",
        f"- Trades CSV: `{trades_path if trades_path else 'none'}`",
        "",
    ]

    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return BacktestReportPaths(markdown_path=markdown_path, trades_path=trades_path)
