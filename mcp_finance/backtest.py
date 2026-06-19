"""策略回测引擎 v2 - Backtrader 事件驱动

A股规则: T+1限制 / 涨跌停过滤 / 万2.5佣金+印花税 / ATR仓位 / 沪深300基准
策略(8种): 双均线 MACD RSI KDJ BOLL + 海龟 波动率趋势 均值回归
风险指标: 夏普 索提诺 卡玛 年化波动率 最大连续亏损
"""

from __future__ import annotations
import math
from datetime import datetime, timedelta
from typing import Any
import backtrader as bt
import pandas as pd
import numpy as np
from mcp_finance.api import get_kline_a

# ============================================================================
# 费率常量
# ============================================================================
COMMISSION_RATE = 0.00025     # 佣金万2.5(买卖双向)
STAMP_TAX_RATE = 0.0005       # 印花税万分之五(仅卖方)
MIN_COMMISSION = 5.0          # 最低佣金5元
STOCK_SLIPPAGE = 0.001        # 滑点千分之一

# ============================================================================
# 自定义佣金方案(含印花税)
# ============================================================================
class _AStockCommission(bt.CommInfoBase):
    """A股佣金: 万2.5(最低5元) + 卖方千0.5印花税"""
    params = (
        ("commission", COMMISSION_RATE),
        ("stamp_tax", STAMP_TAX_RATE),
        ("min_commission", MIN_COMMISSION),
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
    )

    def _getcommission(self, size, price, pseudoexec):
        value = abs(size) * price
        comm = max(value * self.p.commission, self.p.min_commission)
        if size < 0:  # 卖出加印花税
            comm += value * self.p.stamp_tax
        return comm

# ============================================================================
# 工具函数
# ============================================================================
def _kline_to_df(klines: list[dict[str, Any]]) -> pd.DataFrame:
    """将API返回的K线数据转为pandas DataFrame"""
    records = []
    for k in klines:
        try:
            records.append({
                "date": k["日期"],
                "open": float(k["开盘价"]),
                "high": float(k["最高价"]),
                "low": float(k["最低价"]),
                "close": float(k["收盘价"]),
                "volume": float(k.get("成交量(手)", 0)),
            })
        except (KeyError, ValueError):
            continue
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)
    return df

def _is_chi_next(code: str) -> bool:
    """是否创业板/科创板(涨跌幅+-20%)"""
    return code.startswith("30") or code.startswith("68")

# ============================================================================
# Observer - 单次运行记录权益曲线(避免跑两次Cerebro)
# ============================================================================
class _EquityObserver(bt.observer.Observer):
    """每个bar记录当前市值+持仓"""
    lines = ("value", "position")
    plotinfo = dict(plot=False)

    def next(self):
        self.lines.value[0] = self._owner.broker.getvalue()
        self.lines.position[0] = self._owner.position.size if hasattr(self._owner, "position") else 0

# ============================================================================
# 基础策略 - T+1 + 涨跌停 + ATR仓位 + 信号跳过日志
# ============================================================================
class _BaseStrategy(bt.Strategy):
    """A股回测基类: T+1、涨跌停过滤、ATR仓位管理"""
    params = dict(
        code="",
        limit_pct=0.10,
        risk_pct=1.0,
    )

    def __init__(self):
        self.orders = []
        self.trade_log: list[dict] = []
        self.skipped_signals: list[dict] = []
        self._bought_bar = -999  # T+1: 买入bar索引
        self._entry_price = 0.0
        self._trailing_stop = 0.0

    def notify_order(self, order):
        if order.status == order.Completed:
            action = "买入" if order.isbuy() else "卖出"
            dt = order.executed.dt
            if hasattr(dt, "strftime"):
                date_str = dt.strftime("%Y-%m-%d")
            elif isinstance(dt, (int, float)):
                date_str = datetime.fromtimestamp(dt).strftime("%Y-%m-%d")
            else:
                date_str = str(dt)[:10]
            self.trade_log.append({
                "日期": date_str,
                "动作": action,
                "价格": round(order.executed.price, 2),
                "股数": int(order.executed.size),
                "金额": round(order.executed.value, 2),
            })
            if order.isbuy():
                self._bought_bar = len(self.data)

    def _limit_up_down(self):
        """检查当前K线是否涨跌停"""
        if len(self.data) < 2:
            return False, False
        prev_close = self.data.close[-1]
        if prev_close <= 0:
            return False, False
        limit_pct = self.params.limit_pct
        limit_up = self.data.close[0] >= prev_close * (1 + limit_pct - 0.001)
        limit_down = self.data.close[0] <= prev_close * (1 - limit_pct + 0.001)
        return limit_up, limit_down

    def _is_t1_locked(self):
        """T+1限制: 买入当天不能卖出"""
        if self._bought_bar < 0:
            return False
        return len(self.data) == self._bought_bar

    def _calc_size(self, price: float, atr_val: float = 0) -> int:
        """计算买入股数(含ATR仓位管理)"""
        cash = self.broker.getcash()
        if cash <= 0:
            return 0
        if atr_val > 0 and price > 0:
            risk_amount = self.broker.getvalue() * 0.02
            size = int(risk_amount / atr_val / 100) * 100
            cash_size = int(cash * self.params.risk_pct / price / 100) * 100
            return min(size, cash_size)
        return int(cash * self.params.risk_pct / price / 100) * 100

    def _skip_reason(self, reason: str):
        """记录跳过原因"""
        dt = self.data.datetime.date(0)
        self.skipped_signals.append({
            "日期": dt.isoformat() if hasattr(dt, "isoformat") else str(dt),
            "原因": reason,
            "价格": round(float(self.data.close[0]), 2),
        })

    def buy_signal(self) -> bool:
        return False

    def sell_signal(self) -> bool:
        return False

    def next(self):
        limit_up, limit_down = self._limit_up_down()

        if self.buy_signal():
            if limit_up:
                self._skip_reason("涨停无法买入")
            elif self.broker.getcash() <= 0:
                pass
            else:
                price = self.data.close[0]
                atr = getattr(self, "atr", None)
                atr_val = atr[0] if atr is not None else 0
                size = self._calc_size(price, atr_val)
                if size > 0:
                    self.buy(size=size)

        elif self.sell_signal():
            if limit_down:
                self._skip_reason("跌停无法卖出")
            elif self._is_t1_locked():
                self._skip_reason("T+1限制(当日买入不可卖)")
            elif self.position.size > 0:
                self.close()

# ============================================================================
# 经典策略 (5种)
# ============================================================================

class _MaCrossStrategy(_BaseStrategy):
    """双均线交叉"""
    params = dict(fast=5, slow=20)
    def __init__(self):
        super().__init__()
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.params.fast)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.params.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
    def buy_signal(self): return self.crossover > 0
    def sell_signal(self): return self.crossover < 0

class _MACDStrategy(_BaseStrategy):
    """MACD金叉死叉"""
    params = dict(fast=12, slow=26, signal=9)
    def __init__(self):
        super().__init__()
        self.macd = bt.indicators.MACD(self.data.close, period_me1=self.params.fast, period_me2=self.params.slow, period_signal=getattr(self.params, "signal", 9))
        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
    def buy_signal(self): return self.crossover > 0
    def sell_signal(self): return self.crossover < 0

class _RSIStrategy(_BaseStrategy):
    """RSI超买超卖"""
    params = dict(fast=14, slow=0)
    def __init__(self):
        super().__init__()
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.fast)
    def buy_signal(self): return self.rsi < 30
    def sell_signal(self): return self.rsi > 70

class _KDJStrategy(_BaseStrategy):
    """KDJ金叉死叉(修正:直接用Stochastic的percK/percD)"""
    params = dict(fast=9, slow=0)
    def __init__(self):
        super().__init__()
        self.stoch = bt.indicators.Stochastic(self.data, period=self.params.fast, period_dfast=3)
        self.crossover = bt.indicators.CrossOver(self.stoch.percK, self.stoch.percD)
    def buy_signal(self): return self.crossover > 0
    def sell_signal(self): return self.crossover < 0

class _BollingerStrategy(_BaseStrategy):
    """BOLL突破策略"""
    params = dict(fast=20, slow=0)
    def __init__(self):
        super().__init__()
        self.boll = bt.indicators.BollingerBands(self.data.close, period=self.params.fast, devfactor=2.0)
    def buy_signal(self): return self.data.close[0] > self.boll.top[0] and self.data.close[-1] <= self.boll.top[-1]
    def sell_signal(self): return self.data.close[0] < self.boll.bot[0] and self.data.close[-1] >= self.boll.bot[-1]

# ============================================================================
# 进阶策略 (3种)
# ============================================================================

class _TurtleStrategy(_BaseStrategy):
    """海龟交易法则 - Donchian通道突破 + 2ATR跟踪止损"""
    params = dict(fast=20, slow=10)
    def __init__(self):
        super().__init__()
        entry = self.params.fast
        exit_p = self.params.slow
        self.don_high = bt.indicators.Highest(self.data.high, period=entry)
        self.don_low = bt.indicators.Lowest(self.data.low, period=entry)
        self.exit_high = bt.indicators.Highest(self.data.high, period=exit_p)
        self.exit_low = bt.indicators.Lowest(self.data.low, period=exit_p)
        self.atr = bt.indicators.ATR(self.data, period=20)
    def buy_signal(self): return self.data.close[0] > self.don_high[-1]
    def sell_signal(self):
        if self.position.size > 0:
            if self._entry_price > 0 and hasattr(self, "atr"):
                self._trailing_stop = max(self._trailing_stop, self.data.close[0] - 2 * self.atr[0])
            return (self.data.close[0] < self.exit_low[-1] or (self._trailing_stop > 0 and self.data.close[0] < self._trailing_stop))
        return False
    def notify_order(self, order):
        super().notify_order(order)
        if order.status == order.Completed and order.isbuy():
            self._entry_price = order.executed.price
            if hasattr(self, "atr"): self._trailing_stop = self._entry_price - 2 * self.atr[0]

class _VolTrendStrategy(_BaseStrategy):
    """波动率自适应趋势 - 双EMA + ATR趋势过滤 + 波动率仓位"""
    params = dict(fast=20, slow=50)
    def __init__(self):
        super().__init__()
        self.fast_ma = bt.indicators.EMA(self.data.close, period=self.params.fast)
        self.slow_ma = bt.indicators.EMA(self.data.close, period=self.params.slow)
        self.atr = bt.indicators.ATR(self.data, period=20)
        self.atr_sma = bt.indicators.SMA(self.atr, period=100)
    def buy_signal(self):
        trend_up = self.fast_ma[0] > self.slow_ma[0] and self.data.close[0] > self.fast_ma[0]
        vol_expand = self.atr_sma[0] > 0 and self.atr[0] / self.atr_sma[0] > 1.0
        return trend_up and vol_expand
    def sell_signal(self):
        return self.fast_ma[0] < self.slow_ma[0] or self.data.close[0] < self.slow_ma[0]

class _MeanRevStrategy(_BaseStrategy):
    """多条件均值回归 - BOLL下轨 + RSI超卖 + 放量确认"""
    params = dict(fast=20, slow=0)
    def __init__(self):
        super().__init__()
        period = self.params.fast
        self.boll = bt.indicators.BollingerBands(self.data.close, period=period, devfactor=2.0)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.vol_sma = bt.indicators.SMA(self.data.volume, period=20)
    def buy_signal(self):
        near_lower = self.data.close[0] <= self.boll.bot[0] * 1.02
        oversold = self.rsi[0] < 35
        vol_spike = self.vol_sma[0] > 0 and self.data.volume[0] / self.vol_sma[0] > 1.2
        return near_lower and oversold and vol_spike
    def sell_signal(self):
        return self.data.close[0] > self.boll.mid[0] or self.rsi[0] > 65

# ============================================================================
# 策略注册表
# ============================================================================
_STRATEGY_MAP = {
    "ma_cross": _MaCrossStrategy,
    "macd_signal": _MACDStrategy,
    "rsi_signal": _RSIStrategy,
    "kdj_signal": _KDJStrategy,
    "boll_signal": _BollingerStrategy,
    "turtle": _TurtleStrategy,
    "vol_trend": _VolTrendStrategy,
    "mean_rev": _MeanRevStrategy,
}

_STRATEGY_LABELS = {
    "ma_cross": "双均线交叉",
    "macd_signal": "MACD金叉死叉",
    "rsi_signal": "RSI超买超卖",
    "kdj_signal": "KDJ金叉死叉",
    "boll_signal": "BOLL突破",
    "turtle": "海龟交易",
    "vol_trend": "波动率趋势",
    "mean_rev": "均值回归",
}

# ============================================================================
# 核心回测函数
# ============================================================================

def _run_single_backtest(
    code: str, strategy: str = "ma_cross",
    fast_period: int = 5, slow_period: int = 20,
    start_date: str | None = None, end_date: str | None = None,
    initial_capital: float = 100000.0,
    benchmark_code: str | None = "000300",
) -> dict[str, Any]:
    """运行单次A股回测(一次Cerebro, Observer记录权益曲线)"""

    # 日期处理
    if end_date is None: end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    # 获取K线
    klines = get_kline_a(code, period="daily", adjust="qfq", limit=800)
    if klines and isinstance(klines[0], dict) and "error" in klines[0]:
        return {"error": klines[0]["error"]}
    if not klines: return {"error": f"获取{code} K线数据失败"}

    klines = [k for k in klines if "日期" in k]
    klines = [k for k in klines if start_date <= k["日期"] <= end_date]
    min_bars = max(slow_period, 20) + 10
    if len(klines) < min_bars:
        return {"error": f"K线数据不足({len(klines)}条,需{min_bars}条)", "提示": "扩大回测时间范围或减小周期参数"}

    df = _kline_to_df(klines)
    if df.empty: return {"error": "K线数据解析失败"}

    # 构建Cerebro
    cerebro = bt.Cerebro()
    cerebro.adddata(bt.feeds.PandasData(dataname=df))

    strategy_cls = _STRATEGY_MAP.get(strategy)
    if strategy_cls is None: return {"error": f"未知策略: {strategy}"}

    is_cn = _is_chi_next(code)
    limit_pct = 0.20 if is_cn else 0.10

    # 构建策略参数
    strat_kwargs = dict(code=code, limit_pct=limit_pct, fast=fast_period, slow=slow_period)
    if strategy == "macd_signal": strat_kwargs["signal"] = 9

    cerebro.addstrategy(strategy_cls, **strat_kwargs)

    # 资金+佣金(含印花税)+滑点
    cerebro.broker.setcash(initial_capital)
    cerebro.broker.addcommissioninfo(_AStockCommission())
    cerebro.broker.set_slippage_perc(STOCK_SLIPPAGE)

    # 分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.02, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
    cerebro.addanalyzer(_EquityRecorder, _name="equity")
    cerebro.addanalyzer(_AnnualVolatility, _name="ann_vol")

    # Observer
    cerebro.addobserver(_EquityObserver)

    # 运行
    initial_value = cerebro.broker.getvalue()
    results = cerebro.run()
    final_value = cerebro.broker.getvalue()
    strat = results[0]

    # 提取结果
    ret_analyzer = strat.analyzers.returns.get_analysis()
    total_return = ret_analyzer.get("rtot", 0) * 100
    if abs(total_return) < 0.01 and final_value != initial_value:
        total_return = (final_value / initial_value - 1) * 100

    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0) or 0.0
    dd = strat.analyzers.drawdown.get_analysis()
    max_drawdown = dd.get("max", {}).get("drawdown", 0)

    trade_analyzer = strat.analyzers.trades.get_analysis()
    total_closed = trade_analyzer.get("total", {}).get("closed", 0)
    won = trade_analyzer.get("won", {}).get("total", 0)
    win_rate = (won / total_closed * 100) if total_closed > 0 else 0.0
    streak = trade_analyzer.get("streak", {})
    max_consec_loss = streak.get("lost", {}).get("max", 0)

    # 权益曲线
    equity_curve = []
    eq_values = strat.analyzers.equity.get_analysis()
    for i, val in enumerate(eq_values):
        if i < len(df.index):
            equity_curve.append({"日期": str(df.index[i].date()), "市值": round(float(val), 2)})

    # 风险指标
    sortino = _calc_sortino(equity_curve) if equity_curve else 0.0
    calmar = round(total_return / abs(max_drawdown), 2) if max_drawdown and max_drawdown > 0 else 0.0
    ann_vol = strat.analyzers.ann_vol.get_analysis().get("annual_volatility", 0)

    # 买入持有基准
    first_close = float(df["close"].iloc[0])
    last_close = float(df["close"].iloc[-1])
    bh_return = (last_close / first_close - 1) * 100
    bh_equity = []
    for dt, val in zip(df.index, df["close"] / first_close * initial_capital):
        bh_equity.append({"日期": str(dt.date()), "市值": round(float(val), 2)})

    # 指数基准
    index_data = _get_index_benchmark(benchmark_code, start_date, end_date, initial_capital) if benchmark_code else None

    # 年化
    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    years = max(days / 365.0, 0.25)
    strat_annual = round(((1 + total_return / 100) ** (1 / years) - 1) * 100, 2)
    bh_annual = round(((1 + bh_return / 100) ** (1 / years) - 1) * 100, 2)

    # 组装结果
    stock_display = _get_stock_name(code)
    strat_label = f"{_STRATEGY_LABELS.get(strategy, strategy)}({fast_period},{slow_period})"

    result = {
        "策略": strat_label,
        "股票": f"{stock_display}({code})",
        "回测区间": f"{start_date} ~ {end_date}",
        "初始资金": initial_capital,
        "最终资金": round(final_value, 2),
        "总收益率(%)": round(total_return, 2),
        "年化收益率(%)": strat_annual,
        "最大回撤(%)": round(max_drawdown, 2),
        "夏普比率": round(sharpe, 2),
        "索提诺比率": round(sortino, 2),
        "卡玛比率": calmar,
        "年化波动率(%)": round(ann_vol, 2),
        "胜率(%)": round(win_rate, 1),
        "交易次数": total_closed,
        "最大连续亏损(次)": max_consec_loss,
        "交易记录": getattr(strat, "trade_log", []),
        "跳过信号": getattr(strat, "skipped_signals", []),
        "权益曲线": equity_curve,
        "基准(买入持有)": {"总收益率(%)": round(bh_return, 2), "年化收益率(%)": bh_annual, "权益曲线": bh_equity},
    }
    if index_data: result["基准(沪深300)"] = index_data
    result["解读"] = _generate_commentary(strat_label, total_return, max_drawdown, sharpe, bh_return, win_rate, total_closed)
    return result

# ============================================================================
# 自定义Analyzer
# ============================================================================
class _EquityRecorder(bt.analyzers.Analyzer):
    """记录每根bar的策略市值"""
    def __init__(self): self._values = []
    def next(self): self._values.append(self.strategy.broker.getvalue())
    def get_analysis(self): return self._values

class _AnnualVolatility(bt.analyzers.Analyzer):
    """年化波动率"""
    def __init__(self): self._returns = []
    def next(self):
        if len(self.data) > 1:
            prev, curr = self.data.close[-1], self.data.close[0]
            if prev > 0: self._returns.append(curr / prev - 1)
    def get_analysis(self):
        if not self._returns: return {"annual_volatility": 0}
        daily_vol = float(np.std(self._returns))
        return {"annual_volatility": round(daily_vol * np.sqrt(252) * 100, 2)}

# ============================================================================
# 风险指标计算
# ============================================================================
def _calc_sortino(equity_curve: list[dict]) -> float:
    """索提诺比率(只惩罚下行波动)"""
    if len(equity_curve) < 10: return 0.0
    values = [e["市值"] for e in equity_curve]
    returns = [values[i] / values[i-1] - 1 for i in range(1, len(values)) if values[i-1] > 0]
    if not returns: return 0.0
    downside = [r for r in returns if r < 0]
    if not downside: return 0.0
    ds = float(np.std(downside))
    if ds == 0: return 0.0
    annual_return = (1 + float(np.mean(returns))) ** 252 - 1
    annual_downside = ds * np.sqrt(252)
    return round(annual_return / annual_downside, 2) if annual_downside > 0 else 0.0

def _get_index_benchmark(code: str, start_date: str, end_date: str, initial_capital: float) -> dict | None:
    """获取指数基准"""
    try:
        idx_klines = get_kline_a(code, period="daily", adjust="qfq", limit=800)
        if not idx_klines or (isinstance(idx_klines[0], dict) and "error" in idx_klines[0]): return None
        idx_klines = [k for k in idx_klines if "日期" in k and start_date <= k["日期"] <= end_date]
        if len(idx_klines) < 10: return None
        idx_df = _kline_to_df(idx_klines)
        if idx_df.empty: return None
        first, last = float(idx_df["close"].iloc[0]), float(idx_df["close"].iloc[-1])
        idx_return = (last / first - 1) * 100
        idx_equity = [{"日期": str(dt.date()), "市值": round(float(val), 2)} for dt, val in zip(idx_df.index, idx_df["close"] / first * initial_capital)]
        return {"总收益率(%)": round(idx_return, 2), "权益曲线": idx_equity}
    except Exception: return None

def _get_stock_name(code: str) -> str:
    try:
        from mcp_finance.data import STOCK_MAPPING
        return STOCK_MAPPING.get(code, code)
    except Exception: return code

# ============================================================================
# 自然语言解读
# ============================================================================
def _generate_commentary(strat_label: str, strat_return: float, strat_dd: float,
                         strat_sharpe: float, bh_return: float,
                         win_rate: float, total_trades: int) -> str:
    """生成回测结果的自然语言解读"""
    lines = [f"## {strat_label} 回测解读", ""]
    if strat_return > bh_return: lines.append(f"策略跑赢买入持有: {strat_return}% vs {bh_return}%。")
    else: lines.append(f"策略未跑赢买入持有: {strat_return}% vs {bh_return}%。")
    if strat_return > 50: lines.append("收益优秀,但需警惕过拟合。")
    elif strat_return > 0: lines.append("策略实现正收益。")
    else: lines.append("策略录得负收益,参数或市场环境不匹配。")
    if strat_dd > 30: lines.append(f"最大回撤{strat_dd}%偏高,超出多数投资者心理承受。")
    elif strat_dd > 15: lines.append(f"最大回撤{strat_dd}%处于中等水平。")
    else: lines.append(f"最大回撤{strat_dd}%控制良好。")
    if strat_sharpe > 1.5: lines.append("夏普比率优秀(>1.5)。")
    elif strat_sharpe > 0.5: lines.append("夏普比率尚可(0.5~1.5)。")
    else: lines.append("夏普比率偏低(<0.5),风险未获足够补偿。")
    if total_trades > 0:
        lines.append(f"共交易{total_trades}次,胜率{win_rate}%。")
        if win_rate > 60: lines.append("胜率较高。")
        elif win_rate < 40: lines.append("胜率偏低但趋势策略常见(低胜率+高盈亏比)。")
    else: lines.append("回测期间无交易信号。")
    lines.append("")
    lines.append("> 以上为历史数据回测结果,不构成投资建议。过去表现不代表未来收益。")
    return "\n".join(lines)

# ============================================================================
# 公开接口
# ============================================================================
def run_backtest(code: str, strategy: str = "ma_cross", fast_period: int = 5, slow_period: int = 20,
                 start_date: str | None = None, end_date: str | None = None,
                 initial_capital: float = 100000.0, benchmark_index: str | None = "000300",
                 ) -> dict[str, Any]:
    """运行策略回测"""
    return _run_single_backtest(code=code, strategy=strategy, fast_period=fast_period, slow_period=slow_period,
                                start_date=start_date, end_date=end_date,
                                initial_capital=initial_capital, benchmark_code=benchmark_index)

def optimize_backtest(code: str, strategy: str = "ma_cross",
                      fast_range: list[int] | None = None, slow_range: list[int] | None = None,
                      start_date: str | None = None, end_date: str | None = None,
                      metric: str = "sharpe", benchmark_index: str | None = "000300",
                      ) -> dict[str, Any]:
    """网格搜索参数优化(含过拟合警告)"""
    if fast_range is None: fast_range = list(range(5, 25, 5))
    if slow_range is None: slow_range = list(range(20, 60, 10))
    results_list, best, best_val = [], None, -999999.0
    for fast in fast_range:
        for slow in slow_range:
            if slow <= fast: continue
            r = _run_single_backtest(code=code, strategy=strategy, fast_period=fast, slow_period=slow,
                                    start_date=start_date, end_date=end_date,
                                    benchmark_code=benchmark_index)
            if "error" in r: continue
            metric_map = {"sharpe": r.get("夏普比率", 0), "return": r.get("总收益率(%)", 0),
                          "mdd": -abs(r.get("最大回撤(%)", 0)), "win_rate": r.get("胜率(%)", 0),
                          "sortino": r.get("索提诺比率", 0), "calmar": r.get("卡玛比率", 0)}
            val = metric_map.get(metric, r.get("总收益率(%)", 0))
            item = {"fast": fast, "slow": slow, "metric_value": val,
                    "总收益率(%)": r.get("总收益率(%)", 0), "最大回撤(%)": r.get("最大回撤(%)", 0),
                    "夏普比率": r.get("夏普比率", 0), "胜率(%)": r.get("胜率(%)", 0), "交易次数": r.get("交易次数", 0)}
            results_list.append(item)
            if val > best_val: best_val = val; best = item
    if best is None: return {"error": "参数优化失败: 所有组合均无有效结果"}
    # 过拟合检测
    nearby = [x for x in results_list if abs(x["fast"] - best["fast"]) <= 5 and abs(x["slow"] - best["slow"]) <= 10 and x != best]
    warning = ""
    if nearby:
        nv = [x["metric_value"] for x in nearby]
        if best_val != 0 and abs((max(nv) - min(nv)) / best_val) > 0.5:
            warning = "最优参数附近结果波动较大,可能存在过拟合,建议样本外验证"
    return {"策略": _STRATEGY_LABELS.get(strategy, strategy), "股票": _get_stock_name(code),
            "优化目标": metric, "测试组合数": len(fast_range) * len(slow_range),
            "有效结果数": len(results_list),
            "最优参数": {"fast": best["fast"], "slow": best["slow"]},
            "最优表现": {k: v for k, v in best.items() if k not in ("fast", "slow", "metric_value")},
            "所有结果": sorted(results_list, key=lambda x: x["metric_value"], reverse=True)[:20],
            "过拟合警告": warning or "无"}

# ============================================================================
# MCP Tool Handlers
# ============================================================================

from mcp_finance.errors import BacktestError
from mcp_finance.logging_config import get_logger
_blogger = get_logger(__name__)

def handle_backtest(arguments: dict[str, Any]) -> dict[str, Any]:
    """策略回测handler"""
    code = arguments["code"]
    strategy = arguments.get("strategy", "ma_cross")
    fast_period = arguments.get("fast_period", 5)
    slow_period = arguments.get("slow_period", 20)
    start_date = arguments.get("start_date")
    end_date = arguments.get("end_date")
    initial_capital = arguments.get("initial_capital", 100000.0)
    generate_chart = arguments.get("generate_chart", True)

    result = run_backtest(code=code, strategy=strategy, fast_period=fast_period, slow_period=slow_period,
                          start_date=start_date, end_date=end_date, initial_capital=initial_capital)
    if "error" in result: raise BacktestError(str(result["error"]))

    if generate_chart and "权益曲线" in result:
        try:
            from mcp_finance.chart import generate_backtest_chart
            chart_path = generate_backtest_chart(stock_name=result["股票"], strategy_label=result["策略"],
                strategy_curve=result["权益曲线"],
                benchmark_curve=result.get("基准(买入持有)", {}).get("权益曲线"),
                trades=result.get("交易记录", []), initial_capital=initial_capital)
            result["权益曲线图"] = chart_path
            result["权益曲线图提示"] = "交互式HTML文件,请用浏览器打开"
        except Exception as e: result["权益曲线图"] = f"图表生成失败: {e}"

    _blogger.info("回测完成: %s strategy=%s return=%.2f%%", code, strategy, result.get("总收益率(%)", 0))
    return result

def handle_optimize(arguments: dict[str, Any]) -> dict[str, Any]:
    """参数优化handler"""
    code = arguments["code"]
    strategy = arguments.get("strategy", "ma_cross")
    fast_min = arguments.get("fast_min", 5); fast_max = arguments.get("fast_max", 20)
    fast_step = arguments.get("fast_step", 5)
    slow_min = arguments.get("slow_min", 20); slow_max = arguments.get("slow_max", 60)
    slow_step = arguments.get("slow_step", 10)
    start_date = arguments.get("start_date"); end_date = arguments.get("end_date")
    metric = arguments.get("metric", "sharpe")
    fast_range = list(range(fast_min, fast_max + 1, fast_step))
    slow_range = list(range(slow_min, slow_max + 1, slow_step))
    result = optimize_backtest(code=code, strategy=strategy, fast_range=fast_range, slow_range=slow_range,
                               start_date=start_date, end_date=end_date, metric=metric)
    _blogger.info("参数优化完成: %s strategy=%s", code, strategy)
    return result

