"""
持续盯盘脚本 — 定时检查自选股，触发条件后自动推送到钉钉/微信

用法:
    python run_monitor.py

    按 Ctrl+C 停止。

配置方式（三选一）:
    setx DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxx
    setx WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
    setx SERVERCHAN_SENDKEY=SCT你的key

自定义监控列表:
    修改下方 WATCHLIST 即可，支持多只股票、多种条件组合。
"""

from __future__ import annotations
import time
import sys
import os
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cn_stock.api import get_kline, get_realtime_quotations, guess_secid
from cn_stock.indicators import compute_all_indicators
from cn_stock.monitor import evaluate_alert_conditions, push_alerts


# ═══════════════════════════════════════════════════════════════
# 🔧 监控列表 — 在这里配置你要盯的股票和条件
# ═══════════════════════════════════════════════════════════════

WATCHLIST: list[dict[str, Any]] = [
    {
        "code": "600519",       # 股票代码
        "name": "贵州茅台",      # 可选，留空自动获取
        "rules": {
            # "price_above": 2000,     # 涨破 2000 元
            # "price_below": 1500,     # 跌破 1500 元
            # "gain_above": 5,         # 涨超 5%
            # "gain_below": 3,         # 跌超 3%
            # "macd_golden": True,     # MACD 金叉
            # "macd_death": True,      # MACD 死叉
            # "ma_golden": True,       # MA5 金叉 MA20
            # "ma_death": True,        # MA5 死叉 MA20
            # "rsi_above": 80,         # RSI 超买
            # "rsi_below": 20,         # RSI 超卖
        },
        "channel": ["dingtalk"],  # dingtalk / wecom / serverchan
    },
    # 更多示例（取消注释即生效）:
    #
    # {
    #     "code": "300750",
    #     "rules": {"gain_above": 5},
    #     "channel": ["dingtalk"],
    # },
    # {
    #     "code": "000858",
    #     "rules": {"macd_golden": True, "rsi_below": 30},
    #     "channel": ["dingtalk", "wecom"],
    # },
]


# ═══════════════════════════════════════════════════════════════
# 运行参数
# ═══════════════════════════════════════════════════════════════

INTERVAL_SECONDS = 60          # 检查间隔（秒），免费 API 建议 ≥ 30
MAX_CONSECUTIVE_ERRORS = 10    # 连续出错多少次后退出
COOLDOWN_MINUTES = 30          # 同一条件的冷却时间（分钟），避免重复推送


# ═══════════════════════════════════════════════════════════════
# 内部状态
# ═══════════════════════════════════════════════════════════════

_last_triggered: dict[str, float] = {}  # key → 上次触发时间戳


def _cooldown_key(code: str, rule: str) -> str:
    return f"{code}:{rule}"


def _is_in_cooldown(code: str, rule: str) -> bool:
    key = _cooldown_key(code, rule)
    if key not in _last_triggered:
        return False
    elapsed = time.time() - _last_triggered[key]
    return elapsed < COOLDOWN_MINUTES * 60


def _mark_triggered(code: str, rule: str) -> None:
    _last_triggered[_cooldown_key(code, rule)] = time.time()


def check_one(code: str, rules: dict, channels: list[str]) -> list[dict[str, Any]]:
    """检查单只股票，返回触发的告警（已过滤冷却）"""
    try:
        secid = guess_secid(code)
        klines = get_kline(secid, klt="101", fqt="1", lmt=60)
        quotes = get_realtime_quotations([secid])

        if not klines or not quotes:
            return []

        quote = quotes[0]
        stock_name = quote.get("名称", code)
        indicators = compute_all_indicators(klines)

        triggered = evaluate_alert_conditions(code, stock_name, indicators, quote, rules)

        # 冷却过滤
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
        print(f"  ⚠️ {code} 异常: {e}")
        return []


def main():
    print("=" * 50)
    print("📈 mcp-stock-cn 持续盯盘已启动")
    print(f"   监控 {len(WATCHLIST)} 只股票")
    print(f"   间隔 {INTERVAL_SECONDS}s | 冷却 {COOLDOWN_MINUTES}min")
    print("   按 Ctrl+C 停止")
    print("=" * 50)

    # 预热 Baostock
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code == "0":
            print("✅ Baostock 已连接")
    except ImportError:
        print("ℹ️  Baostock 未安装，将使用东方财富/腾讯数据源")

    consecutive_errors = 0

    try:
        while True:
            now = datetime.now()
            print(f"\n[{now:%H:%M:%S}] 检查中...")

            total_triggered = 0
            active_items = 0
            for item in WATCHLIST:
                code = item["code"]
                rules = item.get("rules", {})
                channels = item.get("channel", ["dingtalk"])

                if not rules:
                    continue

                active_items += 1
                triggered = check_one(code, rules, channels)
                if triggered:
                    total_triggered += len(triggered)
                    stock_name = item.get("name", code)
                    for t in triggered:
                        print(f"  🔔 {stock_name}({code}) → {t['msg'][:80]}")
                    consecutive_errors = 0
                else:
                    # 安静模式
                    pass

            if total_triggered > 0:
                print(f"  📬 共推送 {total_triggered} 条告警")
            else:
                if active_items > 0:
                    print(f"  ✅ 无触发")
                else:
                    print(f"  ⚠️  没有启用的监控规则（请配置 WATCHLIST）")

            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n🛑 已停止盯盘")

    finally:
        try:
            import baostock as bs
            bs.logout()
        except ImportError:
            pass


if __name__ == "__main__":
    main()