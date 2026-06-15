"""
策略回测引擎 — 纯 Python 实现，无 Backtrader 依赖

功能:
  - 双均线交叉策略 (ma_cross)
  - MACD 金叉死叉策略 (macd_signal)
  - 逐日模拟交易（单边做多，千一手续费）
  - 输出绩效统计：收益率、夏普、最大回撤、胜率
  - 买入持有 (Buy & Hold) 基准对比

数据来源: 复用 api.get_kline() 获取历史 K 线
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from cn_stock.api import get_kline, guess_secid


def _compute_sma(data: list[float], period: int) -> list[float | None]:
    """简单移动平均"""
    result: list[float | None] = []
    for i in range(len(data)):
        if i + 1 < period:
            result.append(None)
        else:
            result.append(sum(data[i - period + 1 : i + 1]) / period)
    return result


def _compute_ema(data: list[float], period: int) -> list[float | None]:
    """指数移动平均"""
    result: list[float | None] = []
    multiplier = 2 / (period + 1)
    ema: float | None = None
    for i, val in enumerate(data):
        if i == 0:
            ema = val
        elif ema is not None:
            ema = (val - ema) * multiplier + ema
        result.append(ema)
    return result


def _compute_macd(
    prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """计算 MACD 线、信号线、柱状图"""
    ema_fast = _compute_ema(prices, fast)
    ema_slow = _compute_ema(prices, slow)
    dif: list[float | None] = []
    for ef, es in zip(ema_fast, ema_slow):
        if ef is not None and es is not None:
            dif.append(ef - es)
        else:
            dif.append(None)
    dea = _compute_ema([d for d in dif if d is not None], signal)
    # Re-align DEA: pad None for the leading dif Nones
    dea_padded: list[float | None] = [None] * (len(dif) - len(dea)) + dea
    macd_bar: list[float | None] = []
    for d, dd in zip(dif, dea_padded):
        if d is not None and dd is not None:
            macd_bar.append((d - dd) * 2)
        else:
            macd_bar.append(None)
    return dif, dea_padded, macd_bar


def _compute_stats(
    cash_history: list[float],
    position_history: list[int],
    prices: list[float],
    dates: list[str],
    trades: list[dict[str, Any]],
    initial_capital: float,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """从交易历史计算绩效统计"""
    final_value = cash_history[-1]
    total_return_pct = round((final_value / initial_capital - 1) * 100, 2)

    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    years = days / 365.0 if days > 0 else 1.0
    annual_return_pct = round(((final_value / initial_capital) ** (1 / years) - 1) * 100, 2) if years > 0 else 0.0

    # 权益曲线
    equity_curve = []
    for i in range(len(dates)):
        val = cash_history[i] + position_history[i] * prices[i]
        equity_curve.append({"日期": dates[i], "市值": round(val, 2)})

    # 最大回撤
    max_drawdown_pct = 0.0
    peak = initial_capital
    for point in equity_curve:
        val = point["市值"]
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak * 100
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd
    max_drawdown_pct = round(max_drawdown_pct, 2)

    # 夏普比率（基于每日市值收益率）
    daily_returns = []
    for i in range(1, len(equity_curve)):
        prev_val = equity_curve[i - 1]["市值"]
        curr_val = equity_curve[i]["市值"]
        if prev_val > 0:
            daily_returns.append((curr_val - prev_val) / prev_val)

    if len(daily_returns) > 1:
        all_zero = abs(sum(daily_returns)) < 1e-10 and all(abs(r) < 1e-10 for r in daily_returns)
        if all_zero:
            sharpe_ratio = 0.0
        else:
            avg_return = sum(daily_returns) / len(daily_returns)
            variance = sum((r - avg_return) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            std_dev = math.sqrt(variance) if variance > 0 else 1e-10
            risk_free_rate = 0.02 / 252
            sharpe = (avg_return - risk_free_rate) / std_dev * math.sqrt(252)
            sharpe_ratio = round(sharpe, 2)
    else:
        sharpe_ratio = 0.0

    # 胜率
    win_trades = sum(1 for t in trades if t.get("盈亏(%)", 0) > 0)
    total_closed = sum(1 for t in trades if t["动作"] in ("卖出", "平仓"))
    win_rate = round(win_trades / total_closed * 100, 1) if total_closed > 0 else 0.0

    return {
        "最终资金": round(final_value, 2),
        "总收益率(%)": total_return_pct,
        "年化收益率(%)": annual_return_pct,
        "最大回撤(%)": max_drawdown_pct,
        "夏普比率": sharpe_ratio,
        "胜率(%)": win_rate,
        "交易次数": sum(1 for t in trades if t["动作"] in ("卖出", "平仓")),
        "交易记录": trades,
        "权益曲线": equity_curve,
    }


def run_backtest(
    code: str,
    strategy: str = "ma_cross",
    fast_period: int = 5,
    slow_period: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 100000.0,
) -> dict[str, Any]:
    """
    策略回测

    Args:
        code:            6位股票代码，如 "600519"
        strategy:        策略名: "ma_cross" | "macd_signal"
        fast_period:     快线周期 (均线策略用快线MA, MACD策略用fast)
        slow_period:     慢线周期 (均线策略用慢线MA, MACD策略用slow)
        start_date:      开始日期，如 "2024-01-01"，默认一年前
        end_date:        结束日期，如 "2024-12-31"，默认今天
        initial_capital: 初始资金（元）

    Returns:
        回测结果字典
    """
    # ── 日期处理 ──
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        # 默认取足够长的历史（约 2 年）确保指标计算
        sd = datetime.now() - timedelta(days=730)
        start_date = sd.strftime("%Y-%m-%d")

    # ── 获取 K 线 ──
    secid = guess_secid(code)
    beg_str = start_date.replace("-", "")
    end_str = end_date.replace("-", "")
    klines = get_kline(secid, klt="101", fqt="1", lmt=800, beg=beg_str, end=end_str)

    if not klines:
        return {
            "error": f"未能获取 {code} 在 {start_date}~{end_date} 的 K 线数据",
            "提示": "确认股票代码正确，且指定时间段内该股票有交易数据",
        }

    # 过滤日期范围
    filtered = [k for k in klines if start_date <= k["日期"] <= end_date]
    klines = filtered

    if len(klines) < slow_period + 5:
        return {
            "error": f"K 线数据不足（{len(klines)} 条，需要至少 {slow_period + 5} 条）",
            "提示": "请扩大回测时间范围或减少慢线周期参数",
        }

    prices = [float(k["收盘价"]) for k in klines]
    dates = [k["日期"] for k in klines]

    # ── 策略信号计算 ──
    if strategy == "ma_cross":
        fast_line = _compute_sma(prices, fast_period)
        slow_line = _compute_sma(prices, slow_period)
        strategy_label = f"双均线交叉({fast_period},{slow_period})"

        signals: list[int] = [0] * len(prices)
        for i in range(1, len(prices)):
            if fast_line[i] is None or slow_line[i] is None:
                continue
            prev_fast = fast_line[i - 1]
            prev_slow = slow_line[i - 1]
            if prev_fast is None or prev_slow is None:
                continue
            if prev_fast <= prev_slow and fast_line[i] > slow_line[i]:
                signals[i] = 1
            if prev_fast >= prev_slow and fast_line[i] < slow_line[i]:
                signals[i] = -1

    elif strategy == "macd_signal":
        dif, dea, _ = _compute_macd(prices, fast_period, slow_period, 9)
        strategy_label = f"MACD交叉({fast_period},{slow_period},9)"

        signals = [0] * len(prices)
        for i in range(1, len(prices)):
            prev_dif = dif[i - 1]
            prev_dea = dea[i - 1]
            curr_dif = dif[i]
            curr_dea = dea[i]
            if any(x is None for x in [prev_dif, prev_dea, curr_dif, curr_dea]):
                continue
            if prev_dif <= prev_dea and curr_dif > curr_dea:
                signals[i] = 1
            if prev_dif >= prev_dea and curr_dif < curr_dea:
                signals[i] = -1
    else:
        return {"error": f"未知策略: {strategy}", "可选策略": ["ma_cross", "macd_signal"]}

    # ── 逐日模拟交易（单次遍历，同时记录权益曲线）──
    cash = initial_capital
    position = 0
    trades: list[dict[str, Any]] = []
    trade_start = -1
    in_position = False

    # 逐日快照
    cash_history: list[float] = []
    position_history: list[int] = []

    for i in range(len(prices)):
        price = prices[i]
        signal = signals[i]

        if signal == 1 and not in_position:
            # 买入（千一手续费）
            commission_rate = 0.001
            max_trade_value = cash / (1 + commission_rate)
            shares = int(max_trade_value / price)
            shares = (shares // 100) * 100  # 取整到 100 股
            if shares >= 100:
                trade_value = shares * price
                commission = trade_value * commission_rate
                cash -= trade_value + commission
                position = shares
                in_position = True
                trade_start = i
                trades.append({
                    "日期": dates[i],
                    "动作": "买入",
                    "价格": round(price, 2),
                    "股数": shares,
                    "金额": round(trade_value + commission, 2),
                })

        elif signal == -1 and in_position:
            # 卖出（千一手续费）
            commission_rate = 0.001
            trade_value = position * price
            commission = trade_value * commission_rate
            cash += trade_value - commission
            trades.append({
                "日期": dates[i],
                "动作": "卖出",
                "价格": round(price, 2),
                "股数": position,
                "金额": round(trade_value - commission, 2),
                "盈亏(%)": round((price / prices[trade_start] - 1) * 100, 2) if trade_start >= 0 else 0,
            })
            position = 0
            in_position = False

        # 记录每日快照
        cash_history.append(cash)
        position_history.append(position)

    # 最后收盘平仓
    if in_position:
        price = prices[-1]
        commission_rate = 0.001
        trade_value = position * price
        commission = trade_value * commission_rate
        cash += trade_value - commission
        trades.append({
            "日期": dates[-1],
            "动作": "平仓",
            "价格": round(price, 2),
            "股数": position,
            "金额": round(trade_value - commission, 2),
            "盈亏(%)": round((price / prices[trade_start] - 1) * 100, 2) if trade_start >= 0 else 0,
        })
        position = 0
        # 更新最后一天快照
        cash_history[-1] = cash
        position_history[-1] = position

    # ── 策略绩效统计 ──
    strat_stats = _compute_stats(
        cash_history, position_history, prices, dates, trades,
        initial_capital, start_date, end_date,
    )

    # ── 买入持有 (Buy & Hold) 基准 ──
    # 首日全仓买入，最后一日卖出
    first_price = prices[0]
    last_price = prices[-1]
    bh_shares = (int(initial_capital / (first_price * 1.001)) // 100) * 100
    bh_trades: list[dict[str, Any]] = []
    bh_cash_hist: list[float] = []
    bh_pos_hist: list[int] = []

    if bh_shares >= 100:
        bh_commission = bh_shares * first_price * 0.001
        bh_cost = bh_shares * first_price + bh_commission
        bh_cash_remaining = initial_capital - bh_cost
        bh_position = bh_shares
        bh_trades.append({
            "日期": dates[0],
            "动作": "买入",
            "价格": round(first_price, 2),
            "股数": bh_shares,
            "金额": round(bh_cost, 2),
        })
        for i in range(len(prices)):
            bh_cash_hist.append(bh_cash_remaining)
            bh_pos_hist.append(bh_position)
        bh_revenue = bh_position * last_price - bh_position * last_price * 0.001
        bh_cash_remaining += bh_revenue
        bh_cash_hist[-1] = bh_cash_remaining
        bh_pos_hist[-1] = 0
        bh_trades.append({
            "日期": dates[-1],
            "动作": "卖出",
            "价格": round(last_price, 2),
            "股数": bh_position,
            "金额": round(bh_revenue, 2),
            "盈亏(%)": round((last_price / first_price - 1) * 100, 2),
        })
    else:
        # 资金不足以买入 1 手，全现金
        bh_cash_hist = [initial_capital] * len(prices)
        bh_pos_hist = [0] * len(prices)

    bh_stats = _compute_stats(
        bh_cash_hist, bh_pos_hist, prices, dates, bh_trades,
        initial_capital, start_date, end_date,
    )

    result: dict[str, Any] = {
        "策略": strategy_label,
        "股票": f"{_get_stock_name(code)}({code})",
        "时间范围": f"{start_date} ~ {end_date}",
        "初始资金": initial_capital,
        **strat_stats,
        "基准(买入持有)": {
            "最终资金": bh_stats["最终资金"],
            "总收益率(%)": bh_stats["总收益率(%)"],
            "年化收益率(%)": bh_stats["年化收益率(%)"],
            "最大回撤(%)": bh_stats["最大回撤(%)"],
            "夏普比率": bh_stats["夏普比率"],
            "交易记录": bh_trades,
            "权益曲线": bh_stats["权益曲线"],
        },
        "参数": {
            "策略": strategy,
            "fast_period": fast_period,
            "slow_period": slow_period,
        },
    }

    if len(klines) < 30:
        result["警告"] = "K线数据较少（< 30 条），回测结果仅供参考"

    return result


def _get_stock_name(code: str) -> str:
    """从 data.py 的 STOCK_MAPPING 获取股票名称"""
    try:
        from cn_stock.data import STOCK_MAPPING
        return STOCK_MAPPING.get(code, code)
    except Exception:
        return code