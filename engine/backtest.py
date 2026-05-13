from datetime import datetime, timezone

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
        fast_period=range(10, 55, 5),
        slow_period=range(30, 210, 10),
        trend_period=range(100, 350, 50),
        atr_period=range(10, 22, 2),
        atr_multiplier=[i / 10 for i in range(15, 40, 5)],
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
