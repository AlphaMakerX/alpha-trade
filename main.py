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
    settings = get_settings()
    bt_cfg = settings.get("backtest", {})

    timeframe = timeframe or bt_cfg.get("timeframe", "1h")
    start = start or bt_cfg.get("start_date")
    end = end or bt_cfg.get("end_date")

    logger.info(f"开始回测: strategy={strategy}, timeframe={timeframe}")
    logger.info(f"回测区间: {start} ~ {end}")
    logger.info(f"初始资金: {bt_cfg.get('initial_capital', 10000)} USDT")

    # TODO: Phase 4 实现回测引擎调用
    logger.warning("回测引擎尚未实现，请等待后续开发")


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


if __name__ == "__main__":
    cli()
