import math
import time
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path

import pandas as pd
from loguru import logger

from analysis.data_quality import validate_ohlcv_data
from engine.data import load_ohlcv
from engine.factory import make_backtest
from strategies.registry import get_strategy, list_strategies
from utils.config import get_settings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REPORT_DIR = _PROJECT_ROOT / "artifacts" / "searches"

_REPORT_COLUMNS = [
    "strategy",
    "params",
    "train_passed",
    "train_score",
    "train_return_pct",
    "train_annual_return_pct",
    "train_sharpe",
    "train_max_drawdown_pct",
    "train_trades",
    "train_profit_factor",
    "train_fail_reasons",
    "test_passed",
    "test_score",
    "test_return_pct",
    "test_annual_return_pct",
    "test_sharpe",
    "test_max_drawdown_pct",
    "test_trades",
    "test_profit_factor",
    "test_fail_reasons",
]


@dataclass(frozen=True)
class SearchCriteria:
    min_train_trades: int = 30
    min_test_trades: int = 5
    max_drawdown_pct: float = 15.0
    min_profit_factor: float = 1.1
    min_sharpe: float = 0.3


@dataclass(frozen=True)
class SearchReportPaths:
    markdown_path: Path
    summary_path: Path


def _finite_float(value, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def _metric(stats: pd.Series, name: str, default: float = 0.0) -> float:
    return _finite_float(stats.get(name), default)


def _profit_factor(stats: pd.Series) -> float:
    value = stats.get("Profit Factor")
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isinf(result):
        return 5.0
    if math.isnan(result):
        return 0.0
    return result


def score_stats(stats: pd.Series) -> float:
    """Rank candidates by high annual return, then risk-adjusted quality."""
    annual_return = _metric(stats, "Return (Ann.) [%]", _metric(stats, "Return [%]"))
    sharpe = _metric(stats, "Sharpe Ratio")
    max_drawdown = abs(_metric(stats, "Max. Drawdown [%]"))
    profit_factor = min(_profit_factor(stats), 5.0)
    trades = _metric(stats, "# Trades")
    trade_sample_bonus = min(trades / 50.0, 1.5)

    return (
        0.45 * annual_return
        + 8.0 * sharpe
        + 3.0 * profit_factor
        - 0.35 * max_drawdown
        + trade_sample_bonus
    )


def check_criteria(
    stats: pd.Series, criteria: SearchCriteria, min_trades: int
) -> tuple[bool, str]:
    reasons = []
    annual_return = _metric(stats, "Return (Ann.) [%]", _metric(stats, "Return [%]"))
    sharpe = _metric(stats, "Sharpe Ratio")
    max_drawdown = abs(_metric(stats, "Max. Drawdown [%]"))
    trades = int(_metric(stats, "# Trades"))
    profit_factor = _profit_factor(stats)

    if annual_return <= 0:
        reasons.append("annual_return<=0")
    if trades < min_trades:
        reasons.append(f"trades<{min_trades}")
    if max_drawdown > criteria.max_drawdown_pct:
        reasons.append(f"max_dd>{criteria.max_drawdown_pct:g}%")
    if profit_factor < criteria.min_profit_factor:
        reasons.append(f"pf<{criteria.min_profit_factor:g}")
    if sharpe < criteria.min_sharpe:
        reasons.append(f"sharpe<{criteria.min_sharpe:g}")

    return not reasons, "; ".join(reasons)


def _generate_param_combos(opt_params: dict, constraint=None) -> list[dict]:
    names = list(opt_params.keys())
    values = [list(v) for v in opt_params.values()]
    combos = [dict(zip(names, combo)) for combo in product(*values)]
    if constraint is not None:
        combos = [combo for combo in combos if constraint(combo)]
    return combos


def _constraint_for_params(params: dict) -> bool:
    if "fast_period" in params and "slow_period" in params:
        if params["fast_period"] >= params["slow_period"]:
            return False
    if "oversold" in params and "overbought" in params:
        if params["oversold"] >= params["overbought"]:
            return False
    if "oversold" in params and "exit_rsi" in params:
        if params["oversold"] >= params["exit_rsi"]:
            return False
    if "range_adx_threshold" in params and "trend_adx_threshold" in params:
        if params["range_adx_threshold"] > params["trend_adx_threshold"]:
            return False
    return True


def _split_train_test(
    df: pd.DataFrame, oos_ratio: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0 < oos_ratio < 0.8:
        raise ValueError("oos_ratio must be between 0 and 0.8")
    if len(df) < 2:
        raise ValueError("not enough data to split train/test")

    split_at = int(len(df) * (1 - oos_ratio))
    split_at = min(max(split_at, 1), len(df) - 1)
    return df.iloc[:split_at], df.iloc[split_at:]


def _params_text(params: dict) -> str:
    return ", ".join(f"{name}={value}" for name, value in params.items())


def _row_prefix(
    *,
    stats: pd.Series,
    prefix: str,
    criteria: SearchCriteria,
    min_trades: int,
) -> dict:
    passed, fail_reasons = check_criteria(stats, criteria, min_trades)
    return {
        f"{prefix}_passed": passed,
        f"{prefix}_score": score_stats(stats),
        f"{prefix}_return_pct": _metric(stats, "Return [%]"),
        f"{prefix}_annual_return_pct": _metric(
            stats,
            "Return (Ann.) [%]",
            _metric(stats, "Return [%]"),
        ),
        f"{prefix}_sharpe": _metric(stats, "Sharpe Ratio"),
        f"{prefix}_max_drawdown_pct": _metric(stats, "Max. Drawdown [%]"),
        f"{prefix}_trades": int(_metric(stats, "# Trades")),
        f"{prefix}_profit_factor": _profit_factor(stats),
        f"{prefix}_fail_reasons": fail_reasons,
    }


def _format_float(value) -> str:
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
            + " | ".join(_format_float(row.get(column, "")) for column in columns)
            + " |"
        )
    return "\n".join(lines)


def _write_search_report(
    *,
    rows: list[dict],
    strategy_name: str,
    pair: str,
    timeframe: str,
    start: str,
    end: str,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    criteria: SearchCriteria,
    combos_evaluated: int,
    tested_candidates: int,
) -> SearchReportPaths:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_pair = pair.replace("/", "-")
    base_name = f"{timestamp}_{strategy_name}_{safe_pair}_{timeframe}_{start}_{end}"
    markdown_path = _REPORT_DIR / f"{base_name}.md"
    summary_path = _REPORT_DIR / f"{base_name}_summary.csv"

    pd.DataFrame(rows, columns=_REPORT_COLUMNS).to_csv(summary_path, index=False)

    display_columns = [
        "strategy",
        "test_passed",
        "test_score",
        "test_annual_return_pct",
        "test_sharpe",
        "test_max_drawdown_pct",
        "test_trades",
        "test_profit_factor",
        "train_score",
        "params",
    ]
    lines = [
        "# Strategy Search",
        "",
        "## Run",
        "",
        f"- Strategy: `{strategy_name}`",
        f"- Pair: `{pair}`",
        f"- Timeframe: `{timeframe}`",
        f"- Range: `{start}` ~ `{end}`",
        f"- Train: `{train_df.index.min()}` ~ `{train_df.index.max()}`",
        f"- Test: `{test_df.index.min()}` ~ `{test_df.index.max()}`",
        f"- Combos evaluated on train: `{combos_evaluated}`",
        f"- Candidates tested out of sample: `{tested_candidates}`",
        f"- Generated at: `{timestamp}`",
        "",
        "## Criteria",
        "",
        f"- Min train trades: `{criteria.min_train_trades}`",
        f"- Min test trades: `{criteria.min_test_trades}`",
        f"- Max drawdown: `{criteria.max_drawdown_pct}%`",
        f"- Min profit factor: `{criteria.min_profit_factor}`",
        f"- Min Sharpe: `{criteria.min_sharpe}`",
        "",
        "## Top Candidates",
        "",
        _markdown_table(rows, display_columns),
        "",
        "## Artifacts",
        "",
        f"- Summary CSV: `{summary_path}`",
        "",
    ]
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return SearchReportPaths(markdown_path=markdown_path, summary_path=summary_path)


def _candidate_strategy_names(strategy_name: str) -> list[str]:
    if strategy_name == "all":
        return list_strategies()
    get_strategy(strategy_name)
    return [strategy_name]


def _search_train_candidates(
    *,
    strategy_name: str,
    train_df: pd.DataFrame,
    settings: dict,
    criteria: SearchCriteria,
) -> tuple[list[dict], int]:
    strategy_cls = get_strategy(strategy_name)
    combos = _generate_param_combos(
        strategy_cls.optimize_params(), _constraint_for_params
    )
    bt_train = make_backtest(train_df, strategy_cls, settings)

    rows = []
    started_at = time.time()
    for index, params in enumerate(combos, start=1):
        stats = bt_train.run(**params)
        row = {
            "strategy": strategy_name,
            "params": params,
            "params_text": _params_text(params),
        }
        row.update(
            _row_prefix(
                stats=stats,
                prefix="train",
                criteria=criteria,
                min_trades=criteria.min_train_trades,
            )
        )
        rows.append(row)

        if index % 100 == 0 or index == len(combos):
            elapsed = time.time() - started_at
            speed = index / elapsed if elapsed > 0 else 0
            logger.info(
                f"search {strategy_name}: {index}/{len(combos)} "
                f"({index / len(combos) * 100:.0f}%), speed={speed:.1f}/s"
            )

    rows.sort(key=lambda row: (row["train_passed"], row["train_score"]), reverse=True)
    return rows, len(combos)


def _test_candidates(
    *,
    rows: list[dict],
    test_df: pd.DataFrame,
    settings: dict,
    criteria: SearchCriteria,
) -> list[dict]:
    tested = []
    backtests = {}
    started_at = time.time()
    total = len(rows)

    for index, row in enumerate(rows, start=1):
        strategy_name = row["strategy"]
        strategy_cls = get_strategy(strategy_name)
        if strategy_name not in backtests:
            backtests[strategy_name] = make_backtest(test_df, strategy_cls, settings)
        stats = backtests[strategy_name].run(**row["params"])
        result = {
            "strategy": row["strategy"],
            "params": row["params_text"],
            "train_passed": row["train_passed"],
            "train_score": row["train_score"],
            "train_return_pct": row["train_return_pct"],
            "train_annual_return_pct": row["train_annual_return_pct"],
            "train_sharpe": row["train_sharpe"],
            "train_max_drawdown_pct": row["train_max_drawdown_pct"],
            "train_trades": row["train_trades"],
            "train_profit_factor": row["train_profit_factor"],
            "train_fail_reasons": row["train_fail_reasons"],
        }
        result.update(
            _row_prefix(
                stats=stats,
                prefix="test",
                criteria=criteria,
                min_trades=criteria.min_test_trades,
            )
        )
        tested.append(result)

        if index % 20 == 0 or index == total:
            elapsed = time.time() - started_at
            speed = index / elapsed if elapsed > 0 else 0
            logger.info(
                f"search oos: {index}/{total} "
                f"({index / total * 100:.0f}%), speed={speed:.1f}/s"
            )

    tested.sort(
        key=lambda row: (
            row["test_passed"],
            row["test_score"],
            row["train_passed"],
            row["train_score"],
        ),
        reverse=True,
    )
    return tested


def run_strategy_search(
    strategy_name: str,
    pair: str,
    timeframe: str,
    start: str,
    end: str,
    *,
    top: int = 20,
    oos_ratio: float = 0.33,
    criteria: SearchCriteria | None = None,
) -> str:
    """Search parameter candidates and rank them by out-of-sample performance."""
    settings = get_settings()
    bt_cfg = settings.get("backtest", {})
    criteria = criteria or SearchCriteria()

    strategy_name = strategy_name or "all"
    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")

    df = load_ohlcv(pair, timeframe, start, end)
    if df.empty:
        return "无数据，请先运行 fetch 拉取数据"

    data_quality = validate_ohlcv_data(df, pair, timeframe, start, end)
    for warning in data_quality.warnings:
        logger.warning(warning)

    train_df, test_df = _split_train_test(df, oos_ratio)
    strategy_names = _candidate_strategy_names(strategy_name)

    train_rows = []
    combos_evaluated = 0
    for name in strategy_names:
        rows, combo_count = _search_train_candidates(
            strategy_name=name,
            train_df=train_df,
            settings=settings,
            criteria=criteria,
        )
        train_rows.extend(rows)
        combos_evaluated += combo_count

    train_rows.sort(
        key=lambda row: (row["train_passed"], row["train_score"]), reverse=True
    )
    candidates_to_test = train_rows[: max(top * 5, top)]
    tested_rows = _test_candidates(
        rows=candidates_to_test,
        test_df=test_df,
        settings=settings,
        criteria=criteria,
    )
    top_rows = tested_rows[:top]

    report_paths = _write_search_report(
        rows=top_rows,
        strategy_name=strategy_name,
        pair=pair,
        timeframe=timeframe,
        start=start,
        end=end,
        train_df=train_df,
        test_df=test_df,
        criteria=criteria,
        combos_evaluated=combos_evaluated,
        tested_candidates=len(candidates_to_test),
    )

    display = pd.DataFrame(top_rows)[
        [
            "strategy",
            "test_passed",
            "test_score",
            "test_annual_return_pct",
            "test_sharpe",
            "test_max_drawdown_pct",
            "test_trades",
            "test_profit_factor",
            "params",
        ]
    ]

    return "\n".join(
        [
            "=== 策略候选搜索 ===",
            f"训练区间: {train_df.index.min()} ~ {train_df.index.max()}",
            f"样本外区间: {test_df.index.min()} ~ {test_df.index.max()}",
            f"训练组合数: {combos_evaluated}",
            f"样本外测试候选数: {len(candidates_to_test)}",
            "",
            display.to_string(index=False),
            "",
            "=== 数据质量 ===",
            *data_quality.summary_lines(),
            "",
            f"报告已生成: {report_paths.markdown_path}",
            f"汇总 CSV: {report_paths.summary_path}",
        ]
    )
