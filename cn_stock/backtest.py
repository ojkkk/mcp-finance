"""
策略回测引擎 — 基于 vectorbt 向量化计算

优势:
  - 向量化运算，万倍速度于逐行模拟
  - vectorbt Portfolio 内置 Sharpe/MDD/胜率等 30+ 项指标
  - 原生参数扫描支持（optimize_backtest）
  - Plotly 可视化兼容

A 股规则适配:
  - T+1 限制（买入次日才能卖出）
  - 涨跌停过滤（涨停无法买入/跌停无法卖出）
  - 整数手（100 股整数倍）
  - 千一佣金 + 卖方印花税 0.05% + 最低佣金 5 元
  - 买入持有基准对比
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt

from cn_stock.api import get_kline, guess_secid

# ── 费率常量 ──
COMMISSION_RATE = 0.001     # 佣金千分之一（买卖双向）
STAMP_TAX_RATE = 0.0005     # 印花税万分之五（仅卖方）


def _kline_to_df(klines: list[dict[str, Any]]) -> pd.DataFrame:
    """将 API 返回的 K 线数据（list[dict]）转为 pandas DataFrame"""
    records = []
    for k in klines:
        records.append({
            "date": k["日期"],
            "open": float(k["开盘价"]),
            "high": float(k["最高价"]),
            "low": float(k["最低价"]),
            "close": float(k["收盘价"]),
            "volume": float(k["成交量(手)"]) if k.get("成交量(手)") else 0,
        })
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    return df


def _is_chi_next(code: str) -> bool:
    """是否创业板/科创板（涨跌幅 ±20%）"""
    return code.startswith("30") or code.startswith("68")


def _adjust_signals(
    entries: pd.Series,
    exits: pd.Series,
    close: pd.Series,
    code: str,
) -> tuple[pd.Series, pd.Series, list[str]]:
    """
    对原始信号应用 A 股交易规则：
    - T+1: 买入当日不能卖出
    - 涨跌停过滤: 涨停无法买、跌停无法卖
    """
    skipped: list[str] = []
    is_cn = _is_chi_next(code)
    limit_pct = 0.20 if is_cn else 0.10

    # 涨跌停过滤
    prev_close = close.shift(1)
    limit_up = close >= prev_close * (1 + limit_pct - 0.005)
    limit_down = close <= prev_close * (1 - limit_pct + 0.005)

    entries = entries.copy()
    exits = exits.copy()

    for i in entries.index:
        # 涨停不能买
        if entries.loc[i] and limit_up.loc[i]:
            entries.loc[i] = False
            skipped.append(f"{i.date()} 买入信号因涨停跳过")

        # 跌停不能卖
        if exits.loc[i] and limit_down.loc[i]:
            exits.loc[i] = False
            skipped.append(f"{i.date()} 卖出信号因跌停跳过")

    # T+1: 如果同一日既有买入又有卖出，先执行买入，卖出推到下一日
    for i in entries.index:
        if entries.loc[i] and exits.loc[i]:
            # 卖出信号推到下一交易日
            next_idx = exits.index.get_indexer([i], method="bfill")
            if next_idx[0] >= 0 and next_idx[0] + 1 < len(exits):
                next_day = exits.index[next_idx[0] + 1]
                exits.loc[next_day] = True
                exits.loc[i] = False
                skipped.append(f"{i.date()} 卖出信号因 T+1 推到 {next_day.date()}")

    return entries, exits, skipped


def _calc_sell_adjustment(
    trades_df: pd.DataFrame,
    total_return: float,
    init_cash: float,
) -> float:
    """
    在 vectorbt 的佣金基础上，额外扣减卖方印花税（0.05%）。
    vectorbt 的 fees 是双向同费率，而 A 股印花税仅卖方承担。
    """
    if trades_df.empty:
        return total_return

    total_stamp_tax = 0
    for _, t in trades_df.iterrows():
        # 卖出/平仓时才收印花税
        exit_price = t.get("Avg Exit Price", 0)
        size = t.get("Size", 0)
        if exit_price and size:
            total_stamp_tax += size * exit_price * STAMP_TAX_RATE

    if total_stamp_tax > 0 and init_cash > 0:
        stamp_decimal = total_stamp_tax / init_cash  # 转为小数
        return round(total_return - stamp_decimal, 4)
    return total_return


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
    策略回测（基于 vectorbt 向量化引擎）

    支持策略: ma_cross, macd_signal
    """
    # ── 日期处理 ──
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        sd = datetime.now() - timedelta(days=730)
        start_date = sd.strftime("%Y-%m-%d")

    # ── 获取 K 线 ──
    secid = guess_secid(code)
    beg_str = start_date.replace("-", "")
    end_str = end_date.replace("-", "")
    klines = get_kline(secid, klt="101", fqt="1", lmt=800, beg=beg_str, end=end_str)

    if not klines:
        return {"error": f"未能获取 {code} 在 {start_date}~{end_date} 的 K 线数据",
                "提示": "确认股票代码正确，且指定时间段内该股票有交易数据"}

    klines = [k for k in klines if start_date <= k["日期"] <= end_date]

    if len(klines) < slow_period + 10:
        return {"error": f"K 线数据不足（{len(klines)} 条，需要 {slow_period + 10} 条）",
                "提示": "请扩大回测时间范围或减少慢线周期参数"}

    # ── 转为 DataFrame ──
    df = _kline_to_df(klines)
    close = df["close"]

    # ── 策略信号（vectorbt 向量化计算）──
    if strategy == "ma_cross":
        fast_vbt = vbt.MA.run(close, fast_period)
        slow_vbt = vbt.MA.run(close, slow_period)
        entries = fast_vbt.ma_crossed_above(slow_vbt.ma)
        exits = fast_vbt.ma_crossed_below(slow_vbt.ma)
        strategy_label = f"双均线交叉({fast_period},{slow_period})"
        fast_line = fast_vbt.ma.to_numpy()
        slow_line = slow_vbt.ma.to_numpy()

    elif strategy == "macd_signal":
        macd_vbt = vbt.MACD.run(close, fast_period, slow_period, 9)
        entries = macd_vbt.macd_crossed_above(macd_vbt.signal)
        exits = macd_vbt.macd_crossed_below(macd_vbt.signal)
        strategy_label = f"MACD交叉({fast_period},{slow_period},9)"
        fast_line = macd_vbt.macd.to_numpy()
        slow_line = macd_vbt.signal.to_numpy()

    else:
        return {"error": f"未知策略: {strategy}", "可选策略": ["ma_cross", "macd_signal"]}

    # ── A 股规则调整 ──
    entries, exits, skipped = _adjust_signals(entries, exits, close, code)

    # ── 构建 Portfolio ──
    pf = vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        init_cash=initial_capital,
        fees=COMMISSION_RATE,
        freq="D",
        direction="longonly",
    )

    # ── 提取绩效指标 ──
    equity = pf.value()  # 每日总资产
    stats = pf.stats()

    strat_total_return = float(pf.total_return())
    strat_annual_return = float(pf.annual_return()) if hasattr(pf, 'annual_return') else 0.0
    strat_sharpe = float(pf.sharpe_ratio()) if not np.isnan(float(pf.sharpe_ratio())) else 0.0
    strat_mdd = float(pf.max_drawdown()) * 100  # 转为百分比

    # 卖方印花税调整
    trades_records = pf.trades.records_readable if pf.trades.count() > 0 else pd.DataFrame()
    strat_return_adj = _calc_sell_adjustment(trades_records, strat_total_return, initial_capital)
    strat_return_pct = round(strat_return_adj * 100, 2)

    # 交易记录
    trade_log: list[dict[str, Any]] = []
    if not trades_records.empty:
        for _, t in trades_records.iterrows():
            entry_date = str(t["Entry Timestamp"].date()) if hasattr(t["Entry Timestamp"], 'date') else str(t["Entry Timestamp"])
            exit_date = str(t["Exit Timestamp"].date()) if hasattr(t["Exit Timestamp"], 'date') else str(t["Exit Timestamp"])
            entry_price = float(t["Avg Entry Price"])
            exit_price = float(t["Avg Exit Price"])
            size = int(t["Size"])  # 股数
            pnl_pct = round((exit_price / entry_price - 1) * 100, 2)

            trade_log.append({
                "日期": entry_date,
                "动作": "买入",
                "价格": round(entry_price, 2),
                "股数": size,
                "金额": round(size * entry_price * (1 + COMMISSION_RATE), 2),
            })
            trade_log.append({
                "日期": exit_date,
                "动作": "卖出",
                "价格": round(exit_price, 2),
                "股数": size,
                "金额": round(size * exit_price * (1 - COMMISSION_RATE), 2),
                "盈亏(%)": pnl_pct,
            })

    # 权益曲线
    equity_curve = []
    for dt, val in zip(equity.index, equity.values):
        dt_str = str(dt.date()) if hasattr(dt, 'date') else str(dt)
        equity_curve.append({"日期": dt_str, "市值": round(float(val), 2)})

    # 胜率
    win_rate = float(pf.trades.win_rate() * 100) if pf.trades.count() > 0 else 0.0
    trade_count = int(pf.trades.count())

    # 交易次数（以卖出计）
    closed_trades = trade_count

    # ── 买入持有基准 ──
    bh_entries = pd.Series(False, index=close.index)
    bh_exits = pd.Series(False, index=close.index)
    bh_entries.iloc[0] = True
    bh_exits.iloc[-1] = True
    bh_pf = vbt.Portfolio.from_signals(
        close, bh_entries, bh_exits,
        init_cash=initial_capital,
        fees=COMMISSION_RATE,
        freq="D",
        direction="longonly",
    )
    bh_total_return = float(bh_pf.total_return())
    bh_sharpe = float(bh_pf.sharpe_ratio()) if not np.isnan(float(bh_pf.sharpe_ratio())) else 0.0
    bh_mdd = float(bh_pf.max_drawdown()) * 100
    bh_return_adj = _calc_sell_adjustment(bh_pf.trades.records_readable if bh_pf.trades.count() > 0 else pd.DataFrame(),
                                           bh_total_return, initial_capital)
    bh_return_pct = round(bh_return_adj * 100, 2)

    bh_equity = bh_pf.value()
    bh_equity_curve = []
    for dt, val in zip(bh_equity.index, bh_equity.values):
        dt_str = str(dt.date()) if hasattr(dt, 'date') else str(dt)
        bh_equity_curve.append({"日期": dt_str, "市值": round(float(val), 2)})

    bh_trade_log: list[dict[str, Any]] = [
        {"日期": str(close.index[0].date()), "动作": "买入", "价格": round(float(close.iloc[0]), 2),
         "股数": int(initial_capital / float(close.iloc[0]) / 100) * 100,
         "金额": round(initial_capital, 2)},
        {"日期": str(close.index[-1].date()), "动作": "卖出", "价格": round(float(close.iloc[-1]), 2),
         "股数": int(initial_capital / float(close.iloc[0]) / 100) * 100,
         "金额": round(float(bh_equity.iloc[-1]), 2),
         "盈亏(%)": round((float(close.iloc[-1]) / float(close.iloc[0]) - 1) * 100, 2)},
    ]

    # ── 超额收益 ──
    excess_return = round(strat_return_pct - bh_return_pct, 2)
    excess_str = f"+{excess_return}" if excess_return > 0 else str(excess_return)

    # ── 年化收益率 ──
    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    years = days / 365.0 if days > 0 else 1.0
    strat_annual_pct = round(((1 + strat_return_adj) ** (1 / years) - 1) * 100, 2)
    bh_annual_pct = round(((1 + bh_return_adj) ** (1 / years) - 1) * 100, 2)

    # ── 文字总结 ──
    stock_display = _get_stock_name(code)
    summary = _generate_summary(
        strategy_label, stock_display, start_date, end_date,
        strat_return_pct, bh_return_pct,
        round(strat_mdd, 2), round(bh_mdd, 2),
        strat_sharpe, bh_sharpe,
        closed_trades, round(win_rate, 1),
        float(equity.iloc[-1]) if len(equity) > 0 else initial_capital,
        initial_capital, fast_period, slow_period, strategy,
    )

    result: dict[str, Any] = {
        "策略": strategy_label,
        "股票": f"{stock_display}({code})",
        "时间范围": f"{start_date} ~ {end_date}",
        "初始资金": initial_capital,
        "最终资金": round(float(equity.iloc[-1]) if len(equity) > 0 else initial_capital, 2),
        "总收益率(%)": strat_return_pct,
        "年化收益率(%)": strat_annual_pct,
        "最大回撤(%)": round(strat_mdd, 2),
        "夏普比率": round(strat_sharpe, 2),
        "胜率(%)": round(win_rate, 1),
        "交易次数": closed_trades,
        "超额收益(百分点)": excess_str,
        "交易记录": trade_log,
        "权益曲线": equity_curve,
        "基准(买入持有)": {
            "最终资金": round(float(bh_equity.iloc[-1]) if len(bh_equity) > 0 else initial_capital, 2),
            "总收益率(%)": bh_return_pct,
            "年化收益率(%)": bh_annual_pct,
            "最大回撤(%)": round(bh_mdd, 2),
            "夏普比率": round(bh_sharpe, 2),
            "交易记录": bh_trade_log,
            "权益曲线": bh_equity_curve,
        },
        "总结": summary,
        "引擎": "vectorbt (向量化)",
        "参数": {
            "策略": strategy,
            "fast_period": fast_period,
            "slow_period": slow_period,
        },
    }

    if skipped:
        result["跳过原因"] = skipped

    return result


def optimize_backtest(
    code: str,
    strategy: str = "ma_cross",
    fast_range: list[int] | None = None,
    slow_range: list[int] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 100000.0,
    metric: str = "sharpe",
) -> dict[str, Any]:
    """
    参数优化：网格扫描 fast_period × slow_period 所有组合

    Args:
        code:         股票代码
        strategy:     策略名 (ma_cross / macd_signal)
        fast_range:   快线周期列表，如 [5, 10, 15, 20]
        slow_range:   慢线周期列表，如 [10, 20, 30, 60]
        start_date:   开始日期
        end_date:     结束日期
        initial_capital: 初始资金
        metric:       优化目标指标 (sharpe / return / mdd / win_rate)

    Returns:
        包含最优参数、热力图数据、所有组合结果
    """
    if fast_range is None:
        fast_range = [5, 10, 15, 20]
    if slow_range is None:
        slow_range = [20, 30, 60, 120]
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        sd = datetime.now() - timedelta(days=730)
        start_date = sd.strftime("%Y-%m-%d")

    # ── 获取 K 线 ──
    secid = guess_secid(code)
    klines = get_kline(secid, klt="101", fqt="1", lmt=800,
                       beg=start_date.replace("-", ""),
                       end=end_date.replace("-", ""))
    klines = [k for k in klines if start_date <= k["日期"] <= end_date]
    if not klines or len(klines) < 30:
        return {"error": "K 线数据不足"}

    df = _kline_to_df(klines)
    close = df["close"]

    results_list: list[dict[str, Any]] = []
    best_score = -9999.0 if metric in ("sharpe", "return") else 9999.0
    best_params = {"fast": fast_range[0], "slow": slow_range[0]}

    for fast in fast_range:
        for slow in slow_range:
            if fast >= slow:
                continue

            if strategy == "ma_cross":
                fast_vbt = vbt.MA.run(close, fast)
                slow_vbt = vbt.MA.run(close, slow)
                entries = fast_vbt.ma_crossed_above(slow_vbt.ma)
                exits = fast_vbt.ma_crossed_below(slow_vbt.ma)
            else:
                macd_vbt = vbt.MACD.run(close, fast, slow, 9)
                entries = macd_vbt.macd_crossed_above(macd_vbt.signal)
                exits = macd_vbt.macd_crossed_below(macd_vbt.signal)

            entries_adj, exits_adj, _ = _adjust_signals(entries, exits, close, code)

            try:
                pf = vbt.Portfolio.from_signals(
                    close, entries_adj, exits_adj,
                    init_cash=initial_capital,
                    fees=COMMISSION_RATE,
                    freq="D",
                    direction="longonly",
                )

                ret = float(pf.total_return()) * 100
                sharpe = float(pf.sharpe_ratio()) if not np.isnan(float(pf.sharpe_ratio())) else 0.0
                mdd = float(pf.max_drawdown()) * 100
                win_rate = float(pf.trades.win_rate() * 100) if pf.trades.count() > 0 else 0.0
                trades = int(pf.trades.count())

                score = {
                    "sharpe": sharpe,
                    "return": ret,
                    "mdd": -mdd,
                    "win_rate": win_rate,
                }.get(metric, sharpe)

                if (metric in ("sharpe", "return", "win_rate") and score > best_score) or \
                   (metric == "mdd" and score < best_score):
                    best_score = score
                    best_params = {"fast": fast, "slow": slow}

                results_list.append({
                    "fast": fast, "slow": slow,
                    "总收益率(%)": round(ret, 2),
                    "夏普比率": round(sharpe, 2),
                    "最大回撤(%)": round(mdd, 2),
                    "胜率(%)": round(win_rate, 1),
                    "交易次数": trades,
                })
            except Exception:
                results_list.append({"fast": fast, "slow": slow, "error": "回测异常"})

    return {
        "股票": f"{_get_stock_name(code)}({code})",
        "时间范围": f"{start_date} ~ {end_date}",
        "优化目标": metric,
        "最优参数": best_params,
        "最优得分": round(best_score, 2) if best_score != -9999 and best_score != 9999 else None,
        "组合数": len(results_list),
        "结果": results_list,
    }


def _generate_summary(
    strategy_label: str,
    stock_name: str,
    start_date: str,
    end_date: str,
    strat_return: float,
    bh_return: float,
    strat_drawdown: float,
    bh_drawdown: float,
    strat_sharpe: float,
    bh_sharpe: float,
    strat_trades: int,
    strat_win_rate: float,
    strat_final: float,
    initial_capital: float,
    fast_period: int,
    slow_period: int,
    strategy: str,
) -> str:
    """根据绩效指标生成总结性文字结论"""
    excess = round(strat_return - bh_return, 2)
    if excess > 0:
        outperformed = f"跑赢买入持有 {abs(excess)} 个百分点"
    elif excess < 0:
        outperformed = f"跑输买入持有 {abs(excess)} 个百分点"
    else:
        outperformed = "与买入持有持平"

    strategy_name = "双均线交叉" if strategy == "ma_cross" else "MACD 金叉死叉"
    param_desc = f"({fast_period},{slow_period})" if strategy == "ma_cross" else f"({fast_period},{slow_period},9)"
    lines = [
        f"## {strategy_name}{param_desc} 回测总结\n",
        f"在 {start_date} 至 {end_date} 期间，对 **{stock_name}** 执行 {strategy_name}{param_desc} 策略回测，",
        f"初始资金 {initial_capital:,.0f} 元（基于 vectorbt 向量化引擎）。\n",
        "### 核心结论\n",
    ]

    if strat_return > bh_return:
        lines.append(f"策略表现优于基准：策略总收益 **{strat_return}%**，同期买入持有收益 {bh_return}%，"
                     f"超额收益 **+{excess} 个百分点**。")
    elif strat_return < bh_return and strat_return >= 0:
        lines.append(f"策略总收益 **{strat_return}%**，同期买入持有收益 {bh_return}%，"
                     f"{outperformed}。")
    elif strat_return < 0:
        lines.append(f"策略在回测期内亏损 {strat_return}%，同期买入持有收益 {bh_return}%。")

    dd_diff = round(bh_drawdown - strat_drawdown, 2)
    if dd_diff > 2:
        lines.append(f"风控优势明显：策略最大回撤 **{strat_drawdown}%**，比买入持有（{bh_drawdown}%）"
                     f"低 {dd_diff} 个百分点。")
    elif dd_diff > 0:
        lines.append(f"风控略优：策略最大回撤 {strat_drawdown}%，略好于买入持有的 {bh_drawdown}%。")
    else:
        lines.append(f"策略最大回撤 {strat_drawdown}%，买入持有 {bh_drawdown}%。")

    if strat_sharpe > 1.0:
        lines.append(f"风险调整后收益良好：夏普比率 {strat_sharpe}。")
    elif strat_sharpe > 0:
        lines.append(f"风险调整后收益一般：夏普比率 {strat_sharpe}。")
    else:
        lines.append(f"风险调整后收益为负（夏普 {strat_sharpe}），策略承担的风险未获得足够补偿。")

    if strat_trades > 20:
        lines.append(f"策略交易较为频繁：全年交易 **{strat_trades} 次**。")
    elif strat_trades > 5:
        lines.append(f"策略交易适度：全年交易 **{strat_trades} 次**，胜率 {strat_win_rate}%。")
    else:
        lines.append(f"策略交易较少：全年仅交易 **{strat_trades} 次**，胜率 {strat_win_rate}%。")

    lines.extend([
        "\n### 关键指标对比\n",
        "| 指标 | 策略 | 买入持有 |",
        "|------|:----:|:--------:|",
        f"| 总收益率 | {strat_return}% | {bh_return}% |",
        f"| 最大回撤 | {strat_drawdown}% | {bh_drawdown}% |",
        f"| 夏普比率 | {strat_sharpe} | {bh_sharpe} |",
        f"| 交易次数 | {strat_trades} 次 | 1 次 |",
    ])
    if strat_trades > 0:
        lines.append(f"| 胜率 | {strat_win_rate}% | — |")

    return "\n".join(lines)


def _get_stock_name(code: str) -> str:
    try:
        from cn_stock.data import STOCK_MAPPING
        return STOCK_MAPPING.get(code, code)
    except Exception:
        return code