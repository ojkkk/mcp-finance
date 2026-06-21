"""
PyBroker 回测包装模块 (实验性)

提供 handle_pybroker_backtest 函数，供 server.py pybroker_backtest tool 调用。
当前为占位实现，避免 mcp-finance server 因 ImportError 崩溃。
"""
from __future__ import annotations
from typing import Any

from mcp_finance.api import get_kline_a, get_realtime_quote_a
from mcp_finance.indicators import compute_all_indicators
from mcp_finance.data import STOCK_MAPPING
from mcp_finance.logging_config import get_logger

_logger = get_logger(__name__)


def handle_pybroker_backtest(args: dict[str, Any]) -> dict[str, Any]:
    """均值比较信号回测（实验性）

    基于技术指标均值比较生成买卖信号。
    当前实现为简单规则引擎，非真正的 ML 模型。
    """
    code = args.get("code", "")
    start_date = args.get("start_date", "")
    end_date = args.get("end_date", "")
    initial_capital = float(args.get("initial_capital", 100000))
    train_size = float(args.get("train_size", 0.7))

    if not code:
        return {"error": True, "message": "请提供股票代码"}

    stock_name = STOCK_MAPPING.get(code, code)

    # ── 获取 K 线数据 ──
    limit = 800
    klines = get_kline_a(code, period="daily", adjust="qfq", limit=limit)
    if not klines or (isinstance(klines, list) and len(klines) > 0 and "error" in klines[0]):
        return {"error": True, "message": f"无法获取 {code} 的 K 线数据"}

    # 简单过滤日期范围
    filtered = []
    for k in klines:
        d = k.get("日期", "")
        if start_date and d < start_date:
            continue
        if end_date and d > end_date:
            continue
        filtered.append(k)

    if len(filtered) < 30:
        return {"error": True, "message": f"{code} 在指定日期范围内的 K 线数据不足 (需要至少30条)"}

    # ── 计算指标 ──
    indicators = compute_all_indicators(filtered)
    snapshot = indicators.get("snapshot", {})
    signals = indicators.get("signals", [])

    # ── 简单回测逻辑：当短期MA > 长期MA时买入，否则卖出 ──
    closes = [float(k["收盘价"]) for k in filtered]
    dates = [k["日期"] for k in filtered]

    # 使用 MA5 和 MA20 的交叉信号
    from mcp_finance.indicators import _sma
    ma5 = _sma(closes, 5)
    ma20 = _sma(closes, 20)

    position = 0  # 0=空仓, 1=持仓
    cash = initial_capital
    shares = 0
    trades = []
    equity_curve = []

    for i in range(len(dates)):
        if ma5[i] is None or ma20[i] is None or ma5[i] == 0 or ma20[i] == 0:
            equity_curve.append({"日期": dates[i], "市值": cash})
            continue

        price = closes[i]
        current_value = cash + shares * price

        # 买入信号: MA5 上穿 MA20 且空仓
        if i > 0:
            prev_ma5 = ma5[i-1] if ma5[i-1] is not None else 0
            prev_ma20 = ma20[i-1] if ma20[i-1] is not None else 0
            buy_signal = prev_ma5 <= prev_ma20 and ma5[i] > ma20[i] and position == 0
            sell_signal = prev_ma5 >= prev_ma20 and ma5[i] < ma20[i] and position == 1

            if buy_signal:
                shares = int(cash / price / 100) * 100  # 整手买入
                if shares > 0:
                    cost = shares * price
                    cash -= cost
                    position = 1
                    trades.append({"日期": dates[i], "动作": "买入", "价格": price, "金额": cost, "持股": shares})
            elif sell_signal:
                if shares > 0:
                    revenue = shares * price
                    cash += revenue
                    trades.append({"日期": dates[i], "动作": "卖出", "价格": price, "金额": revenue, "持股": 0})
                    shares = 0
                    position = 0

        equity_curve.append({"日期": dates[i], "市值": cash + shares * price})

    # 最终平仓
    if shares > 0 and len(closes) > 0:
        final_price = closes[-1]
        revenue = shares * final_price
        cash += revenue
        trades.append({"日期": dates[-1], "动作": "平仓", "价格": final_price, "金额": revenue, "持股": 0})
        shares = 0

    final_value = cash
    total_return = round((final_value - initial_capital) / initial_capital * 100, 2) if initial_capital > 0 else 0

    # ── 计算夏普比率 ──
    returns = []
    for i in range(1, len(equity_curve)):
        prev_val = equity_curve[i-1]["市值"]
        curr_val = equity_curve[i]["市值"]
        if prev_val > 0:
            returns.append((curr_val - prev_val) / prev_val)

    sharpe = 0
    if len(returns) > 1:
        import math
        avg_ret = sum(returns) / len(returns)
        variance = sum((r - avg_ret) ** 2 for r in returns) / (len(returns) - 1)
        if variance > 0:
            sharpe = round(avg_ret / math.sqrt(variance) * math.sqrt(252), 2)

    # ── 最大回撤 ──
    max_drawdown = 0
    peak = equity_curve[0]["市值"] if equity_curve else initial_capital
    for point in equity_curve:
        val = point["市值"]
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100 if peak > 0 else 0
        if dd > max_drawdown:
            max_drawdown = round(dd, 2)

    return {
        "股票": stock_name,
        "代码": code,
        "策略": "均值比较信号 (MA5/MA20交叉)",
        "初始资金": initial_capital,
        "最终资产": round(final_value, 2),
        "总收益率(%)": total_return,
        "夏普比率": sharpe,
        "最大回撤(%)": max_drawdown,
        "交易次数": len(trades),
        "交易记录": trades[-10:] if trades else [],  # 仅返回最近10笔
        "最新技术信号": signals[:5] if signals else [],
        "提示": "实验性功能 — 当前为简单MA交叉策略，非真正的PyBroker ML模型。model_type参数暂为占位符。",
    }
