"""
单次预警检查模块

提供 handle_set_alert 函数，供 server.py set_alert tool 调用。
检查条件包括：价格突破/跌破、涨跌幅阈值、MACD金叉死叉、均线金叉死叉、RSI超买超卖。
"""
from __future__ import annotations
from typing import Any

from mcp_finance.api import get_realtime_quote_a, get_kline_a
from mcp_finance.indicators import compute_all_indicators, _sma, _ema, calc_rsi
from mcp_finance.data import STOCK_MAPPING
from mcp_finance.logging_config import get_logger

_logger = get_logger(__name__)


def handle_set_alert(args: dict[str, Any]) -> dict[str, Any]:
    """单次预警检查

    支持的 condition 格式:
      - price_above:<value>     — 最新价高于 value
      - price_below:<value>     — 最新价低于 value
      - gain_above:<pct>        — 涨跌幅高于 pct%
      - gain_below:<pct>        — 涨跌幅低于 pct%
      - macd_golden_cross       — MACD 金叉 (DIF 上穿 DEA)
      - macd_dead_cross         — MACD 死叉 (DIF 下穿 DEA)
      - ma_golden_cross:<fast>:<slow> — 均线金叉 (快线上穿慢线)
      - ma_dead_cross:<fast>:<slow>   — 均线死叉 (快线下穿慢线)
      - rsi_oversold            — RSI 低于 30 (超卖)
      - rsi_overbought          — RSI 高于 70 (超买)
    """
    code = args.get("code", "")
    condition_str = args.get("condition", "")
    channel = args.get("channel", "")

    if not code or not condition_str:
        return {"error": True, "message": "参数缺失: code 和 condition 为必填"}

    stock_name = STOCK_MAPPING.get(code, code)

    # 解析条件
    parts = condition_str.split(":", 1)
    cond_type = parts[0].lower()

    # 获取实时行情
    quote = get_realtime_quote_a(code)
    if not quote or "error" in quote:
        # 尝试用 K 线最后一根来获取最新价
        klines = get_kline_a(code, limit=1)
        if klines and isinstance(klines, list) and len(klines) > 0 and "error" not in klines[0]:
            latest = klines[-1]
            quote = latest
        else:
            return {"error": True, "message": f"无法获取 {code} 的行情数据"}

    latest_price = quote.get("最新价")
    change_pct = quote.get("涨跌幅")

    triggered = False
    detail = ""

    if cond_type == "price_above":
        threshold = float(parts[1]) if len(parts) > 1 else 0
        if latest_price is not None and latest_price > threshold:
            triggered = True
            detail = f"{stock_name}({code}) 最新价 {latest_price} > {threshold}，条件满足"
        else:
            detail = f"{stock_name}({code}) 最新价 {latest_price}，未突破 {threshold}"
    elif cond_type == "price_below":
        threshold = float(parts[1]) if len(parts) > 1 else 0
        if latest_price is not None and latest_price < threshold:
            triggered = True
            detail = f"{stock_name}({code}) 最新价 {latest_price} < {threshold}，条件满足"
        else:
            detail = f"{stock_name}({code}) 最新价 {latest_price}，未跌破 {threshold}"
    elif cond_type == "gain_above":
        threshold = float(parts[1]) if len(parts) > 1 else 0
        if change_pct is not None and change_pct > threshold:
            triggered = True
            detail = f"{stock_name}({code}) 涨跌幅 {change_pct}% > {threshold}%，条件满足"
        else:
            detail = f"{stock_name}({code}) 涨跌幅 {change_pct}%，未达阈值 {threshold}%"
    elif cond_type == "gain_below":
        threshold = float(parts[1]) if len(parts) > 1 else 0
        if change_pct is not None and change_pct < threshold:
            triggered = True
            detail = f"{stock_name}({code}) 涨跌幅 {change_pct}% < {threshold}%，条件满足"
        else:
            detail = f"{stock_name}({code}) 涨跌幅 {change_pct}%，未达阈值 {threshold}%"
    elif cond_type in ("macd_golden_cross", "macd_dead_cross"):
        klines = get_kline_a(code, limit=120)
        if not klines or len(klines) < 34:
            return {"error": True, "message": f"{code} K线数据不足，无法计算MACD"}
        indicators = compute_all_indicators(klines)
        signals = indicators.get("signals", [])
        target_signal = "MACD金叉" if cond_type == "macd_golden_cross" else "MACD死叉"
        triggered = any(target_signal in s for s in signals)
        detail = f"{stock_name}({code}) {'检测到' if triggered else '未检测到'} {target_signal}" if triggered else f"{stock_name}({code}) 未检测到 {target_signal}"
    elif cond_type == "ma_golden_cross":
        parts2 = condition_str.split(":")
        fast = int(parts2[1]) if len(parts2) > 1 else 5
        slow = int(parts2[2]) if len(parts2) > 2 else 20
        klines = get_kline_a(code, limit=slow + 10)
        if not klines or len(klines) < slow:
            return {"error": True, "message": f"{code} K线数据不足，无法计算均线"}
        closes = [float(k["收盘价"]) for k in klines]
        ma_fast = _sma(closes, fast)
        ma_slow = _sma(closes, slow)
        if len(ma_fast) >= 2 and len(ma_slow) >= 2:
            prev_fast, curr_fast = ma_fast[-2], ma_fast[-1]
            prev_slow, curr_slow = ma_slow[-2], ma_slow[-1]
            if prev_fast is not None and curr_fast is not None and prev_slow is not None and curr_slow is not None:
                if prev_fast <= prev_slow and curr_fast > curr_slow:
                    triggered = True
        detail = f"{stock_name}({code}) MA{fast} {'上穿' if triggered else '未上穿'} MA{slow}"
    elif cond_type == "ma_dead_cross":
        parts2 = condition_str.split(":")
        fast = int(parts2[1]) if len(parts2) > 1 else 5
        slow = int(parts2[2]) if len(parts2) > 2 else 20
        klines = get_kline_a(code, limit=slow + 10)
        if not klines or len(klines) < slow:
            return {"error": True, "message": f"{code} K线数据不足，无法计算均线"}
        closes = [float(k["收盘价"]) for k in klines]
        ma_fast = _sma(closes, fast)
        ma_slow = _sma(closes, slow)
        if len(ma_fast) >= 2 and len(ma_slow) >= 2:
            prev_fast, curr_fast = ma_fast[-2], ma_fast[-1]
            prev_slow, curr_slow = ma_slow[-2], ma_slow[-1]
            if prev_fast is not None and curr_fast is not None and prev_slow is not None and curr_slow is not None:
                if prev_fast >= prev_slow and curr_fast < curr_slow:
                    triggered = True
        detail = f"{stock_name}({code}) MA{fast} {'下穿' if triggered else '未下穿'} MA{slow}"
    elif cond_type == "rsi_oversold":
        klines = get_kline_a(code, limit=30)
        if not klines or len(klines) < 14:
            return {"error": True, "message": f"{code} K线数据不足，无法计算RSI"}
        closes = [float(k["收盘价"]) for k in klines]
        rsi = calc_rsi(closes, 14)
        if rsi and len(rsi) > 0 and rsi[-1] is not None:
            if rsi[-1] < 30:
                triggered = True
                detail = f"{stock_name}({code}) RSI(14)={rsi[-1]:.2f} < 30，超卖"
            else:
                detail = f"{stock_name}({code}) RSI(14)={rsi[-1]:.2f}，未进入超卖区"
        else:
            detail = f"{stock_name}({code}) RSI计算失败"
    elif cond_type == "rsi_overbought":
        klines = get_kline_a(code, limit=30)
        if not klines or len(klines) < 14:
            return {"error": True, "message": f"{code} K线数据不足，无法计算RSI"}
        closes = [float(k["收盘价"]) for k in klines]
        rsi = calc_rsi(closes, 14)
        if rsi and len(rsi) > 0 and rsi[-1] is not None:
            if rsi[-1] > 70:
                triggered = True
                detail = f"{stock_name}({code}) RSI(14)={rsi[-1]:.2f} > 70，超买"
            else:
                detail = f"{stock_name}({code}) RSI(14)={rsi[-1]:.2f}，未进入超买区"
        else:
            detail = f"{stock_name}({code}) RSI计算失败"
    else:
        return {"error": True, "message": f"不支持的预警条件: {condition_str}"}

    # 推送（暂不实现实际推送，仅记录日志）
    if channel and triggered:
        _logger.info("预警触发: code=%s condition=%s channel=%s", code, condition_str, channel)

    return {
        "code": code,
        "名称": stock_name,
        "condition": condition_str,
        "最新价": latest_price,
        "涨跌幅": change_pct,
        "触发": triggered,
        "详情": detail,
        "channel": channel or "无",
        "提示": "规则不会持久化 — 这是一次性检查，非后台持续盯盘",
    }
