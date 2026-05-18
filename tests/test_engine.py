from datetime import datetime, timezone

import pandas as pd

from engine.data import load_ohlcv, parse_utc_date
from engine.evaluation import (
    annual_segments,
    quarterly_segments,
    _settings_with_costs,
    _summary_row,
)
from engine.factory import backtest_options, make_backtest
from engine.params import format_strategy_params, parse_strategy_params
from engine.search import (
    SearchCriteria,
    _constraint_for_params,
    _generate_param_combos,
    _split_train_test,
    check_criteria,
    score_stats,
)
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


def test_parse_strategy_params_casts_values_from_strategy_defaults():
    params = parse_strategy_params(
        ("fast_period=40", "atr_multiplier=1.5"),
        MaCross,
    )

    assert params == {"fast_period": 40, "atr_multiplier": 1.5}
    assert format_strategy_params(params) == "fast_period=40, atr_multiplier=1.5"


def test_parse_strategy_params_rejects_unknown_param():
    try:
        parse_strategy_params(("missing=1",), MaCross)
    except ValueError as exc:
        assert str(exc) == "未知策略参数: missing"
    else:
        raise AssertionError("expected ValueError")


def test_evaluation_segments_cover_requested_range():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, tzinfo=timezone.utc)

    annual = annual_segments(start, end)
    quarterly = quarterly_segments(start, end)

    assert len(annual) == 1
    assert annual[0].start == start
    assert annual[0].end == end
    assert [segment.start.month for segment in quarterly] == [1, 4, 7, 10]
    assert quarterly[-1].end == end


def test_evaluation_cost_settings_do_not_mutate_original():
    settings = {"trading": {"commission": 0.001, "slippage": 0.0005}}

    adjusted = _settings_with_costs(settings, 0.002, 0.001)

    assert adjusted["trading"]["commission"] == 0.002
    assert adjusted["trading"]["slippage"] == 0.001
    assert settings["trading"]["commission"] == 0.001
    assert settings["trading"]["slippage"] == 0.0005


def test_evaluation_summary_row_extracts_core_metrics():
    stats = pd.Series(
        {
            "Return [%]": 6.0,
            "Buy & Hold Return [%]": 45.0,
            "Sharpe Ratio": 0.75,
            "Max. Drawdown [%]": -4.0,
            "# Trades": 45,
            "Win Rate [%]": 44.4,
            "Profit Factor": 1.34,
            "Exposure Time [%]": 7.0,
        }
    )
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, tzinfo=timezone.utc)

    row = _summary_row(
        group="full",
        label="full",
        start=start,
        end=end,
        bars=8785,
        commission=0.001,
        slippage=0.0005,
        stats=stats,
    )

    assert row["return_pct"] == 6.0
    assert row["buy_hold_return_pct"] == 45.0
    assert row["trades"] == 45
    assert row["start"] == "2024-01-01"
    assert row["end"] == "2025-01-01"


def test_search_score_rewards_return_and_penalizes_drawdown():
    strong = pd.Series(
        {
            "Return [%]": 30.0,
            "Return (Ann.) [%]": 30.0,
            "Sharpe Ratio": 1.2,
            "Max. Drawdown [%]": -8.0,
            "# Trades": 60,
            "Profit Factor": 1.8,
        }
    )
    weak = pd.Series(
        {
            "Return [%]": 18.0,
            "Return (Ann.) [%]": 18.0,
            "Sharpe Ratio": 0.4,
            "Max. Drawdown [%]": -25.0,
            "# Trades": 60,
            "Profit Factor": 1.1,
        }
    )

    assert score_stats(strong) > score_stats(weak)


def test_search_criteria_returns_failure_reasons():
    criteria = SearchCriteria(
        min_train_trades=30,
        min_test_trades=5,
        max_drawdown_pct=15.0,
        min_profit_factor=1.1,
        min_sharpe=0.3,
    )
    stats = pd.Series(
        {
            "Return (Ann.) [%]": -2.0,
            "Sharpe Ratio": 0.1,
            "Max. Drawdown [%]": -20.0,
            "# Trades": 3,
            "Profit Factor": 0.8,
        }
    )

    passed, reasons = check_criteria(
        stats, criteria, min_trades=criteria.min_train_trades
    )

    assert not passed
    assert "annual_return<=0" in reasons
    assert "trades<30" in reasons
    assert "max_dd>15%" in reasons
    assert "pf<1.1" in reasons
    assert "sharpe<0.3" in reasons


def test_search_param_constraints_filter_invalid_combinations():
    combos = _generate_param_combos(
        {
            "fast_period": [10, 60],
            "slow_period": [50],
            "oversold": [40],
            "exit_rsi": [50],
            "range_adx_threshold": [18, 28],
            "trend_adx_threshold": [26],
        },
        _constraint_for_params,
    )

    assert combos == [
        {
            "fast_period": 10,
            "slow_period": 50,
            "oversold": 40,
            "exit_rsi": 50,
            "range_adx_threshold": 18,
            "trend_adx_threshold": 26,
        }
    ]


def test_search_split_uses_tail_as_out_of_sample():
    df = pd.DataFrame(
        {"Close": range(10)},
        index=pd.date_range("2024-01-01", periods=10, freq="h"),
    )

    train_df, test_df = _split_train_test(df, 0.3)

    assert list(train_df["Close"]) == list(range(7))
    assert list(test_df["Close"]) == [7, 8, 9]
