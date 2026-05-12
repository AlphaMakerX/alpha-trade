import sys

from loguru import logger

from utils.config import load_yaml


def setup_logger():
    """根据 config/logging.yaml 初始化日志。"""
    cfg = load_yaml("logging.yaml").get("log", {})

    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        level=cfg.get("level", "INFO"),
        format=cfg.get(
            "format",
            "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
        ),
    )

    # 文件输出
    log_path = cfg.get("path")
    if log_path:
        logger.add(
            log_path,
            level=cfg.get("level", "INFO"),
            format=cfg.get(
                "format",
                "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
            ),
            rotation=cfg.get("rotation", "10 MB"),
            retention=cfg.get("retention", "30 days"),
        )

    return logger
