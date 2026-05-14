from datetime import datetime, timezone

import pandas as pd

from engine.data import load_ohlcv, parse_utc_date
from engine.factory import backtest_options, make_backtest
from strategies.trend.ma_cross import MaCross


def test_parse_utc_date_returns_timezone_aware_datetime():
    assert parse_utc_date("2024-01-01") == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert parse_utc_date(None) is None


def test_load_ohlcv_converts_database_columns(monkeypatch):
    raw = pd.DataFrame(
        {
            "open_time": [
                datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 1, 0, tzinfo=timezone.utc),
            ],
            "open": [101.0, 100.0],
            "high": [102.0, 101.0],
            "low": [99.0, 98.0],
            "close": [100.5, 100.0],
            "volume": [10.0, 11.0],
        }
    )
    captured = {}

    def fake_query_klines(pair, timeframe, start, end):
        captured["args"] = (pair, timeframe, start, end)
        return raw

    monkeypatch.setattr("engine.data.query_klines", fake_query_klines)

    df = load_ohlcv("ETH/USDT", "1h", "2024-01-01", "2024-01-02")

    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert list(df.index) == [
        datetime(2024, 1, 1, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
    ]
    assert captured["args"][0:2] == ("ETH/USDT", "1h")
    assert captured["args"][2] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert captured["args"][3] == datetime(2024, 1, 2, tzinfo=timezone.utc)


def test_backtest_options_uses_defaults_and_config_values():
    settings = {
        "backtest": {
            "initial_capital": "20000",
            "trade_on_close": "true",
            "exclusive_orders": "false",
        },
        "trading": {
            "commission": "0.002",
            "slippage": "0.0007",
        },
    }

    options = backtest_options(settings)

    assert options == {
        "cash": 20000.0,
        "commission": 0.002,
        "spread": 0.0007,
        "trade_on_close": True,
        "exclusive_orders": False,
        "finalize_trades": True,
    }


def test_make_backtest_applies_risk_settings():
    df = pd.DataFrame(
        {
            "Open": [100.0] * 40,
            "High": [101.0] * 40,
            "Low": [99.0] * 40,
            "Close": [100.0] * 40,
            "Volume": [1000.0] * 40,
        },
        index=pd.date_range("2024-01-01", periods=40, freq="h"),
    )
    settings = {
        "backtest": {},
        "trading": {},
        "risk": {
            "risk_per_trade": 0.02,
            "max_position_pct": 0.5,
            "cooldown_bars": 12,
        },
    }

    bt = make_backtest(df, MaCross, settings)

    assert bt._strategy.risk_per_trade == 0.02
    assert bt._strategy.max_position_pct == 0.5
    assert bt._strategy.cooldown_bars == 12
    assert MaCross.risk_per_trade != 0.02
