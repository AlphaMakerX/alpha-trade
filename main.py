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
    from engine.backtest import STRATEGY_MAP, run_backtest

    if strategy not in STRATEGY_MAP:
        click.echo(f"未知策略: {strategy}，可选: {', '.join(STRATEGY_MAP)}")
        return
    click.echo(run_backtest(strategy, timeframe, start, end))


@cli.command()
@click.option("--strategy", "-s", required=True, help="策略名称，如 ma_cross")
@click.option("--timeframe", "-t", default=None, help="K线周期")
@click.option("--start", default=None, help="开始日期，如 2025-01-01")
@click.option("--end", default=None, help="结束日期，如 2026-01-01")
def optimize(strategy, timeframe, start, end):
    """网格搜索最优策略参数"""
    from engine.backtest import STRATEGY_MAP, run_optimize

    if strategy not in STRATEGY_MAP:
        click.echo(f"未知策略: {strategy}，可选: {', '.join(STRATEGY_MAP)}")
        return
    click.echo(run_optimize(strategy, timeframe, start, end))


@cli.command()
@click.option("--strategy", "-s", required=True, help="策略名称，如 ma_cross")
@click.option("--timeframe", "-t", default=None, help="K线周期")
@click.option("--start", default=None, help="开始日期")
@click.option("--end", default=None, help="结束日期")
@click.option("--train-months", default=12, help="训练窗口月数")
@click.option("--test-months", default=6, help="测试窗口月数")
def walkforward(strategy, timeframe, start, end, train_months, test_months):
    """Walk-Forward 分析：滚动窗口训练+测试，验证参数稳定性"""
    from engine.backtest import STRATEGY_MAP, run_walk_forward

    if strategy not in STRATEGY_MAP:
        click.echo(f"未知策略: {strategy}，可选: {', '.join(STRATEGY_MAP)}")
        return
    click.echo(run_walk_forward(strategy, timeframe, start, end, train_months, test_months))


@cli.command()
@click.option("--pair", "-p", default="ETH/USDT", help="交易对")
@click.option("--timeframe", "-t", default="1h", help="K线周期")
def signal(pair, timeframe):
    """基于 MaCross 策略输出当前买卖信号"""
    from engine.signal import get_signal

    click.echo(get_signal(pair, timeframe))


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
@click.option("--end", "-e", default=None, help="结束日期，如 2025-01-01")
def fetch(pair, timeframe, start, end):
    """从 Binance 拉取 K线数据并存入数据库"""
    from datetime import datetime, timezone

    from data.feeds.binance import fetch_all_klines

    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if end else None

    logger.info(f"开始拉取: {pair} {timeframe} from {start} to {end or 'now'}")
    total = fetch_all_klines(pair, timeframe, start_dt, end_dt)
    click.echo(f"完成，共写入 {total} 条数据")


if __name__ == "__main__":
    cli()
