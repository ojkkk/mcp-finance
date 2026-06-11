"""
持续盯盘脚本 — 可自己跑在后台，定期检查股票条件，触发告警就推送

用法：
  1. 先配置环境变量（选一个推送渠道即可）：
     setx DINGTALK_WEBHOOK_URL "https://oapi.dingtalk.com/robot/send?access_token=你的token"
     setx WECOM_WEBHOOK_URL "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
     setx SERVERCHAN_SENDKEY "SCT你的key"

  2. 修改下方 WATCHLIST 添加你想盯的股票和条件

  3. 运行：
     python run_monitor.py
"""

import os
import sys
import time
from datetime import datetime

# ── 修改这里：添加你想盯的股票 ─────────────────────────────────────────
WATCHLIST = [
    # 格式: {"code": "股票代码", "rules": {条件字典}, "channel": ["推送渠道"]}
    # 条件字典支持的 key:
    #   price_above / price_below : 价格突破/跌破
    #   gain_above / gain_below   : 涨跌幅阈值（正数）
    #   macd_golden / macd_death  : MACD 金叉/死叉 (True)
    #   ma_golden  / ma_death     : 均线金叉/死叉 (True)
    #   rsi_above  / rsi_below    : RSI 阈值
    # 推送渠道: "dingtalk" / "wecom" / "serverchan"

    {"code": "600519", "name": "贵州茅台",
     "rules": {"price_below": 1500, "macd_death": True},
     "channel": ["dingtalk"]},

    {"code": "300750", "name": "宁德时代",
     "rules": {"gain_above": 5},
     "channel": ["dingtalk"]},
]

# 检查间隔（秒）
CHECK_INTERVAL = 60

# ── 以下不用改 ─────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from cn_stock.api import get_kline, get_realtime_quotations, guess_secid
from cn_stock.indicators import compute_all_indicators
from cn_stock.monitor import evaluate_alert_conditions, push_alerts


def check_and_push(item: dict) -> bool:
    """检查一只股票，触发告警则推送，返回是否有告警触发"""
    code = item["code"]
    rules = item["rules"]
    channels = item.get("channel", ["dingtalk"])
    name = item.get("name", code)

    secid = guess_secid(code)
    klines = get_kline(secid, klt="101", fqt="1", lmt=60)
    quotes = get_realtime_quotations([secid])

    if not klines or not quotes:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {name}({code}) 数据获取失败，跳过")
        return False

    indicators = compute_all_indicators(klines)
    triggered = evaluate_alert_conditions(code, name, indicators, quotes[0], rules)

    if triggered:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔔 {name}({code}) 触发 {len(triggered)} 条告警")
        for a in triggered:
            print(f"       [{a['rule']}] {a['msg'][:60]}")
        result = push_alerts(triggered, channels=channels)
        if result.get("pushed", 0) > 0:
            print(f"       ✅ 已推送 ({', '.join(result.get('results', {}).keys())})")
        return True
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {name}({code}) 无告警触发")
        return False


def main():
    """主循环：持续盯盘"""
    print("=" * 50)
    print("📊 mcp-stock-cn 持续盯盘脚本")
    print(f"检查间隔: {CHECK_INTERVAL} 秒")
    print(f"盯盘数量: {len(WATCHLIST)} 只")
    print()

    # 验证环境变量
    dingtalk_url = os.environ.get("DINGTALK_WEBHOOK_URL", "")
    wecom_url = os.environ.get("WECOM_WEBHOOK_URL", "")
    serverchan_key = os.environ.get("SERVERCHAN_SENDKEY", "")
    channels_found = []
    if dingtalk_url:
        channels_found.append("钉钉")
    if wecom_url:
        channels_found.append("企业微信")
    if serverchan_key:
        channels_found.append("Server酱")

    if channels_found:
        print(f"推送渠道: {', '.join(channels_found)}")
    else:
        print("⚠️  未检测到推送渠道环境变量！")
        print("   请设置以下之一：")
        print("     setx DINGTALK_WEBHOOK_URL <钉钉webhook>")
        print("     setx WECOM_WEBHOOK_URL <企业微信webhook>")
        print("     setx SERVERCHAN_SENDKEY <Server酱SendKey>")
        print("   告警将仅在控制台打印，不会推送。")
    print()

    print(f"立即开始检查...")
    check_and_push(WATCHLIST[0])  # 先跑一次

    print(f"\n进入循环，每 {CHECK_INTERVAL} 秒检查一次 (Ctrl+C 停止)")
    print("=" * 50)

    try:
        round_num = 1
        while True:
            time.sleep(CHECK_INTERVAL)
            print(f"\n--- 第 {round_num} 轮检查 ---")
            for item in WATCHLIST:
                check_and_push(item)
            round_num += 1
    except KeyboardInterrupt:
        print("\n\n🛑 盯盘已停止")
        sys.exit(0)


if __name__ == "__main__":
    main()