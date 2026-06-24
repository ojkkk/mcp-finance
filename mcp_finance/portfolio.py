"""
投资组合分析模块 — 多股组合回测 / 相关性矩阵 / 夏普最优组合

基于纯 Python 实现，不依赖外部优化库。
"""

from __future__ import annotations
from typing import Any
import math

from mcp_finance.api import handle_kline, _detect_market
from mcp_finance.data import STOCK_MAPPING
from mcp_finance.logging_config import get_logger

_logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. 相关性矩阵
# ═══════════════════════════════════════════════════════════════

def get_correlation_matrix(codes: list[str], days: int = 120) -> dict:
    """计算多只股票收益率的相关性矩阵

    Args:
        codes: 股票代码列表
        days: 回溯天数
    """
    if len(codes) < 2:
        return {"error": True, "message": "至少需要2只股票"}

    # 获取所有股票的收盘价序列
    price_series: dict[str, list[float]] = {}
    names: dict[str, str] = {}
    failed = []

    for code in codes:
        name = STOCK_MAPPING.get(code, code)
        names[code] = name
        try:
            market = _detect_market(code)
            klines = handle_kline({"code": code, "market": market, "ktype": "daily", "limit": days})
        except Exception as e:
            _logger.warning("correlation_matrix: %s kline failed: %s", code, e)
            failed.append(code)
            continue

        if isinstance(klines, dict) and "error" in klines:
            klines = []
        elif not isinstance(klines, list):
            klines = []
        if not klines or len(klines) < 20:
            failed.append(code)
            continue
        closes = []
        for k in klines:
            try:
                closes.append(float(k["收盘价"]))
            except (KeyError, ValueError):
                continue
        if len(closes) >= 20:
            price_series[code] = closes

    if len(price_series) < 2:
        return {"error": True, "message": "有效数据不足（至少需要2只股票有20天以上数据）"}

    # 对齐长度
    min_len = min(len(v) for v in price_series.values())
    for code in price_series:
        price_series[code] = price_series[code][-min_len:]

    # 计算日收益率
    returns: dict[str, list[float]] = {}
    for code, prices in price_series.items():
        rets = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                rets.append((prices[i] - prices[i-1]) / prices[i-1])
        returns[code] = rets

    # 计算相关系数矩阵
    valid_codes = list(returns.keys())
    n = len(valid_codes)
    matrix = [[0.0] * n for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 1.0
            else:
                matrix[i][j] = round(_pearson(returns[valid_codes[i]], returns[valid_codes[j]]), 3)

    # 格式化输出
    corr_data = []
    for i in range(n):
        row = {"股票": f"{names.get(valid_codes[i], valid_codes[i])}({valid_codes[i]})"}
        for j in range(n):
            row[valid_codes[j]] = matrix[i][j]
        corr_data.append(row)

    return {
        "股票列表": [f"{names.get(c, c)}({c})" for c in valid_codes],
        "数据天数": min_len - 1,
        "相关性矩阵": corr_data,
        "平均相关性": round(_avg_correlation(matrix), 3),
        "低相关配对": _find_low_corr_pairs(valid_codes, names, matrix, top_n=5),
        "失败": failed if failed else None,
    }


def _pearson(x: list[float], y: list[float]) -> float:
    """计算皮尔逊相关系数"""
    n = min(len(x), len(y))
    if n < 2:
        return 0
    x = x[:n]
    y = y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x) / (n - 1))
    sy = math.sqrt(sum((v - my) ** 2 for v in y) / (n - 1))
    if sx == 0 or sy == 0:
        return 0
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (n - 1)
    return cov / (sx * sy)


def _avg_correlation(matrix: list[list[float]]) -> float:
    """计算平均非自相关系数"""
    n = len(matrix)
    if n <= 1:
        return 0
    total = 0.0
    count = 0
    for i in range(n):
        for j in range(n):
            if i != j:
                total += matrix[i][j]
                count += 1
    return total / count if count > 0 else 0


def _find_low_corr_pairs(codes: list[str], names: dict, matrix: list[list[float]], top_n: int = 5) -> list:
    """找出相关性最低的配对"""
    n = len(codes)
    pairs = []
    for i in range(n):
        for j in range(i+1, n):
            pairs.append((
                f"{names.get(codes[i], codes[i])} vs {names.get(codes[j], codes[j])}",
                matrix[i][j]
            ))
    pairs.sort(key=lambda x: x[1])
    return [{"配对": p[0], "相关系数": p[1]} for p in pairs[:top_n]]


def handle_correlation_matrix(arguments: dict) -> dict:
    return get_correlation_matrix(arguments["codes"], arguments.get("days", 120))


# ═══════════════════════════════════════════════════════════════
# 2. 投资组合回测
# ═══════════════════════════════════════════════════════════════

def portfolio_backtest(
    codes: list[str],
    weights: list[float] | None = None,
    initial_capital: float = 100000,
    days: int = 250,
) -> dict:
    """多股等权/自定义权重组合回测

    Args:
        codes: 股票代码列表
        weights: 权重列表，默认等权
        initial_capital: 初始资金
        days: 回溯天数
    """
    if len(codes) < 1:
        return {"error": True, "message": "至少需要1只股票"}

    weights = weights or [1.0 / len(codes)] * len(codes)
    if len(weights) != len(codes):
        return {"error": True, "message": "权重数量必须与股票数量一致"}
    if abs(sum(weights) - 1.0) > 0.01:
        return {"error": True, "message": f"权重之和必须为1，当前: {sum(weights)}"}

    # 获取所有股票价格
    price_data: dict[str, list[dict]] = {}
    names: dict[str, str] = {}
    for code in codes:
        names[code] = STOCK_MAPPING.get(code, code)
        try:
            market = _detect_market(code)
            klines = handle_kline({"code": code, "market": market, "ktype": "daily", "limit": days})
        except Exception as e:
            _logger.warning("portfolio_backtest: %s kline failed: %s", code, e)
            continue

        if isinstance(klines, dict) and "error" in klines:
            klines = []
        elif not isinstance(klines, list):
            klines = []
        if klines and len(klines) >= 20:
            price_data[code] = klines

    if len(price_data) < 1:
        return {"error": True, "message": "无有效数据"}

    # 找到所有股票的共同日期范围
    all_dates = set()
    for code, klines in price_data.items():
        for k in klines:
            all_dates.add(k["日期"])
    common_dates = sorted(all_dates)

    if len(common_dates) < 20:
        return {"error": True, "message": f"共同交易日太少 ({len(common_dates)}天)"}

    # 构建价格矩阵
    price_matrix: dict[str, dict[str, float]] = {}
    for code, klines in price_data.items():
        date_price = {k["日期"]: float(k["收盘价"]) for k in klines if "收盘价" in k}
        price_matrix[code] = {}
        for d in common_dates:
            price_matrix[code][d] = date_price.get(d, 0)

    # 计算组合日收益率
    portfolio_values = []
    prev_value = initial_capital
    daily_returns = []

    for d in common_dates:
        daily_return = 0.0
        for i, code in enumerate(codes):
            if code in price_matrix:
                today = price_matrix[code].get(d, 0)
                yesterday = price_matrix[code].get(prev_date if "prev_date" in dir() else common_dates[0], today)
                # 用简单方法：计算每只股票的仓位价值
                pass
        
        # 简化：直接用第一天初始化仓位
        if not portfolio_values:
            # 初始化分配
            positions = {}
            for i, code in enumerate(codes):
                if code in price_matrix:
                    price = price_matrix[code][d]
                    if price > 0:
                        shares = (initial_capital * weights[i]) / price
                        positions[code] = {"shares": shares, "weight": weights[i]}
            
            total = initial_capital
            portfolio_values.append({"日期": d, "市值": round(total, 2)})
            continue

        # 计算当日市值
        total = 0.0
        for code, pos in positions.items():
            if code in price_matrix and d in price_matrix[code]:
                price = price_matrix[code][d]
                if price > 0:
                    total += pos["shares"] * price

        if portfolio_values:
            prev_val = portfolio_values[-1]["市值"]
            if prev_val > 0:
                daily_returns.append((total - prev_val) / prev_val)

        portfolio_values.append({"日期": d, "市值": round(total, 2)})

    if len(portfolio_values) < 2:
        return {"error": True, "message": "回测数据不足"}

    # 绩效统计
    final_value = portfolio_values[-1]["市值"]
    total_return = round((final_value - initial_capital) / initial_capital * 100, 2)

    # 夏普比率
    sharpe = 0.0
    if len(daily_returns) > 1:
        avg_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((r - avg_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        if variance > 0:
            sharpe = round(avg_ret / math.sqrt(variance) * math.sqrt(252), 2)

    # 最大回撤
    max_dd = 0.0
    peak = initial_capital
    for pv in portfolio_values:
        val = pv["市值"]
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = round(dd, 2)

    # 年化收益率（简化）
    trading_days = len(portfolio_values) - 1
    if trading_days > 0:
        annual_return = round(((final_value / initial_capital) ** (252 / trading_days) - 1) * 100, 2)
    else:
        annual_return = 0.0

    return {
        "组合": [{"代码": c, "名称": names.get(c, c), "权重": round(weights[i] * 100, 1)} for i, c in enumerate(codes)],
        "初始资金": initial_capital,
        "最终资产": round(final_value, 2),
        "总收益率(%)": total_return,
        "年化收益率(%)": annual_return,
        "夏普比率": sharpe,
        "最大回撤(%)": max_dd,
        "回测天数": trading_days,
        "权益曲线": portfolio_values[:50] if len(portfolio_values) > 50 else portfolio_values,
        "提示": f"权益曲线仅展示最近{min(50, len(portfolio_values))}个点",
    }


def handle_portfolio_backtest(arguments: dict) -> dict:
    return portfolio_backtest(
        arguments["codes"],
        arguments.get("weights"),
        float(arguments.get("initial_capital", 100000)),
        arguments.get("days", 250),
    )
