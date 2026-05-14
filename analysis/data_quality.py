from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd


_TIMEFRAME_FREQ = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}


@dataclass
class DataQualityReport:
    pair: str
    timeframe: str
    requested_start: str | None
    requested_end: str | None
    rows: int
    first_open: pd.Timestamp | None
    last_open: pd.Timestamp | None
    duplicate_bars: int = 0
    missing_bars: int = 0
    non_positive_price_rows: int = 0
    invalid_ohlc_rows: int = 0
    non_positive_volume_rows: int = 0
    timezone_name: str = "unknown"
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.warnings

    def summary_lines(self) -> list[str]:
        status = "OK" if self.ok else "WARN"
        lines = [
            f"数据质量: {status}",
            f"  交易对/周期: {self.pair} {self.timeframe}",
            f"  请求区间: {self.requested_start or '-'} ~ {self.requested_end or '-'}",
            f"  实际区间: {self.first_open or '-'} ~ {self.last_open or '-'}",
            f"  K线数量: {self.rows}",
            f"  时区: {self.timezone_name}",
            f"  重复K线: {self.duplicate_bars}",
            f"  缺失K线: {self.missing_bars}",
            f"  非正价格行: {self.non_positive_price_rows}",
            f"  OHLC异常行: {self.invalid_ohlc_rows}",
            f"  非正成交量行: {self.non_positive_volume_rows}",
        ]
        if self.warnings:
            lines.append("  警告:")
            lines.extend(f"    - {warning}" for warning in self.warnings)
        return lines

    def markdown_table(self) -> str:
        rows = [
            ("status", "OK" if self.ok else "WARN"),
            ("pair", self.pair),
            ("timeframe", self.timeframe),
            ("requested_start", self.requested_start or "-"),
            ("requested_end", self.requested_end or "-"),
            ("first_open", self.first_open or "-"),
            ("last_open", self.last_open or "-"),
            ("rows", self.rows),
            ("timezone", self.timezone_name),
            ("duplicate_bars", self.duplicate_bars),
            ("missing_bars", self.missing_bars),
            ("non_positive_price_rows", self.non_positive_price_rows),
            ("invalid_ohlc_rows", self.invalid_ohlc_rows),
            ("non_positive_volume_rows", self.non_positive_volume_rows),
        ]
        lines = ["| Check | Value |", "| --- | --- |"]
        lines.extend(f"| {name} | {value} |" for name, value in rows)
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines)


def _parse_date(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.Timestamp(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc))


def _timezone_name(index: pd.Index) -> str:
    tz = getattr(index, "tz", None)
    return str(tz) if tz is not None else "naive"


def _align_timestamp_to_index(ts: pd.Timestamp | None, index: pd.DatetimeIndex) -> pd.Timestamp | None:
    if ts is None:
        return None
    index_tz = getattr(index, "tz", None)
    if index_tz is None:
        return ts.tz_localize(None) if ts.tzinfo is not None else ts
    if ts.tzinfo is None:
        return ts.tz_localize(index_tz)
    return ts.tz_convert(index_tz)


def _count_missing_bars(index: pd.DatetimeIndex, timeframe: str) -> int:
    freq = _TIMEFRAME_FREQ.get(timeframe)
    if not freq or index.empty:
        return 0

    unique_index = pd.DatetimeIndex(index.drop_duplicates()).sort_values()
    if len(unique_index) < 2:
        return 0

    expected = pd.date_range(start=unique_index[0], end=unique_index[-1], freq=freq)
    return int(len(expected.difference(unique_index)))


def validate_ohlcv_data(
    df: pd.DataFrame,
    pair: str,
    timeframe: str,
    requested_start: str | None = None,
    requested_end: str | None = None,
) -> DataQualityReport:
    """Validate loaded OHLCV data without mutating it."""
    if df.empty:
        return DataQualityReport(
            pair=pair,
            timeframe=timeframe,
            requested_start=requested_start,
            requested_end=requested_end,
            rows=0,
            first_open=None,
            last_open=None,
            warnings=["数据为空"],
        )

    idx = pd.DatetimeIndex(pd.to_datetime(df.index))
    first_open = idx.min()
    last_open = idx.max()
    duplicate_bars = int(idx.duplicated().sum())
    missing_bars = _count_missing_bars(idx, timeframe)

    price_cols = [col for col in ["Open", "High", "Low", "Close"] if col in df.columns]
    non_positive_price_rows = 0
    invalid_ohlc_rows = 0
    if price_cols:
        non_positive_price_rows = int((df[price_cols] <= 0).any(axis=1).sum())

    if {"Open", "High", "Low", "Close"}.issubset(df.columns):
        high_too_low = df["High"] < df[["Open", "Close"]].max(axis=1)
        low_too_high = df["Low"] > df[["Open", "Close"]].min(axis=1)
        low_above_high = df["Low"] > df["High"]
        invalid_ohlc_rows = int((high_too_low | low_too_high | low_above_high).sum())

    non_positive_volume_rows = 0
    if "Volume" in df.columns:
        non_positive_volume_rows = int((df["Volume"] <= 0).sum())

    requested_start_ts = _align_timestamp_to_index(_parse_date(requested_start), idx)
    requested_end_ts = _align_timestamp_to_index(_parse_date(requested_end), idx)

    warnings: list[str] = []
    if duplicate_bars:
        warnings.append(f"发现 {duplicate_bars} 根重复 K线")
    if missing_bars:
        warnings.append(f"发现 {missing_bars} 根缺失 K线")
    if non_positive_price_rows:
        warnings.append(f"发现 {non_positive_price_rows} 行价格 <= 0")
    if invalid_ohlc_rows:
        warnings.append(f"发现 {invalid_ohlc_rows} 行 OHLC 关系异常")
    if requested_start_ts is not None and first_open > requested_start_ts:
        warnings.append(f"首根 K线晚于请求开始时间: {first_open}")
    if requested_end_ts is not None and last_open < requested_end_ts:
        warnings.append(f"末根 K线早于请求结束时间: {last_open}")

    return DataQualityReport(
        pair=pair,
        timeframe=timeframe,
        requested_start=requested_start,
        requested_end=requested_end,
        rows=len(df),
        first_open=first_open,
        last_open=last_open,
        duplicate_bars=duplicate_bars,
        missing_bars=missing_bars,
        non_positive_price_rows=non_positive_price_rows,
        invalid_ohlc_rows=invalid_ohlc_rows,
        non_positive_volume_rows=non_positive_volume_rows,
        timezone_name=_timezone_name(idx),
        warnings=warnings,
    )
