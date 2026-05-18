import math
import time
from itertools import product

from dateutil.relativedelta import relativedelta

import pandas as pd
from backtesting import Backtest
from loguru import logger

from analysis.data_quality import validate_ohlcv_data
from analysis.report import write_backtest_report
from engine.data import load_ohlcv, parse_utc_date
from engine.factory import backtest_options, make_backtest
from engine.params import format_strategy_params
from strategies.registry import get_strategy, strategy_registry
from utils.config import get_settings

STRATEGY_MAP = strategy_registry()


def _log_data_quality(data_quality) -> None:
    for warning in data_quality.warnings:
        logger.warning(warning)


def run_backtest(
    strategy_name: str,
    pair: str,
    timeframe: str,
    start: str,
    end: str,
    strategy_params: dict[str, object],
) -> str:
    """运行回测，返回格式化的统计结果。"""
    settings = get_settings()
    bt_cfg = settings.get("backtest", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")

    logger.info(
        f"开始回测: strategy={strategy_name}, pair={pair}, timeframe={timeframe}"
    )
    logger.info(f"回测区间: {start} ~ {end}")
    logger.info(f"初始资金: {bt_cfg.get('initial_capital', 10000)} USDT")

    df = load_ohlcv(pair, timeframe, start, end)
    if df.empty:
        return "无数据，请先运行 fetch 拉取数据"

    data_quality = validate_ohlcv_data(df, pair, timeframe, start, end)
    _log_data_quality(data_quality)

    bt = make_backtest(df, get_strategy(strategy_name), settings)
    stats = bt.run(**strategy_params)
    report_paths = write_backtest_report(
        stats=stats,
        strategy_name=strategy_name,
        pair=pair,
        timeframe=timeframe,
        start=start,
        end=end,
        backtest_options=backtest_options(settings),
        data_quality=data_quality,
    )

    lines = [
        str(stats),
        "",
        "=== 数据质量 ===",
        *data_quality.summary_lines(),
        "",
        f"报告已生成: {report_paths.markdown_path}",
    ]
    if strategy_params:
        lines.insert(1, f"参数覆盖: {format_strategy_params(strategy_params)}")
    if report_paths.trades_path is not None:
        lines.append(f"交易明细: {report_paths.trades_path}")
    return "\n".join(lines)


def _generate_param_combos(opt_params: dict, constraint=None) -> list[dict]:
    """生成参数组合列表，应用约束过滤。"""
    names = list(opt_params.keys())
    values = [list(v) for v in opt_params.values()]
    combos = [dict(zip(names, combo)) for combo in product(*values)]
    if constraint:
        combos = [c for c in combos if constraint(c)]
    return combos


def _grid_search_with_progress(
    bt: Backtest, combos: list[dict], label: str = ""
) -> tuple[dict, pd.Series]:
    """带进度输出的网格搜索，返回 (最优参数, 最优 stats)。"""
    total = len(combos)
    best_sqn = -math.inf
    best_params = None
    best_stats = None
    start_time = time.time()

    for i, params in enumerate(combos):
        stats = bt.run(**params)
        sqn = stats["SQN"]

        if not math.isnan(sqn) and sqn > best_sqn:
            best_sqn = sqn
            best_params = params
            best_stats = stats

        if (i + 1) % 50 == 0 or i + 1 == total:
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed
            eta = (total - i - 1) / speed if speed > 0 else 0
            logger.info(
                f"{label}进度: {i + 1}/{total} ({(i + 1) / total * 100:.0f}%) "
                f"已用 {elapsed:.0f}s, 预计剩余 {eta:.0f}s, "
                f"当前最优 SQN={best_sqn:.2f}"
            )

    return best_params, best_stats


def run_optimize(strategy_name: str, timeframe: str, start: str, end: str) -> str:
    """网格搜索最优参数，带进度输出。"""
    settings = get_settings()
    bt_cfg = settings.get("backtest", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")
    pair = settings.get("trading", {}).get("pair", "ETH/USDT")

    df = load_ohlcv(pair, timeframe, start, end)
    if df.empty:
        return "无数据，请先运行 fetch 拉取数据"
    _log_data_quality(validate_ohlcv_data(df, pair, timeframe, start, end))

    strategy_cls = get_strategy(strategy_name)
    opt_params = strategy_cls.optimize_params()
    constraint_fn = (
        (lambda c: c["fast_period"] < c["slow_period"])
        if "fast_period" in opt_params
        else None
    )
    combos = _generate_param_combos(opt_params, constraint_fn)

    bt = make_backtest(df, strategy_cls, settings)

    logger.info(f"开始参数优化: 策略={strategy_name}, 组合数={len(combos)}")

    best_params, best_stats = _grid_search_with_progress(bt, combos)

    lines = ["\n=== 最优参数 ==="]
    for param_name in opt_params:
        lines.append(f"  {param_name}: {best_params[param_name]}")
    lines.append("\n=== 回测指标 ===")
    lines.append(str(best_stats))
    return "\n".join(lines)


def run_walk_forward(
    strategy_name: str,
    pair: str,
    timeframe: str,
    start: str,
    end: str,
    train_months: int,
    test_months: int,
    strategy_params: dict[str, object],
) -> str:
    """Walk-Forward 分析：滚动窗口训练+测试。"""
    settings = get_settings()
    bt_cfg = settings.get("backtest", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")
    strategy_cls = get_strategy(strategy_name)

    start_dt = parse_utc_date(start)
    end_dt = parse_utc_date(end)

    # 加载全量数据
    df_all = load_ohlcv(pair, timeframe, start, end)
    if df_all.empty:
        return "无数据，请先运行 fetch 拉取数据"
    _log_data_quality(validate_ohlcv_data(df_all, pair, timeframe, start, end))

    opt_params = strategy_cls.optimize_params()
    constraint_fn = (
        (lambda c: c["fast_period"] < c["slow_period"])
        if "fast_period" in opt_params
        else None
    )
    combos = _generate_param_combos(opt_params, constraint_fn)

    def _optimize_and_test(train_df, test_df, win_num, test_label):
        if strategy_params:
            best_params = strategy_params
        else:
            bt_train = make_backtest(train_df, strategy_cls, settings)
            best_params, _ = _grid_search_with_progress(
                bt_train, combos, label=f"窗口{win_num} "
            )

        bt_test = make_backtest(test_df, strategy_cls, settings)
        test_stats = bt_test.run(**best_params)

        return {
            "window": win_num,
            "test": test_label,
            "params": best_params,
            "return": test_stats["Return [%]"],
            "max_dd": test_stats["Max. Drawdown [%]"],
            "trades": test_stats["# Trades"],
            "win_rate": test_stats["Win Rate [%]"],
            "sqn": test_stats["SQN"],
        }

    # 滚动窗口
    results = []
    window_start = start_dt
    window_num = 1

    while window_start + relativedelta(months=train_months + test_months) <= end_dt:
        train_end = window_start + relativedelta(months=train_months)
        test_end = train_end + relativedelta(months=test_months)

        train_df = df_all[(df_all.index >= window_start) & (df_all.index < train_end)]
        test_df = df_all[(df_all.index >= train_end) & (df_all.index < test_end)]

        if train_df.empty or test_df.empty:
            window_start = train_end
            continue

        logger.info(
            f"窗口 {window_num}: 训练 {window_start.date()} ~ {train_end.date()}, "
            f"测试 {train_end.date()} ~ {test_end.date()}"
        )

        results.append(
            _optimize_and_test(
                train_df, test_df, window_num, f"{train_end.date()} ~ {test_end.date()}"
            )
        )

        window_start = train_end
        window_num += 1

    # 处理最后一段不足 test_months 的数据
    if window_start + relativedelta(months=train_months) < end_dt:
        train_end = window_start + relativedelta(months=train_months)
        train_df = df_all[(df_all.index >= window_start) & (df_all.index < train_end)]
        test_df = df_all[(df_all.index >= train_end) & (df_all.index < end_dt)]

        if not train_df.empty and not test_df.empty:
            logger.info(
                f"窗口 {window_num}: 训练 {window_start.date()} ~ {train_end.date()}, "
                f"测试 {train_end.date()} ~ {end_dt.date()}"
            )

            results.append(
                _optimize_and_test(
                    train_df,
                    test_df,
                    window_num,
                    f"{train_end.date()} ~ {end_dt.date()}",
                )
            )

    # 格式化输出
    lines = ["\n=== Walk-Forward 分析结果 ===\n"]
    for r in results:
        lines.append(f"窗口 {r['window']}: {r['test']}")
        p = r["params"]
        param_str = ", ".join(f"{k}={v}" for k, v in p.items())
        lines.append(f"  参数: {param_str}")
        lines.append(
            f"  收益: {r['return']:.2f}%  回撤: {r['max_dd']:.2f}%  "
            f"交易: {r['trades']}  胜率: {r['win_rate']:.1f}%  SQN: {r['sqn']:.2f}"
        )
        lines.append("")

    # 汇总
    if results:
        avg_return = sum(r["return"] for r in results) / len(results)
        avg_dd = sum(r["max_dd"] for r in results) / len(results)
        profitable = sum(1 for r in results if r["return"] > 0)
        lines.append(f"=== 汇总 ===")
        lines.append(f"窗口数: {len(results)}")
        lines.append(f"盈利窗口: {profitable}/{len(results)}")
        lines.append(f"平均收益: {avg_return:.2f}%")
        lines.append(f"平均回撤: {avg_dd:.2f}%")

    return "\n".join(lines)
