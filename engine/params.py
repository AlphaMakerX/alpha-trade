def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError(f"布尔参数值无效: {value}")


def _parse_value(value: str, current_value: object) -> object:
    if isinstance(current_value, bool):
        return _parse_bool(value)
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        return int(value)
    if isinstance(current_value, float):
        return float(value)
    if isinstance(current_value, str):
        return value
    raise ValueError(f"不支持覆盖该参数类型: {type(current_value).__name__}")


def parse_strategy_params(
    raw_params: tuple[str, ...], strategy_cls: type
) -> dict[str, object]:
    params: dict[str, object] = {}
    for raw_param in raw_params:
        if "=" not in raw_param:
            raise ValueError(f"参数格式必须是 name=value: {raw_param}")

        name, raw_value = raw_param.split("=", 1)
        name = name.strip()
        raw_value = raw_value.strip()
        if not name:
            raise ValueError(f"参数名不能为空: {raw_param}")
        if not hasattr(strategy_cls, name):
            raise ValueError(f"未知策略参数: {name}")
        if not raw_value:
            raise ValueError(f"参数值不能为空: {name}")

        params[name] = _parse_value(raw_value, getattr(strategy_cls, name))
    return params


def format_strategy_params(strategy_params: dict[str, object]) -> str:
    return ", ".join(f"{name}={value}" for name, value in strategy_params.items())
