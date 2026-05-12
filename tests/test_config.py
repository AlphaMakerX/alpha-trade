from utils.config import get_settings, load_yaml


def test_load_settings():
    settings = get_settings()
    assert "exchange" in settings
    assert "trading" in settings
    assert "backtest" in settings


def test_load_logging():
    cfg = load_yaml("logging.yaml")
    assert "log" in cfg
    assert cfg["log"]["level"] == "INFO"


def test_trading_pair():
    settings = get_settings()
    assert settings["trading"]["pair"] == "ETH/USDT"
