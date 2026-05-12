import os
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"

_settings_cache: dict | None = None


def _resolve_env_vars(obj):
    """递归替换配置中的 ${ENV_VAR} 为环境变量值。"""
    if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
        return os.getenv(obj[2:-1], obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(i) for i in obj]
    return obj


def load_yaml(filename: str) -> dict:
    """加载 config/ 目录下的 YAML 文件。"""
    path = _CONFIG_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return _resolve_env_vars(data) if data else {}


def get_settings() -> dict:
    """获取全局配置（带缓存）。"""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = load_yaml("settings.yaml")
    return _settings_cache
