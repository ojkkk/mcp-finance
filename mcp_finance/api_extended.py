"""
扩展数据源模块 — 分钟K线 / 资金流向 / 机构持仓 / 宏观数据 / 研报公告

基于 easy-tdx + AKShare 提供报告建议方向 5 的数据能力。
"""

from __future__ import annotations
from typing import Any
from datetime import datetime, timedelta

import pandas as pd

from mcp_finance.api import _get_tdx, _get_ak, _call_with_net_timeout, _to_sina_code, _detect_market
from mcp_finance.data import STOCK_MAPPING
from mcp_finance.logging_config import get_logger

_logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. 分钟级 K 线
# ═══════════════════════════════════════════════════════════════

def get_minute_kline(code: str, freq: str = "5", limit: int = 240) -> list[dict]:
    """获取分钟级 K 线 (仅A股，easy-tdx 数据源)

    Args:
        code: 6位股票代码
        freq: K线周期，1/5/15/30/60 分钟
        limit: 返回条数，默认240条
    """
    try:
        tdx = _get_tdx()
        from easy_tdx import Period
        period_map = {"1": Period.M1, "5": Period.M5, "15": Period.M15,
                       "30": Period.M30, "60": Period.M60}
        period = period_map.get(freq, Period.M5)

        from mcp_finance.api import _tdx_market
        market = _tdx_market(code)
        bars = tdx.get_kline(market, code, period, count=limit)

        if not bars:
            return [{"error": f"未获取到 {code} 的分钟K线数据"}]

        records = []
        for bar in bars[-limit:]:
            records.append({
                "时间": str(bar.time) if hasattr(bar, "time") else "",
                "开盘价": float(bar.open) if hasattr(bar, "open") else 0,
                "最高价": float(bar.high) if hasattr(bar, "high") else 0,
                "最低价": float(bar.low) if hasattr(bar, "low") else 0,
                "收盘价": float(bar.close) if hasattr(bar, "close") else 0,
                "成交量": int(bar.volume) if hasattr(bar, "volume") else 0,
            })
        return records
    except Exception as e:
        _logger.warning("分钟K线获取失败 %s: %s", code, e)
        return [{"error": f"获取分钟K线失败: {e}"}]


def handle_minute_kline(arguments: dict) -> list[dict]:
    """分钟K线 handler"""
    code = arguments["code"]
    freq = arguments.get("freq", "5")
    limit = min(int(arguments.get("limit", 240)), 800)
    stock_name = STOCK_MAPPING.get(code, code)
    result = get_minute_kline(code, freq=freq, limit=limit)
    if isinstance(result, list) and len(result) > 0 and "error" not in result[0]:
        _logger.info("分钟K线: %s freq=%smin count=%d", code, freq, len(result))
    return {"股票": stock_name, "代码": code, "周期": f"{freq}分钟", "数据": result}


# ═══════════════════════════════════════════════════════════════
# 2. 个股资金流向
# ═══════════════════════════════════════════════════════════════
def get_fund_flow(code: str, days: int = 5) -> dict:
    """获取个股资金流向 (仅A股，easy-tdx 实时数据)

    主力净流入数据来自通达信实时行情，毫秒级响应。
    注：仅返回当日数据，历史多日需本地持久化。

    Args:
        code: 6位股票代码
        days: 保留兼容，当前仅返回当日
    """
    stock_name = STOCK_MAPPING.get(code, code)
    try:
        from mcp_finance.api import _get_tdx, _tdx_market
        tdx = _get_tdx()
        market = _tdx_market(code)
        df = tdx.get_stock_quotes([(market.value, code)])
        if df is None or df.empty:
            return {"error": f"未获取到 {code} 的资金流向数据"}

        row = df.iloc[0]
        main_net = float(row.get("main_net_amount", 0) or 0)
        amount = float(row.get("amount", 0) or 0)
        close = float(row.get("close", 0) or 0)
        pre_close = float(row.get("pre_close", 0) or 0)
        change_pct = round((close - pre_close) / pre_close * 100, 2) if pre_close > 0 else 0
        turnover = float(row.get("turnover", 0) or 0)
        vol_ratio = float(row.get("vol_ratio", 1) or 1)

        if main_net > 10000000:
            direction = "大幅净流入"
        elif main_net > 0:
            direction = "小幅净流入"
        elif main_net < -10000000:
            direction = "大幅净流出"
        elif main_net < 0:
            direction = "小幅净流出"
        else:
            direction = "持平"

        return {
            "股票": stock_name,
            "代码": code,
            "主力净流入(元)": main_net,
            "主力净流入(万元)": round(main_net / 10000, 2),
            "成交额(元)": amount,
            "最新价": close,
            "涨跌幅(%)": change_pct,
            "换手率(%)": turnover,
            "量比": vol_ratio,
            "主力动向": direction,
            "数据源": "easy-tdx(通达信实时)",
            "提示": "当前仅返回当日实时数据",
        }
    except Exception as e:
        _logger.warning("资金流向获取失败 %s: %s", code, e)
        return {"error": f"获取资金流向失败: {e}"}

def handle_fund_flow(arguments: dict) -> dict:
    """资金流向 handler"""
    return get_fund_flow(arguments["code"], arguments.get("days", 5))


# ═══════════════════════════════════════════════════════════════
# 3. 机构持仓（十大股东）
# ═══════════════════════════════════════════════════════════════

def get_institutional_holdings(code: str) -> dict:
    """获取机构持仓/十大股东 (仅A股，AKShare 东方财富)

    Args:
        code: 6位股票代码
    """
    try:
        ak = _get_ak()
        # 十大流通股东
        df = _call_with_net_timeout(
            lambda: ak.stock_main_stock_holder(stock=code)
        )
        if df is None or df.empty:
            return {"error": f"未获取到 {code} 的十大股东数据"}

        # 过滤最新一期数据
        latest_date = df["截至日期"].max() if "截至日期" in df.columns else None
        if latest_date:
            df = df[df["截至日期"] == latest_date]
        records = []
        for _, row in df.head(10).iterrows():
            def _safe_int(v):
                try:
                    return int(float(v)) if pd.notna(v) else 0
                except (ValueError, TypeError):
                    return 0
            def _safe_float(v):
                try:
                    return float(v) if pd.notna(v) else 0.0
                except (ValueError, TypeError):
                    return 0.0
            records.append({
                "排名": _safe_int(row.get("编号")),
                "股东名称": str(row.get("股东名称", "")),
                "持股数量(股)": _safe_int(row.get("持股数量")),
                "持股比例(%)": _safe_float(row.get("持股比例")),
                "股本性质": str(row.get("股本性质", "")),
                "截至日期": str(row.get("截至日期", "")),
            })

        return {
            "股票": STOCK_MAPPING.get(code, code),
            "代码": code,
            "十大股东": records,
            "数据源": "AKShare-新浪",
        }
    except Exception as e:
        _logger.warning("机构持仓获取失败 %s: %s", code, e)
        return {"error": f"获取机构持仓失败: {e}"}


def handle_institutional_holdings(arguments: dict) -> dict:
    """机构持仓 handler"""
    return get_institutional_holdings(arguments["code"])


# ═══════════════════════════════════════════════════════════════
# 4. 宏观数据 (GDP/CPI/PMI)
# ═══════════════════════════════════════════════════════════════

_MACRO_INDICATORS = {
    "gdp": ("macro_china_gdp", "中国GDP"),
    "cpi": ("macro_china_cpi_monthly", "中国CPI(月度)"),
    "pmi": ("macro_china_pmi", "中国PMI"),
    "money_supply": ("macro_china_money_supply", "中国货币供应量"),
    "fx_reserve": ("macro_china_fx_reserves_yearly", "中国外汇储备"),
}


def get_macro_data(indicator: str = "cpi", limit: int = 20) -> dict:
    """获取宏观经济数据 (AKShare)

    Args:
        indicator: 指标类型 gdp/cpi/pmi/money_supply/fx_reserve
        limit: 返回最近几期
    """
    if indicator not in _MACRO_INDICATORS:
        return {"error": f"不支持的宏观指标: {indicator}，支持: {list(_MACRO_INDICATORS.keys())}"}

    func_name, cn_name = _MACRO_INDICATORS[indicator]
    try:
        ak = _get_ak()
        func = getattr(ak, func_name, None)
        if func is None:
            return {"error": f"AKShare 不支持 {func_name} 接口"}

        df = _call_with_net_timeout(lambda: func())
        if df is None or df.empty:
            return {"error": f"未获取到 {cn_name} 数据"}

        records = []
        for _, row in df.tail(limit).iterrows():
            records.append({str(k): (None if pd.isna(v) else v) for k, v in row.items()})

        return {
            "指标": cn_name,
            "数据": records,
            "数据源": "AKShare",
        }
    except Exception as e:
        _logger.warning("宏观数据获取失败 %s: %s", indicator, e)
        return {"error": f"获取宏观数据失败: {e}"}


def handle_macro_data(arguments: dict) -> dict:
    """宏观数据 handler"""
    return get_macro_data(
        arguments.get("indicator", "cpi"),
        arguments.get("limit", 20)
    )


# ═══════════════════════════════════════════════════════════════
# 5. 研报/公告查询
# ═══════════════════════════════════════════════════════════════

def get_research_reports(code: str, limit: int = 10) -> dict:
    """获取个股研报 (仅A股，AKShare 东方财富)

    Args:
        code: 6位股票代码
        limit: 返回条数
    """
    try:
        ak = _get_ak()
        df = _call_with_net_timeout(
            lambda: ak.stock_research_report_em(symbol=code)
        )
        if df is None or df.empty:
            return {"error": f"未获取到 {code} 的研报数据"}

        records = []
        # BUG-L1 修复: AKShare 研报字段名含年份（如 "2026-盈利预测-收益"），硬编码会跨年失效
        # 改为动态匹配当前年份 + 次年的盈利预测字段
        from datetime import datetime as _dt
        _cur_year = _dt.now().year
        _next_year = _cur_year + 1
        _cur_key = f"{_cur_year}-盈利预测-收益"
        _next_key = f"{_next_year}-盈利预测-收益"
        _cur_pe_key = f"{_cur_year}-盈利预测-市盈率"
        _next_pe_key = f"{_next_year}-盈利预测-市盈率"
        for _, row in df.head(limit).iterrows():
            rec = {
                "日期": str(row.get("日期", "")),
                "机构": str(row.get("机构", "")),
                "评级": str(row.get("东财评级", "")),
                "标题": str(row.get("报告名称", "")),
                "行业": str(row.get("行业", "")),
            }
            # 优先取次年预测（更前瞻），回退到当年
            rec["预测年份"] = _next_year if row.get(_next_key) is not None else _cur_year
            rec["预测收益"] = row.get(_next_key) or row.get(_cur_key)
            rec["预测市盈率"] = row.get(_next_pe_key) or row.get(_cur_pe_key)
            records.append(rec)

        return {
            "股票": STOCK_MAPPING.get(code, code),
            "代码": code,
            "研报": records,
            "数据源": "AKShare-东方财富",
        }
    except Exception as e:
        _logger.warning("研报获取失败 %s: %s", code, e)
        return {"error": f"获取研报失败: {e}"}


def handle_research_reports(arguments: dict) -> dict:
    """研报 handler"""
    return get_research_reports(arguments["code"], arguments.get("limit", 10))
