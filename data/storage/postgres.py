from datetime import datetime

import pandas as pd
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from data.storage.database import get_engine
from data.storage.models import klines, metadata


def init_db():
    """创建表结构。"""
    metadata.create_all(get_engine())
    logger.info("数据库表初始化完成")


def upsert_klines(pair: str, timeframe: str, rows: list[list]) -> int:
    """批量写入 K线数据，重复数据自动跳过。

    rows: [[open_time(datetime), open, high, low, close, volume], ...]
    """
    if not rows:
        return 0

    values = [
        {
            "pair": pair,
            "timeframe": timeframe,
            "open_time": row[0],
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5],
            "close_time": row[6],
            "quote_asset_volume": row[7],
            "number_of_trades": row[8],
            "taker_buy_base_asset_volume": row[9],
            "taker_buy_quote_asset_volume": row[10],
        }
        for row in rows
    ]

    stmt = pg_insert(klines).values(values).on_conflict_do_nothing(
        index_elements=["pair", "timeframe", "open_time"]
    )

    with get_engine().begin() as conn:
        result = conn.execute(stmt)
        inserted = result.rowcount

    logger.info(f"写入 {inserted} 条 K线数据 ({pair} {timeframe})")
    return inserted


def get_latest_open_time(pair: str, timeframe: str) -> datetime | None:
    """查询该交易对/周期的最新时间戳，无数据返回 None。"""
    stmt = select(func.max(klines.c.open_time)).where(
        klines.c.pair == pair,
        klines.c.timeframe == timeframe,
    )
    with get_engine().connect() as conn:
        return conn.execute(stmt).scalar()


def count_klines(
    pair: str,
    timeframe: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """统计指定交易对/周期/区间内的 K线数量。"""
    stmt = select(func.count()).select_from(klines).where(
        klines.c.pair == pair,
        klines.c.timeframe == timeframe,
    )

    if start is not None:
        stmt = stmt.where(klines.c.open_time >= start)
    if end is not None:
        stmt = stmt.where(klines.c.open_time <= end)

    with get_engine().connect() as conn:
        return int(conn.execute(stmt).scalar() or 0)


def query_klines(
    pair: str,
    timeframe: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    """查询 K线数据，返回 DataFrame。"""
    stmt = select(
        klines.c.open_time,
        klines.c.open,
        klines.c.high,
        klines.c.low,
        klines.c.close,
        klines.c.volume,
        klines.c.close_time,
        klines.c.quote_asset_volume,
        klines.c.number_of_trades,
        klines.c.taker_buy_base_asset_volume,
        klines.c.taker_buy_quote_asset_volume,
    ).where(
        klines.c.pair == pair,
        klines.c.timeframe == timeframe,
    )

    if start is not None:
        stmt = stmt.where(klines.c.open_time >= start)
    if end is not None:
        stmt = stmt.where(klines.c.open_time <= end)

    stmt = stmt.order_by(klines.c.open_time)

    with get_engine().connect() as conn:
        return pd.read_sql(stmt, conn)
