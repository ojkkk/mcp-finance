"""日志配置 — 统一的结构化日志"""

from __future__ import annotations
import logging
import sys

_logger_cache: dict[str, logging.Logger] = {}

# 默认格式
_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s | %(message)s"
_DATE_FMT = "%H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger（带缓存）"""
    if name in _logger_cache:
        return _logger_cache[name]

    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT, _DATE_FMT))
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    _logger_cache[name] = logger
    return logger


def set_level(level: int | str) -> None:
    """全局设置日志级别"""
    logging.root.setLevel(level)


def enable_debug() -> None:
    set_level(logging.DEBUG)
