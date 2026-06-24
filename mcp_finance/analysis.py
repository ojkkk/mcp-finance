"""
分析引擎 — AI 辅助解读 / 多因子选股 / 股票对比

提供 analyze_stock / compare_stocks / factor_screener 三个核心分析工具。
"""

from __future__ import annotations
from typing import Any
import math

from mcp_finance.api import (
    handle_realtime_quote, handle_kline, handle_financials,
    get_all_a_stocks_snapshot, _detect_market,
)
from mcp_finance.indicators import compute_all_indicators
from mcp_finance.data import STOCK_MAPPING
from mcp_finance.logging_config import get_logger

_logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. 综合个股分析 (analyze_stock)
# ═══════════════════════════════════════════════════════════════

def analyze_stock(code: str) -> dict:
    """综合个股分析 — 行情+技术+财务+信号（A股/港股/美股自适应）

    一站式分析，输出结构化数据供 AI 解读。
    """
    stock_name = STOCK_MAPPING.get(code, code)
    market = _detect_market(code)

    # ── 1. 实时行情（多市场）──
    quote = handle_realtime_quote({"code": code, "market": market})
    if not quote or "error" in quote:
        return {"error": True, "message": f"无法获取 {code} 的行情数据", "市场": market}

    # ── 2. 技术指标 (最近120天日K) ──
    tech = {}
    try:
        klines = handle_kline({"code": code, "market": market, "ktype": "daily", "limit": 120})
        if isinstance(klines, dict) and "error" in klines:
            klines = []
        elif not isinstance(klines, list):
            klines = []
    except Exception:
        klines = []

    if klines and len(klines) >= 30:
        indicators = compute_all_indicators(klines)
        snapshot = indicators.get("snapshot", {})
        signals = indicators.get("signals", [])
        latest = klines[-1] if klines else {}

        tech = {
            "最新收盘价": latest.get("收盘价"),
            "MA5": snapshot.get("MA5"),
            "MA20": snapshot.get("MA20"),
            "MA60": snapshot.get("MA60"),
            "MACD_DIF": snapshot.get("MACD_DIF"),
            "MACD_DEA": snapshot.get("MACD_DEA"),
            "MACD柱": snapshot.get("MACD柱"),
            "KDJ_K": snapshot.get("KDJ_K"),
            "KDJ_D": snapshot.get("KDJ_D"),
            "KDJ_J": snapshot.get("KDJ_J"),
            "RSI_14": snapshot.get("RSI_14"),
            "BOLL上轨": snapshot.get("BOLL_upper"),
            "BOLL中轨": snapshot.get("BOLL_mid"),
            "BOLL下轨": snapshot.get("BOLL_lower"),
            "当前信号": signals[:5] if signals else [],
        }

    # ── 3. 财务数据（多市场）──
    financials = {}
    try:
        fin = handle_financials({"code": code, "market": market, "count": 4})
        if isinstance(fin, list):
            fin = {"数据": fin}
        if fin and "error" not in fin and "数据" in fin:
            financials["最近期数"] = fin.get("财务期数", 0)
            financials["数据"] = fin["数据"]
    except Exception:
        pass

    # ── 4. 综合评分 ──
    score = _compute_stock_score(quote, tech, financials)

    # ── 5. 均线排列 ──
    ma_arrangement = _analyze_ma_arrangement(tech)

    return {
        "股票": stock_name,
        "代码": code,
        "市场": market,
        "行情": {
            "最新价": quote.get("最新价"),
            "涨跌幅(%)": quote.get("涨跌幅"),
            "换手率(%)": quote.get("换手率"),
            "量比": quote.get("量比"),
            "市盈率": quote.get("市盈率"),
            "市净率": quote.get("市净率"),
            "总市值(亿)": quote.get("总市值"),
        },
        "技术指标": tech,
        "均线排列": ma_arrangement,
        "财务": financials,
        "综合评分": score,
        "提示": "此分析仅供 AI 辅助参考，不构成投资建议",
    }


def handle_analyze_stock(arguments: dict) -> dict:
    return analyze_stock(arguments["code"])
def handle_analyze_stock(arguments: dict) -> dict:
    return analyze_stock(arguments["code"])


# ═══════════════════════════════════════════════════════════════
# 2. 多股对比 (compare_stocks)
# ═══════════════════════════════════════════════════════════════

def compare_stocks(codes: list[str]) -> dict:
    """多股横向对比"""
    results = []
    for code in codes:
        try:
            analysis = analyze_stock(code)
            if "error" in analysis:
                results.append({"代码": code, "错误": analysis["message"]})
            else:
                results.append({
                    "代码": code,
                    "名称": analysis["股票"],
                    "最新价": analysis["行情"]["最新价"],
                    "涨跌幅(%)": analysis["行情"]["涨跌幅(%)"],
                    "市盈率": analysis["行情"]["市盈率"],
                    "市净率": analysis["行情"]["市净率"],
                    "总市值(亿)": analysis["行情"]["总市值(亿)"],
                    "综合评分": analysis["综合评分"]["总分"],
                    "评级": analysis["综合评分"]["等级"],
                    "均线": analysis["均线排列"]["状态"],
                    "信号": analysis["技术指标"].get("当前信号", [])[:3],
                })
        except Exception as e:
            results.append({"代码": code, "错误": str(e)})

    # 按评分排序
    results.sort(key=lambda x: x.get("综合评分", 0), reverse=True)

    return {
        "对比数量": len(results),
        "排名": results,
        "最佳": results[0] if results else None,
    }


def handle_compare_stocks(arguments: dict) -> dict:
    return compare_stocks(arguments["codes"])


# ═══════════════════════════════════════════════════════════════
# 3. 多因子选股 (factor_screener)
# ═══════════════════════════════════════════════════════════════

_FACTOR_WEIGHTS = {
    "momentum": 0.25,
    "value": 0.25,
    "quality": 0.20,
    "growth": 0.15,
    "volatility": 0.15,
}


def factor_screener(
    top_n: int = 30,
    min_market_cap: float = 50,
) -> dict:
    """多因子打分选股

    因子维度:
      - momentum: 涨跌幅 + 量比
      - value: 市盈率 + 市净率 (越低越好)
      - quality: ROE (越高越好)
      - growth: 营收/利润增长率
      - volatility: 换手率 (适中最好)

    返回 top_n 综合排名。
    """
    try:
        snapshot = get_all_a_stocks_snapshot()
    except Exception as e:
        return {"error": True, "message": f"获取全市场数据失败: {e}"}

    if snapshot is None or (hasattr(snapshot, "empty") and snapshot.empty):
        return {"error": True, "message": "全市场数据为空"}

    import pandas as pd
    df = snapshot if isinstance(snapshot, pd.DataFrame) else pd.DataFrame()

    scored = []
    for _, row in df.iterrows():
        try:
            code = str(row.get("f12", ""))
            name = str(row.get("f14", ""))
            if not code or len(code) != 6:
                continue
            # 排除ST/新股
            if "ST" in name or "*ST" in name:
                continue

            # 提取因子
            gain = float(row.get("f3", 0) or 0)  # 涨跌幅
            pe = float(row.get("f9", 0) or 0)     # 市盈率
            pb = float(row.get("f23", 99) or 99)   # 市净率
            turnover = float(row.get("f8", 0) or 0) # 换手率
            volume_ratio = float(row.get("f10", 1) or 1) # 量比
            market_cap = float(row.get("f20", 0) or 0) # 总市值(亿)

            # 过滤小市值
            if market_cap < min_market_cap:
                continue

            # 因子得分 (0-100)
            # momentum: 涨跌幅 + 量比
            m_score = min(100, max(0, 50 + gain * 5 + (volume_ratio - 1) * 20))

            # value: PE越低越好，PB越低越好
            v_score = 0
            if 0 < pe < 200 and 0 < pb < 20:
                v_score = min(100, max(0, 100 - pe * 0.8 - pb * 2))
            elif 0 < pe < 200:
                v_score = min(100, max(0, 100 - pe * 0.6))

            # quality: 换手率适中最好 (2-8% 理想)
            q_score = 50
            if 0 < turnover < 1:
                q_score = 30
            elif 1 <= turnover <= 3:
                q_score = 60
            elif 3 < turnover <= 8:
                q_score = 80
            elif 8 < turnover <= 15:
                q_score = 50
            else:
                q_score = 20

            # growth: 用涨跌幅近似
            g_score = min(100, max(0, 50 + gain * 3))

            # volatility: 量比适中
            vol_score = min(100, max(0, 50 - abs(volume_ratio - 1.2) * 30))

            total = (
                _FACTOR_WEIGHTS["momentum"] * m_score +
                _FACTOR_WEIGHTS["value"] * v_score +
                _FACTOR_WEIGHTS["quality"] * q_score +
                _FACTOR_WEIGHTS["growth"] * g_score +
                _FACTOR_WEIGHTS["volatility"] * vol_score
            )

            scored.append({
                "代码": code,
                "名称": name,
                "最新价": float(row.get("f2", 0) or 0),
                "涨跌幅(%)": gain,
                "市盈率": pe,
                "市净率": pb,
                "换手率(%)": turnover,
                "总市值(亿)": market_cap,
                "动量得分": round(m_score),
                "价值得分": round(v_score),
                "质量得分": round(q_score),
                "增长得分": round(g_score),
                "波动得分": round(vol_score),
                "综合得分": round(total, 1),
            })
        except Exception:
            continue

    scored.sort(key=lambda x: x["综合得分"], reverse=True)
    top = scored[:top_n]

    return {
        "策略": "多因子打分 (动量+价值+质量+增长+波动)",
        "筛选结果": len(scored),
        "返回": len(top),
        "因子权重": _FACTOR_WEIGHTS,
        "排名": top,
    }


def handle_factor_screener(arguments: dict) -> dict:
    return factor_screener(
        top_n=arguments.get("top_n", 30),
        min_market_cap=float(arguments.get("min_market_cap", 50)),
    )


# ═══════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════

def _analyze_ma_arrangement(tech: dict) -> dict:
    """分析均线排列状态"""
    ma5 = tech.get("MA5")
    ma20 = tech.get("MA20")
    ma60 = tech.get("MA60")

    if ma5 is None or ma20 is None:
        return {"状态": "数据不足"}

    if ma60 is not None:
        if ma5 > ma20 > ma60:
            return {"状态": "多头排列", "含义": "短期>中期>长期，上升趋势"}
        elif ma5 < ma20 < ma60:
            return {"状态": "空头排列", "含义": "短期<中期<长期，下降趋势"}

    if ma5 > ma20:
        return {"状态": "短多", "含义": "MA5在MA20之上，短线偏多"}
    else:
        return {"状态": "短空", "含义": "MA5在MA20之下，短线偏空"}


def _compute_stock_score(quote: dict, tech: dict, financials: dict) -> dict:
    """综合评分 0-100"""
    score = 50
    reasons = []

    # 技术面 (30分)
    tech_score = 0
    signals = tech.get("当前信号", [])
    if any("金叉" in s for s in signals):
        tech_score += 10
        reasons.append("技术金叉信号")
    if any("超卖" in s for s in signals):
        tech_score += 8
        reasons.append("RSI超卖(可能反弹)")
    ma_state = _analyze_ma_arrangement(tech)
    if "多头" in ma_state.get("状态", ""):
        tech_score += 10
        reasons.append("均线多头排列")
    elif "空头" in ma_state.get("状态", ""):
        tech_score -= 5
        reasons.append("均线空头排列")
    tech_score = max(0, min(30, tech_score))
    score += tech_score - 15

    # 估值面 (25分)
    pe = quote.get("市盈率")
    pb = quote.get("市净率")
    val_score = 15
    if pe is not None:
        if 0 < pe < 15:
            val_score += 10
            reasons.append(f"低市盈率(PE={pe:.1f})")
        elif pe > 60:
            val_score -= 5
            reasons.append(f"高市盈率(PE={pe:.1f})")
    if pb is not None:
        if 0 < pb < 1.5:
            val_score += 5
            reasons.append(f"低市净率(PB={pb:.2f})")
    val_score = max(0, min(25, val_score))
    score += val_score - 12

    # 动量面 (25分)
    change_pct = quote.get("涨跌幅")
    mom_score = 15
    if change_pct is not None:
        if change_pct > 3:
            mom_score += 8
            reasons.append(f"当日强势(涨{change_pct}%)")
        elif change_pct < -5:
            mom_score -= 5
            reasons.append(f"当日大跌(跌{abs(change_pct)}%)")
    mom_score = max(0, min(25, mom_score))
    score += mom_score - 12

    # 财务面 (20分)
    fin_score = 10
    fin_data = financials.get("数据", [])
    if fin_data and len(fin_data) > 0:
        latest_fin = fin_data[0]
        roe_val = latest_fin.get("净资产收益率")
        if roe_val is not None:
            try:
                roe = float(roe_val)
                if roe > 15:
                    fin_score += 8
                    reasons.append(f"高ROE({roe}%)")
                elif roe > 5:
                    fin_score += 3
            except (ValueError, TypeError):
                pass
    fin_score = max(0, min(20, fin_score))
    score += fin_score - 10

    score = max(0, min(100, round(score)))

    level = "优秀" if score >= 80 else "良好" if score >= 65 else "一般" if score >= 50 else "偏弱" if score >= 35 else "较差"

    return {
        "总分": score,
        "等级": level,
        "关键因素": reasons[:5],
    }
