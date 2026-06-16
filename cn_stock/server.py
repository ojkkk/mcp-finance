"""
mcp-stock-cn — 中国股市实时行情 MCP Server

提供 Tools:
  - get_realtime_quote        — 查询 A 股/指数实时行情
  - get_kline                 — 获取 K 线数据
  - get_financials            — 获取财务数据
  - get_market_indices        — 大盘指数行情
  - get_sector_ranking        — 板块涨幅排行
  - get_north_flow            — 北向/南向资金流向
  - search_stock              — 搜索股票
  - batch_quotes              — 批量查询行情
  - get_technical_indicators  — 技术指标 + 信号识别
  - stock_screener            — 全市场股票筛选
  - set_alert                 — 条件告警 + 推送
  - plot_kline                — Plotly 交互式 K 线图

提供 Resources:
  - stock://popular           — 热门 A 股列表
  - stock://{code}/realtime   — 单只股票实时行情
"""

from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from cn_stock.api import (
    get_financials,
    get_kline,
    get_market_indices,
    get_north_flow,
    get_realtime_quotations,
    get_sector_ranking,
    guess_secid,
    search_stocks,
    _fetch_json,
    _get_tencent_realtime,
)
from cn_stock.data import SECTORS, HOT_STOCKS
from cn_stock.indicators import compute_all_indicators
from cn_stock.screener import screen_stocks
from cn_stock.backtest import run_backtest, optimize_backtest
from cn_stock.monitor import evaluate_alert_conditions, push_alerts
from cn_stock.chart import generate_kline_chart, generate_backtest_chart

server = Server("mcp-stock-cn")


# ═════════════════════════════════════════════════════════════════════
# Resources
# ═════════════════════════════════════════════════════════════════════

@server.list_resources()
async def list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            uri="stock://popular",
            name="热门 A 股",
            description="A 股热门股票列表（含代码、名称）",
            mimeType="application/json",
        ),
        # 动态 resource 通过 list_resource_templates 提供
    ]


@server.list_resource_templates()
async def list_resource_templates() -> list[types.ResourceTemplate]:
    return [
        types.ResourceTemplate(
            uriTemplate="stock://{code}/realtime",
            name="个股实时行情",
            description="查询单只 A 股或指数的实时行情",
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "stock://popular":
        import json
        return json.dumps(HOT_STOCKS, ensure_ascii=False, indent=2)

    # 动态: stock://{code}/realtime
    import re
    m = re.match(r"stock://(\w+)/realtime", uri)
    if m:
        code = m.group(1)
        secid = guess_secid(code)
        quotes = get_realtime_quotations([secid])
        if quotes:
            import json
            return json.dumps(quotes[0], ensure_ascii=False, indent=2)
        raise ValueError(f"未找到股票代码: {code}")

    raise ValueError(f"未知资源 URI: {uri}")


# ═════════════════════════════════════════════════════════════════════
# Tools
# ═════════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_realtime_quote",
            description="查询 A 股/指数实时行情，支持股票代码或名称",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码或名称，如 '600519'、'贵州茅台'、'上证指数'",
                    },
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_kline",
            description="获取股票 K 线数据（日/周/月/60分钟）",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码，如 '600519'",
                    },
                    "ktype": {
                        "type": "string",
                        "description": "K线类型: daily=日K, weekly=周K, monthly=月K, minute60=60分钟",
                        "default": "daily",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数，最多 800",
                        "default": 120,
                    },
                    "adjust": {
                        "type": "string",
                        "description": "复权方式: qfq=前复权, bfq=不复权, hfq=后复权",
                        "default": "qfq",
                    },
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_financials",
            description="获取股票核心财务数据（营收、净利润、ROE 等）",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "6位股票代码，如 '600519'",
                    },
                    "count": {
                        "type": "integer",
                        "description": "最近几期数据",
                        "default": 4,
                    },
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="get_market_indices",
            description="获取主要大盘指数实时行情（上证、深证、创业板、沪深300、科创50）",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="get_sector_ranking",
            description="获取行业/概念板块涨幅排行榜",
            inputSchema={
                "type": "object",
                "properties": {
                    "sector_type": {
                        "type": "string",
                        "description": "板块类型: industry=行业板块, concept=概念板块, region=地域板块",
                        "default": "industry",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "返回前 N 名",
                        "default": 10,
                    },
                },
            },
        ),
        types.Tool(
            name="get_north_flow",
            description="获取北向/南向资金流向（沪深港通）",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "最近几天",
                        "default": 5,
                    },
                },
            },
        ),
        types.Tool(
            name="search_stock",
            description="按关键词搜索股票（代码或名称）",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如 '茅台'、'6005'",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "返回条数",
                        "default": 10,
                    },
                },
                "required": ["keyword"],
            },
        ),
        types.Tool(
            name="batch_quotes",
            description="批量查询多只股票的实时行情",
            inputSchema={
                "type": "object",
                "properties": {
                    "codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "股票代码列表，如 ['600519', '300750', '000333']",
                    },
                },
                "required": ["codes"],
            },
        ),
        # ── 新增工具 ─────────────────────────────────────────────
        types.Tool(
            name="get_technical_indicators",
            description="计算股票技术指标：MA(5/10/20/60/120/250)、MACD(DIF/DEA/柱)、KDJ(K/D/J)、RSI(6/14/24)、BOLL(上下轨)、WR、BIAS，并自动识别金叉/死叉/超买超卖/均线排列信号",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "6位股票代码，如 '600519'",
                    },
                    "days": {
                        "type": "integer",
                        "description": "取多少根 K 线计算（建议 60-250，越多指标越完整）",
                        "default": 120,
                    },
                    "ktype": {
                        "type": "string",
                        "description": "K线类型: daily=日K, weekly=周K",
                        "default": "daily",
                    },
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="stock_screener",
            description="全市场 A 股筛选：按涨跌幅、量比、换手率、市盈率、市净率、ROE、市值、主力净流入、股息率等条件筛选股票，返回匹配列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_gain": {
                        "type": "number",
                        "description": "最低涨跌幅 %，如 3.0 表示至少涨 3%",
                    },
                    "max_gain": {
                        "type": "number",
                        "description": "最高涨跌幅 %，如 -5.0 表示跌不超过 5%",
                    },
                    "min_volume_ratio": {
                        "type": "number",
                        "description": "最低量比（当日成交量/5日均量），如 1.5 表示放量 50%",
                    },
                    "min_turnover": {
                        "type": "number",
                        "description": "最低换手率 %，如 5.0",
                    },
                    "max_pe": {
                        "type": "number",
                        "description": "最高市盈率（过滤亏损/高估值），如 50",
                    },
                    "min_market_cap": {
                        "type": "number",
                        "description": "最低总市值（亿元），如 100",
                    },
                    "min_pb": {
                        "type": "number",
                        "description": "最低市净率 PB，如 1.0 表示至少 1 倍",
                    },
                    "max_pb": {
                        "type": "number",
                        "description": "最高市净率 PB，如 5.0",
                    },
                    "min_roe": {
                        "type": "number",
                        "description": "最低净资产收益率 ROE(%)，如 10.0",
                    },
                    "min_main_inflow": {
                        "type": "number",
                        "description": "最低主力净流入（万元），正值表示净流入，如 5000",
                    },
                    "min_dividend": {
                        "type": "number",
                        "description": "最低股息率(%)，如 3.0",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "返回前 N 条",
                        "default": 30,
                    },
                },
            },
        ),
        types.Tool(
            name="backtest_strategy",
            description="策略回测：对指定股票跑历史策略回测，返回收益率、夏普比率、最大回撤、交易记录等绩效统计",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "6位股票代码，如 '600519'",
                    },
                    "strategy": {
                        "type": "string",
                        "description": "策略名称: ma_cross=双均线交叉, macd_signal=MACD金叉死叉",
                        "default": "ma_cross",
                    },
                    "fast_period": {
                        "type": "integer",
                        "description": "快线周期: 均线策略用(MA周期), MACD策略用(fast周期)",
                        "default": 5,
                    },
                    "slow_period": {
                        "type": "integer",
                        "description": "慢线周期: 均线策略用(MA周期), MACD策略用(slow周期)",
                        "default": 20,
                    },
                    "start_date": {
                        "type": "string",
                        "description": "回测开始日期，如 '2024-01-01'，默认一年前",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "回测结束日期，如 '2024-12-31'，默认今天",
                    },
                    "initial_capital": {
                        "type": "number",
                        "description": "初始资金（元），默认 100000",
                        "default": 100000,
                    },
                    "generate_chart": {
                        "type": "boolean",
                        "description": "是否生成权益曲线对比图（策略 vs 基准），默认 true",
                        "default": True,
                    },
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="optimize_strategy",
            description="参数优化：网格扫描策略参数组合，自动找出最优参数（基于 vectorbt 向量化引擎）",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码，如 '000333'"},
                    "strategy": {"type": "string", "description": "策略: ma_cross=双均线, macd_signal=MACD", "default": "ma_cross"},
                    "fast_min": {"type": "integer", "description": "快线最小值", "default": 5},
                    "fast_max": {"type": "integer", "description": "快线最大值", "default": 20},
                    "fast_step": {"type": "integer", "description": "快线步长", "default": 5},
                    "slow_min": {"type": "integer", "description": "慢线最小值", "default": 20},
                    "slow_max": {"type": "integer", "description": "慢线最大值", "default": 60},
                    "slow_step": {"type": "integer", "description": "慢线步长", "default": 10},
                    "start_date": {"type": "string", "description": "开始日期，如 '2024-01-01'"},
                    "end_date": {"type": "string", "description": "结束日期，如 '2024-12-31'"},
                    "metric": {"type": "string", "description": "优化目标: sharpe/return/mdd/win_rate", "default": "sharpe"},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="set_alert",
            description="设置股票预警条件，支持：价格突破/跌破、涨跌幅阈值、MACD金叉死叉、均线金叉死叉、RSI超买超卖。触发后可通过钉钉/企业微信/Server酱推送",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码，如 '600519'",
                    },
                    "price_above": {
                        "type": "number",
                        "description": "股价突破此价格则告警",
                    },
                    "price_below": {
                        "type": "number",
                        "description": "股价跌破此价格则告警",
                    },
                    "gain_above": {
                        "type": "number",
                        "description": "涨幅超过此 % 则告警",
                    },
                    "gain_below": {
                        "type": "number",
                        "description": "跌幅超过此 % 则告警",
                    },
                    "macd_golden": {
                        "type": "boolean",
                        "description": "MACD 金叉告警",
                    },
                    "macd_death": {
                        "type": "boolean",
                        "description": "MACD 死叉告警",
                    },
                    "ma_golden": {
                        "type": "boolean",
                        "description": "均线金叉 (MA5上穿MA20) 告警",
                    },
                    "ma_death": {
                        "type": "boolean",
                        "description": "均线死叉 (MA5下穿MA20) 告警",
                    },
                    "rsi_above": {
                        "type": "number",
                        "description": "RSI(14) 超过此值告警，如 80",
                    },
                    "rsi_below": {
                        "type": "number",
                        "description": "RSI(14) 低于此值告警，如 20",
                    },
                    "push_channel": {
                        "type": "string",
                        "description": "推送渠道: dingtalk / wecom / serverchan",
                        "default": "dingtalk",
                    },
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="plot_kline",
            description="⚠️ 生成交互式 K 线 HTML 文件（不是PNG图片！），含蜡烛图+均线+成交量+MACD/KDJ/RSI副图。返回文件路径，请务必用浏览器打开该 HTML 文件查看（支持缩放/平移/悬停查看数值）",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "6位股票代码，如 '600519'",
                    },
                    "days": {
                        "type": "integer",
                        "description": "K 线条数",
                        "default": 120,
                    },
                    "ktype": {
                        "type": "string",
                        "description": "K线类型: daily=日K, weekly=周K",
                        "default": "daily",
                    },
                    "show_macd": {
                        "type": "boolean",
                        "description": "是否显示 MACD 副图",
                        "default": True,
                    },
                    "show_kdj": {
                        "type": "boolean",
                        "description": "是否显示 KDJ 副图",
                        "default": False,
                    },
                    "show_rsi": {
                        "type": "boolean",
                        "description": "是否显示 RSI 副图",
                        "default": False,
                    },
                },
                "required": ["code"],
            },
        ),
        # ── AKShare 第四数据源 ──
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
            description="🧪 诊断所有数据源是否可用（Baostock / 东方财富 / 腾讯），逐项测试并返回状态",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str,
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    if name == "get_realtime_quote":
        code = arguments["code"]
        secid = _resolve_secid(code)
        quotes = get_realtime_quotations([secid])
        if not quotes:
            return [types.TextContent(type="text", text=f"未找到股票数据: {code}")]
        return [types.TextContent(
            type="text",
            text=_format_json(quotes[0]),
        )]

    elif name == "get_kline":
        code = arguments["code"]
        secid = guess_secid(code)
        ktype_map = {
            "daily": "101",
            "weekly": "102",
            "monthly": "103",
            "minute60": "60",
        }
        adjust_map = {
            "qfq": "1",   # 前复权
            "bfq": "0",   # 不复权
            "hfq": "2",   # 后复权
        }
        klt = ktype_map.get(arguments.get("ktype", "daily"), "101")
        fqt = adjust_map.get(arguments.get("adjust", "qfq"), "1")
        lmt = min(arguments.get("limit", 120), 800)

        klines = get_kline(secid, klt=klt, fqt=fqt, lmt=lmt)
        if not klines:
            return [types.TextContent(
                type="text",
                text=f"未获取到 {code} 的 K 线数据（非交易日或参数有误）",
            )]
        return [types.TextContent(
            type="text",
            text=_format_json(klines),
        )]

    elif name == "get_financials":
        code = arguments["code"]
        count = arguments.get("count", 4)
        data = get_financials(code, page_size=count)
        if not data:
            return [types.TextContent(
                type="text",
                text=f"未找到 {code} 的财务数据",
            )]
        return [types.TextContent(
            type="text",
            text=_format_json(data),
        )]

    elif name == "get_market_indices":
        indices = get_market_indices()
        if not indices:
            return [types.TextContent(type="text", text="获取大盘指数失败")]
        return [types.TextContent(
            type="text",
            text=_format_json(indices),
        )]

    elif name == "get_sector_ranking":
        sector_type = arguments.get("sector_type", "industry")
        top_n = min(arguments.get("top_n", 10), 50)
        data = get_sector_ranking(sector_type=sector_type, top_n=top_n)
        if not data:
            return [types.TextContent(type="text", text="获取板块排行失败")]
        return [types.TextContent(
            type="text",
            text=_format_json(data),
        )]

    elif name == "get_north_flow":
        days = min(arguments.get("days", 5), 30)
        data = get_north_flow(days=days)
        if not data:
            return [types.TextContent(type="text", text="获取北向资金数据失败")]
        return [types.TextContent(
            type="text",
            text=_format_json(data),
        )]

    elif name == "search_stock":
        keyword = arguments["keyword"]
        top_n = min(arguments.get("top_n", 10), 50)
        results = search_stocks(keyword, top_n=top_n)
        if not results:
            return [types.TextContent(
                type="text",
                text=f"未找到匹配股票: {keyword}",
            )]
        return [types.TextContent(
            type="text",
            text=_format_json(results),
        )]

    elif name == "batch_quotes":
        codes = arguments.get("codes", [])
        if not codes:
            return [types.TextContent(type="text", text="请提供至少一个股票代码")]
        secids = [guess_secid(c) for c in codes]
        quotes = get_realtime_quotations(secids)
        if not quotes:
            return [types.TextContent(type="text", text="获取批量行情失败")]
        # 把传入的原始代码映射回去
        return [types.TextContent(
            type="text",
            text=_format_json(quotes),
        )]

    # ── 新增工具处理器 ──────────────────────────────────────────
    elif name == "get_technical_indicators":
        code = arguments["code"]
        secid = guess_secid(code)
        days = min(arguments.get("days", 120), 800)
        ktype = arguments.get("ktype", "daily")
        klt_map = {"daily": "101", "weekly": "102", "monthly": "103"}
        klt = klt_map.get(ktype, "101")

        klines = get_kline(secid, klt=klt, fqt="1", lmt=days)
        if not klines:
            return [types.TextContent(type="text", text=f"无法获取 {code} 的 K 线数据")]

        dates = [k["日期"] for k in klines]
        result = compute_all_indicators(klines, dates)

        # 附上实时行情
        quote = get_realtime_quotations([secid])
        if quote:
            result["实时行情"] = quote[0]

        return [types.TextContent(type="text", text=_format_json(result))]

    elif name == "stock_screener":
        min_gain = arguments.get("min_gain")
        max_gain = arguments.get("max_gain")
        min_volume_ratio = arguments.get("min_volume_ratio")
        min_turnover = arguments.get("min_turnover")
        max_pe = arguments.get("max_pe")
        min_market_cap = arguments.get("min_market_cap")
        min_pb = arguments.get("min_pb")
        max_pb = arguments.get("max_pb")
        min_roe = arguments.get("min_roe")
        min_main_inflow = arguments.get("min_main_inflow")
        min_dividend = arguments.get("min_dividend")
        top_n = min(arguments.get("top_n", 30), 100)

        if not any([min_gain, max_gain, min_volume_ratio, min_turnover, max_pe, min_market_cap,
                     min_pb, max_pb, min_roe, min_main_inflow, min_dividend]):
            return [types.TextContent(
                type="text",
                text="请至少设置一个筛选条件",
            )]

        result = screen_stocks(
            min_gain=min_gain,
            max_gain=max_gain,
            min_volume_ratio=min_volume_ratio,
            min_turnover=min_turnover,
            max_pe=max_pe,
            min_market_cap=min_market_cap,
            min_pb=min_pb,
            max_pb=max_pb,
            min_roe=min_roe,
            min_main_inflow=min_main_inflow,
            min_dividend=min_dividend,
            top_n=top_n,
        )
        return [types.TextContent(type="text", text=_format_json(result))]

    elif name == "backtest_strategy":
        code = arguments["code"]
        strategy = arguments.get("strategy", "ma_cross")
        fast_period = arguments.get("fast_period", 5)
        slow_period = arguments.get("slow_period", 20)
        start_date = arguments.get("start_date")
        end_date = arguments.get("end_date")
        initial_capital = arguments.get("initial_capital", 100000.0)
        generate_chart = arguments.get("generate_chart", True)

        result = run_backtest(
            code=code,
            strategy=strategy,
            fast_period=fast_period,
            slow_period=slow_period,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )

        # 生成权益曲线对比图
        if generate_chart and "error" not in result and "权益曲线" in result:
            try:
                stock_name = result["股票"]
                chart_path = generate_backtest_chart(
                    stock_name=stock_name,
                    strategy_label=result["策略"],
                    strategy_curve=result["权益曲线"],
                    benchmark_curve=result["基准(买入持有)"]["权益曲线"] if "基准(买入持有)" in result else None,
                    trades=result.get("交易记录", []),
                    initial_capital=initial_capital,
                )
                result["权益曲线图"] = chart_path
                result["权益曲线图提示"] = "这不是图片！这是一个交互式HTML文件，请用浏览器打开"
            except Exception as e:
                result["权益曲线图"] = f"图表生成失败: {e}"

        return [types.TextContent(type="text", text=_format_json(result))]

    elif name == "optimize_strategy":
        code = arguments["code"]
        strategy = arguments.get("strategy", "ma_cross")
        fast_min = arguments.get("fast_min", 5)
        fast_max = arguments.get("fast_max", 20)
        fast_step = arguments.get("fast_step", 5)
        slow_min = arguments.get("slow_min", 20)
        slow_max = arguments.get("slow_max", 60)
        slow_step = arguments.get("slow_step", 10)
        start_date = arguments.get("start_date")
        end_date = arguments.get("end_date")
        metric = arguments.get("metric", "sharpe")

        fast_range = list(range(fast_min, fast_max + 1, fast_step))
        slow_range = list(range(slow_min, slow_max + 1, slow_step))

        result = optimize_backtest(
            code=code, strategy=strategy,
            fast_range=fast_range, slow_range=slow_range,
            start_date=start_date, end_date=end_date,
            metric=metric,
        )
        return [types.TextContent(type="text", text=_format_json(result))]

    elif name == "set_alert":
        code = arguments["code"]
        secid = guess_secid(code)

        klines = get_kline(secid, klt="101", fqt="1", lmt=60)
        indicators = compute_all_indicators(klines) if klines else {"snapshot": {}, "signals": []}
        quotes = get_realtime_quotations([secid])
        quote = quotes[0] if quotes else {}

        rules: dict[str, Any] = {}
        for key in ["price_above", "price_below", "gain_above", "gain_below",
                     "rsi_above", "rsi_below"]:
            if key in arguments and arguments[key] is not None:
                rules[key] = arguments[key]
        for key in ["macd_golden", "macd_death", "ma_golden", "ma_death"]:
            if arguments.get(key):
                rules[key] = True

        if not rules:
            return [types.TextContent(type="text", text="请至少设置一个告警条件")]

        stock_name = quote.get("名称", code)
        triggered = evaluate_alert_conditions(code, stock_name, indicators, quote, rules)
        channel = arguments.get("push_channel", "dingtalk")
        push_result = push_alerts(triggered, channels=[channel])

        result = {
            "股票": f"{stock_name}({code})",
            "当前价": quote.get("最新价"),
            "涨跌幅": quote.get("涨跌幅"),
            "规则": rules,
            "触发告警": triggered,
            "推送结果": push_result,
        }
        return [types.TextContent(type="text", text=_format_json(result))]

    elif name == "plot_kline":
        code = arguments["code"]
        secid = guess_secid(code)
        days = min(arguments.get("days", 120), 800)
        ktype = arguments.get("ktype", "daily")
        klt_map = {"daily": "101", "weekly": "102", "monthly": "103"}
        klt = klt_map.get(ktype, "101")

        klines = get_kline(secid, klt=klt, fqt="1", lmt=days)
        if not klines:
            return [types.TextContent(type="text", text=f"无法获取 {code} 的 K 线数据")]

        quotes = get_realtime_quotations([secid])
        stock_name = quotes[0]["名称"] if quotes else code
        indicators = compute_all_indicators(klines)

        show_macd = arguments.get("show_macd", True)
        show_kdj = arguments.get("show_kdj", False)
        show_rsi = arguments.get("show_rsi", False)

        try:
            output_path = generate_kline_chart(
                kline_data=klines,
                stock_name=stock_name,
                indicators=indicators,
                show_volume=True,
                show_macd=show_macd,
                show_kdj=show_kdj,
                show_rsi=show_rsi,
            )
            result = {
                "⚠️重要提示": "这不是图片！这是一个交互式HTML文件，请用浏览器打开下面的路径",
                "股票": f"{stock_name}({code})",
                "K线条数": len(klines),
                "起止日期": f"{klines[0]['日期']} ~ {klines[-1]['日期']}",
                "HTML文件路径": output_path,
                "打开方式": "在文件管理器中找到该文件 → 双击用浏览器打开 → 可缩放/平移/悬停查看每根K线数值",
                "最新收盘价": klines[-1]["收盘价"],
                "技术信号": indicators.get("signals", []),
            }
            return [types.TextContent(type="text", text=_format_json(result))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"生成图表失败: {e}")]

    # ── AKShare 第四数据源 ──
    elif name == "get_dragon_tiger":
        from cn_stock.akshare_data import get_dragon_tiger
        result = get_dragon_tiger(date=arguments.get("date"))
        return [types.TextContent(type="text", text=_format_json(result))]

    elif name == "get_block_trades":
        from cn_stock.akshare_data import get_block_trades
        result = get_block_trades(
            symbol=arguments.get("symbol"),
            start_date=arguments.get("start_date"),
            end_date=arguments.get("end_date"),
        )
        return [types.TextContent(type="text", text=_format_json(result))]

    elif name == "get_margin_trading":
        from cn_stock.akshare_data import get_margin_trading
        result = get_margin_trading(
            market=arguments.get("market", "all"),
            date=arguments.get("date"),
        )
        return [types.TextContent(type="text", text=_format_json(result))]

    elif name == "test_data_sources":
        from datetime import datetime, timedelta

        results: dict[str, Any] = {
            "测试时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "数据源": {},
        }

        # 1. Baostock
        try:
            import baostock as bs
            lg = bs.login()
            if lg.error_code == "0":
                rs = bs.query_history_k_data_plus(
                    "sh.600519", "date,close",
                    start_date=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                    end_date=datetime.now().strftime("%Y-%m-%d"),
                    frequency="d", adjustflag="2",
                )
                rows = []
                while rs.next():
                    row = rs.get_row_data()
                    if row and row[0]:
                        rows.append(row)
                bs.logout()
                results["数据源"]["Baostock"] = {
                    "状态": "✅ 正常",
                    "数据条数": len(rows),
                    "说明": "历史K线 · 量化级数据",
                }
            else:
                results["数据源"]["Baostock"] = {"状态": f"❌ 登录失败", "错误码": lg.error_code}
        except ImportError:
            results["数据源"]["Baostock"] = {"状态": "⚠️ 未安装", "修复": "pip install baostock"}
        except Exception as e:
            results["数据源"]["Baostock"] = {"状态": f"❌ {e}"}

        # 2. 东方财富 K线
        try:
            klines_em = _fetch_json("push2.eastmoney.com", "/api/qt/stock/kline/get", {
                "secid": "1.600519", "klt": "101", "fqt": "1", "lmt": "5",
                "fields1": "f1,f2", "fields2": "f51,f52",
                "ut": "7eea3edcaed734bea9cffc9f32ec1c0c",
            })
            if klines_em.get("rc") == 0:
                cnt = len(klines_em.get("data", {}).get("klines", []))
                results["数据源"]["东方财富K线"] = {"状态": "✅ 正常", "数据条数": cnt}
            else:
                results["数据源"]["东方财富K线"] = {"状态": "❌", "响应": klines_em.get("rc")}
        except Exception as e:
            results["数据源"]["东方财富K线"] = {"状态": f"❌ {e}"}

        # 3. 东方财富 实时行情
        try:
            quotes = get_realtime_quotations(["1.600519"])
            results["数据源"]["东方财富实时行情"] = {
                "状态": "✅ 正常" if quotes else "❌ 返回空",
            }
        except Exception as e:
            results["数据源"]["东方财富实时行情"] = {"状态": f"❌ {e}"}

        # 4. 腾讯财经
        try:
            tx = _get_tencent_realtime(["1.600519"])
            results["数据源"]["腾讯财经"] = {
                "状态": "✅ 正常" if tx else "❌ 返回空",
                "数据条数": len(tx) if tx else 0,
            }
        except Exception as e:
            results["数据源"]["腾讯财经"] = {"状态": f"❌ {e}"}

        ok = sum(1 for v in results["数据源"].values() if "✅" in str(v.get("状态", "")))
        total = len(results["数据源"])
        results["总结"] = f"{ok}/{total} 数据源可用"
        if ok == 0:
            results["建议"] = "所有数据源不可用，请检查网络连接或安装 baostock: pip install baostock"

        return [types.TextContent(type="text", text=_format_json(results))]

    else:
        raise ValueError(f"未知工具: {name}")


# ═════════════════════════════════════════════════════════════════════
# 辅助函数
# ═════════════════════════════════════════════════════════════════════

def _resolve_secid(code: str) -> str:
    """将股票代码或名称解析为 secid"""
    code = code.strip()

    # 尝试直接匹配名称 → 代码
    from cn_stock.data import STOCK_MAPPING
    for c, name in STOCK_MAPPING.items():
        if code == name:
            return guess_secid(c)

    # 尝试匹配指数名称
    from cn_stock.api import INDEX_SECIDS
    if code in INDEX_SECIDS:
        return INDEX_SECIDS[code]

    # 作为代码处理
    return guess_secid(code)


def _format_json(data: Any) -> str:
    """格式化 JSON 输出（兼容 numpy 类型）"""
    import json
    try:
        import numpy as np
        class _NPEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, (np.integer,)):
                    return int(obj)
                if isinstance(obj, (np.floating,)):
                    return float(obj)
                if isinstance(obj, (np.bool_,)):
                    return bool(obj)
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
                return super().default(obj)
        return json.dumps(data, ensure_ascii=False, indent=2, cls=_NPEncoder)
    except ImportError:
        return json.dumps(data, ensure_ascii=False, indent=2)


# ═════════════════════════════════════════════════════════════════════
# 入口
# ═════════════════════════════════════════════════════════════════════

async def main():
    # 预热 Baostock 会话
    try:
        import baostock as bs
        bs.login()
    except ImportError:
        pass

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-stock-cn",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

    # 清理 Baostock 会话
    try:
        import baostock as bs
        bs.logout()
    except ImportError:
        pass


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())