import pandas as pd
from backtesting import Backtest


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_float(value, default: float) -> float:
    if value is None:
        return default
    return float(value)


def backtest_options(settings: dict) -> dict:
    """Build one canonical Backtesting.py config from project settings."""
    bt_cfg = settings.get("backtest", {})
    trading = settings.get("trading", {})

    return {
        "cash": _as_float(bt_cfg.get("initial_capital"), 10000.0),
        "commission": _as_float(trading.get("commission"), 0.001),
        # Backtesting.py models spread as a relative bid/ask cost. We map the
        # configured slippage into spread so every run uses the same cost model.
        "spread": _as_float(trading.get("slippage"), 0.0),
        "trade_on_close": _as_bool(bt_cfg.get("trade_on_close"), False),
        "exclusive_orders": _as_bool(bt_cfg.get("exclusive_orders"), True),
        "finalize_trades": _as_bool(bt_cfg.get("finalize_trades"), True),
    }


def _strategy_with_risk_settings(strategy_cls, settings: dict):
    risk_cfg = {
        name: value
        for name, value in settings.get("risk", {}).items()
        if hasattr(strategy_cls, name)
    }
    if not risk_cfg:
        return strategy_cls

    name = f"{strategy_cls.__name__}WithRisk"
    return type(name, (strategy_cls,), risk_cfg)


def make_backtest(df: pd.DataFrame, strategy_cls, settings: dict) -> Backtest:
    """Create Backtest objects through a single strict factory."""
    return Backtest(
        df,
        _strategy_with_risk_settings(strategy_cls, settings),
        **backtest_options(settings),
    )
