from strategies.base import BaseStrategy
from strategies.mean_revert.rsi_revert import RsiRevert
from strategies.trend.ma_cross import MaCross


_STRATEGIES: dict[str, type[BaseStrategy]] = {
    "ma_cross": MaCross,
    "rsi_revert": RsiRevert,
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
