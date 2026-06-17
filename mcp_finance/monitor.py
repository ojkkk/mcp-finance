"""
异常监控 + 消息推送模块

支持:
  - 条件触发式告警（价格突破、金叉死叉、涨跌幅阈值）
  - 钉钉机器人 webhook 推送
  - 企业微信机器人 webhook 推送
  - Server酱 (微信) 推送

配置方式:
  设置环境变量:
    DINGTALK_WEBHOOK_URL
    WECOM_WEBHOOK_URL
    SERVERCHAN_SENDKEY
"""

from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
from typing import Any
from datetime import datetime


def _get_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ═══════════════════════════════════════════════════════════════
# 推送渠道
# ═══════════════════════════════════════════════════════════════

def send_dingtalk(title: str, text: str, webhook_url: str = "") -> bool:
    """钉钉机器人推送"""
    url = webhook_url or _get_env("DINGTALK_WEBHOOK_URL")
    if not url:
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = json.dumps({
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"## {title}\n\n{text}\n\n> {now}",
            },
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def send_wecom(title: str, text: str, webhook_url: str = "") -> bool:
    """企业微信机器人推送"""
    url = webhook_url or _get_env("WECOM_WEBHOOK_URL")
    if not url:
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = json.dumps({
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n{text}\n<font color=\"comment\">{now}</font>",
            },
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def send_serverchan(title: str, desp: str, sendkey: str = "") -> bool:
    """Server酱 (微信推送) https://sct.ftqq.com/"""
    key = sendkey or _get_env("SERVERCHAN_SENDKEY")
    if not key:
        return False
    try:
        url = f"https://sctapi.ftqq.com/{key}.send"
        data = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# 监控条件评估
# ═══════════════════════════════════════════════════════════════

def evaluate_alert_conditions(
    stock_code: str,
    stock_name: str,
    indicators: dict[str, Any],
    quote: dict[str, Any],
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    评估告警条件

    支持的规则:
      - price_above:   股价突破 X 元
      - price_below:   股价跌破 X 元
      - gain_above:    涨幅超过 X%
      - gain_below:    跌幅超过 X%（正数）
      - ma_golden:     均线金叉 (MA5上穿MA20)
      - ma_death:      均线死叉
      - macd_golden:   MACD 金叉
      - macd_death:    MACD 死叉
      - rsi_above:     RSI 超过
      - rsi_below:     RSI 低于

    Returns:
        触发的告警列表
    """
    triggered: list[dict[str, Any]] = []
    snap = indicators.get("snapshot", {})

    price = quote.get("最新价")
    gain = quote.get("涨跌幅")

    # 价格突破
    if "price_above" in rules and price is not None:
        threshold = rules["price_above"]
        if price >= threshold:
            triggered.append({
                "rule": "price_above",
                "value": price,
                "msg": f"{stock_name}({stock_code}) 涨破 {threshold} 元，现价 {price}",
            })

    if "price_below" in rules and price is not None:
        threshold = rules["price_below"]
        if price <= threshold:
            triggered.append({
                "rule": "price_below",
                "value": price,
                "msg": f"{stock_name}({stock_code}) 跌破 {threshold} 元，现价 {price}",
            })

    # 涨跌幅
    if gain is not None:
        if "gain_above" in rules and gain >= rules["gain_above"]:
            triggered.append({
                "rule": "gain_above",
                "value": gain,
                "msg": f"{stock_name}({stock_code}) 涨 {gain:.2f}%（阈值 {rules['gain_above']}%）",
            })
        if "gain_below" in rules and gain <= -rules["gain_below"]:
            triggered.append({
                "rule": "gain_below",
                "value": gain,
                "msg": f"{stock_name}({stock_code}) 跌 {gain:.2f}%（阈值 -{rules['gain_below']}%）",
            })

    # RSI
    rsi = snap.get("RSI14")
    if rsi is not None:
        if "rsi_above" in rules and rsi >= rules["rsi_above"]:
            triggered.append({
                "rule": "rsi_above",
                "value": rsi,
                "msg": f"{stock_name}({stock_code}) RSI(14)={rsi:.2f} > {rules['rsi_above']}",
            })
        if "rsi_below" in rules and rsi <= rules["rsi_below"]:
            triggered.append({
                "rule": "rsi_below",
                "value": rsi,
                "msg": f"{stock_name}({stock_code}) RSI(14)={rsi:.2f} < {rules['rsi_below']}",
            })

    # 技术信号
    signals = indicators.get("signals", [])
    signal_types = {s["type"] for s in signals} if signals else set()

    rule_to_signal = {
        "macd_golden": "MACD金叉",
        "macd_death": "MACD死叉",
        "ma_golden": "MA5金叉MA20",
        "ma_death": "MA5死叉MA20",
    }

    for rule_key, signal_name in rule_to_signal.items():
        if rules.get(rule_key) and signal_name in signal_types:
            triggered.append({
                "rule": rule_key,
                "msg": f"{stock_name}({stock_code}) {signal_name} 触发",
            })

    return triggered


def push_alerts(
    alerts: list[dict[str, Any]],
    channels: list[str] | None = None,
) -> dict[str, Any]:
    """推送告警到指定渠道"""
    if channels is None:
        channels = ["dingtalk"]

    if not alerts:
        return {"pushed": 0, "channels": channels, "status": "无告警触发"}

    title = f"股票预警 - {len(alerts)} 条触发"
    text = "\n\n".join(
        f"**{a['rule']}**: {a['msg']}" for a in alerts
    )

    results: dict[str, bool] = {}
    if "dingtalk" in channels:
        results["dingtalk"] = send_dingtalk(title, text)
    if "wecom" in channels:
        results["wecom"] = send_wecom(title, text)
    if "serverchan" in channels:
        results["serverchan"] = send_serverchan(title, text)

    return {
        "pushed": len(alerts),
        "alerts": alerts,
        "channels": channels,
        "results": results,
        "status": "已推送" if any(results.values()) else "推送失败（未配置 webhook）",
    }
# ═══════════════════════════════════════════════════════════════
# MCP Tool Handler
# ═══════════════════════════════════════════════════════════════

from mcp_finance.errors import NoDataError
from mcp_finance.logging_config import get_logger

_mlogger = get_logger(__name__)


def handle_set_alert(arguments: dict[str, Any]) -> dict[str, Any]:
    """设置告警条件并立即评估"""
    from typing import Any
    from mcp_finance.api import get_kline_a, get_realtime_quote_a
    from mcp_finance.indicators import compute_all_indicators

    code = arguments["code"]
    pass  # secid removed

    klines = get_kline_a(code, period="daily", adjust="qfq", limit=60)
    indicators = compute_all_indicators(klines) if klines else {"snapshot": {}, "signals": []}
    quotes = [get_realtime_quote_a(code)]
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
        raise NoDataError("请至少设置一个告警条件")

    stock_name = quote.get("名称", code)
    triggered = evaluate_alert_conditions(code, stock_name, indicators, quote, rules)
    channel = arguments.get("push_channel", "dingtalk")
    push_result = push_alerts(triggered, channels=[channel])

    _mlogger.info("告警评估: %s rules=%d triggered=%d", code, len(rules), len(triggered))
    return {
        "股票": f"{stock_name}({code})",
        "当前价": quote.get("最新价"),
        "涨跌幅": quote.get("涨跌幅"),
        "规则": rules,
        "触发告警": triggered,
        "推送结果": push_result,
    }
