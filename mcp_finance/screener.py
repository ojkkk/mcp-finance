"""
股票筛选器 — 按技术面条件全市场扫描 A 股

筛选维度:
  - 涨跌幅 / 振幅 / 换手率
  - 成交量变化（量比）
  - 市盈率 / 市净率
  - 总市值 / 流通市值

数据来源: 东方财富全市场行情接口 (push2.eastmoney.com)
"""

from __future__ import annotations
from typing import Any

from mcp_finance.api import get_all_a_stocks_snapshot


# 东方财富 push2 接口字段对照
# ──────────────────────────────────────
# f2=最新价  f3=涨跌幅(%)  f4=涨跌额  f5=成交量(手)
# f6=成交额(万)  f7=振幅(%)  f8=换手率(%)  f9=市盈率(动)
# f10=量比  f12=代码  f14=名称
# f15=最高  f16=最低  f17=今开  f18=昨收
# f20=总市值(元)  f21=流通市值(元)
# f23=市净率(PB)
# ※ 注意: ROE(f37)/股息率(f45)/主力净流入(f62) 来自不同数据源，当前暂未接入


def _fetch_all_a_stocks(page: int = 1, page_size: int = 100) -> list[dict[str, Any]]:
    """获取全市场 A 股行情数据（通过 AKShare）

    注: page/page_size 参数保留仅用于兼容，实际总会返回全量数据。
    """
    data = get_all_a_stocks_snapshot()
    if not data:
        return []
    # Convert to legacy format for backward compat
    result = []
    for item in data:
        result.append({
            "f12": item.get("代码", ""),
            "f14": item.get("名称", ""),
            "f2": item.get("最新价"),
            "f3": item.get("涨跌幅"),
            "f7": item.get("振幅"),
            "f8": item.get("换手率"),
            "f9": item.get("市盈率"),
            "f10": item.get("量比"),
            "f15": item.get("最高"),
            "f16": item.get("最低"),
            "f17": item.get("今开"),
            "f18": item.get("昨收"),
            "f20": item.get("总市值"),
            "f21": item.get("流通市值"),
            "f23": item.get("市净率"),
            "f37": None,  # ROE from different source
            "f45": None,  # dividend from different source
            "f62": None,  # main_inflow from different source
        })
    return result


def screen_stocks(
    min_gain: float | None = None,
    max_gain: float | None = None,
    min_volume_ratio: float | None = None,
    min_turnover: float | None = None,
    max_pe: float | None = None,
    min_market_cap: float | None = None,
    # ── 新增筛选维度（v0.2.0）──
    min_pb: float | None = None,
    max_pb: float | None = None,
    min_roe: float | None = None,
    min_main_inflow: float | None = None,
    min_dividend: float | None = None,
    top_n: int = 50,
) -> dict[str, Any]:
    """
    按条件筛选 A 股

    Args:
        min_gain:           最低涨跌幅 (%)
        max_gain:           最高涨跌幅 (%)
        min_volume_ratio:   最低量比（当日成交量/5日均量）
        min_turnover:       最低换手率 (%)
        max_pe:             最高市盈率（动）
        min_market_cap:     最低总市值（亿元）
        min_pb:             最低市净率 (倍)
        max_pb:             最高市净率 (倍)
        min_roe:            最低净资产收益率 ROE (%)
        min_main_inflow:    最低主力净流入（万元），正值表示净流入
        min_dividend:       最低股息率 (%)
        top_n:              返回前 N 条

    Returns:
        {"matched": [...], "total_scanned": int, "conditions": {...}}
    """
    all_stocks = _fetch_all_a_stocks()

    matched: list[dict[str, Any]] = []
    conditions = {
        "min_gain": min_gain,
        "max_gain": max_gain,
        "min_volume_ratio": min_volume_ratio,
        "min_turnover": min_turnover,
        "max_pe": max_pe,
        "min_market_cap": min_market_cap,
        # 新增条件
        "min_pb": min_pb,
        "max_pb": max_pb,
        "min_roe": min_roe,
        "min_main_inflow": min_main_inflow,
        "min_dividend": min_dividend,
    }

    def _f(val: Any) -> float | None:
        if val is None or val == "-":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    for item in all_stocks:
        code = item.get("f12", "")
        name = item.get("f14", "")
        if not code or not name:
            continue

        gain = _f(item.get("f3"))
        volume_ratio = _f(item.get("f10"))
        turnover = _f(item.get("f8"))
        pe = _f(item.get("f9"))
        market_cap = _f(item.get("f20"))
        pb = _f(item.get("f23"))
        roe = _f(item.get("f37"))
        dividend = _f(item.get("f45"))
        main_inflow = _f(item.get("f62"))

        # 过滤 — 原有
        if min_gain is not None and (gain is None or gain < min_gain):
            continue
        if max_gain is not None and (gain is not None and gain > max_gain):
            continue
        if min_volume_ratio is not None and (volume_ratio is None or volume_ratio < min_volume_ratio):
            continue
        if min_turnover is not None and (turnover is None or turnover < min_turnover):
            continue
        if max_pe is not None and (pe is None or pe > max_pe):
            continue
        if min_market_cap is not None and (market_cap is None or market_cap < min_market_cap * 1e8):
            continue

        # 过滤 — 新增
        if min_pb is not None and (pb is None or pb < min_pb):
            continue
        if max_pb is not None and (pb is not None and pb > max_pb):
            continue
        # ROE/股息率/主力净流入 — 数据暂未提供时排除（设了条件但值为None则排除）
        if min_roe is not None and (roe is None or roe < min_roe):
            continue
        if min_main_inflow is not None and (main_inflow is None or main_inflow < min_main_inflow):
            continue
        if min_dividend is not None and (dividend is None or dividend < min_dividend):
            continue


        matched.append({
            "代码": code,
            "名称": name,
            "最新价": item.get("f2"),
            "涨跌幅(%)": gain,
            "量比": volume_ratio,
            "换手率(%)": turnover,
            "振幅(%)": _f(item.get("f7")),
            "市盈率(动)": pe,
            "市净率(PB)": pb,
            "ROE(%)": roe,
            "股息率(%)": dividend,
            "主力净流入(万元)": main_inflow,
            "总市值(元)": market_cap,
            "今开": item.get("f17"),
            "最高": item.get("f15"),
            "最低": item.get("f16"),
            "昨收": item.get("f18"),
        })

    matched.sort(key=lambda x: x["涨跌幅(%)"] if x["涨跌幅(%)"] is not None else -9999, reverse=True)

    return {
        "matched": matched[:top_n],
        "count": len(matched),
        "total_scanned": len(all_stocks),
        "conditions": conditions,
    }
# ═══════════════════════════════════════════════════════════════
# MCP Tool Handler
# ═══════════════════════════════════════════════════════════════

from mcp_finance.errors import NoDataError
from mcp_finance.logging_config import get_logger

_slogger = get_logger(__name__)


def handle_stock_screener(arguments: dict[str, Any]) -> dict[str, Any]:
    """全市场股票筛选 handler"""
    from typing import Any

    result = screen_stocks(
        min_gain=arguments.get("min_gain"),
        max_gain=arguments.get("max_gain"),
        min_volume_ratio=arguments.get("min_volume_ratio"),
        min_turnover=arguments.get("min_turnover"),
        max_pe=arguments.get("max_pe"),
        min_market_cap=arguments.get("min_market_cap"),
        min_pb=arguments.get("min_pb"),
        max_pb=arguments.get("max_pb"),
        min_roe=arguments.get("min_roe"),
        min_main_inflow=arguments.get("min_main_inflow"),
        min_dividend=arguments.get("min_dividend"),
        top_n=arguments.get("top_n", 50),
    )
    if not result.get("matched"):
        raise NoDataError("未找到符合条件的股票")
    _slogger.info("选股完成: matched=%d scanned=%d", result["count"], result["total_scanned"])
    return result
