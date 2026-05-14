from strategies.base import BaseStrategy
from strategies.composite.regime_switch import RegimeSwitch
from strategies.mean_revert.bollinger_revert import BollingerRevert
from strategies.mean_revert.rsi_revert import RsiRevert
from strategies.trend.ma_cross import MaCross
from strategies.trend.trend_breakout import TrendBreakout


_STRATEGIES: dict[str, type[BaseStrategy]] = {
    "bollinger_revert": BollingerRevert,
    "ma_cross": MaCross,
    "regime_switch": RegimeSwitch,
    "rsi_revert": RsiRevert,
    "trend_breakout": TrendBreakout,
}


def get_strategy(name: str) -> type[BaseStrategy]:
    try:
        return _STRATEGIES[name]
    except KeyError as exc:
        available = ", ".join(list_strategies())
        raise KeyError(f"未知策略: {name}，可选: {available}") from exc


def list_strategies() -> list[str]:
    return sorted(_STRATEGIES)


def strategy_registry() -> dict[str, type[BaseStrategy]]:
    return dict(_STRATEGIES)
