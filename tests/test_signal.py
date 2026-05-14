from datetime import datetime, timedelta, timezone

from engine import signal as signal_module
from strategies.trend.ma_cross import MaCross


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2024, 1, 10, 12, 0, tzinfo=tz)


def test_signal_uses_requested_timeframe_delta(monkeypatch):
    captured = {}

    def fake_fetch_klines(pair, timeframe, since, limit=1000, end=None):
        captured["since"] = since
        captured["limit"] = limit
        return []

    monkeypatch.setattr(signal_module, "datetime", FixedDateTime)
    monkeypatch.setattr(signal_module, "fetch_klines", fake_fetch_klines)

    result = signal_module.get_signal("ETH/USDT", "4h")

    expected_since = FixedDateTime.now(timezone.utc) - MaCross.bars_needed() * timedelta(hours=4)
    assert captured["since"] == expected_since
    assert captured["limit"] == MaCross.bars_needed()
    assert "K线数据不足" in result
