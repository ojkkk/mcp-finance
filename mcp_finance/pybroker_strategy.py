"""
PyBroker ML 增强策略模块

基于 PyBroker 框架实现 Walkforward Analysis 和 ML-based 交易策略。

注意: 当前实现使用均值阈值比较生成信号，并非真正的 ML 模型预测。
model_type 参数仅影响标签名，xgboost/random_forest/linear 走相同逻辑。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import numpy as np

from mcp_finance.api import get_kline_a
from mcp_finance.logging_config import get_logger

_logger = get_logger(__name__)


def _kline_to_pybroker_df(klines: list[dict[str, Any]]) -> pd.DataFrame:
    """将 API 返回的 K 线数据转为 PyBroker 兼容的 DataFrame"""
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


def _add_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """添加技术指标作为 ML 特征"""
    close = df["close"]
    volume = df["volume"]

    # 均线
    df["ma5"] = close.rolling(5).mean()
    df["ma10"] = close.rolling(10).mean()
    df["ma20"] = close.rolling(20).mean()
    df["ma60"] = close.rolling(60).mean()

    # 价格动量
    df["ret_1d"] = close.pct_change(1)
    df["ret_5d"] = close.pct_change(5)
    df["ret_10d"] = close.pct_change(10)
    df["ret_20d"] = close.pct_change(20)

    # 波动率
    df["volatility_5d"] = df["ret_1d"].rolling(5).std()
    df["volatility_20d"] = df["ret_1d"].rolling(20).std()

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # 成交量
    df["volume_ma5"] = volume.rolling(5).mean()
    df["volume_ratio"] = volume / df["volume_ma5"].replace(0, np.nan)

    # BOLL
    df["boll_mid"] = close.rolling(20).mean()
    boll_std = close.rolling(20).std()
    df["boll_upper"] = df["boll_mid"] + 2 * boll_std
    df["boll_lower"] = df["boll_mid"] - 2 * boll_std
    df["boll_width"] = (df["boll_upper"] - df["boll_lower"]) / df["boll_mid"]

    return df


def run_pybroker_backtest(
    code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 100000.0,
    model_type: str = "xgboost",
    train_size: float = 0.7,
) -> dict[str, Any]:
    """使用 PyBroker 运行 ML 增强回测

    Args:
        code: 股票代码
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金
        model_type: ML 模型类型 (xgboost / random_forest / linear)
        train_size: 训练集比例

    Returns:
        回测结果字典
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        sd = datetime.now() - timedelta(days=730)
        start_date = sd.strftime("%Y-%m-%d")

    # 获取 K 线数据
    klines = get_kline_a(code, period="daily", adjust="qfq", limit=800)
    if not klines:
        return {"error": f"未能获取 {code} 的 K 线数据"}

    klines = [k for k in klines if start_date <= k["日期"] <= end_date]
    if len(klines) < 60:
        return {"error": f"K 线数据不足（{len(klines)} 条，需要至少 60 条）"}

    df = _kline_to_pybroker_df(klines)
    df = _add_technical_features(df)
    df.dropna(inplace=True)

    if len(df) < 30:
        return {"error": f"计算技术指标后数据不足（{len(df)} 条）"}

    # 准备特征和标签
    features = [
        "ma5", "ma10", "ma20", "ret_1d", "ret_5d", "ret_10d",
        "volatility_5d", "rsi_14", "macd", "macd_signal", "macd_hist",
        "volume_ratio", "boll_width",
    ]
    # 剔除不存在的列
    features = [f for f in features if f in df.columns]

    # 标签：未来 5 日收益为正
    df["future_ret"] = df["close"].pct_change(5).shift(-5)
    df["label"] = (df["future_ret"] > 0.02).astype(int)

    df_labeled = df[features + ["label"]].dropna()

    if len(df_labeled) < 30:
        return {"error": f"标记后数据不足（{len(df_labeled)} 条）"}

    # ── 模拟 Walkforward Analysis ──
    split_idx = int(len(df_labeled) * train_size)
    train_df = df_labeled.iloc[:split_idx]
    test_df = df_labeled.iloc[split_idx:]

    # 简单信号：用训练集计算各特征均值方向
    train_means = train_df[features].mean()
    test_signals = test_df[features].gt(train_means, axis=1).mean(axis=1)
    test_signals = test_signals.map(lambda x: x > 0.5)

    # 回测模拟
    test_prices = df.loc[test_df.index, "close"]
    test_dates = test_prices.index

    position = 0
    cash = initial_capital
    trades = []
    equity_curve = []
    entry_price = 0
    entry_date = None

    for i, (date, signal) in enumerate(zip(test_dates, test_signals)):
        price = float(test_prices.loc[date])

        if signal and cash > 0 and position == 0:
            # 买入
            size = int(cash / price / 100) * 100
            if size > 0:
                cost = size * price * (1 + 0.001)  # 含佣金
                if cost <= cash:
                    position = size
                    cash -= cost
                    entry_price = price
                    entry_date = date
                    trades.append({"日期": str(date.date()), "动作": "买入",
                                   "价格": round(price, 2), "股数": size,
                                   "金额": round(cost, 2)})

        elif not signal and position > 0:
            # 卖出
            proceeds = position * price * (1 - 0.001 - 0.0005)  # 含佣金+印花税
            pnl_pct = round((price / entry_price - 1) * 100, 2) if entry_price else 0
            cash += proceeds
            trades.append({"日期": str(date.date()), "动作": "卖出",
                           "价格": round(price, 2), "股数": position,
                           "金额": round(proceeds, 2), "盈亏(%)": pnl_pct})
            position = 0

        total_value = cash + position * price
        equity_curve.append({"日期": str(date.date()), "市值": round(total_value, 2)})

    # 最终平仓
    if position > 0 and len(test_dates) > 0:
        price = float(test_prices.iloc[-1])
        proceeds = position * price * (1 - 0.001 - 0.0005)
        pnl_pct = round((price / entry_price - 1) * 100, 2) if entry_price else 0
        cash += proceeds
        trades.append({"日期": str(test_dates[-1].date()), "动作": "卖出(平仓)",
                       "价格": round(price, 2), "股数": position,
                       "金额": round(proceeds, 2), "盈亏(%)": pnl_pct})
        position = 0

    final_value = cash
    total_return = (final_value / initial_capital - 1) * 100

    # 基准（买入持有）
    bh_prices = test_prices
    bh_final = float(bh_prices.iloc[-1]) / float(bh_prices.iloc[0]) * initial_capital
    bh_return = (bh_final / initial_capital - 1) * 100

    # 年化
    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    years = days / 365.0 if days > 0 else 1.0
    strat_annual_pct = round(((1 + total_return / 100) ** (1 / years) - 1) * 100, 2)
    bh_annual_pct = round(((1 + bh_return / 100) ** (1 / years) - 1) * 100, 2)

    # 胜率
    closed_trades = [t for t in trades if "盈亏(%)" in t]
    won = sum(1 for t in closed_trades if t.get("盈亏(%)", 0) > 0)
    win_rate = (won / len(closed_trades) * 100) if closed_trades else 0

    # 回撤
    peak = initial_capital
    max_drawdown = 0
    for pt in equity_curve:
        val = pt["市值"]
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > max_drawdown:
            max_drawdown = dd

    return {
        "策略": f"PyBroker ML ({model_type})",
        "股票": code,
        "时间范围": f"{start_date} ~ {end_date}",
        "初始资金": initial_capital,
        "最终资金": round(final_value, 2),
        "总收益率(%)": round(total_return, 2),
        "年化收益率(%)": strat_annual_pct,
        "最大回撤(%)": round(max_drawdown, 2),
        "胜率(%)": round(win_rate, 1),
        "交易次数": len(closed_trades),
        "特征数": len(features),
        "训练集比例": train_size,
        "模型类型": model_type,
        "交易记录": trades,
        "权益曲线": equity_curve,
        "基准(买入持有)": {
            "最终资金": round(bh_final, 2),
            "总收益率(%)": round(bh_return, 2),
            "年化收益率(%)": bh_annual_pct,
        },
        "引擎": f"PyBroker (simulated - {model_type})",
        "注意提示": "本策略基于均值阈值比较生成信号，非真实 ML 模型预测，model_type 仅影响标签",
    }


# ═══════════════════════════════════════════════════════════════
# MCP Tool Handler
# ═══════════════════════════════════════════════════════════════

from mcp_finance.errors import BacktestError


def handle_pybroker_backtest(arguments: dict[str, Any]) -> dict[str, Any]:
    """PyBroker ML 回测 handler"""
    code = arguments["code"]
    start_date = arguments.get("start_date")
    end_date = arguments.get("end_date")
    initial_capital = arguments.get("initial_capital", 100000.0)
    model_type = arguments.get("model_type", "xgboost")
    train_size = arguments.get("train_size", 0.7)

    result = run_pybroker_backtest(
        code=code,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        model_type=model_type,
        train_size=train_size,
    )
    if "error" in result:
        raise BacktestError(str(result["error"]))

    _logger.info("PyBroker回测完成: %s model=%s return=%.2f%%", code, model_type, result.get("总收益率(%)", 0))
    return result
