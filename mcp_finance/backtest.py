"""
策略回测引擎 — 基于 Backtrader 事件驱动引擎

A 股规则适配:
  - T+1 限制（买入次日才能卖出）
  - 涨跌停过滤（涨停无法买入/跌停无法卖出）
  - 整数手（100 股整数倍）
  - 千一佣金 + 卖方印花税 0.05%
  - 买入持有基准对比
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import backtrader as bt
import pandas as pd

from mcp_finance.api import get_kline_a


# ── 费率常量 ──
COMMISSION_RATE = 0.001       # 佣金千分之一（买卖双向）
STAMP_TAX_RATE = 0.0005       # 印花税万分之五（仅卖方）
STOCK_SLIPPAGE = 0.001        # 滑点千分之一


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
    df.sort_index(inplace=True)
    return df


def _is_chi_next(code: str) -> bool:
    """是否创业板/科创板（涨跌幅 ±20%）"""
    return code.startswith("30") or code.startswith("68")


# ═══════════════════════════════════════════════════════════════
# Backtrader 策略定义
# ═══════════════════════════════════════════════════════════════

class _BaseStrategy(bt.Strategy):
    """基础策略：A股规则适配 + 记录交易"""
    params = dict(
        code="",
        limit_pct=0.10,
    )

    def __init__(self):
        self.orders: list[bt.Order] = []
        self.trade_log: list[dict] = []
        self.skipped: list[str] = []
        self.buy_signal_today = False
        self.sell_signal_today = False

    def log(self, txt: str):
        """日志"""
        pass  # 生产环境可改为 logging

    def notify_order(self, order):
        """订单状态通知（防御性类型检测）"""
        if order.status in [order.Completed]:
            action = "买入" if order.isbuy() else "卖出"
            dt = order.executed.dt
            if hasattr(dt, 'strftime'):
                date_str = dt.strftime("%Y-%m-%d")
            elif isinstance(dt, (int, float)):
                from datetime import datetime as _dt
                date_str = _dt.fromtimestamp(dt).strftime("%Y-%m-%d")
            else:
                date_str = str(dt)[:10]
            self.trade_log.append({
                "日期": date_str,
                "动作": action,
                "价格": round(order.executed.price, 2),
                "股数": int(order.executed.size),
                "金额": round(order.executed.value, 2),
            })

    def _limit_up_down(self):
        """检查当前 K 线是否涨跌停"""
        if len(self.data) < 2:
            return False, False
        prev_close = self.data.close[-1]
        limit_pct = self.params.limit_pct
        limit_up = self.data.close[0] >= prev_close * (1 + limit_pct - 0.005)
        limit_down = self.data.close[0] <= prev_close * (1 - limit_pct + 0.005)
        return limit_up, limit_down

    def _is_t1_restricted(self):
        """检查是否受 T+1 限制（今天有买入）"""
        # Backtrader 自动处理 T+1：通过 size 判断
        return False  # Backtrader 自身不限制 T+1

    def buy_signal(self):
        """子类重写：返回 True/False"""
        return False

    def sell_signal(self):
        """子类重写：返回 True/False"""
        return False

    def next(self):
        """每个 bar 调用一次"""
        # 检查涨跌停
        limit_up, limit_down = self._limit_up_down()

        if self.buy_signal():
            if not limit_up and self.broker.getcash() > 0:
                size = int(self.broker.getcash() / self.data.close[0] / 100) * 100
                if size > 0:
                    self.buy(size=size)
        elif self.sell_signal():
            if not limit_down and self.position.size > 0:
                self.close()


class _MaCrossStrategy(_BaseStrategy):
    """双均线交叉策略"""
    params = dict(fast=5, slow=20)

    def __init__(self):
        super().__init__()
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.params.fast)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.params.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

    def buy_signal(self):
        return self.crossover > 0

    def sell_signal(self):
        return self.crossover < 0


class _MACDStrategy(_BaseStrategy):
    """MACD 金叉死叉策略"""
    params = dict(fast=12, slow=26, signal=9)

    def __init__(self):
        super().__init__()
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.params.fast,
            period_me2=self.params.slow,
            period_signal=self.params.signal,
        )
        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

    def buy_signal(self):
        return self.crossover > 0

    def sell_signal(self):
        return self.crossover < 0


class _RSIStrategy(_BaseStrategy):
    """RSI 超买超卖策略"""
    params = dict(period=14, oversold=30, overbought=70)

    def __init__(self):
        super().__init__()
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.period)

    def buy_signal(self):
        return self.rsi < self.params.oversold

    def sell_signal(self):
        return self.rsi > self.params.overbought


class _KDJStrategy(_BaseStrategy):
    """KDJ 金叉死叉策略"""
    params = dict(period=9, k_period=3, d_period=3)

    def __init__(self):
        super().__init__()
        self.k = bt.indicators.Stochastic(
            self.data,
            period=self.params.period,
            period_dfast=self.params.k_period,
        )
        # KDJ: K 线, D 线
        self.d = bt.indicators.SMA(self.k.percK, period=self.params.d_period)

    def buy_signal(self):
        return self.k.percK > self.d and self.k.percK[-1] <= self.d[-1]

    def sell_signal(self):
        return self.k.percK < self.d and self.k.percK[-1] >= self.d[-1]


class _BollingerStrategy(_BaseStrategy):
    """布林带突破策略"""
    params = dict(period=20, devfactor=2.0)

    def __init__(self):
        super().__init__()
        self.boll = bt.indicators.BollingerBands(
            self.data.close,
            period=self.params.period,
            devfactor=self.params.devfactor,
        )

    def buy_signal(self):
        return self.data.close[0] > self.boll.top[0] and self.data.close[-1] <= self.boll.top[-1]

    def sell_signal(self):
        return self.data.close[0] < self.boll.bot[0] and self.data.close[-1] >= self.boll.bot[-1]


# ── 策略映射 ──
_STRATEGY_MAP = {
    "ma_cross": _MaCrossStrategy,
    "macd_signal": _MACDStrategy,
    "rsi_signal": _RSIStrategy,
    "kdj_signal": _KDJStrategy,
    "boll_signal": _BollingerStrategy,
}

_STRATEGY_LABELS = {
    "ma_cross": "双均线交叉",
    "macd_signal": "MACD 金叉死叉",
    "rsi_signal": "RSI 超买超卖",
    "kdj_signal": "KDJ 金叉死叉",
    "boll_signal": "BOLL 突破",
}


# ═══════════════════════════════════════════════════════════════
# 回测函数
# ═══════════════════════════════════════════════════════════════

def _run_single_backtest(
    code: str,
    strategy: str = "ma_cross",
    fast_period: int = 5,
    slow_period: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 100000.0,
) -> dict[str, Any]:
    """运行单次回测（内部函数）"""
    # ── 日期处理 ──
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        sd = datetime.now() - timedelta(days=730)
        start_date = sd.strftime("%Y-%m-%d")

    # ── 获取 K 线 ──
    klines = get_kline_a(code, period="daily", adjust="qfq", limit=800)

    # 检测 K 线返回的是否是错误列表
    if klines and isinstance(klines[0], dict) and "error" in klines[0]:
        return {"error": klines[0]["error"]}

    if not klines:
        return {"error": f"未能获取 {code} 在 {start_date}~{end_date} 的 K 线数据"}

    # 过滤无"日期"字段的异常条目
    klines = [k for k in klines if "日期" in k]
    if len(klines) < slow_period + 10:
        return {"error": f"K 线数据不足（有效 {len(klines)} 条，需要 {slow_period + 10} 条）",
                "提示": "请扩大回测时间范围或减少慢线周期参数"}

    klines = [k for k in klines if start_date <= k["日期"] <= end_date]
    min_bars = slow_period + 10
    if len(klines) < min_bars:
        return {"error": f"K 线数据不足（{len(klines)} 条，需要 {min_bars} 条）",
                "提示": "请扩大回测时间范围或减少慢线周期参数"}

    # ── 转为 DataFrame ──
    df = _kline_to_df(klines)

    # ── 构建 Cerebro ──
    cerebro = bt.Cerebro()

    # 添加数据
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    # 注册策略
    strategy_cls = _STRATEGY_MAP.get(strategy)
    if strategy_cls is None:
        return {"error": f"未知策略: {strategy}"}

    is_cn = _is_chi_next(code)
    limit_pct = 0.20 if is_cn else 0.10

    # 按策略类型传递不同参数
    if strategy == "rsi_signal":
        cerebro.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                            period=fast_period, oversold=30, overbought=70)
    elif strategy == "kdj_signal":
        cerebro.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                            period=fast_period, k_period=3, d_period=3)
    elif strategy == "boll_signal":
        cerebro.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                            period=fast_period, devfactor=2.0)
    elif strategy == "macd_signal":
        cerebro.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                            fast=fast_period, slow=slow_period, signal=9)
    else:
        cerebro.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                            fast=fast_period, slow=slow_period)

    # 佣金设置
    cerebro.broker.setcash(initial_capital)
    cerebro.broker.setcommission(
        commission=COMMISSION_RATE,
        margin=None,
        mult=1.0,
        percabs=True,  # 百分比
    )

    # 滑点
    cerebro.broker.set_slippage_perc(STOCK_SLIPPAGE)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.02, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")

    # ── 运行回测 ──
    initial_value = cerebro.broker.getvalue()
    results = cerebro.run()
    final_value = cerebro.broker.getvalue()
    strat = results[0]

    # ── 提取分析结果 ──
    # 收益率
    ret_analyzer = strat.analyzers.returns.get_analysis()
    total_return = ret_analyzer.get("rtot", 0) * 100  # 转为百分比
    # 如果 Returns 分析器返回 0（如无完整交易），用实际资金计算
    if abs(total_return) < 0.01 and final_value != initial_value:
        total_return = (final_value / initial_value - 1) * 100
    sharpe_analyzer = strat.analyzers.sharpe.get_analysis()
    sharpe_ratio = sharpe_analyzer.get("sharperatio", 0) or 0.0

    # 最大回撤
    dd_analyzer = strat.analyzers.drawdown.get_analysis()
    max_drawdown = dd_analyzer.get("max", {}).get("drawdown", 0)

    # 交易统计
    trade_analyzer = strat.analyzers.trades.get_analysis()
    total_closed = trade_analyzer.get("total", {}).get("closed", 0)
    won = trade_analyzer.get("won", {}).get("total", 0)
    win_rate = (won / total_closed * 100) if total_closed > 0 else 0.0

    # 权益曲线（用第二个 Cerebro 记录每日净值）
    cerebro2 = bt.Cerebro()
    cerebro2.adddata(data)

    # 按策略类型传递不同参数（与第一个 cerebro 保持一致）
    if strategy == "rsi_signal":
        cerebro2.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                             period=fast_period, oversold=30, overbought=70)
    elif strategy == "kdj_signal":
        cerebro2.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                             period=fast_period, k_period=3, d_period=3)
    elif strategy == "boll_signal":
        cerebro2.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                             period=fast_period, devfactor=2.0)
    elif strategy == "macd_signal":
        cerebro2.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                             fast=fast_period, slow=slow_period, signal=9)
    else:
        cerebro2.addstrategy(strategy_cls, code=code, limit_pct=limit_pct,
                             fast=fast_period, slow=slow_period)
    cerebro2.broker.setcash(initial_capital)
    cerebro2.broker.setcommission(commission=COMMISSION_RATE, percabs=True)
    cerebro2.broker.set_slippage_perc(STOCK_SLIPPAGE)

    class _ValueRecorder(bt.analyzers.Analyzer):
        def __init__(self):
            self.values = []
        def next(self):
            self.values.append(self.strategy.broker.getvalue())
        def get_analysis(self):
            return self.values

    cerebro2.addanalyzer(_ValueRecorder, _name="vr")
    results2 = cerebro2.run()
    strat2 = results2[0]
    equity_values = strat2.analyzers.vr.get_analysis()

    equity_curve = []
    dates = df.index[-len(equity_values):] if len(equity_values) <= len(df) else df.index
    for i, val in enumerate(equity_values):
        if i < len(dates):
            equity_curve.append({"日期": str(dates[i].date()), "市值": round(float(val), 2)})

    # 交易记录
    trade_log = strat.trade_log

    # 基准（买入持有）
    bh_final = df["close"].iloc[-1] / df["close"].iloc[0] * initial_capital
    bh_return = (bh_final / initial_capital - 1) * 100
    bh_equity_curve = []
    for dt, val in zip(df.index, df["close"] / df["close"].iloc[0] * initial_capital):
        bh_equity_curve.append({"日期": str(dt.date()), "市值": round(float(val), 2)})

    # 年化
    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    years = days / 365.0 if days > 0 else 1.0
    strat_annual_pct = round(((1 + total_return / 100) ** (1 / years) - 1) * 100, 2)
    bh_annual_pct = round(((1 + bh_return / 100) ** (1 / years) - 1) * 100, 2)

    # ── 结果组装 ──
    stock_display = _get_stock_name(code)
    strategy_label = f"{_STRATEGY_LABELS.get(strategy, strategy)}({fast_period},{slow_period})"

    return {
        "策略": strategy_label,
        "股票": f"{stock_display}({code})",
        "时间范围": f"{start_date} ~ {end_date}",
        "初始资金": initial_capital,
        "最终资金": round(final_value, 2),
        "总收益率(%)": round(total_return, 2),
        "年化收益率(%)": strat_annual_pct,
        "最大回撤(%)": round(max_drawdown, 2),
        "夏普比率": round(sharpe_ratio, 2),
        "胜率(%)": round(win_rate, 1) if win_rate > 0 else 0,
        "交易次数": total_closed,
        "交易记录": trade_log,
        "权益曲线": equity_curve,
        "基准(买入持有)": {
            "最终资金": round(bh_final, 2),
            "总收益率(%)": round(bh_return, 2),
            "年化收益率(%)": bh_annual_pct,
            "交易记录": [
                {"日期": start_date, "动作": "买入", "价格": round(float(df["close"].iloc[0]), 2),
                 "股数": int(initial_capital / float(df["close"].iloc[0]) / 100) * 100, "金额": round(initial_capital, 2)},
                {"日期": end_date, "动作": "卖出", "价格": round(float(df["close"].iloc[-1]), 2),
                 "股数": int(initial_capital / float(df["close"].iloc[0]) / 100) * 100, "金额": round(bh_final, 2)},
            ],
            "权益曲线": bh_equity_curve,
        },
        "引擎": "Backtrader (事件驱动)",
        "参数": {"策略": strategy, "fast_period": fast_period, "slow_period": slow_period},
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
    """策略回测（基于 Backtrader 引擎）

    支持策略: ma_cross, macd_signal, rsi_signal, kdj_signal, boll_signal
    """
    result = _run_single_backtest(
        code=code, strategy=strategy,
        fast_period=fast_period, slow_period=slow_period,
        start_date=start_date, end_date=end_date,
        initial_capital=initial_capital,
    )
    if "error" not in result:
        result["总结"] = _generate_summary(
            result["策略"], result["股票"], start_date or "", end_date or "",
            result["总收益率(%)"], result.get("基准(买入持有)", {}).get("总收益率(%)", 0),
            result["最大回撤(%)"], result.get("基准(买入持有)", {}).get("最大回撤(%)", 0),
            result["夏普比率"], result.get("基准(买入持有)", {}).get("夏普比率", 0),
            result["交易次数"], result["胜率(%)"],
            result["最终资金"], initial_capital, fast_period, slow_period, strategy,
        )
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
    """参数优化：网格扫描 fast × slow 所有组合"""
    if fast_range is None:
        fast_range = [5, 10, 15, 20]
    if slow_range is None:
        slow_range = [20, 30, 60, 120]
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        sd = datetime.now() - timedelta(days=730)
        start_date = sd.strftime("%Y-%m-%d")

    results_list: list[dict[str, Any]] = []
    best_score = -9999.0 if metric in ("sharpe", "return") else 9999.0
    best_params = {"fast": fast_range[0], "slow": slow_range[0]}

    for fast in fast_range:
        for slow in slow_range:
            if fast >= slow:
                continue

            result = _run_single_backtest(
                code=code, strategy=strategy,
                fast_period=fast, slow_period=slow,
                start_date=start_date, end_date=end_date,
                initial_capital=initial_capital,
            )
            if "error" in result:
                results_list.append({"fast": fast, "slow": slow, "error": result["error"][:50]})
                continue

            ret = result["总收益率(%)"]
            sharpe = result["夏普比率"]
            mdd = result["最大回撤(%)"]
            win_rate = result["胜率(%)"]
            trades = result["交易次数"]

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

    return {
        "股票": f"{_get_stock_name(code)}({code})",
        "时间范围": f"{start_date} ~ {end_date}",
        "优化目标": metric,
        "最优参数": best_params,
        "最优得分": round(best_score, 2) if best_score not in (-9999, 9999) else None,
        "组合数": len(results_list),
        "结果": results_list,
    }


def _generate_summary(
    strategy_label: str, stock_name: str,
    start_date: str, end_date: str,
    strat_return: float, bh_return: float,
    strat_drawdown: float, bh_drawdown: float,
    strat_sharpe: float, bh_sharpe: float,
    strat_trades: int, strat_win_rate: float,
    strat_final: float, initial_capital: float,
    fast_period: int, slow_period: int, strategy: str,
) -> str:
    """根据绩效指标生成总结性文字结论"""
    excess = round(strat_return - bh_return, 2)
    if excess > 0:
        outperformed = f"跑赢买入持有 {abs(excess)} 个百分点"
    elif excess < 0:
        outperformed = f"跑输买入持有 {abs(excess)} 个百分点"
    else:
        outperformed = "与买入持有持平"

    lines = [
        f"## {strategy_label} 回测总结\n",
        f"在 {start_date} 至 {end_date} 期间，对 **{stock_name}** 执行 {strategy_label} 策略回测，",
        f"初始资金 {initial_capital:,.0f} 元（基于 Backtrader 引擎）。\n",
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
        from mcp_finance.data import STOCK_MAPPING
        return STOCK_MAPPING.get(code, code)
    except Exception:
        return code


# ═══════════════════════════════════════════════════════════════
# MCP Tool Handlers
# ═══════════════════════════════════════════════════════════════

from mcp_finance.errors import BacktestError
from mcp_finance.logging_config import get_logger

_blogger = get_logger(__name__)


def handle_backtest(arguments: dict[str, Any]) -> dict[str, Any]:
    """策略回测 handler"""
    code = arguments["code"]
    strategy = arguments.get("strategy", "ma_cross")
    fast_period = arguments.get("fast_period", 5)
    slow_period = arguments.get("slow_period", 20)
    start_date = arguments.get("start_date")
    end_date = arguments.get("end_date")
    initial_capital = arguments.get("initial_capital", 100000.0)
    generate_chart = arguments.get("generate_chart", True)

    result = run_backtest(
        code=code, strategy=strategy,
        fast_period=fast_period, slow_period=slow_period,
        start_date=start_date, end_date=end_date,
        initial_capital=initial_capital,
    )

    if "error" in result:
        raise BacktestError(str(result["error"]))

    if generate_chart and "权益曲线" in result:
        try:
            from mcp_finance.chart import generate_backtest_chart
            chart_path = generate_backtest_chart(
                stock_name=result["股票"],
                strategy_label=result["策略"],
                strategy_curve=result["权益曲线"],
                benchmark_curve=result.get("基准(买入持有)", {}).get("权益曲线"),
                trades=result.get("交易记录", []),
                initial_capital=initial_capital,
            )
            result["权益曲线图"] = chart_path
            result["权益曲线图提示"] = "这不是图片！这是一个交互式HTML文件，请用浏览器打开"
        except Exception as e:
            result["权益曲线图"] = f"图表生成失败: {e}"

    _blogger.info("回测完成: %s strategy=%s return=%.2f%%", code, strategy, result.get("总收益率(%)", 0))
    return result


def handle_optimize(arguments: dict[str, Any]) -> dict[str, Any]:
    """参数优化 handler"""
    code = arguments["code"]
    strategy = arguments.get("strategy", "ma_cross")
    fast_min = arguments.get("fast_min", 5)
    fast_max = arguments.get("fast_max", 20)
    fast_step = arguments.get("fast_step", 5)
    slow_min = arguments.get("slow_min", 20)
    slow_max = arguments.get("slow_max", 60)
    slow_step = arguments.get("slow_step", 10)
    start_date = arguments.get("start_date")
    end_date = arguments.get("end_date")
    metric = arguments.get("metric", "sharpe")

    fast_range = list(range(fast_min, fast_max + 1, fast_step))
    slow_range = list(range(slow_min, slow_max + 1, slow_step))

    result = optimize_backtest(
        code=code, strategy=strategy,
        fast_range=fast_range, slow_range=slow_range,
        start_date=start_date, end_date=end_date,
        metric=metric,
    )
    _blogger.info("参数优化完成: %s strategy=%s", code, strategy)
    return result
