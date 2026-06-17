"""
持续盯盘脚本 — 定时检查自选股，触发条件后自动推送到钉钉/微信

用法:
    python run_monitor.py

    按 Ctrl+C 停止。

前置条件:
    setx DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxx
    setx WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
    setx SERVERCHAN_SENDKEY=SCT你的key

自定义监控列表:
    修改下方 WATCHLIST 即可。
"""

from __future__ import annotations
import time
from datetime import datetime
from typing import Any

from mcp_finance.api import get_kline_a, get_realtime_quote_a
from mcp_finance.indicators import compute_all_indicators
from mcp_finance.monitor import evaluate_alert_conditions, push_alerts


# ═══════════════════════════════════════════════════════════════
# 🔧 监控列表 — 配置你要盯的股票
# ═══════════════════════════════════════════════════════════════

WATCHLIST: list[dict[str, Any]] = [
    {
        "code": "600519",
        "rules": {
            # "price_below": 1500,   # 跌破 1500
            # "gain_above": 5,       # 涨超 5%
            # "gain_below": 3,       # 跌超 3%
            # "macd_golden": True,   # MACD 金叉
            # "macd_death": True,    # MACD 死叉
            # "ma_golden": True,     # MA5金叉MA20
            # "ma_death": True,      # MA5死叉MA20
            # "rsi_above": 80,       # RSI超买
            # "rsi_below": 20,       # RSI超卖
        },
        "channel": ["dingtalk"],
    },
]

INTERVAL_SECONDS = 60
COOLDOWN_MINUTES = 30

_last_triggered: dict[str, float] = {}


def _cooldown_key(code: str, rule: str) -> str:
    return f"{code}:{rule}"


def _is_in_cooldown(code: str, rule: str) -> bool:
    key = _cooldown_key(code, rule)
    if key not in _last_triggered:
        return False
    return (time.time() - _last_triggered[key]) < COOLDOWN_MINUTES * 60


def _mark_triggered(code: str, rule: str) -> None:
    _last_triggered[_cooldown_key(code, rule)] = time.time()


def check_one(code: str, rules: dict, channels: list[str]) -> list[dict[str, Any]]:
    try:
        pass  # using code directly
        klines = get_kline_a(code, period="daily", adjust="qfq", limit=60)
        quotes = [get_realtime_quote_a(code)]
        if not klines or not quotes:
            return []
        quote = quotes[0]
        name = quote.get("名称", code)
        indicators = compute_all_indicators(klines)
        triggered = evaluate_alert_conditions(code, name, indicators, quote, rules)
        fresh = []
        for alert in triggered:
            rule = alert.get("rule", "")
            if not _is_in_cooldown(code, rule):
                fresh.append(alert)
                _mark_triggered(code, rule)
        if fresh:
            push_alerts(fresh, channels=channels)
        return fresh
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] ⚠️ {code} 异常: {e}")
        return []


def main():
    print("=" * 50)
    print("📈 mcp-finance 持续盯盘已启动")
    print(f"   监控 {len(WATCHLIST)} 只 | 间隔 {INTERVAL_SECONDS}s | 冷却 {COOLDOWN_MINUTES}min")
    print("   按 Ctrl+C 停止")
    print("=" * 50)

    print("AKShare data source ready")

    try:
        while True:
            now = datetime.now()
            total = 0
            for item in WATCHLIST:
                rules = item.get("rules", {})
                if not rules:
                    continue
                triggered = check_one(item["code"], rules, item.get("channel", ["dingtalk"]))
                if triggered:
                    total += len(triggered)
                    for t in triggered:
                        print(f"  [{now:%H:%M:%S}] 🔔 {item['code']} → {t['msg']}")
            if total == 0 and now.second < INTERVAL_SECONDS:
                print(f"  [{now:%H:%M:%S}] ✅ 无触发")
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\n🛑 已停止")



if __name__ == "__main__":
    main()