"""日志配置 — 统一的结构化日志

支持通过环境变量配置:
  LOG_LEVEL   — 日志级别 (DEBUG/INFO/WARNING/ERROR)，默认 INFO
  LOG_FORMAT  — 日志格式: "text"(默认) 或 "json"
"""

from __future__ import annotations
import json
import logging
import os
import sys
from datetime import datetime, timezone

_logger_cache: dict[str, logging.Logger] = {}

_TEXT_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s | %(message)s"
_DATE_FMT = "%H:%M:%S"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }, ensure_ascii=False)


def _get_format() -> str:
    fmt = os.environ.get("LOG_FORMAT", "text")
    return "json" if fmt.lower() == "json" else "text"


def _get_level() -> int:
    name = os.environ.get("LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger（带缓存）"""
    if name in _logger_cache:
        return _logger_cache[name]

    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        if _get_format() == "json":
            handler.setFormatter(_JsonFormatter())
        else:
            handler.setFormatter(logging.Formatter(_TEXT_FORMAT, _DATE_FMT))
        logger.addHandler(handler)

    logger.setLevel(_get_level())
    _logger_cache[name] = logger
    return logger


def set_level(level: int | str) -> None:
    """全局设置日志级别"""
    logging.root.setLevel(level)


def enable_debug() -> None:
    set_level(logging.DEBUG)
