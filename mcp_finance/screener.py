"""
股票筛选器 — 按技术面条件全市场扫描 A 股

筛选维度:
  - 涨跌幅 / 振幅 / 换手率
  - 成交量变化（量比）
  - 市盈率 / 市净率
  - 总市值 / 流通市值
  - ROE（净资产收益率，通过 AKShare 财务缓存获取）
  - 主力净流入（通过 easy-tdx 实时行情获取）

数据源优先级:
  1. AKShare 东方财富全市场行情 (stock_zh_a_spot) — 主数据源
  2. AKShare 财务摘要 (stock_financial_abstract) — ROE 等指标
  3. easy-tdx — 主力净流入
  注意: Tushare 不用于选股器（免费版限频 1次/分钟，远不足以支撑全市场扫描）
"""

from __future__ import annotations
from typing import Any

from mcp_finance.api import get_all_a_stocks_snapshot, get_main_inflow_batch
from mcp_finance.financials import preload_financials


# 慢速维度查询上限：候选股超过此数时，只对前 N 只做 ROE/主力净流入查询
_MAX_SLOW_LOOKUPS = 150


def _fetch_all_a_stocks() -> list[dict[str, Any]]:
    """获取全市场 A 股行情数据"""
    data = get_all_a_stocks_snapshot()
    if not data:
        return []
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
            "f37": None,  # ROE
            "f45": None,  # 股息率 — 东方财富全市场快照字段不包含股息率，始终为 None；筛选时不会生效
            "f62": None,  # 主力净流入
        })
    return result


def screen_stocks(
    min_gain: float | None = None,
    max_gain: float | None = None,
    min_volume_ratio: float | None = None,
    min_turnover: float | None = None,
    max_pe: float | None = None,
    min_market_cap: float | None = None,
    min_pb: float | None = None,
    max_pb: float | None = None,
    min_roe: float | None = None,
    
    top_n: int = 50,
) -> dict[str, Any]:
    """
    按条件筛选 A 股（两遍过滤：快速维度 → ROE/主力净流入慢速维度）

    慢速维度（ROE/主力净流入）仅在候选股 ≤ 150 只时查询，超出则跳过慢速维度。
    """
    all_stocks = _fetch_all_a_stocks()

    conditions = {
        "min_gain": min_gain,
        "max_gain": max_gain,
        "min_volume_ratio": min_volume_ratio,
        "min_turnover": min_turnover,
        "max_pe": max_pe,
        "min_market_cap": min_market_cap,
        "min_pb": min_pb,
        "max_pb": max_pb,
        "min_roe": min_roe,
    }

    def _f(val: Any) -> float | None:
        if val is None or val == "-":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    # ── 判断是否需要慢速维度 ──
    need_roe = min_roe is not None
    need_slow = need_roe

    # ── 第一遍：快速维度过滤 ──
    candidates: list[dict[str, Any]] = []
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

        if min_gain is not None and gain is not None and gain < min_gain:
            continue
        if max_gain is not None and (gain is not None and gain > max_gain):
            continue
        if min_volume_ratio is not None and volume_ratio is not None and volume_ratio < min_volume_ratio:
            continue
        if min_turnover is not None and turnover is not None and turnover < min_turnover:
            continue
        if max_pe is not None and pe is not None and pe > max_pe:
            continue
        if min_market_cap is not None and market_cap is not None and market_cap < min_market_cap * 1e8:
            continue
        if min_pb is not None and pb is not None and pb < min_pb:
            continue
        if max_pb is not None and (pb is not None and pb > max_pb):
            continue

        candidates.append(item)

    # ── 慢速维度：候选股太多则跳过查询 ──
    slow_skipped = False
    if need_slow and candidates:
        if len(candidates) > _MAX_SLOW_LOOKUPS:
            slow_skipped = True
        else:
            # 按涨跌幅预排序，优先查涨幅高的
            candidates.sort(key=lambda x: _f(x.get("f3")) or -999, reverse=True)

            candidate_codes = [item["f12"] for item in candidates if item.get("f12")]

            # ROE: 批量并行获取
            if need_roe and candidate_codes:
                fin_results = preload_financials(candidate_codes, max_workers=4)
                for item in candidates:
                    code = item.get("f12", "")
                    if code and code in fin_results:
                        fin = fin_results[code]
                        if fin.get("roe") is not None:
                            item["f37"] = fin["roe"]

            # 主力净流入: 批量获取
    matched: list[dict[str, Any]] = []
    for item in candidates:
        code = item.get("f12", "")
        name = item.get("f14", "")

        gain = _f(item.get("f3"))
        volume_ratio = _f(item.get("f10"))
        turnover = _f(item.get("f8"))
        pe = _f(item.get("f9"))
        market_cap = _f(item.get("f20"))
        pb = _f(item.get("f23"))
        roe = _f(item.get("f37"))
        dividend = _f(item.get("f45"))  # 保留字段但数据源暂不支持

        # 慢速维度过滤（仅当数据可用时才过滤）
        if min_roe is not None and roe is not None and roe < min_roe:
            continue

        matched.append({
            "代码": code,
            "名称": name,
            "最新价": item.get("f2"),
            "涨跌幅": gain,
            "量比": volume_ratio,
            "换手率": turnover,
            "振幅": _f(item.get("f7")),
            "市盈率": pe,
            "市净率": pb,
            "ROE": roe,
            "股息率": dividend,
            "总市值": market_cap,
            "今开": item.get("f17"),
            "最高": item.get("f15"),
            "最低": item.get("f16"),
            "昨收": item.get("f18"),
        })

    matched.sort(key=lambda x: x["涨跌幅"] if x["涨跌幅"] is not None else -9999, reverse=True)

    result = {
        "matched": matched[:int(top_n)],
        "count": len(matched),
        "total_scanned": len(all_stocks),
        "conditions": conditions,
    }
    if slow_skipped:
        result["_note"] = f"慢速维度(ROE/主力净流入)已跳过：候选股过多({len(candidates)}只 > {_MAX_SLOW_LOOKUPS}上限)，请缩小快速维度条件后重试"

    return result


# ═══════════════════════════════════════════════════════════════
# MCP Tool Handler
# ═══════════════════════════════════════════════════════════════

from mcp_finance.errors import NoDataError
from mcp_finance.logging_config import get_logger

_slogger = get_logger(__name__)


def handle_stock_screener(arguments: dict[str, Any]) -> dict[str, Any]:
    """全市场股票筛选 handler"""
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
        top_n=arguments.get("top_n", 50),
    )
    if not result.get("matched"):
        raise NoDataError("未找到符合条件的股票")
    _slogger.info("选股完成: matched=%d scanned=%d", result["count"], result["total_scanned"])
    return result
