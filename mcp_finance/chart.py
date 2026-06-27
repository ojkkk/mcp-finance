"""
ECharts 交互式图表生成模块

输出 HTML 文件，可在浏览器中打开，支持:
  - 蜡烛图 + 均线叠加 (MA5/10/20/60)
  - 成交量柱状图
  - 技术指标副图 (MACD / KDJ / RSI)
  - 缩放、平移、悬停查看数值
  - 回测权益曲线对比
  - 多股归一化走势对比
"""

from __future__ import annotations
import json
import os
import time as _time
from datetime import datetime
from typing import Any

from mcp_finance.indicators import _sma, _ema, calc_kdj, calc_rsi

_ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"

def _arr(vals, default_null=False):
    """将 Python list 转为 JS array，None 转为 null 或 '-'"""
    if default_null:
        return json.dumps([v if v is not None else None for v in vals])
    return json.dumps([v if v is not None else "-" for v in vals])


_HTML_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="__CDN__"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#1a1a2e;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
#chart{{width:100vw;height:{height}}}
</style>
</head>
<body>
<div id="chart"></div>
<script>
var chart=echarts.init(document.getElementById("chart"),"dark");
{chart_js}
window.addEventListener("resize",function(){{chart.resize()}});
</script>
</body>
</html>""".replace("__CDN__", _ECHARTS_CDN)


def _wrap_html(chart_js, title="", height="100vh"):
    return _HTML_TPL.format(title=title, height=height, chart_js=chart_js)


# ═══════════════════════════════════════════════════════════════
# K 线图
# ═══════════════════════════════════════════════════════════════

def generate_kline_chart(
    kline_data,
    stock_name="",
    indicators=None,
    show_volume=True,
    show_macd=True,
    show_kdj=False,
    show_rsi=False,
    output_path="",
):
    """生成交互式 K 线 HTML 图表 (ECharts)"""
    if not kline_data:
        raise ValueError("K 线数据为空")

    dates = [k["日期"] for k in kline_data]
    opens = [float(k["开盘价"]) for k in kline_data]
    highs = [float(k["最高价"]) for k in kline_data]
    lows = [float(k["最低价"]) for k in kline_data]
    closes = [float(k["收盘价"]) for k in kline_data]
    volumes = [float(k.get("成交量(手)", 0) or 0) for k in kline_data]

    n = len(dates)

    # 均线
    ma5 = _sma(closes, 5) if n >= 5 else [None] * n
    ma10 = _sma(closes, 10) if n >= 10 else [None] * n
    ma20 = _sma(closes, 20) if n >= 20 else [None] * n
    ma60 = _sma(closes, 60) if n >= 60 else [None] * n

    # MACD — use calc_macd from indicators module
    from mcp_finance.indicators import calc_macd as _calc_macd
    macd_result = _calc_macd(closes, fast=12, slow=26, signal=9)
    dif = macd_result["DIF"]
    dea = macd_result["DEA"]
    macd_hist = macd_result["MACD"]

    # KDJ — use calc_kdj from indicators module
    from mcp_finance.indicators import calc_kdj as _calc_kdj
    kdj_result = _calc_kdj(highs, lows, closes, n=9)
    k_vals = kdj_result["K"]
    d_vals = kdj_result["D"]
    j_vals = kdj_result["J"]

    # RSI — use calc_rsi from indicators module
    rsi6 = calc_rsi(closes, 6)
    rsi14 = calc_rsi(closes, 14)
    rsi24 = calc_rsi(closes, 24)

    # OHLV data for candlestick
    ohlc_data = [[opens[i], closes[i], lows[i], highs[i]] for i in range(n)]
    vol_data = [[i, v, closes[i] >= opens[i] if i < n else True] for i, v in enumerate(volumes)]

    # 网格布局 — 固定像素高度，页面可滚动，面板间留间距
    MAIN_H = 500
    SUB_H = 220
    GAP = 16
    panels = [{"id": "main", "top": 0, "height": MAIN_H}]
    cur = MAIN_H + GAP
    if show_volume:
        panels.append({"id": "volume", "top": cur, "height": SUB_H})
        cur += SUB_H + GAP
    if show_macd:
        panels.append({"id": "macd", "top": cur, "height": SUB_H})
        cur += SUB_H + GAP
    if show_kdj:
        panels.append({"id": "kdj", "top": cur, "height": SUB_H})
        cur += SUB_H + GAP
    if show_rsi:
        panels.append({"id": "rsi", "top": cur, "height": SUB_H})
        cur += SUB_H + GAP
    total_height = cur - GAP  # 去掉末尾多余间距

    # 构建 ECharts option
    grids = []
    xaxes = []
    yaxes = []
    series = []

    for i, p in enumerate(panels):
        pid = p["id"]
        top = p['top']
        h = p['height']
        grids.append({"left": "8%", "right": "3%", "top": top, "height": h})
        show_label = "true" if i == len(panels) - 1 else "false"
        xaxes.append({
            "gridIndex": i, "type": "category", "data": dates,
            "axisLabel": {"show": i == len(panels) - 1},
            "axisLine": {"onZero": False}, "splitLine": {"show": False}
        })
        if pid == "main":
            yaxes.append({"gridIndex": i, "scale": True, "splitArea": {"show": True}})
        elif pid == "volume":
            yaxes.append({"gridIndex": i})
        elif pid == "macd":
            yaxes.append({"gridIndex": i, "scale": True})
        elif pid in ("kdj", "rsi"):
            yaxes.append({"gridIndex": i, "min": 0, "max": 100})

    gi = 0  # main grid index

    # K线
    series.append({
        "name": "K线", "type": "candlestick", "xAxisIndex": gi, "yAxisIndex": gi,
        "data": ohlc_data,
        "itemStyle": {"color": "#ef5350", "color0": "#26a69a", "borderColor": "#ef5350", "borderColor0": "#26a69a"}
    })

    # 均线
    for label, vals, color in [("MA5", ma5, "#FF9800"), ("MA10", ma10, "#2196F3"),
                                ("MA20", ma20, "#9C27B0"), ("MA60", ma60, "#4CAF50")]:
        series.append({
            "name": label, "type": "line", "xAxisIndex": gi, "yAxisIndex": gi,
            "data": [v if v is not None else None for v in vals],
            "smooth": True, "lineStyle": {"width": 1, "color": color}, "symbol": "none"
        })

    # 成交量
    if show_volume:
        gi += 1
        series.append({
            "name": "成交量", "type": "bar", "xAxisIndex": gi, "yAxisIndex": gi,
            "data": vol_data,
            "itemStyle": {
                "color": "function(p){return p.data[2]?'#ef5350':'#26a69a'}"
            }
        })

    # MACD
    if show_macd:
        gi += 1
        series.append({
            "name": "DIF", "type": "line", "xAxisIndex": gi, "yAxisIndex": gi,
            "data": [v if v is not None else None for v in dif],
            "lineStyle": {"color": "#FF9800"}, "symbol": "none"
        })
        series.append({
            "name": "DEA", "type": "line", "xAxisIndex": gi, "yAxisIndex": gi,
            "data": [v if v is not None else None for v in dea],
            "lineStyle": {"color": "#2196F3"}, "symbol": "none"
        })
        macd_bar = [[i, v] for i, v in enumerate(macd_hist)]
        series.append({
            "name": "MACD", "type": "bar", "xAxisIndex": gi, "yAxisIndex": gi,
            "data": macd_bar,
            "itemStyle": {
                "color": "function(p){return p.data[1]>=0?'#ef5350':'#26a69a'}"
            }
        })

    # KDJ
    if show_kdj:
        gi += 1
        for label, vals, color in [("K", k_vals, "#FF9800"), ("D", d_vals, "#2196F3"), ("J", j_vals, "#9C27B0")]:
            series.append({
                "name": label, "type": "line", "xAxisIndex": gi, "yAxisIndex": gi,
                "data": [v if v is not None else None for v in vals],
                "lineStyle": {"color": color}, "symbol": "none"
            })

    # RSI
    if show_rsi:
        gi += 1
        for label, vals, color in [("RSI6", rsi6, "#FF9800"), ("RSI14", rsi14, "#2196F3"), ("RSI24", rsi24, "#9C27B0")]:
            series.append({
                "name": label, "type": "line", "xAxisIndex": gi, "yAxisIndex": gi,
                "data": [v if v is not None else None for v in vals],
                "lineStyle": {"color": color}, "symbol": "none"
            })
        # Reference lines
        series.append({
            "name": "参考线", "type": "line", "xAxisIndex": gi, "yAxisIndex": gi,
            "markLine": {
                "silent": True, "symbol": "none",
                "lineStyle": {"color": "#666", "type": "dashed"},
                "data": [{"yAxis": 70}, {"yAxis": 30}]
            },
            "data": [], "symbol": "none"
        })

    # 图例
    legend = ["K线", "MA5", "MA10", "MA20", "MA60"]
    if show_volume: legend.append("成交量")
    if show_macd: legend.extend(["DIF", "DEA", "MACD"])
    if show_kdj: legend.extend(["K", "D", "J"])
    if show_rsi: legend.extend(["RSI6", "RSI14", "RSI24", "参考线"])

    # dataZoom range
    zoom_start = max(0, 100 - max(60, n * 100 // 250))
    datazoom_indices = list(range(len(panels)))

    option = {
        "animation": False,
        "grid": grids,
        "xAxis": xaxes,
        "yAxis": yaxes,
        "series": series,
        "dataZoom": [
            {"type": "inside", "xAxisIndex": datazoom_indices, "start": zoom_start, "end": 100},
            {"type": "slider", "xAxisIndex": datazoom_indices, "start": zoom_start, "end": 100, "height": 25, "bottom": 5}
        ],
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
        "legend": {"data": legend, "top": 5, "textStyle": {"color": "#ccc", "fontSize": 11}}
    }

    chart_js = "var option=" + json.dumps(option, ensure_ascii=False, default=str) + ";chart.setOption(option);"

    title = f"{stock_name or '股票'} — K线图"
    # BUG 修复: total_height 仅在 generate_kline_chart 内定义，此处为 K线图专属
    html = _wrap_html(chart_js, title=title, height=f"{total_height}px")

    if not output_path:
        chart_dir = os.path.join(os.path.dirname(__file__), "..", "charts")
        os.makedirs(chart_dir, exist_ok=True)
        ts = int(_time.time())
        safe_name = stock_name.replace(" ", "_").replace("/", "_") if stock_name else "stock"
        output_path = os.path.join(chart_dir, f"{safe_name}_kline_{ts}.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return os.path.abspath(output_path)


# ═══════════════════════════════════════════════════════════════
# 回测权益曲线对比图
# ═══════════════════════════════════════════════════════════════

def generate_backtest_chart(
    stock_name="",
    strategy_label="",
    strategy_curve=None,
    benchmark_label="买入持有",
    benchmark_curve=None,
    output_path="",
):
    """生成回测权益曲线对比图（策略 vs 基准）"""
    strategy_curve = strategy_curve or []
    benchmark_curve = benchmark_curve or []

    s_dates = [str(pt.get("日期", pt.get("date", ""))) for pt in strategy_curve]
    s_values = [float(pt.get("市值", pt.get("value", pt.get("equity", 0)))) for pt in strategy_curve]

    b_dates = [str(pt.get("日期", pt.get("date", ""))) for pt in benchmark_curve]
    b_values = [float(pt.get("市值", pt.get("value", pt.get("equity", 0)))) for pt in benchmark_curve]

    all_dates = s_dates if len(s_dates) >= len(b_dates) else b_dates

    option = {
        "animation": True,
        "grid": {"left": "10%", "right": "8%", "top": "12%", "bottom": "12%"},
        "xAxis": {"type": "category", "data": all_dates, "axisLabel": {"rotate": 30}},
        "yAxis": {
            "type": "value", "scale": True,
            "axisLabel": {"formatter": "function(v){return (v/10000).toFixed(0)+'万'}"}
        },
        "series": [
            {
                "name": strategy_label or "策略",
                "type": "line", "data": [v if v is not None else None for v in s_values],
                "smooth": True,
                "lineStyle": {"color": "#4F46E5", "width": 2},
                "areaStyle": {
                    "color": {
                        "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                        "colorStops": [
                            {"offset": 0, "color": "rgba(79,70,229,0.3)"},
                            {"offset": 1, "color": "rgba(79,70,229,0.02)"}
                        ]
                    }
                },
                "symbol": "none"
            },
            {
                "name": benchmark_label or "买入持有",
                "type": "line", "data": [v if v is not None else None for v in b_values],
                "smooth": True,
                "lineStyle": {"color": "#94A3B8", "width": 1.5, "type": "dashed"},
                "symbol": "none"
            }
        ],
        "dataZoom": [
            {"type": "inside", "start": 0, "end": 100},
            {"type": "slider", "start": 0, "end": 100, "height": 20, "bottom": 5}
        ],
        "tooltip": {
            "trigger": "axis",
            "formatter": "function(p){var r=p[0].axisValue+'<br/>';p.forEach(function(i){if(i.value!=null)r+=i.marker+' '+i.seriesName+': ¥'+i.value.toLocaleString()+'<br/>'});return r}"
        },
        "legend": {
            "data": [strategy_label or "策略", benchmark_label or "买入持有"],
            "top": 5, "textStyle": {"color": "#ccc"}
        }
    }

    chart_js = "var option=" + json.dumps(option, ensure_ascii=False, default=str) + ";chart.setOption(option);"

    title = f"回测权益曲线 — {stock_name}"
    # BUG-C2 修复: 原引用未定义的 total_height，导致回测图表永远生成失败
    html = _wrap_html(chart_js, title=title, height="500px")

    if not output_path:
        chart_dir = os.path.join(os.path.dirname(__file__), "..", "charts")
        os.makedirs(chart_dir, exist_ok=True)
        ts = int(_time.time())
        safe_name = stock_name.replace(" ", "_") if stock_name else "backtest"
        output_path = os.path.join(chart_dir, f"{safe_name}_backtest_{ts}.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return os.path.abspath(output_path)


# ═══════════════════════════════════════════════════════════════
# 多股对比图
# ═══════════════════════════════════════════════════════════════

def generate_comparison_chart(codes, days=120, output_path=""):
    """生成多只股票走势对比图 (归一化)"""
    from mcp_finance.api import handle_kline, _detect_market
    from mcp_finance.data import STOCK_MAPPING

    if len(codes) < 2:
        raise ValueError("至少需要2只股票")

    series_data = []
    legend_data = []

    for code in codes:
        name = STOCK_MAPPING.get(code, code)
        try:
            market = _detect_market(code)
            klines = handle_kline({"code": code, "market": market, "ktype": "daily", "limit": days})
        except Exception:
            continue
        if isinstance(klines, dict) and "error" in klines:
            klines = []
        if not isinstance(klines, list) or len(klines) < 10:
            continue

        _dates = [k["日期"] for k in klines]
        _closes = [float(k["收盘价"]) for k in klines]
        if _closes and _closes[0] > 0:
            base = _closes[0]
            normalized = [round(c / base * 100, 2) for c in _closes]
        else:
            normalized = _closes

        series_data.append({"name": f"{name}({code})", "dates": _dates[-days:], "values": normalized[-days:]})
        legend_data.append(f"{name}({code})")

    if not series_data:
        raise ValueError("无有效数据生成对比图")

    all_dates = max((s["dates"] for s in series_data), key=len)

    series = []
    for s in series_data:
        series.append({
            "name": s["name"], "type": "line",
            "data": [v if v is not None else None for v in s["values"]],
            "smooth": True, "symbol": "none", "lineStyle": {"width": 2}
        })

    option = {
        "animation": True,
        "grid": {"left": "10%", "right": "8%", "top": "12%", "bottom": "12%"},
        "xAxis": {"type": "category", "data": all_dates, "axisLabel": {"rotate": 30}},
        "yAxis": {"type": "value", "name": "归一化价格 (基值=100)", "scale": True},
        "series": series,
        "dataZoom": [
            {"type": "inside", "start": 0, "end": 100},
            {"type": "slider", "start": 0, "end": 100, "height": 20, "bottom": 5}
        ],
        "tooltip": {"trigger": "axis"},
        "legend": {"data": legend_data, "top": 5, "textStyle": {"color": "#ccc"}}
    }

    chart_js = "var option=" + json.dumps(option, ensure_ascii=False, default=str) + ";chart.setOption(option);"

    title = "股票走势对比 (归一化基值=100)"
    # BUG-C2 修复: 原引用未定义的 total_height，导致对比图生成失败
    html = _wrap_html(chart_js, title=title, height="500px")

    if not output_path:
        chart_dir = os.path.join(os.path.dirname(__file__), "..", "charts")
        os.makedirs(chart_dir, exist_ok=True)
        ts = int(_time.time())
        output_path = os.path.join(chart_dir, f"comparison_{ts}.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return os.path.abspath(output_path)


# ═══════════════════════════════════════════════════════════════
# MCP Handlers
# ═══════════════════════════════════════════════════════════════

def handle_plot_kline(arguments):
    """MCP 工具: plot_kline"""
    code = arguments.get("code", "600519")
    days = int(arguments.get("days", 120))
    ktype = arguments.get("ktype", "daily")
    show_macd = arguments.get("show_macd", True)
    show_kdj = arguments.get("show_kdj", False)
    show_rsi = arguments.get("show_rsi", False)

    from mcp_finance.api import handle_kline, _detect_market
    from mcp_finance.data import STOCK_MAPPING
    from mcp_finance.indicators import compute_all_indicators

    market = _detect_market(code)
    name = STOCK_MAPPING.get(code, code)

    klines = handle_kline({"code": code, "market": market, "ktype": ktype, "limit": days + 120})
    if isinstance(klines, dict) and "error" in klines:
        return {"error": True, "message": f"获取K线失败: {klines['error']}"}
    if not isinstance(klines, list) or len(klines) < 10:
        return {"error": True, "message": "K线数据不足"}

    klines = klines[-days:]

    ind = compute_all_indicators(klines)

    chart_dir = os.path.join(os.path.dirname(__file__), "..", "charts")
    os.makedirs(chart_dir, exist_ok=True)
    ts = int(_time.time())
    safe_name = name.replace(" ", "_").replace("/", "_").replace("*", "")
    output_path = os.path.join(chart_dir, f"{safe_name}_{ts}.html")

    path = generate_kline_chart(
        kline_data=klines,
        stock_name=f"{name}({code})",
        indicators=ind,
        show_macd=show_macd,
        show_kdj=show_kdj,
        show_rsi=show_rsi,
        output_path=output_path,
    )

    return {
        "股票": f"{name}({code})",
        "K线条数": len(klines),
        "HTML文件路径": path,
        "打开方式": "双击用浏览器打开 → 可缩放/平移/悬停查看每根K线数值",
        "最新收盘价": klines[-1]["收盘价"],
        "技术信号": ind.get("signals", []),
    }


def handle_comparison_chart(arguments):
    """多股对比图 handler"""
    codes = arguments["codes"]
    path = generate_comparison_chart(codes, arguments.get("days", 120))
    return {
        "对比股票": codes,
        "HTML文件路径": path,
        "打开方式": "双击用浏览器打开，可缩放/平移/悬停查看数值",
    }


# ═══════════════════════════════════════════════════════════════
# PNG 导出 (保留接口兼容)
# ═══════════════════════════════════════════════════════════════

def export_chart_png(html_path=""):
    """将 HTML 图表导出为 PNG（需要 kaleido）"""
    try:
        import kaleido
        return {"error": False, "message": "kaleido 已安装，PNG导出可用"}
    except ImportError:
        return {"error": True, "message": "需要安装 kaleido: pip install kaleido"}
