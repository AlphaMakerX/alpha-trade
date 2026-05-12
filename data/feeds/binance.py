import time
from datetime import datetime, timedelta, timezone

import requests
from loguru import logger

from data.storage.postgres import upsert_klines, get_latest_open_time

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


def _pair_to_symbol(pair: str) -> str:
    """ETH/USDT → ETHUSDT"""
    return pair.replace("/", "")


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _dt_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def fetch_klines(
    pair: str,
    timeframe: str,
    since: datetime,
    limit: int = 1000,
) -> list[list]:
    """从 Binance 公共 API 拉取一批 K线数据。

    返回: [[open_time(datetime), open, high, low, close, volume], ...]
    """
    symbol = _pair_to_symbol(pair)
    interval = _TF_MAP.get(timeframe, timeframe)

    resp = requests.get(
        f"{BASE_URL}/api/v3/klines",
        params={
            "symbol": symbol,
            "interval": interval,
            "startTime": _dt_to_ms(since),
            "limit": limit,
        },
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


def fetch_all_klines(
    pair: str,
    timeframe: str,
    start: datetime,
    end: datetime | None = None,
    batch_size: int = 1000,
) -> int:
    """批量拉取历史 K线数据并写入数据库。

    支持增量：如果 DB 中已有数据，从最新时间点之后继续拉取。
    返回总写入条数。
    """
    delta = _TF_DELTA[timeframe]

    # 增量：检查 DB 中最新时间戳
    latest = get_latest_open_time(pair, timeframe)
    if latest is not None and latest >= start:
        start = latest + delta
        logger.info(f"增量拉取: 从 {start} 继续")

    if end is None:
        end = datetime.now(tz=timezone.utc)

    total_inserted = 0
    current = start
    retries = 0

    while current < end:
        try:
            ohlcv = fetch_klines(pair, timeframe, current, batch_size)
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

        inserted = upsert_klines(pair, timeframe, ohlcv)
        total_inserted += inserted

        # 下一批从最后一条的时间戳 + 一个周期开始
        current = ohlcv[-1][0] + delta

        logger.debug(
            f"已拉取 {len(ohlcv)} 条, 累计写入 {total_inserted} 条, "
            f"最新时间: {ohlcv[-1][0]}"
        )

        # 限频保护
        time.sleep(0.5)

    logger.info(f"拉取完成: {pair} {timeframe}, 共写入 {total_inserted} 条")
    return total_inserted
