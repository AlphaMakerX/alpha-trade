import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from loguru import logger

from data.feeds.cleaner import clean_klines
from data.storage.postgres import count_klines, upsert_klines, get_latest_open_time

BASE_URL = "https://data-api.binance.vision"

# Binance timeframe 映射（ccxt 风格 → Binance API 风格）
_TF_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# timeframe → timedelta，用于增量续拉
_TF_DELTA = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}

MAX_RETRIES = 5

_KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
]


def timeframe_delta(timeframe: str) -> timedelta:
    try:
        return _TF_DELTA[timeframe]
    except KeyError as exc:
        supported = ", ".join(sorted(_TF_DELTA))
        raise ValueError(f"不支持的周期: {timeframe}，可选: {supported}") from exc


def _pair_to_symbol(pair: str) -> str:
    """ETH/USDT → ETHUSDT"""
    return pair.replace("/", "")


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _dt_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _clean_ohlcv_rows(rows: list[list]) -> list[list]:
    if not rows:
        return []
    df = pd.DataFrame(rows, columns=_KLINE_COLUMNS)
    cleaned = clean_klines(df)
    return cleaned[_KLINE_COLUMNS].values.tolist()


def fetch_klines(
    pair: str,
    timeframe: str,
    since: datetime,
    limit: int = 1000,
    end: datetime | None = None,
) -> list[list]:
    """从 Binance 公共 API 拉取一批 K线数据。

    返回: [[open_time(datetime), open, high, low, close, volume], ...]
    """
    symbol = _pair_to_symbol(pair)
    interval = _TF_MAP.get(timeframe, timeframe)

    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": _dt_to_ms(since),
        "limit": limit,
    }
    if end is not None:
        params["endTime"] = _dt_to_ms(end)

    resp = requests.get(
        f"{BASE_URL}/api/v3/klines",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()

    # Binance 返回: [open_time, open, high, low, close, volume, close_time,
    #   quote_asset_volume, number_of_trades, taker_buy_base, taker_buy_quote, ignore]
    return [
        [
            _ms_to_dt(row[0]),
            float(row[1]),
            float(row[2]),
            float(row[3]),
            float(row[4]),
            float(row[5]),
            _ms_to_dt(row[6]),
            float(row[7]),
            int(row[8]),
            float(row[9]),
            float(row[10]),
        ]
        for row in resp.json()
    ]


def _expected_bar_count(start: datetime, end: datetime, delta: timedelta) -> int:
    """Return inclusive bar count from start to end for one fixed timeframe."""
    if end < start:
        return 0
    return int((end - start).total_seconds() // delta.total_seconds()) + 1


def _is_range_complete(pair: str, timeframe: str, start: datetime, end: datetime, delta: timedelta) -> bool:
    expected = _expected_bar_count(start, end, delta)
    existing = count_klines(pair, timeframe, start, end)
    logger.info(f"区间完整性检查: {start} ~ {end}, 已有 {existing}/{expected} 根")
    return existing >= expected


def fetch_all_klines(
    pair: str,
    timeframe: str,
    start: datetime,
    end: datetime | None = None,
    batch_size: int = 1000,
) -> int:
    """批量拉取历史 K线数据并写入数据库。

    支持增量和历史回补：
    - 如果 start 到 DB 最新时间之间完整，则从最新时间点之后继续拉取。
    - 如果区间内存在缺口，则从请求的 start 开始回补，重复数据由 upsert 跳过。
    返回总写入条数。
    """
    delta = timeframe_delta(timeframe)

    if end is None:
        end = datetime.now(tz=timezone.utc)

    # 增量：检查 DB 中最新时间戳
    latest = get_latest_open_time(pair, timeframe)
    if latest is not None and latest >= start:
        complete_until = min(latest, end)
        if _is_range_complete(pair, timeframe, start, complete_until, delta):
            start = latest + delta
            logger.info(f"历史区间完整，增量拉取: 从 {start} 继续")
        else:
            logger.info(f"发现历史缺口，回补拉取: 从 {start} 开始")

    total_inserted = 0
    current = start
    retries = 0

    while current <= end:
        try:
            ohlcv = fetch_klines(pair, timeframe, current, batch_size, end=end)
            retries = 0  # 成功则重置
        except Exception as e:
            retries += 1
            if retries >= MAX_RETRIES:
                logger.error(f"连续失败 {MAX_RETRIES} 次，停止拉取: {e}")
                break
            logger.warning(f"拉取失败 ({retries}/{MAX_RETRIES}): {e}, 等待 5 秒后重试")
            time.sleep(5)
            continue

        if not ohlcv:
            logger.info("无更多数据，拉取完成")
            break

        # 交易所通常会遵守 endTime，这里再做一层保护。
        ohlcv = [row for row in ohlcv if row[0] <= end]
        if not ohlcv:
            logger.info("已到达结束时间，拉取完成")
            break

        last_open_time = ohlcv[-1][0]
        ohlcv = _clean_ohlcv_rows(ohlcv)
        if not ohlcv:
            logger.warning("清洗后无有效 K线，继续下一批")
            current = last_open_time + delta
            time.sleep(0.5)
            continue

        inserted = upsert_klines(pair, timeframe, ohlcv)
        total_inserted += inserted

        # 下一批从最后一条的时间戳 + 一个周期开始
        current = last_open_time + delta

        logger.debug(
            f"已拉取 {len(ohlcv)} 条, 累计写入 {total_inserted} 条, "
            f"最新时间: {ohlcv[-1][0]}"
        )

        # 限频保护
        time.sleep(0.5)

    logger.info(f"拉取完成: {pair} {timeframe}, 共写入 {total_inserted} 条")
    return total_inserted
