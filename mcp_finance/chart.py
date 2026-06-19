"""
Plotly 交互式 K 线图生成模块

输出 HTML 文件，可在浏览器中打开，支持:
  - 蜡烛图 + 均线叠加 (MA5/10/20/60)
  - 成交量柱状图
  - 技术指标副图 (MACD / KDJ / RSI)
  - 缩放、平移、悬停查看数值
"""

from __future__ import annotations
import os
from datetime import datetime
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from mcp_finance.indicators import _sma, _ema, calc_kdj, calc_rsi


def _calc_sma(values: list[float], n: int) -> list[float | None]:
    """委托至 indicators._sma（保留原函数名保持调用兼容）"""
    return _sma(values, n)


def _calc_ema(values: list[float], n: int) -> list[float | None]:
    """委托至 indicators._ema"""
    return _ema(values, n)


def _calc_kdj_simple(
    high: list[float], low: list[float], close: list[float], n: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """委托至 indicators.calc_kdj，返回 tuple 保持调用兼容"""
    result = calc_kdj(high, low, close, n)
    return result["K"], result["D"], result["J"]


def _calc_rsi_simple(close: list[float], n: int = 14) -> list[float | None]:
    """委托至 indicators.calc_rsi"""
    return calc_rsi(close, n)


def generate_kline_chart(
    kline_data: list[dict[str, Any]],
    stock_name: str = "",
    indicators: dict[str, Any] | None = None,
    show_volume: bool = True,
    show_macd: bool = True,
    show_kdj: bool = False,
    show_rsi: bool = False,
    output_path: str = "",
) -> str:
    """
    生成交互式 K 线 HTML 图表

    Args:
        kline_data:   get_kline() 返回的 K 线列表
        stock_name:   股票名称
        indicators:   compute_all_indicators() 的结果（可选）
        show_volume:  是否显示成交量副图
        show_macd:    是否显示 MACD 副图
        show_kdj:     是否显示 KDJ 副图
        show_rsi:     是否显示 RSI 副图
        output_path:  输出文件路径，留空自动生成

    Returns:
        HTML 文件绝对路径
    """
    if not kline_data:
        raise ValueError("K 线数据为空")

    dates = [k["日期"] for k in kline_data]
    opens = [float(k["开盘价"]) for k in kline_data]
    highs = [float(k["最高价"]) for k in kline_data]
    lows = [float(k["最低价"]) for k in kline_data]
    closes = [float(k["收盘价"]) for k in kline_data]
    volumes = [float(k.get("成交量(手)", 0) or 0) for k in kline_data]

    # ── 计算副图行数及位置 ──
    subplot_rows = 1
    row_volume = row_macd = row_kdj = row_rsi = 0
    cr = 1
    if show_volume:
        cr += 1
        row_volume = cr
    if show_macd:
        cr += 1
        row_macd = cr
    if show_kdj:
        cr += 1
        row_kdj = cr
    if show_rsi:
        cr += 1
        row_rsi = cr
    subplot_rows = cr

    # ── 行高 ──
    main_h = 0.5
    sub_h = (1.0 - main_h) / (subplot_rows - 1) if subplot_rows > 1 else 0.5
    row_heights = [main_h] + [sub_h] * (subplot_rows - 1)

    specs = [[{"secondary_y": False}]]
    for _ in range(subplot_rows - 1):
        specs.append([{"secondary_y": False}])

    fig = make_subplots(
        rows=subplot_rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        specs=specs,
    )

    # ═══════════════════════════════════════════
    # 主图: 蜡烛图 + 均线
    # ═══════════════════════════════════════════
    candle = go.Candlestick(
        x=dates,
        open=opens, high=highs, low=lows, close=closes,
        name="K线",
        increasing_line_color="#ef5350",
        decreasing_line_color="#26a69a",
        increasing_fillcolor="#ef5350",
        decreasing_fillcolor="#26a69a",
    )
    fig.add_trace(candle, row=1, col=1)

    for label, period, color in [
        ("MA5", 5, "#FF9800"),
        ("MA10", 10, "#2196F3"),
        ("MA20", 20, "#9C27B0"),
        ("MA60", 60, "#4CAF50"),
    ]:
        if len(closes) >= period:
            ma_vals = _calc_sma(closes, period)
            fig.add_trace(go.Scatter(
                x=dates, y=ma_vals,
                mode="lines", name=label,
                line=dict(color=color, width=1.2), opacity=0.7,
            ), row=1, col=1)

    # ═══════════════════════════════════════════
    # 成交量
    # ═══════════════════════════════════════════
    if show_volume and row_volume:
        vol_colors = []
        for i in range(len(closes)):
            if i > 0 and closes[i] >= closes[i - 1]:
                vol_colors.append("#ef5350")
            else:
                vol_colors.append("#26a69a")
        fig.add_trace(go.Bar(
            x=dates, y=volumes, name="成交量(手)",
            marker_color=vol_colors, opacity=0.6, showlegend=False,
        ), row=row_volume, col=1)
        fig.update_yaxes(title_text="成交量(手)", row=row_volume, col=1)

    # ═══════════════════════════════════════════
    # MACD
    # ═══════════════════════════════════════════
    if show_macd and row_macd:
        dif = _calc_ema(closes, 12)
        dea = _calc_ema(closes, 26)
        macd_dif: list[float | None] = []
        for i in range(len(closes)):
            if dif[i] is not None and dea[i] is not None:
                macd_dif.append(round(dif[i] - dea[i], 4))
            else:
                macd_dif.append(None)
        dif_clean = [x if x is not None else 0.0 for x in macd_dif]
        dea_list = _calc_ema(dif_clean, 9)
        macd_dea: list[float | None] = []
        macd_bar: list[float | None] = []
        for i in range(len(macd_dif)):
            if macd_dif[i] is not None and dea_list[i] is not None:
                macd_dea.append(dea_list[i])
                macd_bar.append(round((macd_dif[i] - dea_list[i]) * 2, 4))
            else:
                macd_dea.append(None)
                macd_bar.append(None)

        bar_colors = [
            "#ef5350" if v is not None and v >= 0 else "#26a69a" if v is not None else "#999"
            for v in macd_bar
        ]
        fig.add_trace(go.Bar(
            x=dates, y=macd_bar, name="MACD柱",
            marker_color=bar_colors, opacity=0.5, showlegend=False,
        ), row=row_macd, col=1)
        fig.add_trace(go.Scatter(
            x=dates, y=macd_dif, name="DIF",
            line=dict(color="#FF9800", width=1.2),
        ), row=row_macd, col=1)
        fig.add_trace(go.Scatter(
            x=dates, y=macd_dea, name="DEA",
            line=dict(color="#2196F3", width=1.2),
        ), row=row_macd, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="#666", opacity=0.3, row=row_macd, col=1)
        fig.update_yaxes(title_text="MACD", row=row_macd, col=1)

    # ═══════════════════════════════════════════
    # KDJ
    # ═══════════════════════════════════════════
    if show_kdj and row_kdj:
        kdj_k, kdj_d, kdj_j = _calc_kdj_simple(highs, lows, closes)
        fig.add_trace(go.Scatter(
            x=dates, y=kdj_k, name="K",
            line=dict(color="#FF9800", width=1.2),
        ), row=row_kdj, col=1)
        fig.add_trace(go.Scatter(
            x=dates, y=kdj_d, name="D",
            line=dict(color="#2196F3", width=1.2),
        ), row=row_kdj, col=1)
        fig.add_trace(go.Scatter(
            x=dates, y=kdj_j, name="J",
            line=dict(color="#9C27B0", width=1.2),
        ), row=row_kdj, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="#ef5350", opacity=0.3, row=row_kdj, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="#26a69a", opacity=0.3, row=row_kdj, col=1)
        fig.update_yaxes(title_text="KDJ", row=row_kdj, col=1, range=[0, 100])

    # ═══════════════════════════════════════════
    # RSI
    # ═══════════════════════════════════════════
    if show_rsi and row_rsi:
        rsi6 = _calc_rsi_simple(closes, 6)
        rsi14 = _calc_rsi_simple(closes, 14)
        fig.add_trace(go.Scatter(
            x=dates, y=rsi6, name="RSI6",
            line=dict(color="#FF9800", width=1),
        ), row=row_rsi, col=1)
        fig.add_trace(go.Scatter(
            x=dates, y=rsi14, name="RSI14",
            line=dict(color="#2196F3", width=1.5),
        ), row=row_rsi, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", opacity=0.3, row=row_rsi, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#26a69a", opacity=0.3, row=row_rsi, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="#666", opacity=0.2, row=row_rsi, col=1)
        fig.update_yaxes(title_text="RSI", row=row_rsi, col=1, range=[0, 100])

    # ═══════════════════════════════════════════
    # 布局
    # ═══════════════════════════════════════════
    title = f"{stock_name or '股票'} — K线图（交互式HTML · 浏览器打开）"
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=18)),
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        modebar=dict(orientation="v", bgcolor="rgba(0,0,0,0.3)", color="rgba(255,255,255,0.9)"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=50, b=10),
        height=400 + 200 * (subplot_rows - 1),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#333", row=subplot_rows, col=1)
    fig.update_yaxes(title_text="价格(元)", row=1, col=1, showgrid=True, gridcolor="#333")

    # ── 输出 HTML ──
    if not output_path:
        chart_dir = os.path.join(os.getcwd(), "charts")
        os.makedirs(chart_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = stock_name.replace("/", "_").replace("\\", "_") if stock_name else "chart"
        output_path = os.path.join(chart_dir, f"{safe_name}_{ts}.html")

    html = fig.to_html(include_plotlyjs="embed", full_html=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return os.path.abspath(output_path)


def generate_backtest_chart(
    stock_name: str,
    strategy_label: str,
    strategy_curve: list[dict[str, Any]],
    benchmark_curve: list[dict[str, Any]] | None = None,
    trades: list[dict[str, Any]] | None = None,
    initial_capital: float = 100000.0,
    output_path: str | None = None,
) -> str:
    """
    生成回测权益曲线对比图（策略 vs 基准）

    Args:
        stock_name:       股票名称
        strategy_label:   策略名称标签
        strategy_curve:   策略权益曲线 [{"日期": str, "市值": float}, ...]
        benchmark_curve:  基准权益曲线（买入持有）
        trades:           交易记录（用于标注买卖点）
        initial_capital:  初始资金
        output_path:      输出 HTML 路径，默认 %TEMP%/mcp-stock-cn-charts/

    Returns:
        HTML 文件路径
    """
    fig = go.Figure()

    # ── 策略权益曲线 ──
    dates = [p["日期"] for p in strategy_curve]
    strat_values = [p["市值"] for p in strategy_curve]

    fig.add_trace(go.Scatter(
        x=dates,
        y=strat_values,
        mode="lines",
        name=strategy_label,
        line=dict(color="#00d4ff", width=2),
        hovertemplate="%{x}<br>策略: %{y:.2f}<extra></extra>",
    ))

    # ── 基准权益曲线 ──
    if benchmark_curve:
        bh_dates = [p["日期"] for p in benchmark_curve]
        bh_values = [p["市值"] for p in benchmark_curve]
        fig.add_trace(go.Scatter(
            x=bh_dates,
            y=bh_values,
            mode="lines",
            name="买入持有(基准)",
            line=dict(color="#ffa600", width=2, dash="dash"),
            hovertemplate="%{x}<br>基准: %{y:.2f}<extra></extra>",
        ))

    # ── 初始资金基线 ──
    fig.add_hline(
        y=initial_capital,
        line=dict(color="#666", width=1, dash="dot"),
        annotation_text=f"初始资金 {initial_capital:,.0f}",
        annotation_position="bottom right",
    )

    # ── 买卖点标注 ──
    if trades:
        buy_dates = []
        buy_values = []
        sell_dates = []
        sell_values = []
        for t in trades:
            if t["动作"] == "买入":
                buy_dates.append(t["日期"])
                buy_values.append(t["金额"])
            elif t["动作"] in ("卖出", "平仓"):
                sell_dates.append(t["日期"])
                sell_values.append(t["金额"])

        if buy_dates:
            fig.add_trace(go.Scatter(
                x=buy_dates,
                y=buy_values,
                mode="markers",
                name="买入",
                marker=dict(color="#00ff88", size=10, symbol="triangle-up"),
                hovertemplate="买入: %{x}<br>金额: %{y:.2f}<extra></extra>",
            ))
        if sell_dates:
            fig.add_trace(go.Scatter(
                x=sell_dates,
                y=sell_values,
                mode="markers",
                name="卖出",
                marker=dict(color="#ff4466", size=10, symbol="triangle-down"),
                hovertemplate="卖出: %{x}<br>金额: %{y:.2f}<extra></extra>",
            ))

    # ── 布局 ──
    fig.update_layout(
        title=f"回测权益曲线 — {stock_name}",
        xaxis_title="日期",
        yaxis_title="总资金(元)",
        template="plotly_dark",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=60, b=10),
        height=500,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#333")
    fig.update_yaxes(showgrid=True, gridcolor="#333", tickformat=",.0f")

    # ── 输出 HTML ──
    if not output_path:
        chart_dir = os.path.join(os.getcwd(), "charts")
        os.makedirs(chart_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = stock_name.replace("/", "_").replace("\\", "_")
        output_path = os.path.join(chart_dir, f"{safe_name}_backtest_{ts}.html")

    html = fig.to_html(include_plotlyjs="embed", full_html=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return os.path.abspath(output_path)
# ═══════════════════════════════════════════════════════════════
# MCP Tool Handler
# ═══════════════════════════════════════════════════════════════

from mcp_finance.errors import NoDataError
from mcp_finance.logging_config import get_logger

_clogger = get_logger(__name__)


def handle_plot_kline(arguments: dict[str, Any]) -> dict[str, Any]:
    """生成交互式 K 线图 handler"""
    from typing import Any
    from mcp_finance.api import get_kline_a
    from mcp_finance.indicators import compute_all_indicators
    from mcp_finance.data import STOCK_MAPPING

    code = arguments["code"]
    market = arguments.get("market", "a")
    days = min(arguments.get("days", 120), 800)
    ktype = arguments.get("ktype", "daily")

    from mcp_finance.api import get_kline_a, get_kline_hk, get_kline_us, get_kline_futures
    kline_fn = {"a": get_kline_a, "hk": get_kline_hk, "us": get_kline_us, "futures": get_kline_futures}.get(market)
    if kline_fn is None:
        raise NoDataError(f"不支持的市场类型: {market}")
    klines = kline_fn(code, period=ktype, adjust="qfq", limit=days) if market == "a" else kline_fn(code, period=ktype, limit=days)
    if not klines:
        raise NoDataError(f"无法获取 {code} 的 K 线数据")

    stock_name = STOCK_MAPPING.get(code, code)
    indicators = compute_all_indicators(klines)

    show_macd = arguments.get("show_macd", True)
    show_kdj = arguments.get("show_kdj", False)
    show_rsi = arguments.get("show_rsi", False)

    output_path = generate_kline_chart(
        kline_data=klines,
        stock_name=stock_name,
        indicators=indicators,
        show_volume=True,
        show_macd=show_macd,
        show_kdj=show_kdj,
        show_rsi=show_rsi,
    )

    _clogger.info("K线图生成: %s days=%d path=%s", code, len(klines), output_path)
    return {
        "⚠️重要提示": "这不是图片！这是一个交互式HTML文件，请用浏览器打开下面的路径",
        "股票": f"{stock_name}({code})",
        "K线条数": len(klines),
        "起止日期": f"{klines[0]['日期']} ~ {klines[-1]['日期']}",
        "HTML文件路径": output_path,
        "打开方式": "在文件管理器中找到该文件 → 双击用浏览器打开 → 可缩放/平移/悬停查看每根K线数值",
        "最新收盘价": klines[-1]["收盘价"],
        "技术信号": indicators.get("signals", []),
    }
