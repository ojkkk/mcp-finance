"""
mcp-finance — 全市场实时行情 MCP Server

提供 31 个 Tools + Resources，基于 AKShare / easy-tdx / yfinance 数据源。
Handler 逻辑已拆分到各模块，本文件使用 MCP Python SDK 2.x 的 MCPServer 注册路由。
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from typing import Annotated, Any

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

from mcp.server import MCPServer
from pydantic import BaseModel, Field

from mcp_finance import __version__
from mcp_finance.analysis import handle_analyze_stock, handle_compare_stocks, handle_factor_screener
from mcp_finance.api import (
    handle_batch_quotes,
    handle_block_trades,
    handle_dragon_tiger,
    handle_financials,
    handle_futures_list,
    handle_kline,
    handle_margin_trading,
    handle_market_indices,
    handle_north_flow,
    handle_realtime_quote,
    handle_sector_ranking,
    handle_test_data_sources,
)
from mcp_finance.api_extended import (
    handle_fund_flow,
    handle_institutional_holdings,
    handle_macro_data,
    handle_minute_kline,
    handle_research_reports,
)
from mcp_finance.backtest import handle_backtest, handle_monte_carlo, handle_optimize, handle_walk_forward
from mcp_finance.chart import handle_comparison_chart, handle_plot_kline
from mcp_finance.data import HOT_STOCKS
from mcp_finance.errors import StockError, format_error_response
from mcp_finance.indicators import handle_technical_indicators
from mcp_finance.logging_config import get_logger
from mcp_finance.portfolio import handle_correlation_matrix, handle_portfolio_backtest
from mcp_finance.screener import handle_stock_screener
from mcp_finance.validators import (
    AnalyzeStockParams,
    BacktestParams,
    BatchQuotesParams,
    BlockTradesParams,
    CompareStocksParams,
    ComparisonChartParams,
    CorrelationMatrixParams,
    DragonTigerParams,
    FactorScreenerParams,
    FinancialsParams,
    FundFlowParams,
    InstitutionalHoldingsParams,
    KlineParams,
    MacroDataParams,
    MarginTradingParams,
    MarketIndicesParams,
    MinuteKlineParams,
    MonteCarloParams,
    NorthFlowParams,
    OptimizeParams,
    PlotKlineParams,
    PortfolioBacktestParams,
    RealtimeQuoteParams,
    ResearchReportsParams,
    ScreenerParams,
    SearchStockParams,
    SectorRankingParams,
    TechnicalIndicatorsParams,
    WalkForwardParams,
    validate_and_coerce,
)

logger = get_logger(__name__)
mcp = MCPServer("mcp-finance", version=__version__)


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


def _format_json(data: Any) -> str:
    """格式化 JSON 输出（兼容 numpy 类型）"""
    kwargs = {"ensure_ascii": False, "indent": 2}
    if _NPEncoder is not None:
        kwargs["cls"] = _NPEncoder
    return json.dumps(data, **kwargs)


# ================================================================
# Tool handlers
# ================================================================

def _search_stock(args: dict[str, Any]) -> list:
    from mcp_finance.api import search_stocks
    return search_stocks(args.get("market", "a"), args["keyword"], args.get("top_n", 10))


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "get_realtime_quote": handle_realtime_quote,
    "get_kline": handle_kline,
    "get_financials": handle_financials,
    "get_market_indices": handle_market_indices,
    "get_sector_ranking": handle_sector_ranking,
    "get_north_flow": handle_north_flow,
    "batch_quotes": handle_batch_quotes,
    "get_technical_indicators": handle_technical_indicators,
    "stock_screener": handle_stock_screener,
    "backtest_strategy": handle_backtest,
    "optimize_strategy": handle_optimize,
    "walk_forward": handle_walk_forward,
    "monte_carlo_test": handle_monte_carlo,
    "plot_kline": handle_plot_kline,
    "comparison_chart": handle_comparison_chart,
    "get_dragon_tiger": handle_dragon_tiger,
    "get_block_trades": handle_block_trades,
    "get_margin_trading": handle_margin_trading,
    "get_futures_list": handle_futures_list,
    "test_data_sources": handle_test_data_sources,
    "get_minute_kline": handle_minute_kline,
    "get_fund_flow": handle_fund_flow,
    "get_institutional_holdings": handle_institutional_holdings,
    "get_macro_data": handle_macro_data,
    "get_research_reports": handle_research_reports,
    "analyze_stock": handle_analyze_stock,
    "compare_stocks": handle_compare_stocks,
    "factor_screener": handle_factor_screener,
    "correlation_matrix": handle_correlation_matrix,
    "portfolio_backtest": handle_portfolio_backtest,
    "search_stock": _search_stock,
}

# 保持与旧版 tools/list 一致的工具展示顺序。
_TOOL_NAMES = [
    "get_realtime_quote",
    "get_kline",
    "get_financials",
    "get_market_indices",
    "get_sector_ranking",
    "get_north_flow",
    "get_futures_list",
    "batch_quotes",
    "get_technical_indicators",
    "stock_screener",
    "backtest_strategy",
    "optimize_strategy",
    "plot_kline",
    "get_dragon_tiger",
    "get_block_trades",
    "get_margin_trading",
    "test_data_sources",
    "search_stock",
    "get_minute_kline",
    "get_fund_flow",
    "get_institutional_holdings",
    "get_macro_data",
    "get_research_reports",
    "analyze_stock",
    "compare_stocks",
    "correlation_matrix",
    "portfolio_backtest",
    "comparison_chart",
    "factor_screener",
    "walk_forward",
    "monte_carlo_test",
]

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_realtime_quote": "查询全市场实时行情。market: a=A股, hk=港股, us=美股, futures=期货",
    "get_kline": "获取股票 K 线数据（日/周/月/60分钟+前/后复权）。market: a/hk/us/futures",
    "get_financials": (
        "获取股票财务数据：核心指标(营收/净利润/EPS/每股净资产)、盈利能力(ROE/ROA/毛利率/净利率)"
        "、成长能力(营收增长率/净利润增长率)"
        "、财务风险(资产负债率/流动比率)、营运能力(周转率)。支持 A 股 (a) / 港股 (hk) / 美股 (us)，默认 a"
        "。A股数据源 AKShare东方财富+同花顺双源，港美股 yfinance 兜底"
    ),
    "get_market_indices": (
        "获取大盘指数实时行情。market: a=A股(上证/深证/创业板/沪深300/科创50/上证50/中证500)"
        ", hk=港股(恒生/恒生科技/国企)"
        ", us=美股(道琼斯/纳斯达克/标普500)"
    ),
    "get_sector_ranking": "获取行业/概念板块涨幅排行榜",
    "get_north_flow": "获取北向/南向资金流向（沪深港通）",
    "get_futures_list": "获取国内期货合约实时行情列表（商品期货+股指期货），含最新价/涨跌幅/持仓量",
    "batch_quotes": "批量查询多只股票的实时行情",
    "get_technical_indicators": (
        "计算股票技术指标：MA(5/10/20/60/120/250)、MACD(DIF/DEA/柱)、KDJ(K/D/J)"
        "、RSI(6/14/24)、BOLL(上下轨)、WR、BIAS"
        "，并自动识别金叉/死叉/超买超卖/均线排列信号"
    ),
    "stock_screener": (
        "全市场 A 股筛选：按涨跌幅、量比、换手率、市盈率、市净率、ROE、毛利率、净利率"
        "、营收增长率、市值等条件筛选股票"
        "，返回匹配列表"
    ),
    "backtest_strategy": (
        "策略回测：对指定股票跑历史策略回测，返回收益率、夏普比率、最大回撤、交易记录等绩效统计"
        "。支持 A 股(6位代码)/港股(5位代码)/美股(字母代码)"
        "，自动识别市场"
    ),
    "optimize_strategy": (
        "参数优化：支持网格扫描(grid)和贝叶斯优化(bayesian)两种模式。贝叶斯模式基于 Optuna TPE 采样器"
        "，50次试验通常优于200组网格扫描"
        "，自动剪枝+参数重要性分析。支持 A 股(6位代码)/港股(5位代码)/美股(字母代码)。网格模式组合数上限 200 组"
    ),
    "plot_kline": (
        "生成交互式 K 线 HTML 文件（不是PNG图片！），含蜡烛图+均线+成交量+MACD/KDJ/RSI副图"
        "。返回文件路径"
        "，请务必用浏览器打开该 HTML 文件查看（支持缩放/平移/悬停查看数值）"
    ),
    "get_dragon_tiger": "龙虎榜明细：每日上榜股票的营业部买卖金额、净买入等（AKShare 新浪数据源）",
    "get_block_trades": "大宗交易：单只股票或全市场的大宗交易明细，含成交价/折溢价率等",
    "get_margin_trading": "融资融券（两融）：沪深两市个股融资余额、融券余量、融资买入额等",
    "test_data_sources": "诊断所有数据源是否可用（A股/港股/美股/期货/北向资金），逐项测试并返回状态",
    "search_stock": "按代码或名称模糊搜索股票（A股/港股/美股），纯本地映射无网络调用，毫秒级返回",
    "get_minute_kline": "获取分钟级K线数据（仅A股）。支持1/5/15/30/60分钟周期，基于 easy-tdx 毫秒级数据源",
    "get_fund_flow": (
        "获取个股资金流向（仅A股，主力净流入/成交额/换手率/量比），基于 easy-tdx 通达信实时数据"
        "，毫秒级响应"
    ),
    "get_institutional_holdings": "获取个股十大流通股东/机构持仓数据（仅A股），基于 AKShare 东方财富",
    "get_macro_data": "获取中国宏观经济数据（仅中国）：GDP/CPI/PMI/货币供应量/外汇储备，基于 AKShare",
    "get_research_reports": "获取个股研报（仅A股，机构评级/目标价），基于 AKShare 东方财富",
    "analyze_stock": "综合个股分析：一站式返回行情+技术指标+均线排列+财务+综合评分（0-100），结果结构化供AI解读",
    "compare_stocks": "多股横向对比：同时分析多只股票，按综合评分排名，快速找出最优标的",
    "correlation_matrix": "计算多只股票收益率的相关性矩阵，找出低相关配对，辅助分散投资决策",
    "portfolio_backtest": "多股投资组合回测：支持自定义权重/等权，返回收益率/夏普/最大回撤/权益曲线",
    "comparison_chart": "生成多只股票走势对比图（归一化），交互式HTML，支持缩放/平移/悬停查看数值",
    "factor_screener": "多因子选股：全市场A股按动量/价值/质量/增长/波动五因子综合打分排名，返回Top N。过滤ST和新股",
    "walk_forward": "Walk-Forward 样本外验证：滚动训练和测试策略参数，评估策略稳健性与过拟合风险",
    "monte_carlo_test": "蒙特卡洛稳健性检验：重排交易收益序列，估计正收益概率、回撤分布和原策略百分位",
}

_TOOL_TIMEOUTS: dict[str, float] = {
    "walk_forward": 300.0,
    "optimize_strategy": 180.0,
    "backtest_strategy": 120.0,
}

_TOOL_MODELS: dict[str, type[BaseModel]] = {
    "get_kline": KlineParams,
    "get_financials": FinancialsParams,
    "get_sector_ranking": SectorRankingParams,
    "get_north_flow": NorthFlowParams,
    "get_technical_indicators": TechnicalIndicatorsParams,
    "stock_screener": ScreenerParams,
    "backtest_strategy": BacktestParams,
    "optimize_strategy": OptimizeParams,
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
}


def _annotation_for_field(field: Any) -> Any:
    """把 Pydantic 字段描述/约束转成函数签名中的 Annotated 元数据。"""
    extras: list[Any] = []
    if field.description:
        extras.append(Field(description=field.description))
    extras.extend(field.metadata)
    if extras:
        return Annotated[(field.annotation, *extras)]
    return field.annotation


def _make_tool_wrapper(
    name: str,
    handler: Callable[[dict[str, Any]], Any],
    model: type[BaseModel] | None,
    timeout: float,
) -> Callable[..., Any]:
    """基于 validator 模型生成带真实参数的 v2 工具包装函数。"""
    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}

    if model is not None:
        for fname, field in model.model_fields.items():
            annotation = _annotation_for_field(field)
            if field.is_required():
                parameter = inspect.Parameter(
                    fname,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=annotation,
                )
            else:
                parameter = inspect.Parameter(
                    fname,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=field.get_default(call_default_factory=True),
                    annotation=annotation,
                )
            parameters.append(parameter)
            annotations[fname] = annotation

    async def wrapper(**kwargs: Any) -> str:
        return await _invoke_tool(name, handler, model, kwargs, timeout)

    wrapper.__name__ = name
    wrapper.__qualname__ = name
    wrapper.__signature__ = inspect.Signature(parameters)
    wrapper.__annotations__ = annotations
    wrapper.__doc__ = _TOOL_DESCRIPTIONS[name]
    return wrapper


async def _invoke_tool(
    name: str,
    handler: Callable[[dict[str, Any]], Any],
    model: type[BaseModel] | None,
    arguments: dict[str, Any],
    timeout: float,
) -> str:
    """统一分发到同步 handler，并保留超时/错误响应格式。"""
    if model is not None:
        try:
            arguments = validate_and_coerce(model, arguments)
        except StockError as e:
            return _format_json(format_error_response(e))

    try:
        result = await asyncio.wait_for(asyncio.to_thread(handler, arguments), timeout=timeout)
        return _format_json(result)
    except asyncio.TimeoutError:
        logger.error("Tool %s timed out (%.0fs) — thread pool may be exhausted", name, timeout)
        return _format_json({
            "error": True,
            "code": "TIMEOUT",
            "message": f"工具调用超时 ({int(timeout)}s)。可能是网络请求阻塞或线程池耗尽，请稍后重试",
        })
    except StockError as e:
        logger.warning("Tool %s error: %s", name, e.message)
        return _format_json(format_error_response(e))
    except Exception as e:
        logger.exception("Tool %s unexpected error", name)
        return _format_json({
            "error": True,
            "code": "INTERNAL_ERROR",
            "message": str(e),
        })


for _name in _TOOL_NAMES:
    mcp.add_tool(
        _make_tool_wrapper(
            _name,
            TOOL_HANDLERS[_name],
            _TOOL_MODELS.get(_name),
            _TOOL_TIMEOUTS.get(_name, 90.0),
        ),
        name=_name,
        description=_TOOL_DESCRIPTIONS[_name],
    )


# ================================================================
# Resources
# ================================================================

@mcp.resource(
    "stock://popular",
    name="热门股票列表",
    description="常用A股/指数代码和名称",
    mime_type="application/json",
)
def popular_resource() -> str:
    return _format_json(HOT_STOCKS)


@mcp.resource(
    "stock://market/indices",
    name="大盘指数",
    description="上证/深证/创业板/沪深300/科创50实时行情",
    mime_type="application/json",
)
def market_indices_resource() -> str:
    return _format_json(handle_market_indices({"market": "a"}))


@mcp.resource(
    "stock://{code}/realtime",
    name="个股实时行情",
    description="指定股票的实时行情",
    mime_type="application/json",
)
def realtime_resource(code: str) -> str:
    return _format_json(handle_realtime_quote({"code": code}))


@mcp.resource(
    "stock://{code}/kline",
    name="个股日K线",
    description="指定股票最近30根日K线",
    mime_type="application/json",
)
def kline_resource(code: str) -> str:
    return _format_json(handle_kline({"code": code, "ktype": "daily", "limit": 30}))


@mcp.resource(
    "stock://{code}/indicators",
    name="个股技术指标",
    description="指定股票120日技术指标",
    mime_type="application/json",
)
def indicators_resource(code: str) -> str:
    return _format_json(handle_technical_indicators({"code": code, "days": 120}))


# ================================================================
# Entry
# ================================================================

async def main():
    logger.info("mcp-finance v%s starting (MCP SDK 2.x, easy-tdx + AKShare)", __version__)

    # 启动预热：后台预初始化 TDX 连接和 AKShare 数据
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
            _get_ak()
            logger.info("预热: AKShare 模块加载成功")
        except Exception as e:
            logger.warning("预热: AKShare 加载跳过 (%s)", e)
        logger.info("mcp-finance 预热完成，可以处理请求")

    asyncio.create_task(_warmup())
    await mcp.run_stdio_async()


def cli():
    """sync entry point for console_scripts"""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
