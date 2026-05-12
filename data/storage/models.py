from sqlalchemy import (
    BigInteger,
    Column,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP

metadata = MetaData()

klines = Table(
    "klines",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("pair", String(20), nullable=False),
    Column("timeframe", String(5), nullable=False),
    Column("open_time", TIMESTAMP(timezone=True), nullable=False),
    Column("open", Numeric, nullable=False),
    Column("high", Numeric, nullable=False),
    Column("low", Numeric, nullable=False),
    Column("close", Numeric, nullable=False),
    Column("volume", Numeric, nullable=False),
    Column("close_time", TIMESTAMP(timezone=True), nullable=False),
    Column("quote_asset_volume", Numeric, nullable=False),
    Column("number_of_trades", Integer, nullable=False),
    Column("taker_buy_base_asset_volume", Numeric, nullable=False),
    Column("taker_buy_quote_asset_volume", Numeric, nullable=False),
    UniqueConstraint("pair", "timeframe", "open_time"),
    Index("idx_klines_lookup", "pair", "timeframe", "open_time"),
)
