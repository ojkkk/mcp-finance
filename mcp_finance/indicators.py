"""
技术指标计算模块 — 纯 Python 实现，零外部依赖

支持的指标:
  - MA    (简单移动平均 5/10/20/60/120/250)
  - MACD  (DIF/DEA/柱状图)
  - KDJ   (随机指标 K/D/J)
  - RSI   (相对强弱 6/14/24)
  - BOLL  (布林带)
  - WR    (威廉指标)
  - BIAS  (乖离率)
  - 均线形态识别 (金叉/死叉/多头排列/空头排列)
  - 自动信号汇总
"""

from __future__ import annotations
from typing import Any


# ═══════════════════════════════════════════════════════════════
# 基础计算
# ═══════════════════════════════════════════════════════════════

def _sma(values: list[float], n: int) -> list[float | None]:
    """简单移动平均 (SMA)，前 n-1 项为 None"""
    result: list[float | None] = []
    window: list[float] = []
    for v in values:
        window.append(v)
        if len(window) > n:
            window.pop(0)
        if len(window) == n:
            result.append(round(sum(window) / n, 4))
        else:
            result.append(None)
    return result


def _ema(values: list[float], n: int) -> list[float | None]:
    """指数移动平均 (EMA)"""
    if not values:
        return []
    mult = 2.0 / (n + 1)
    result: list[float | None] = []
    prev: float | None = None
    for i, v in enumerate(values):
        if i < n - 1:
            result.append(None)
            continue
        if i == n - 1:
            sma = sum(values[:n]) / n
            result.append(round(sma, 4))
            prev = sma
        else:
            ema_val = (v - prev) * mult + prev
            result.append(round(ema_val, 4))
            prev = ema_val
    return result


def _highest(values: list[float], n: int) -> list[float | None]:
    """滚动 N 日最高价"""
    result: list[float | None] = []
    window: list[float] = []
    for v in values:
        window.append(v)
        if len(window) > n:
            window.pop(0)
        if len(window) == n:
            result.append(max(window))
        else:
            result.append(None)
    return result


def _lowest(values: list[float], n: int) -> list[float | None]:
    """滚动 N 日最低价"""
    result: list[float | None] = []
    window: list[float] = []
    for v in values:
        window.append(v)
        if len(window) > n:
            window.pop(0)
        if len(window) == n:
            result.append(min(window))
        else:
            result.append(None)
    return result


# ═══════════════════════════════════════════════════════════════
# MACD
# ═══════════════════════════════════════════════════════════════

def calc_macd(
    close: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, list[float | None]]:
    """MACD: DIF = EMA(fast) - EMA(slow); DEA = EMA(DIF, signal); BAR = (DIF-DEA)*2"""
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)

    dif: list[float | None] = []
    for i in range(len(close)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            dif.append(round(ema_fast[i] - ema_slow[i], 4))  # type: ignore[arg-type]
        else:
            dif.append(None)

    dif_clean = [d if d is not None else 0.0 for d in dif]
    dea_raw = _ema(dif_clean, signal)
    slow_start = max(fast, slow) - 1

    dea: list[float | None] = []
    for i in range(len(dif)):
        if dif[i] is not None and dea_raw[i] is not None and i >= slow_start + signal - 1:
            dea.append(dea_raw[i])
        else:
            dea.append(None)

    macd_bar: list[float | None] = []
    for i in range(len(dif)):
        if dif[i] is not None and dea[i] is not None:
            macd_bar.append(round((dif[i] - dea[i]) * 2, 4))  # type: ignore[arg-type]
        else:
            macd_bar.append(None)

    return {"DIF": dif, "DEA": dea, "MACD": macd_bar}


# ═══════════════════════════════════════════════════════════════
# KDJ
# ═══════════════════════════════════════════════════════════════

def calc_kdj(
    high: list[float],
    low: list[float],
    close: list[float],
    n: int = 9,
) -> dict[str, list[float | None]]:
    """KDJ: RSV → K/D/J"""
    highest_h = _highest(high, n)
    lowest_l = _lowest(low, n)

    rsv: list[float | None] = []
    for i in range(len(close)):
        if highest_h[i] is not None and lowest_l[i] is not None:
            diff = highest_h[i] - lowest_l[i]  # type: ignore[arg-type]
            if diff == 0:
                rsv.append(50.0)
            else:
                rsv.append(round((close[i] - lowest_l[i]) / diff * 100, 2))  # type: ignore[arg-type]
        else:
            rsv.append(None)

    k: list[float | None] = []
    d: list[float | None] = []
    j: list[float | None] = []
    prev_k = 50.0
    prev_d = 50.0

    for r in rsv:
        if r is not None:
            prev_k = round(2 / 3 * prev_k + 1 / 3 * r, 2)
            prev_d = round(2 / 3 * prev_d + 1 / 3 * prev_k, 2)
            k.append(prev_k)
            d.append(prev_d)
            j.append(round(3 * prev_k - 2 * prev_d, 2))
        else:
            k.append(None)
            d.append(None)
            j.append(None)

    return {"K": k, "D": d, "J": j}


# ═══════════════════════════════════════════════════════════════
# RSI
# ═══════════════════════════════════════════════════════════════

def calc_rsi(close: list[float], n: int = 14) -> list[float | None]:
    """RSI (Wilder's smoothing)"""
    if len(close) < n + 1:
        return [None] * len(close)

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(close)):
        delta = close[i] - close[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    result: list[float | None] = [None]
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n

    for i in range(len(gains)):
        if i == n - 1:
            rs = avg_gain / avg_loss if avg_loss != 0 else 100
            result.append(round(100 - 100 / (1 + rs), 2))
        elif i >= n:
            avg_gain = (avg_gain * (n - 1) + gains[i]) / n
            avg_loss = (avg_loss * (n - 1) + losses[i]) / n
            rs = avg_gain / avg_loss if avg_loss != 0 else 100
            result.append(round(100 - 100 / (1 + rs), 2))
        else:
            result.append(None)

    return result


# ═══════════════════════════════════════════════════════════════
# BOLL
# ═══════════════════════════════════════════════════════════════

def calc_boll(
    close: list[float],
    n: int = 20,
    k: float = 2.0,
) -> dict[str, list[float | None]]:
    """布林带: MID=SMA, UPPER/LOWER = MID ± k*σ"""
    mid = _sma(close, n)
    upper: list[float | None] = []
    lower: list[float | None] = []

    for i in range(len(close)):
        if mid[i] is not None:
            window = close[i - n + 1 : i + 1]
            mean = sum(window) / n
            variance = sum((x - mean) ** 2 for x in window) / n
            std = variance ** 0.5
            upper.append(round(mid[i] + k * std, 4))  # type: ignore[arg-type]
            lower.append(round(mid[i] - k * std, 4))  # type: ignore[arg-type]
        else:
            upper.append(None)
            lower.append(None)

    return {"MID": mid, "UPPER": upper, "LOWER": lower}


# ═══════════════════════════════════════════════════════════════
# WR / BIAS
# ═══════════════════════════════════════════════════════════════

def calc_wr(
    high: list[float],
    low: list[float],
    close: list[float],
    n: int = 10,
) -> list[float | None]:
    """威廉指标: (HN - C) / (HN - LN) × 100"""
    highest_h = _highest(high, n)
    lowest_l = _lowest(low, n)
    result: list[float | None] = []
    for i in range(len(close)):
        if highest_h[i] is not None and lowest_l[i] is not None:
            rng = highest_h[i] - lowest_l[i]  # type: ignore[arg-type]
            if rng == 0:
                result.append(50.0)
            else:
                result.append(round((highest_h[i] - close[i]) / rng * 100, 2))  # type: ignore[arg-type]
        else:
            result.append(None)
    return result


def calc_bias(close: list[float], n: int = 6) -> list[float | None]:
    """乖离率: (C - MA) / MA × 100%"""
    ma = _sma(close, n)
    result: list[float | None] = []
    for i in range(len(close)):
        if ma[i] is not None:
            result.append(round((close[i] - ma[i]) / ma[i] * 100, 2))  # type: ignore[arg-type]
        else:
            result.append(None)
    return result


# ═══════════════════════════════════════════════════════════════
# 综合入口 — 输入 K 线数据，输出全部指标 + 信号
# ═══════════════════════════════════════════════════════════════

def compute_all_indicators(
    kline_data: list[dict[str, Any]],
    dates: list[str] | None = None,
) -> dict[str, Any]:
    """
    一站式：输入 K 线，输出快照、信号、金叉死叉列表

    Args:
        kline_data: K 线列表，每条含 "收盘价"/"最高价"/"最低价"
        dates:      对应的日期列表（可选）

    Returns:
        含 "snapshot"/"signals"/"golden_cross_5_20"/... 的字典
    """
    closes = [float(k["收盘价"]) for k in kline_data]
    highs = [float(k["最高价"]) for k in kline_data]
    lows = [float(k["最低价"]) for k in kline_data]

    n = len(closes)

    ma5 = _sma(closes, 5)
    ma10 = _sma(closes, 10)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60) if n >= 60 else [None] * n
    ma120 = _sma(closes, 120) if n >= 120 else [None] * n
    ma250 = _sma(closes, 250) if n >= 250 else [None] * n

    macd_result = calc_macd(closes)
    kdj_result = calc_kdj(highs, lows, closes)
    rsi6 = calc_rsi(closes, 6)
    rsi14 = calc_rsi(closes, 14)
    rsi24 = calc_rsi(closes, 24) if n >= 25 else [None] * n
    boll_result = calc_boll(closes)
    wr10 = calc_wr(highs, lows, closes, 10)
    bias6 = calc_bias(closes, 6)

    # ── 形态识别 ──
    golden_5_20 = _cross(ma5, ma20, True)
    death_5_20 = _cross(ma5, ma20, False)
    macd_golden = _cross(macd_result["DIF"], macd_result["DEA"], True)
    macd_death = _cross(macd_result["DIF"], macd_result["DEA"], False)

    def _last(lst: list[float | None]) -> float | None:
        for v in reversed(lst):
            if v is not None:
                return v
        return None

    # ── 当前快照 ──
    snapshot = {
        "MA5": _last(ma5),
        "MA10": _last(ma10),
        "MA20": _last(ma20),
        "MA60": _last(ma60),
        "MA120": _last(ma120),
        "MA250": _last(ma250),
        "MACD_DIF": _last(macd_result["DIF"]),
        "MACD_DEA": _last(macd_result["DEA"]),
        "MACD_BAR": _last(macd_result["MACD"]),
        "KDJ_K": _last(kdj_result["K"]),
        "KDJ_D": _last(kdj_result["D"]),
        "KDJ_J": _last(kdj_result["J"]),
        "RSI6": _last(rsi6),
        "RSI14": _last(rsi14),
        "RSI24": _last(rsi24),
        "BOLL_UPPER": _last(boll_result["UPPER"]),
        "BOLL_MID": _last(boll_result["MID"]),
        "BOLL_LOWER": _last(boll_result["LOWER"]),
        "WR10": _last(wr10),
        "BIAS6": _last(bias6),
    }

    # ── 信号汇总 ──
    signals: list[dict[str, Any]] = []

    for crosses, label in [
        (golden_5_20, "MA5金叉MA20"), (death_5_20, "MA5死叉MA20"),
        (macd_golden, "MACD金叉"), (macd_death, "MACD死叉"),
    ]:
        if crosses:
            c = crosses[-1]
            signals.append({
                "type": label,
                "desc": label,
                "index": c["index"],
                "date": dates[c["index"]] if dates and c["index"] < len(dates) else "",
            })

    # KDJ 超买/超卖
    k_val, d_val = _last(kdj_result["K"]), _last(kdj_result["D"])
    if k_val is not None and d_val is not None:
        if k_val > 80 and d_val > 80:
            signals.append({"type": "KDJ超买", "desc": f"K={k_val:.2f} D={d_val:.2f} — 短期可能回调"})
        elif k_val < 20 and d_val < 20:
            signals.append({"type": "KDJ超卖", "desc": f"K={k_val:.2f} D={d_val:.2f} — 短期可能反弹"})

    # MACD 柱转向
    macd_bar = macd_result["MACD"]
    if len(macd_bar) >= 2 and macd_bar[-1] is not None and macd_bar[-2] is not None:
        if macd_bar[-2] < 0 and macd_bar[-1] > 0:
            signals.append({"type": "MACD柱转正", "desc": "MACD柱由负转正，多头信号"})
        elif macd_bar[-2] > 0 and macd_bar[-1] < 0:
            signals.append({"type": "MACD柱转负", "desc": "MACD柱由正转负，空头信号"})

    # RSI 判断
    rsi_val = _last(rsi14)
    if rsi_val is not None:
        if rsi_val > 80:
            signals.append({"type": "RSI严重超买", "desc": f"RSI(14)={rsi_val:.2f} > 80"})
        elif rsi_val > 70:
            signals.append({"type": "RSI偏高", "desc": f"RSI(14)={rsi_val:.2f}，注意回调"})
        elif rsi_val < 20:
            signals.append({"type": "RSI严重超卖", "desc": f"RSI(14)={rsi_val:.2f} < 20"})
        elif rsi_val < 30:
            signals.append({"type": "RSI偏低", "desc": f"RSI(14)={rsi_val:.2f}，可能反弹"})

    # 均线多头/空头排列
    ma5_val, ma10_val, ma20_val = _last(ma5), _last(ma10), _last(ma20)
    if ma5_val and ma10_val and ma20_val:
        if ma5_val > ma10_val > ma20_val:
            signals.append({"type": "均线多头排列", "desc": f"MA5({ma5_val:.2f}) > MA10({ma10_val:.2f}) > MA20({ma20_val:.2f})"})
        elif ma5_val < ma10_val < ma20_val:
            signals.append({"type": "均线空头排列", "desc": f"MA5({ma5_val:.2f}) < MA10({ma10_val:.2f}) < MA20({ma20_val:.2f})"})

    return {
        "snapshot": snapshot,
        "signals": signals,
        "golden_cross_5_20": golden_5_20[-3:],
        "death_cross_5_20": death_5_20[-3:],
        "macd_golden_cross": macd_golden[-3:],
        "macd_death_cross": macd_death[-3:],
    }


# ═══════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════

def _cross(
    short: list[float | None],
    long: list[float | None],
    up: bool,
) -> list[dict[str, Any]]:
    """通用上穿/下穿检测"""
    crosses: list[dict[str, Any]] = []
    label = "金叉" if up else "死叉"
    for i in range(1, len(short)):
        if short[i] is None or long[i] is None or short[i - 1] is None or long[i - 1] is None:
            continue
        if up:
            if short[i - 1] <= long[i - 1] and short[i] > long[i]:
                crosses.append({
                    "index": i, "short": round(short[i], 4), "long": round(long[i], 4), "type": label,
                })
        else:
            if short[i - 1] >= long[i - 1] and short[i] < long[i]:
                crosses.append({
                    "index": i, "short": round(short[i], 4), "long": round(long[i], 4), "type": label,
                })
    return crosses
# ═══════════════════════════════════════════════════════════════
# MCP Tool Handler
# ═══════════════════════════════════════════════════════════════

from mcp_finance.errors import NoDataError
from mcp_finance.logging_config import get_logger

_ilogger = get_logger(__name__)


def handle_technical_indicators(arguments: dict[str, Any]) -> dict[str, Any]:
    """计算技术指标 + 信号识别"""
    from typing import Any
    from mcp_finance.api import get_kline_a, get_realtime_quote_a

    code = arguments["code"]
    pass  # secid removed, using code directly
    days = min(arguments.get("days", 120), 800)
    ktype = arguments.get("ktype", "daily")
    klt_map = {"daily": "101", "weekly": "102", "monthly": "103"}
    klt = klt_map.get(ktype, "101")

    klines = get_kline_a(code, period=ktype, adjust="qfq", limit=days)
    if not klines:
        raise NoDataError(f"无法获取 {code} 的 K 线数据")

    dates = [k["日期"] for k in klines]
    result = compute_all_indicators(klines, dates)

    quote = [get_realtime_quote_a(code)]
    if quote:
        q = quote[0]
        result["实时行情"] = {
            "代码": q.get("代码", code),
            "名称": q.get("名称", ""),
            "最新价": q.get("最新价"),
            "涨跌幅": q.get("涨跌幅"),
            "今开": q.get("今开"),
            "昨收": q.get("昨收"),
            "最高": q.get("最高"),
            "最低": q.get("最低"),
            "成交量(手)": q.get("成交量(手)"),
            "成交额(元)": q.get("成交额(元)"),
        }

    _ilogger.info("技术指标计算: %s days=%d", code, len(klines))
    return result
