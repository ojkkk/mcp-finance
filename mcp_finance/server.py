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
from mcp_finance.backtest import handle_backtest, handle_optimize
from mcp_finance.chart import handle_plot_kline
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
TOOL_HANDLERS["plot_kline"] = handle_plot_kline
TOOL_HANDLERS["get_dragon_tiger"] = handle_dragon_tiger
TOOL_HANDLERS["get_block_trades"] = handle_block_trades
TOOL_HANDLERS["get_margin_trading"] = handle_margin_trading
TOOL_HANDLERS["get_futures_list"] = handle_futures_list
TOOL_HANDLERS["test_data_sources"] = handle_test_data_sources


# -- Search (纯本地，无网络) --
@_register("search_stock")
def _search_stock(args: dict) -> list:
    from mcp_finance.api import search_stocks
    return search_stocks(args.get("market", "a"), args["keyword"], args.get("top_n", 10))


# -- Alert (一次性检查) --
@_register("set_alert")
def _set_alert(args: dict) -> dict:
    from mcp_finance.monitor import handle_set_alert
    return handle_set_alert(args)


# -- PyBroker (placeholder) --
@_register("pybroker_backtest")
def _pybroker_backtest(args: dict) -> dict:
    from mcp_finance.pybroker_strategy import handle_pybroker_backtest
    return handle_pybroker_backtest(args)


# ================================================================
# Resources
# ================================================================

@server.list_resources()
async def list_resources() -> list[types.Resource]:
    return [
        types.Resource(uri="stock://popular", name="热门股票列表", description="常用A股/指数代码和名称", mimeType="application/json"),
        types.Resource(uri="stock://market/indices", name="大盘指数", description="上证/深证/创业板/沪深300/科创50实时行情", mimeType="application/json"),
        types.Resource(uri="stock://{code}/realtime", name="个股实时行情", description="指定股票的实时行情数据", mimeType="application/json"),
        types.Resource(uri="stock://{code}/kline", name="个股K线", description="指定股票最近30天日K线", mimeType="application/json"),
        types.Resource(uri="stock://{code}/indicators", name="个股技术指标", description="指定股票的技术指标计算结果", mimeType="application/json"),
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
            description="获取股票核心财务数据（营收、净利润、ROE 等）。支持 A 股 (a) / 港股 (hk) / 美股 (us)，默认 a",
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
            description="全市场 A 股筛选：按涨跌幅、量比、换手率、市盈率、市净率、ROE、主力净流入、市值等条件筛选股票，返回匹配列表。注意：股息率/主力净流入字段当前暂不可用（数据源不支持），传入对应参数将不生效",
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
                    "min_roe": {"type": "number", "description": "最低净资产收益率 ROE(%)，如 10.0 — 通过财务缓存获取"},
                    "min_main_inflow": {"type": "number", "description": "（暂不可用）最低主力净流入（万元），正值表示净流入，如 5000"},
                    "min_dividend": {"type": "number", "description": "（暂不可用）最低股息率(%)，如 3.0 — 数据源不支持，传入此参数不生效"},
                    "min_market_cap": {"type": "number", "description": "最低总市值（亿元），如 100"},
                    "top_n": {"type": "integer", "description": "返回前 N 条"},
                },
            },
        ),
        types.Tool(
            name="backtest_strategy",
            description="策略回测：对指定股票跑历史策略回测，返回收益率、夏普比率、最大回撤、交易记录等绩效统计",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码，如 '600519'"},
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
            description="参数优化：网格扫描策略参数组合，自动找出最优参数（基于 Backtrader 事件驱动引擎）。注意：总组合数上限 200 组",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码，如 '000333'"},
                    "strategy": {"type": "string", "description": "策略: ma_cross=双均线, macd_signal=MACD, rsi_signal=RSI, kdj_signal=KDJ, boll_signal=BOLL"},
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
            name="set_alert",
            description="单次预警检查：立即检查是否满足条件并返回结果。规则不会持久化 — 这是一次性检查，非后台持续盯盘。如需持续监控，请独立运行 run_monitor.py。条件支持：价格突破/跌破、涨跌幅阈值、MACD金叉死叉、均线金叉死叉、RSI超买超卖。触发后可通过钉钉/企业微信/Server酱推送",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码"},
                    "condition": {"type": "string", "description": "预警条件，如 'price_above:1900' 或 'macd_golden_cross'"},
                    "channel": {"type": "string", "description": "推送渠道: dingtalk / wecom / serverchan"},
                },
                "required": ["code", "condition"],
            },
        ),
        types.Tool(
            name="pybroker_backtest",
            description="均值比较信号回测（实验性）：基于技术指标均值比较生成买卖信号，非真正的 ML 模型。model_type 参数暂为占位符，所有模型走同一规则。",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码，如 '600519'"},
                    "start_date": {"type": "string", "description": "开始日期，如 '2024-01-01'"},
                    "end_date": {"type": "string", "description": "结束日期，如 '2024-12-31'"},
                    "initial_capital": {"type": "number", "description": "初始资金（元），默认 100000"},
                    "train_size": {"type": "number", "description": "训练集比例，默认 0.7"},
                },
                "required": ["code"],
            },
        ),
    ]


# ================================================================
# Parameter Validators
# ================================================================

_TOOL_VALIDATORS: dict[str, Any] = {}
try:
    from mcp_finance.validators import (
        KlineParams, FinancialsParams, SectorRankingParams,
        NorthFlowParams, TechnicalIndicatorsParams,
        ScreenerParams, BacktestParams, OptimizeParams,
        PlotKlineParams, validate_and_coerce,
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
        "plot_kline": PlotKlineParams,
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
            import sys
            old_stdout = sys.stdout
            try:
                sys.stdout = open(os.devnull, "w", encoding="utf-8")
                return handler(arguments)
            finally:
                sys.stdout.close()
                sys.stdout = old_stdout

        result = await asyncio.wait_for(asyncio.to_thread(_safe_handler), timeout=90.0)
        return [types.TextContent(type="text", text=_format_json(result))]
    except asyncio.TimeoutError:
        logger.error("Tool %s timed out (90s) — thread pool may be exhausted", name)
        return [types.TextContent(type="text", text=_format_json({
            "error": True, "code": "TIMEOUT",
            "message": "工具调用超时 (90s)。可能是网络请求阻塞或线程池耗尽，请稍后重试",
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

