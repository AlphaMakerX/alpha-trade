from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

import pandas as pd
from backtesting import Backtest
from loguru import logger

from data.storage.postgres import query_klines
from strategies.trend.ma_cross import MaCross
from utils.config import get_settings

STRATEGY_MAP = {
    "ma_cross": MaCross,
}


def _load_data(pair: str, timeframe: str, start: str | None, end: str | None) -> pd.DataFrame:
    """从 DB 加载 K线数据并转换为 Backtesting.py 格式。"""
    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc) if start else None
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if end else None

    df = query_klines(pair, timeframe, start_dt, end_dt)
    if df.empty:
        return df

    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })
    return df.set_index("open_time")


def run_backtest(strategy_name: str, timeframe: str, start: str, end: str) -> str:
    """运行回测，返回格式化的统计结果。"""
    settings = get_settings()
    bt_cfg = settings.get("backtest", {})
    trading = settings.get("trading", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")
    pair = trading.get("pair", "ETH/USDT")

    logger.info(f"开始回测: strategy={strategy_name}, timeframe={timeframe}")
    logger.info(f"回测区间: {start} ~ {end}")
    logger.info(f"初始资金: {bt_cfg.get('initial_capital', 10000)} USDT")

    df = _load_data(pair, timeframe, start, end)
    if df.empty:
        return "无数据，请先运行 fetch 拉取数据"

    bt = Backtest(
        df,
        STRATEGY_MAP[strategy_name],
        cash=bt_cfg.get("initial_capital", 10000),
        commission=trading.get("commission", 0.001),
    )
    return str(bt.run())


def run_optimize(strategy_name: str, timeframe: str, start: str, end: str) -> str:
    """网格搜索最优参数，返回格式化结果。"""
    settings = get_settings()
    bt_cfg = settings.get("backtest", {})
    trading = settings.get("trading", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")
    pair = trading.get("pair", "ETH/USDT")

    df = _load_data(pair, timeframe, start, end)
    if df.empty:
        return "无数据，请先运行 fetch 拉取数据"

    bt = Backtest(
        df,
        STRATEGY_MAP[strategy_name],
        cash=bt_cfg.get("initial_capital", 10000),
        commission=trading.get("commission", 0.001),
    )

    logger.info("开始参数优化（网格搜索）...")

    stats = bt.optimize(
        **_OPTIMIZE_PARAMS,
        constraint=lambda p: p.fast_period < p.slow_period,
        maximize="SQN",
    )

    s = stats["_strategy"]
    lines = [
        "\n=== 最优参数 ===",
        f"fast_period:     {s.fast_period}",
        f"slow_period:     {s.slow_period}",
        f"trend_period:    {s.trend_period}",
        f"atr_period:      {s.atr_period}",
        f"atr_multiplier:  {s.atr_multiplier}",
        "\n=== 回测指标 ===",
        str(stats),
    ]
    return "\n".join(lines)


_OPTIMIZE_PARAMS = {
    "fast_period": range(10, 55, 5),
    "slow_period": range(30, 210, 10),
    "trend_period": range(100, 350, 50),
    "atr_period": range(10, 22, 2),
    "atr_multiplier": [i / 10 for i in range(15, 40, 5)],
}


def run_walk_forward(
    strategy_name: str,
    timeframe: str,
    start: str,
    end: str,
    train_months: int,
    test_months: int,
) -> str:
    """Walk-Forward 分析：滚动窗口训练+测试。"""
    settings = get_settings()
    bt_cfg = settings.get("backtest", {})
    trading = settings.get("trading", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")
    pair = trading.get("pair", "ETH/USDT")
    cash = bt_cfg.get("initial_capital", 10000)
    commission = trading.get("commission", 0.001)
    strategy_cls = STRATEGY_MAP[strategy_name]

    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # 加载全量数据
    df_all = _load_data(pair, timeframe, start, end)
    if df_all.empty:
        return "无数据，请先运行 fetch 拉取数据"

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

        # 训练：优化参数
        bt_train = Backtest(train_df, strategy_cls, cash=cash, commission=commission)
        train_stats = bt_train.optimize(
            **_OPTIMIZE_PARAMS,
            constraint=lambda p: p.fast_period < p.slow_period,
            maximize="SQN",
        )

        # 提取最优参数
        s = train_stats["_strategy"]
        best_params = {
            "fast_period": s.fast_period,
            "slow_period": s.slow_period,
            "trend_period": s.trend_period,
            "atr_period": s.atr_period,
            "atr_multiplier": s.atr_multiplier,
        }

        # 测试：用训练得到的参数跑回测
        bt_test = Backtest(test_df, strategy_cls, cash=cash, commission=commission)
        test_stats = bt_test.run(**best_params)

        results.append({
            "window": window_num,
            "train": f"{window_start.date()} ~ {train_end.date()}",
            "test": f"{train_end.date()} ~ {test_end.date()}",
            "params": best_params,
            "return": test_stats["Return [%]"],
            "max_dd": test_stats["Max. Drawdown [%]"],
            "trades": test_stats["# Trades"],
            "win_rate": test_stats["Win Rate [%]"],
            "sqn": test_stats["SQN"],
        })

        window_start = train_end
        window_num += 1

    # 处理最后一段不足 test_months 的数据
    if window_start + relativedelta(months=train_months) < end_dt:
        train_end = window_start + relativedelta(months=train_months)
        test_df = df_all[(df_all.index >= train_end) & (df_all.index < end_dt)]
        train_df = df_all[(df_all.index >= window_start) & (df_all.index < train_end)]

        if not train_df.empty and not test_df.empty:
            logger.info(
                f"窗口 {window_num}: 训练 {window_start.date()} ~ {train_end.date()}, "
                f"测试 {train_end.date()} ~ {end_dt.date()}"
            )

            bt_train = Backtest(train_df, strategy_cls, cash=cash, commission=commission)
            train_stats = bt_train.optimize(
                **_OPTIMIZE_PARAMS,
                constraint=lambda p: p.fast_period < p.slow_period,
                maximize="SQN",
            )

            s = train_stats["_strategy"]
            best_params = {
                "fast_period": s.fast_period,
                "slow_period": s.slow_period,
                "trend_period": s.trend_period,
                "atr_period": s.atr_period,
                "atr_multiplier": s.atr_multiplier,
            }

            bt_test = Backtest(test_df, strategy_cls, cash=cash, commission=commission)
            test_stats = bt_test.run(**best_params)

            results.append({
                "window": window_num,
                "train": f"{window_start.date()} ~ {train_end.date()}",
                "test": f"{train_end.date()} ~ {end_dt.date()}",
                "params": best_params,
                "return": test_stats["Return [%]"],
                "max_dd": test_stats["Max. Drawdown [%]"],
                "trades": test_stats["# Trades"],
                "win_rate": test_stats["Win Rate [%]"],
                "sqn": test_stats["SQN"],
            })

    # 格式化输出
    lines = ["\n=== Walk-Forward 分析结果 ===\n"]
    for r in results:
        lines.append(f"窗口 {r['window']}: {r['test']}")
        p = r["params"]
        lines.append(f"  参数: fast={p['fast_period']}, slow={p['slow_period']}, "
                      f"trend={p['trend_period']}, atr={p['atr_period']}, mult={p['atr_multiplier']}")
        lines.append(f"  收益: {r['return']:.2f}%  回撤: {r['max_dd']:.2f}%  "
                      f"交易: {r['trades']}  胜率: {r['win_rate']:.1f}%  SQN: {r['sqn']:.2f}")
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
