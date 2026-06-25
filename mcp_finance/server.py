"""
mcp-finance — 全市场实时行情 MCP Server

提供 20+ 个 Tools + 2 个 Resources，基于 AKShare 统一数据源（A股/期货/港股/美股）。
Handler 逻辑已拆分到各模块，本文件只负责 MCP 路由和格式化输出。
"""

from __future__ import annotations
from typing import Any
import asyncio
import json
import os
import re

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

# 提前导入所有 handler，避免 handler 内延迟导入时 Python import 锁竞争导致死锁
from mcp_finance import __version__
from mcp_finance.api import handle_realtime_quote, handle_kline, handle_financials, handle_market_indices, handle_sector_ranking, handle_north_flow, handle_batch_quotes, handle_dragon_tiger, handle_block_trades, handle_margin_trading, handle_futures_list, handle_test_data_sources
from mcp_finance.indicators import handle_technical_indicators
from mcp_finance.screener import handle_stock_screener
from mcp_finance.backtest import handle_backtest, handle_optimize, handle_walk_forward, handle_monte_carlo
from mcp_finance.chart import handle_plot_kline, handle_comparison_chart
from mcp_finance.portfolio import handle_correlation_matrix, handle_portfolio_backtest
from mcp_finance.analysis import handle_analyze_stock, handle_compare_stocks, handle_factor_screener
from mcp_finance.api_extended import (
    handle_minute_kline, handle_fund_flow, handle_institutional_holdings,
    handle_macro_data, handle_research_reports,
)
from mcp_finance.data import HOT_STOCKS
from mcp_finance.errors import StockError, format_error_response
from mcp_finance.logging_config import get_logger, set_level

logger = get_logger(__name__)
server = Server("mcp-finance")


# ================================================================
# NumPy JSON encoder (module-level, avoid redefinition on each call)
# ================================================================

if _HAS_NUMPY:
    class _NPEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)
else:
    _NPEncoder = None


# ================================================================
# Tool Handler
# ================================================================

TOOL_HANDLERS: dict[str, Any] = {}

def _register(name: str):
    def decorator(func):
        TOOL_HANDLERS[name] = func
        return func
    return decorator


# Direct handler registrations (thin wrappers eliminated)
TOOL_HANDLERS["get_realtime_quote"] = handle_realtime_quote
TOOL_HANDLERS["get_kline"] = handle_kline
TOOL_HANDLERS["get_financials"] = handle_financials
TOOL_HANDLERS["get_market_indices"] = handle_market_indices
TOOL_HANDLERS["get_sector_ranking"] = handle_sector_ranking
TOOL_HANDLERS["get_north_flow"] = handle_north_flow
TOOL_HANDLERS["batch_quotes"] = handle_batch_quotes
TOOL_HANDLERS["get_technical_indicators"] = handle_technical_indicators
TOOL_HANDLERS["stock_screener"] = handle_stock_screener
TOOL_HANDLERS["backtest_strategy"] = handle_backtest
TOOL_HANDLERS["optimize_strategy"] = handle_optimize
TOOL_HANDLERS["walk_forward"] = handle_walk_forward
TOOL_HANDLERS["monte_carlo_test"] = handle_monte_carlo
TOOL_HANDLERS["plot_kline"] = handle_plot_kline
TOOL_HANDLERS["comparison_chart"] = handle_comparison_chart
TOOL_HANDLERS["get_dragon_tiger"] = handle_dragon_tiger
TOOL_HANDLERS["get_block_trades"] = handle_block_trades
TOOL_HANDLERS["get_margin_trading"] = handle_margin_trading
TOOL_HANDLERS["get_futures_list"] = handle_futures_list
TOOL_HANDLERS["test_data_sources"] = handle_test_data_sources
TOOL_HANDLERS["get_minute_kline"] = handle_minute_kline
TOOL_HANDLERS["get_fund_flow"] = handle_fund_flow
TOOL_HANDLERS["get_institutional_holdings"] = handle_institutional_holdings
TOOL_HANDLERS["get_macro_data"] = handle_macro_data
TOOL_HANDLERS["get_research_reports"] = handle_research_reports
TOOL_HANDLERS["analyze_stock"] = handle_analyze_stock
TOOL_HANDLERS["compare_stocks"] = handle_compare_stocks
TOOL_HANDLERS["factor_screener"] = handle_factor_screener
TOOL_HANDLERS["correlation_matrix"] = handle_correlation_matrix
TOOL_HANDLERS["portfolio_backtest"] = handle_portfolio_backtest


# -- Search (纯本地，无网络) --
@_register("search_stock")
def _search_stock(args: dict) -> list:
    from mcp_finance.api import search_stocks
    return search_stocks(args.get("market", "a"), args["keyword"], args.get("top_n", 10))
# ================================================================
# Resources
# ================================================================

@server.list_resources()
async def list_resources() -> list[types.Resource]:
    return [
        types.Resource(uri="stock://popular", name="热门股票列表", description="常用A股/指数代码和名称", mimeType="application/json"),
        types.Resource(uri="stock://market/indices", name="大盘指数", description="上证/深证/创业板/沪深300/科创50实时行情", mimeType="application/json"),

    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "stock://popular":
        return json.dumps(HOT_STOCKS, ensure_ascii=False, indent=2)

    if uri == "stock://market/indices":
        indices = handle_market_indices({"market": "a"})
        return json.dumps(indices, ensure_ascii=False, indent=2)

    m = re.match(r"stock://(\w+)/realtime", uri)
    if m:
        code = m.group(1)
        try:
            result = handle_realtime_quote({"code": code})
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            raise ValueError(f"Stock not found: {code}") from e

    m = re.match(r"stock://(\w+)/kline", uri)
    if m:
        code = m.group(1)
        try:
            klines = handle_kline({"code": code, "ktype": "daily", "limit": 30})
            return json.dumps(klines, ensure_ascii=False, indent=2)
        except Exception as e:
            raise ValueError(f"K-line not found: {code}") from e

    m = re.match(r"stock://(\w+)/indicators", uri)
    if m:
        code = m.group(1)
        try:
            result = handle_technical_indicators({"code": code, "days": 120})
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            raise ValueError(f"Indicators not found: {code}") from e

    raise ValueError(f"Unknown resource URI: {uri}")


# ================================================================
# Tools
# ================================================================

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_realtime_quote",
            description="查询全市场实时行情。market: a=A股, hk=港股, us=美股, futures=期货",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码或名称，如 '600519'、'贵州茅台'、'00700'（港股）、'AAPL'（美股）"},
                    "market": {"type": "string", "description": "市场类型: a/hk/us/futures，默认 a"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_kline",
            description="获取股票 K 线数据（日/周/月/60分钟+前/后复权）。market: a/hk/us/futures",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码，如 '600519'"},
                    "market": {"type": "string", "description": "市场: a/hk/us/futures，默认 a"},
                    "ktype": {"type": "string", "description": "K线类型: daily=日K, weekly=周K, monthly=月K"},
                    "adjust": {"type": "string", "description": "复权方式: qfq=前复权, bfq=不复权, hfq=后复权 (仅A股)"},
                    "limit": {"type": "integer", "description": "返回条数，最多 800"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_financials",
            description="获取股票核心财务数据（营收、净利润、ROE 等）。支持 A 股 (a) / 港股 (hk) / 美股 (us)，默认 a。港美股使用 yfinance 兜底",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码，如 '600519'(A股) / '00700'(港股) / 'AAPL'(美股)"},
                    "market": {"type": "string", "description": "市场: a/hk/us，默认 a"},
                    "count": {"type": "integer", "description": "最近几期数据"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_market_indices",
            description="获取大盘指数实时行情。market: a=A股(上证/深证/创业板/沪深300/科创50/上证50/中证500), hk=港股(恒生/恒生科技/国企), us=美股(道琼斯/纳斯达克/标普500)",
            inputSchema={
                "type": "object",
                "properties": {
                    "market": {"type": "string", "description": "市场: a/hk/us，默认 a"},
                },
            },
        ),
        types.Tool(
            name="get_sector_ranking",
            description="获取行业/概念板块涨幅排行榜",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector_type": {"type": "string", "description": "板块类型: industry=行业板块, concept=概念板块, region=地域板块"},
                    "top_n": {"type": "integer", "description": "返回前 N 名"},
                },
            },
        ),
        types.Tool(
            name="get_north_flow",
            description="获取北向/南向资金流向（沪深港通）",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "最近几天"},
                },
            },
        ),
        types.Tool(
            name="get_futures_list",
            description="获取国内期货合约实时行情列表（商品期货+股指期货），含最新价/涨跌幅/持仓量",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="batch_quotes",
            description="批量查询多只股票的实时行情",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {"type": "array", "items": {"type": "string"}, "description": "股票代码列表，如 ['600519', '300750', '000333']"},
                    "market": {"type": "string", "description": "市场: a/hk/us，默认 a"},
                },
                "required": ["codes"],
            },
        ),
        types.Tool(
            name="get_technical_indicators",
            description="计算股票技术指标：MA(5/10/20/60/120/250)、MACD(DIF/DEA/柱)、KDJ(K/D/J)、RSI(6/14/24)、BOLL(上下轨)、WR、BIAS，并自动识别金叉/死叉/超买超卖/均线排列信号",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码，如 '600519'(A股) / '00700'(港股) / 'AAPL'(美股)"},
                    "market": {"type": "string", "description": "市场: a/hk/us，默认 a"},
                    "days": {"type": "integer", "description": "取多少根 K 线计算（建议 60-250，越多指标越完整）"},
                    "ktype": {"type": "string", "description": "K线类型: daily=日K, weekly=周K"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="stock_screener",
            description="全市场 A 股筛选：按涨跌幅、量比、换手率、市盈率、市净率、ROE、市值等条件筛选股票，返回匹配列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_gain": {"type": "number", "description": "最低涨跌幅 %，如 3.0 表示至少涨 3%"},
                    "max_gain": {"type": "number", "description": "最高涨跌幅 %，如 -5.0 表示跌不超过 5%"},
                    "min_volume_ratio": {"type": "number", "description": "最低量比（当日成交量/5日均量），如 1.5 表示放量 50%"},
                    "min_turnover": {"type": "number", "description": "最低换手率 %，如 5.0"},
                    "max_pe": {"type": "number", "description": "最高市盈率（过滤亏损/高估值），如 50"},
                    "min_pb": {"type": "number", "description": "最低市净率 PB，如 1.0 表示至少 1 倍"},
                    "max_pb": {"type": "number", "description": "最高市净率 PB，如 5.0"},
                    "min_roe": {"type": "number", "description": "最低净资产收益率 ROE(%)，如 10.0 — 通过财务缓存获取"},                    "min_market_cap": {"type": "number", "description": "最低总市值（亿元），如 100"},
                    "top_n": {"type": "integer", "description": "返回前 N 条"},
                },
            },
        ),
        types.Tool(
            name="backtest_strategy",
            description="策略回测：对指定股票跑历史策略回测，返回收益率、夏普比率、最大回撤、交易记录等绩效统计。支持 A 股(6位代码)/港股(5位代码)/美股(字母代码)，自动识别市场",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码，如 '600519'(A股) / '00700'(港股) / 'AAPL'(美股)"},
                    "strategy": {"type": "string", "description": "策略名称: ma_cross=双均线 macd_signal=MACD rsi_signal=RSI kdj_signal=KDJ boll_signal=BOLL turtle=海龟 vol_trend=波动率趋势 mean_rev=均值回归"},
                    "fast_period": {"type": "integer", "description": "快线周期: 均线策略用(MA周期), MACD策略用(fast周期)"},
                    "slow_period": {"type": "integer", "description": "慢线周期: 均线策略用(MA周期), MACD策略用(slow周期)"},
                    "start_date": {"type": "string", "description": "回测开始日期，如 '2024-01-01'，默认一年前"},
                    "end_date": {"type": "string", "description": "回测结束日期，如 '2024-12-31'，默认今天"},
                    "initial_capital": {"type": "number", "description": "初始资金（元），默认 100000"},
                    "generate_chart": {"type": "boolean", "description": "是否生成权益曲线对比图（策略 vs 基准），默认 true"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="optimize_strategy",
            description="参数优化：支持网格扫描(grid)和贝叶斯优化(bayesian)两种模式。贝叶斯模式基于 Optuna TPE 采样器，50次试验通常优于200组网格扫描，自动剪枝+参数重要性分析。支持 A 股(6位代码)/港股(5位代码)/美股(字母代码)。网格模式组合数上限 200 组",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码，如 '000333'(A股) / '00700'(港股) / 'AAPL'(美股)"},
                    "strategy": {"type": "string", "description": "策略: ma_cross=双均线, macd_signal=MACD, rsi_signal=RSI, kdj_signal=KDJ, boll_signal=BOLL, custom=自定义组合"},
                    "fast_min": {"type": "integer", "description": "快线最小值"},
                    "fast_max": {"type": "integer", "description": "快线最大值"},
                    "fast_step": {"type": "integer", "description": "快线步长"},
                    "slow_min": {"type": "integer", "description": "慢线最小值"},
                    "slow_max": {"type": "integer", "description": "慢线最大值"},
                    "slow_step": {"type": "integer", "description": "慢线步长"},
                    "start_date": {"type": "string", "description": "开始日期，如 '2024-01-01'"},
                    "end_date": {"type": "string", "description": "结束日期，如 '2024-12-31'"},
                    "metric": {"type": "string", "description": "优化目标: sharpe/return/mdd/win_rate"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="plot_kline",
            description="生成交互式 K 线 HTML 文件（不是PNG图片！），含蜡烛图+均线+成交量+MACD/KDJ/RSI副图。返回文件路径，请务必用浏览器打开该 HTML 文件查看（支持缩放/平移/悬停查看数值）",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "股票代码，如 '600519'(A股) / '00700'(港股) / 'AAPL'(美股)"},
                    "market": {"type": "string", "description": "市场: a/hk/us，默认 a"},
                    "days": {"type": "integer", "description": "K 线条数"},
                    "ktype": {"type": "string", "description": "K线类型: daily=日K, weekly=周K"},
                    "show_macd": {"type": "boolean", "description": "是否显示 MACD 副图"},
                    "show_kdj": {"type": "boolean", "description": "是否显示 KDJ 副图"},
                    "show_rsi": {"type": "boolean", "description": "是否显示 RSI 副图"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_dragon_tiger",
            description="龙虎榜明细：每日上榜股票的营业部买卖金额、净买入等（AKShare 新浪数据源）",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "日期 YYYYMMDD，如 '20250613'，默认今天"},
                },
            },
        ),
        types.Tool(
            name="get_block_trades",
            description="大宗交易：单只股票或全市场的大宗交易明细，含成交价/折溢价率等",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码，如 '000333'；留空返回全市场"},
                    "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                },
            },
        ),
        types.Tool(
            name="get_margin_trading",
            description="融资融券（两融）：沪深两市个股融资余额、融券余量、融资买入额等",
            inputSchema={
                "type": "object",
                "properties": {
                    "market": {"type": "string", "description": "市场: sh=上证 sz=深证 all=两市，默认 all"},
                    "date": {"type": "string", "description": "日期 YYYYMMDD，如 '20250613'，默认今天"},
                },
            },
        ),
        types.Tool(
            name="test_data_sources",
            description="诊断所有数据源是否可用（A股/港股/美股/期货/北向资金），逐项测试并返回状态",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="search_stock",
            description="按代码或名称模糊搜索股票（A股/港股/美股），纯本地映射无网络调用，毫秒级返回",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词（代码或名称）"},
                    "market": {"type": "string", "description": "市场: a/A股, hk/港股, us/美股, 默认 a"},
                    "top_n": {"type": "integer", "description": "最多返回条数，默认 10"},
                },
                "required": ["keyword"],
            },
        ),
        types.Tool(
            name="get_minute_kline",
            description="获取分钟级K线数据（仅A股）。支持1/5/15/30/60分钟周期，基于 easy-tdx 毫秒级数据源",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码，如 '600519'"},
                    "freq": {"type": "string", "description": "K线周期: 1/5/15/30/60，默认5分钟"},
                    "limit": {"type": "integer", "description": "返回条数，默认240"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_fund_flow",
            description="获取个股资金流向（仅A股，主力净流入/成交额/换手率/量比），基于 easy-tdx 通达信实时数据，毫秒级响应",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码，如 '600519'"},
                    "days": {"type": "integer", "description": "最近几天，默认5"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_institutional_holdings",
            description="获取个股十大流通股东/机构持仓数据（仅A股），基于 AKShare 东方财富",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码，如 '600519'"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_macro_data",
            description="获取中国宏观经济数据（仅中国）：GDP/CPI/PMI/货币供应量/外汇储备，基于 AKShare",
            inputSchema={
                "type": "object",
                "properties": {
                    "indicator": {"type": "string", "description": "指标类型: gdp/cpi/pmi/money_supply/fx_reserve，默认 cpi"},
                    "limit": {"type": "integer", "description": "返回最近几期，默认20"},
                },
            },
        ),
        types.Tool(
            name="get_research_reports",
            description="获取个股研报（仅A股，机构评级/目标价），基于 AKShare 东方财富",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码，如 '600519'"},
                    "limit": {"type": "integer", "description": "返回条数，默认10"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="analyze_stock",
            description="综合个股分析：一站式返回行情+技术指标+均线排列+财务+综合评分（0-100），结果结构化供AI解读",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码，如 '600519'"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="compare_stocks",
            description="多股横向对比：同时分析多只股票，按综合评分排名，快速找出最优标的",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {"type": "array", "items": {"type": "string"}, "description": "股票代码列表，如 ['600519', '000858', '300750']"},
                },
                "required": ["codes"],
            },
        ),
        types.Tool(
            name="correlation_matrix",
            description="计算多只股票收益率的相关性矩阵，找出低相关配对，辅助分散投资决策",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {"type": "array", "items": {"type": "string"}, "description": "股票代码列表，如 ['600519', '000858', '300750']"},
                    "days": {"type": "integer", "description": "回溯天数，默认120"},
                },
                "required": ["codes"],
            },
        ),
        types.Tool(
            name="portfolio_backtest",
            description="多股投资组合回测：支持自定义权重/等权，返回收益率/夏普/最大回撤/权益曲线",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {"type": "array", "items": {"type": "string"}, "description": "股票代码列表"},
                    "weights": {"type": "array", "items": {"type": "number"}, "description": "权重列表，默认等权"},
                    "initial_capital": {"type": "number", "description": "初始资金，默认100000"},
                    "days": {"type": "integer", "description": "回溯天数，默认250"},
                },
                "required": ["codes"],
            },
        ),
        types.Tool(
            name="comparison_chart",
            description="生成多只股票走势对比图（归一化），交互式HTML，支持缩放/平移/悬停查看数值",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {"type": "array", "items": {"type": "string"}, "description": "股票代码列表，如 ['600519', '000858']"},
                    "days": {"type": "integer", "description": "回溯天数，默认120"},
                },
                "required": ["codes"],
            },
        ),
        types.Tool(
            name="factor_screener",
            description="多因子选股：全市场A股按动量/价值/质量/增长/波动五因子综合打分排名，返回Top N。过滤ST和新股",
            inputSchema={
                "type": "object",
                "properties": {
                    "top_n": {"type": "integer", "description": "返回前N名，默认30"},
                    "min_market_cap": {"type": "number", "description": "最低总市值(亿)，默认50"},
                },
            },
        ),
    ]


# ================================================================
# Parameter Validators
# ================================================================

_TOOL_VALIDATORS: dict[str, Any] = {}
try:
    from mcp_finance.validators import (
        KlineParams, FinancialsParams, SectorRankingParams, RealtimeQuoteParams, MarketIndicesParams, BatchQuotesParams, DragonTigerParams, BlockTradesParams, MarginTradingParams, SearchStockParams, MinuteKlineParams, FundFlowParams, InstitutionalHoldingsParams, MacroDataParams, ResearchReportsParams, AnalyzeStockParams, CompareStocksParams, FactorScreenerParams, PortfolioBacktestParams, CorrelationMatrixParams, ComparisonChartParams,
        NorthFlowParams, TechnicalIndicatorsParams,
        ScreenerParams, BacktestParams, OptimizeParams,
        PlotKlineParams, validate_and_coerce,
        # BUG-18 修复: 导入新增的 walk_forward 和 monte_carlo 验证器
        WalkForwardParams, MonteCarloParams,
    )
    _TOOL_VALIDATORS.update({
        "get_kline": KlineParams,
        "get_financials": FinancialsParams,
        "get_sector_ranking": SectorRankingParams,
        "get_north_flow": NorthFlowParams,
        "get_technical_indicators": TechnicalIndicatorsParams,
        "stock_screener": ScreenerParams,
        "backtest_strategy": BacktestParams,
        "optimize_strategy": OptimizeParams,
        # BUG-18 修复: 注册 walk_forward 和 monte_carlo_test 验证器
        # 原来缺少注册导致 LLM 传字符串类型整数参数时不会被自动转换，引发 TypeError
        "walk_forward": WalkForwardParams,
        "monte_carlo_test": MonteCarloParams,
        "plot_kline": PlotKlineParams,
        "get_realtime_quote": RealtimeQuoteParams,
        "get_market_indices": MarketIndicesParams,
        "batch_quotes": BatchQuotesParams,
        "get_dragon_tiger": DragonTigerParams,
        "get_block_trades": BlockTradesParams,
        "get_margin_trading": MarginTradingParams,
        "search_stock": SearchStockParams,
        "get_minute_kline": MinuteKlineParams,
        "get_fund_flow": FundFlowParams,
        "get_institutional_holdings": InstitutionalHoldingsParams,
        "get_macro_data": MacroDataParams,
        "get_research_reports": ResearchReportsParams,
        "analyze_stock": AnalyzeStockParams,
        "compare_stocks": CompareStocksParams,
        "factor_screener": FactorScreenerParams,
        "portfolio_backtest": PortfolioBacktestParams,
        "correlation_matrix": CorrelationMatrixParams,
        "comparison_chart": ComparisonChartParams,
    })
    _HAS_VALIDATORS = True
except ImportError:
    _HAS_VALIDATORS = False


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """统一路由：分发到注册的 handler，统一格式化和错误处理"""
    if _HAS_VALIDATORS and name in _TOOL_VALIDATORS:
        arguments = validate_and_coerce(_TOOL_VALIDATORS[name], arguments)

    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")

    try:
        # 在 asyncio.to_thread 中执行同步 handler，不阻塞事件循环
        # 临时重定向 stdout → devnull，防止 akshare/easy-tdx 的 print 输出
        # 污染 MCP JSON-RPC 通信通道（MCP 走 stdio，stdout 只应输出 JSON-RPC）
        def _safe_handler():
            # BUG-19 修复: 原来的实现不是异常安全的:
            # 1. open(os.devnull) 失败时 sys.stdout 未被还原
            # 2. sys.stdout.close() 在 restore 之前执行，抛异常则 stdout 永久丢失
            import sys
            old_stdout = sys.stdout
            devnull_fh = None
            try:
                devnull_fh = open(os.devnull, "w", encoding="utf-8")
                sys.stdout = devnull_fh
                return handler(arguments)
            finally:
                sys.stdout = old_stdout   # 先还原，确保无论如何都能恢复
                if devnull_fh is not None:
                    try:
                        devnull_fh.close()
                    except Exception:
                        pass

        # optimize_strategy 需要更长时间
        timeout = 300.0 if name == "walk_forward" else 180.0 if name == "optimize_strategy" else 120.0 if name == "backtest_strategy" else 90.0
        result = await asyncio.wait_for(asyncio.to_thread(_safe_handler), timeout=timeout)
        return [types.TextContent(type="text", text=_format_json(result))]
    except asyncio.TimeoutError:
        logger.error("Tool %s timed out (%.0fs) — thread pool may be exhausted", name, timeout)
        return [types.TextContent(type="text", text=_format_json({
            "error": True, "code": "TIMEOUT",
            "message": f"工具调用超时 ({int(timeout)}s)。可能是网络请求阻塞或线程池耗尽，请稍后重试",
        }))]
    except StockError as e:
        logger.warning("Tool %s error: %s", name, e.message)
        return [types.TextContent(type="text", text=_format_json(format_error_response(e)))]
    except Exception as e:
        logger.exception("Tool %s unexpected error", name)
        return [types.TextContent(type="text", text=_format_json({
            "error": True, "code": "INTERNAL_ERROR", "message": str(e),
        }))]


# ================================================================
# Helpers
# ================================================================

def _format_json(data: Any) -> str:
    """格式化 JSON 输出（兼容 numpy 类型）"""
    kwargs = {"ensure_ascii": False, "indent": 2}
    if _NPEncoder is not None:
        kwargs["cls"] = _NPEncoder
    return json.dumps(data, **kwargs)


# ================================================================
# Entry
# ================================================================

async def main():
    logger.info("mcp-finance v%s starting (easy-tdx + AKShare)", __version__)

    # ── 启动预热：后台预初始化 TDX 连接和 AKShare 数据 ──
    async def _warmup():
        try:
            from mcp_finance.api import _get_tdx
            tdx = await asyncio.to_thread(_get_tdx)
            if tdx:
                logger.info("预热: easy-tdx 连接成功")
        except Exception as e:
            logger.warning("预热: easy-tdx 初始化跳过 (%s)", e)
        try:
            from mcp_finance.api import _get_ak
            ak = _get_ak()
            logger.info("预热: AKShare 模块加载成功")
        except Exception as e:
            logger.warning("预热: AKShare 加载跳过 (%s)", e)
        logger.info("mcp-finance 预热完成，可以处理请求")

    asyncio.create_task(_warmup())

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-finance",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def cli():
    """sync entry point for console_scripts"""
    import asyncio
    asyncio.run(main())

if __name__ == "__main__":
    cli()


