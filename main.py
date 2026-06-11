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
@click.option("--pair", "-p", default="ETH/USDT", help="交易对")
@click.option("--timeframe", "-t", default=None, help="K线周期，如 1h / 4h / 1d")
@click.option("--start", default=None, help="回测开始日期，如 2024-01-01")
@click.option("--end", default=None, help="回测结束日期，如 2025-01-01")
@click.option(
    "--param", "raw_params", multiple=True, help="策略参数覆盖，如 fast_period=40"
)
def backtest(strategy, pair, timeframe, start, end, raw_params):
    """运行策略回测"""
    from engine.backtest import run_backtest
    from engine.params import parse_strategy_params
    from strategies.registry import get_strategy, list_strategies

    strategies = list_strategies()
    if strategy not in strategies:
        click.echo(f"未知策略: {strategy}，可选: {', '.join(strategies)}")
        return
    try:
        strategy_params = parse_strategy_params(raw_params, get_strategy(strategy))
    except ValueError as exc:
        click.echo(str(exc))
        return
    click.echo(run_backtest(strategy, pair, timeframe, start, end, strategy_params))


@cli.command()
@click.option("--strategy", "-s", required=True, help="策略名称，如 ma_cross")
@click.option("--timeframe", "-t", default=None, help="K线周期")
@click.option("--start", default=None, help="开始日期，如 2025-01-01")
@click.option("--end", default=None, help="结束日期，如 2026-01-01")
def optimize(strategy, timeframe, start, end):
    """网格搜索最优策略参数"""
    from engine.backtest import run_optimize
    from strategies.registry import list_strategies

    strategies = list_strategies()
    if strategy not in strategies:
        click.echo(f"未知策略: {strategy}，可选: {', '.join(strategies)}")
        return
    click.echo(run_optimize(strategy, timeframe, start, end))


@cli.command("search")
@click.option("--strategy", "-s", default="all", help="策略名称，或 all 搜索全部策略")
@click.option("--pair", "-p", default="ETH/USDT", help="交易对")
@click.option("--timeframe", "-t", default=None, help="K线周期")
@click.option("--start", default=None, help="开始日期")
@click.option("--end", default=None, help="结束日期")
@click.option("--top", default=20, help="输出前 N 个候选")
@click.option("--oos-ratio", default=0.33, help="尾部样本外数据比例")
@click.option("--min-train-trades", default=30, help="训练段最少交易数")
@click.option("--min-test-trades", default=5, help="样本外最少交易数")
@click.option("--max-drawdown", default=15.0, help="最大回撤绝对值上限，百分比")
@click.option("--min-profit-factor", default=1.1, help="最低 Profit Factor")
@click.option("--min-sharpe", default=0.3, help="最低 Sharpe")
def search(
    strategy,
    pair,
    timeframe,
    start,
    end,
    top,
    oos_ratio,
    min_train_trades,
    min_test_trades,
    max_drawdown,
    min_profit_factor,
    min_sharpe,
):
    """搜索并排序策略参数候选，训练段优化，尾部样本外验证。"""
    from engine.search import SearchCriteria, run_strategy_search
    from strategies.registry import list_strategies

    strategies = list_strategies()
    if strategy != "all" and strategy not in strategies:
        click.echo(f"未知策略: {strategy}，可选: all, {', '.join(strategies)}")
        return

    criteria = SearchCriteria(
        min_train_trades=min_train_trades,
        min_test_trades=min_test_trades,
        max_drawdown_pct=max_drawdown,
        min_profit_factor=min_profit_factor,
        min_sharpe=min_sharpe,
    )
    click.echo(
        run_strategy_search(
            strategy,
            pair,
            timeframe,
            start,
            end,
            top=top,
            oos_ratio=oos_ratio,
            criteria=criteria,
        )
    )


@cli.command()
@click.option("--strategy", "-s", required=True, help="策略名称，如 ma_cross")
@click.option("--pair", "-p", default="ETH/USDT", help="交易对")
@click.option("--timeframe", "-t", default=None, help="K线周期")
@click.option("--start", default=None, help="开始日期")
@click.option("--end", default=None, help="结束日期")
@click.option("--train-months", default=12, help="训练窗口月数")
@click.option("--test-months", default=6, help="测试窗口月数")
@click.option(
    "--param", "raw_params", multiple=True, help="固定策略参数，如 fast_period=40"
)
def walkforward(
    strategy, pair, timeframe, start, end, train_months, test_months, raw_params
):
    """Walk-Forward 分析：滚动窗口训练+测试，验证参数稳定性"""
    from engine.backtest import run_walk_forward
    from engine.params import parse_strategy_params
    from strategies.registry import get_strategy, list_strategies

    strategies = list_strategies()
    if strategy not in strategies:
        click.echo(f"未知策略: {strategy}，可选: {', '.join(strategies)}")
        return
    try:
        strategy_params = parse_strategy_params(raw_params, get_strategy(strategy))
    except ValueError as exc:
        click.echo(str(exc))
        return
    click.echo(
        run_walk_forward(
            strategy,
            pair,
            timeframe,
            start,
            end,
            train_months,
            test_months,
            strategy_params,
        )
    )


@cli.command()
@click.option("--strategy", "-s", required=True, help="策略名称，如 regime_switch")
@click.option("--pair", "-p", default="ETH/USDT", help="交易对")
@click.option("--timeframe", "-t", default=None, help="K线周期")
@click.option("--start", default=None, help="开始日期，如 2024-01-01")
@click.option("--end", default=None, help="结束日期，如 2025-01-01")
@click.option(
    "--param", "raw_params", multiple=True, help="策略参数覆盖，如 fast_period=40"
)
def evaluate(strategy, pair, timeframe, start, end, raw_params):
    """评估默认参数：全区间、年度/季度分段和成本压力测试"""
    from engine.evaluation import run_strategy_evaluation
    from engine.params import parse_strategy_params
    from strategies.registry import get_strategy, list_strategies

    strategies = list_strategies()
    if strategy not in strategies:
        click.echo(f"未知策略: {strategy}，可选: {', '.join(strategies)}")
        return
    try:
        strategy_params = parse_strategy_params(raw_params, get_strategy(strategy))
    except ValueError as exc:
        click.echo(str(exc))
        return
    click.echo(
        run_strategy_evaluation(strategy, pair, timeframe, start, end, strategy_params)
    )


@cli.command()
@click.option("--pair", "-p", default="ETH/USDT", help="交易对")
@click.option("--timeframe", "-t", default="1h", help="K线周期")
def signal(pair, timeframe):
    """基于 MaCross 策略输出当前买卖信号"""
    from engine.signal import get_signal

    click.echo(get_signal(pair, timeframe))


@cli.command()
@click.option("--pair", "-p", default="ETH/USDT", help="交易对")
@click.option("--timeframe", "-t", default="1h", help="K线周期")
def analyze(pair, timeframe):
    """读 DB 行情，规则定倾向 + LLM 解读当前走势（仅描述，非买卖建议）"""
    from engine.analyst import analyze as run_analyze

    click.echo(run_analyze(pair, timeframe))


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
    end_dt = (
        datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if end else None
    )

    logger.info(f"开始拉取: {pair} {timeframe} from {start} to {end or 'now'}")
    total = fetch_all_klines(pair, timeframe, start_dt, end_dt)
    click.echo(f"完成，共写入 {total} 条数据")


if __name__ == "__main__":
    cli()
