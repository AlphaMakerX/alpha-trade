import pandas as pd

from analysis.data_quality import validate_ohlcv_data
from analysis.report import write_backtest_report


def _make_ohlcv(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0] * len(index),
            "High": [101.0] * len(index),
            "Low": [99.0] * len(index),
            "Close": [100.5] * len(index),
            "Volume": [1000.0] * len(index),
        },
        index=index,
    )


def test_validate_ohlcv_data_detects_missing_bars():
    index = pd.to_datetime(
        [
            "2024-01-01 00:00:00+00:00",
            "2024-01-01 01:00:00+00:00",
            "2024-01-01 03:00:00+00:00",
        ]
    )
    df = _make_ohlcv(pd.DatetimeIndex(index))

    report = validate_ohlcv_data(df, "ETH/USDT", "1h", "2024-01-01", "2024-01-01")

    assert report.missing_bars == 1
    assert not report.ok


def test_write_backtest_report_creates_markdown_and_trades(tmp_path, monkeypatch):
    trades = pd.DataFrame(
        {
            "EntryTime": [pd.Timestamp("2024-01-01 00:00:00")],
            "ExitTime": [pd.Timestamp("2024-01-01 01:00:00")],
            "PnL": [10.0],
        }
    )
    stats = pd.Series(
        {
            "Start": pd.Timestamp("2024-01-01 00:00:00"),
            "End": pd.Timestamp("2024-01-01 01:00:00"),
            "Return [%]": 1.0,
            "Buy & Hold Return [%]": 0.5,
            "Commissions [$]": 2.0,
            "# Trades": 1,
            "_trades": trades,
        }
    )
    data_report = validate_ohlcv_data(
        _make_ohlcv(pd.date_range("2024-01-01", periods=2, freq="h")),
        "ETH/USDT",
        "1h",
        "2024-01-01",
        "2024-01-01",
    )

    monkeypatch.setattr("analysis.report._REPORT_DIR", tmp_path)

    paths = write_backtest_report(
        stats=stats,
        strategy_name="ma_cross",
        pair="ETH/USDT",
        timeframe="1h",
        start="2024-01-01",
        end="2024-01-01",
        backtest_options={
            "cash": 10000,
            "commission": 0.001,
            "spread": 0.0005,
            "trade_on_close": False,
            "exclusive_orders": True,
            "finalize_trades": True,
        },
        data_quality=data_report,
    )

    assert paths.markdown_path.exists()
    assert paths.trades_path is not None
    assert paths.trades_path.exists()
