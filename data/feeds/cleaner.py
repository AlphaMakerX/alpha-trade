import pandas as pd
from loguru import logger


def clean_klines(df: pd.DataFrame) -> pd.DataFrame:
    """清洗 K线数据。

    - 按 open_time 去重
    - 去除价格为 0 或负数的异常行
    - 缺失值用前值填充
    """
    if df.empty:
        return df

    before = len(df)

    # 去重
    df = df.drop_duplicates(subset=["open_time"], keep="last")

    # 去除异常值（价格 <= 0）
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols:
        if col in df.columns:
            df = df[df[col] > 0]

    # 缺失值前值填充
    df = df.ffill()

    after = len(df)
    if before != after:
        logger.warning(f"清洗: {before} → {after} 条 (移除 {before - after} 条异常数据)")

    return df.sort_values("open_time").reset_index(drop=True)
