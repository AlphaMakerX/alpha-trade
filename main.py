import click
from loguru import logger

from utils.config import get_settings
from utils.logger import setup_logger


@click.group()
def cli():
    """Alpha Trade - ETH/USDT 量化交易系统"""
    setup_logger()


@cli.command()
@click.option("--strategy", "-s", required=True, help="策略名称，如 ma_cross")
@click.option("--timeframe", "-t", default=None, help="K线周期，如 1h / 4h / 1d")
@click.option("--start", default=None, help="回测开始日期，如 2024-01-01")
@click.option("--end", default=None, help="回测结束日期，如 2025-01-01")
def backtest(strategy, timeframe, start, end):
    """运行策略回测"""
    from datetime import datetime, timezone

    from backtesting import Backtest

    from data.storage.postgres import query_klines
    from strategies.trend.ma_cross import MaCross

    STRATEGY_MAP = {
        "ma_cross": MaCross,
    }

    if strategy not in STRATEGY_MAP:
        click.echo(f"未知策略: {strategy}，可选: {', '.join(STRATEGY_MAP)}")
        return

    settings = get_settings()
    bt_cfg = settings.get("backtest", {})
    trading = settings.get("trading", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")
    pair = trading.get("pair", "ETH/USDT")
    initial_capital = bt_cfg.get("initial_capital", 10000)
    commission = trading.get("commission", 0.001)

    logger.info(f"开始回测: strategy={strategy}, timeframe={timeframe}")
    logger.info(f"回测区间: {start} ~ {end}")
    logger.info(f"初始资金: {initial_capital} USDT")

    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc) if start else None
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if end else None

    df = query_klines(pair, timeframe, start_dt, end_dt)
    if df.empty:
        click.echo("无数据，请先运行 fetch 拉取数据")
        return

    # Backtesting.py 要求列名首字母大写，index 为 datetime
    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })
    df = df.set_index("open_time")

    bt = Backtest(
        df,
        STRATEGY_MAP[strategy],
        cash=initial_capital,
        commission=commission,
    )
    stats = bt.run()
    click.echo(stats)


@cli.command()
@click.option("--strategy", "-s", required=True, help="策略名称，如 ma_cross")
@click.option("--timeframe", "-t", default=None, help="K线周期")
@click.option("--start", default=None, help="开始日期，如 2025-01-01")
@click.option("--end", default=None, help="结束日期，如 2026-01-01")
def optimize(strategy, timeframe, start, end):
    """网格搜索最优策略参数"""
    from datetime import datetime, timezone

    from backtesting import Backtest

    from data.storage.postgres import query_klines
    from strategies.trend.ma_cross import MaCross

    STRATEGY_MAP = {
        "ma_cross": MaCross,
    }

    if strategy not in STRATEGY_MAP:
        click.echo(f"未知策略: {strategy}，可选: {', '.join(STRATEGY_MAP)}")
        return

    settings = get_settings()
    bt_cfg = settings.get("backtest", {})
    trading = settings.get("trading", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")
    pair = trading.get("pair", "ETH/USDT")
    initial_capital = bt_cfg.get("initial_capital", 10000)
    commission = trading.get("commission", 0.001)

    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc) if start else None
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if end else None

    df = query_klines(pair, timeframe, start_dt, end_dt)
    if df.empty:
        click.echo("无数据，请先运行 fetch 拉取数据")
        return

    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })
    df = df.set_index("open_time")

    bt = Backtest(
        df,
        STRATEGY_MAP[strategy],
        cash=initial_capital,
        commission=commission,
    )

    logger.info("开始参数优化（网格搜索）...")

    stats = bt.optimize(
        fast_period=range(5, 55, 5),
        slow_period=range(20, 210, 10),
        trend_period=range(100, 350, 50),
        stop_loss=[i / 100 for i in range(3, 9)],
        take_profit=[i / 100 for i in range(5, 25, 5)],
        constraint=lambda p: p.fast_period < p.slow_period,
        maximize="SQN",
    )

    click.echo("\n=== 最优参数 ===")
    s = stats["_strategy"]
    click.echo(f"fast_period:   {s.fast_period}")
    click.echo(f"slow_period:   {s.slow_period}")
    click.echo(f"trend_period:  {s.trend_period}")
    click.echo(f"stop_loss:     {s.stop_loss}")
    click.echo(f"take_profit:   {s.take_profit}")
    click.echo("\n=== 回测指标 ===")
    click.echo(stats)


@cli.command()
def info():
    """显示当前配置信息"""
    settings = get_settings()
    trading = settings.get("trading", {})
    click.echo(f"交易对: {trading.get('pair')}")
    click.echo(f"手续费: {trading.get('commission')}")
    click.echo(f"滑点: {trading.get('slippage')}")
    data_cfg = settings.get("data", {})
    click.echo(f"周期: {', '.join(data_cfg.get('timeframes', []))}")


@cli.command()
def initdb():
    """初始化数据库表结构"""
    from data.storage.postgres import init_db

    init_db()
    click.echo("数据库初始化完成")


@cli.command()
@click.option("--pair", "-p", default="ETH/USDT", help="交易对")
@click.option("--timeframe", "-t", default="1h", help="K线周期")
@click.option("--start", "-s", required=True, help="开始日期，如 2024-01-01")
def fetch(pair, timeframe, start):
    """从 Binance 拉取 K线数据并存入数据库"""
    from datetime import datetime, timezone

    from data.feeds.binance import fetch_all_klines

    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    logger.info(f"开始拉取: {pair} {timeframe} from {start}")
    total = fetch_all_klines(pair, timeframe, start_dt)
    click.echo(f"完成，共写入 {total} 条数据")



if __name__ == "__main__":
    cli()
