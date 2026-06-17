"""
AKShare 数据源模块 (已合并到 api.py)

此文件保留作为向后兼容的 re-export 层。
所有功能已迁移到 mcp_finance.api 模块。
"""

from mcp_finance.api import (
    get_dragon_tiger,
    get_block_trades,
    get_margin_trading,
    get_futures_list,
    get_realtime_quote_a,
    get_realtime_quote_hk,
    get_realtime_quote_us,
    get_realtime_quote_futures,
    get_kline_a,
    get_kline_hk,
    get_kline_us,
    get_kline_futures,
    test_data_sources,
    handle_dragon_tiger,
    handle_block_trades,
    handle_margin_trading,
    handle_futures_list,
)

__all__ = [
    "get_dragon_tiger", "get_block_trades", "get_margin_trading",
    "get_futures_list",
    "get_realtime_quote_a", "get_realtime_quote_hk",
    "get_realtime_quote_us", "get_realtime_quote_futures",
    "get_kline_a", "get_kline_hk", "get_kline_us", "get_kline_futures",
    "test_data_sources",
    "handle_dragon_tiger", "handle_block_trades",
    "handle_margin_trading", "handle_futures_list",
]
