"""mcp-finance Web Dashboard v6 — Robust multi-source financial data server."""
from __future__ import annotations
from typing import Any
import json, os, math, time, traceback, sys
# ── 自动加载 .env ──
try:
    from dotenv import load_dotenv
    _env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    load_dotenv(_env_file)
except ImportError:
    pass  # python-dotenv 未安装，用户需手动设置环境变量
from flask import Flask, jsonify, request, render_template

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcp_finance.api import (
    handle_realtime_quote, handle_kline, handle_market_indices,
    handle_north_flow, handle_batch_quotes, _safe_float,
    handle_sector_ranking, get_all_a_stocks_snapshot,
)
from mcp_finance.screener import handle_stock_screener
from mcp_finance.backtest import handle_backtest, handle_optimize, handle_walk_forward, handle_monte_carlo
from mcp_finance.data import HOT_STOCKS, STOCK_MAPPING
try:
    from mcp_finance.tushare_source import is_available as _ts_available, get_financial_indicators_batch as _ts_fin_batch
except ImportError:
    _ts_available = lambda: False
    _ts_fin_batch = lambda codes: {}

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_log = logging.getLogger("dashboard")

_log.info("mcp-finance Dashboard v6 starting...")

app = Flask(__name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"))
app.json.ensure_ascii = False


# ═══════════════ Helpers ═══════════════
def _sf(v):
    try:
        if v is None: return None
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except: return None

def _safe_call(handler, args):
    try:
        r = handler(args)
        return r if isinstance(r, dict) else {"data": r}
    except Exception as e:
        _log.error(f"{handler.__name__}: {traceback.format_exc()}")
        return {"error": True, "message": str(e)}


# ═══════════════ Pages ═══════════════
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/screener")
def screener_page():
    return render_template("screener.html")

@app.route("/backtest")
def backtest_page():
    return render_template("backtest.html")


# ═══════════════ Market Data ═══════════════
@app.route("/api/market/indices")
def api_indices():
    return jsonify(_safe_call(handle_market_indices, {"market": request.args.get("market", "a")}))


@app.route("/api/market/sectors")
def api_sectors():
    st = request.args.get("type", "industry")
    tn = int(request.args.get("top_n", 20))
    # Try TDX first
    try:
        from mcp_finance.api import _get_tdx
        tdx = _get_tdx()
        if tdx:
            df = tdx.get_board_list()
            if df is not None and not df.empty:
                df = df[df["price"] > 0.01].copy()
                codes = df["code"].astype(str)
                if st == "industry":
                    df = df[codes.str.startswith("880")]
                elif st == "concept":
                    df = df[codes.str.startswith("881")]
                if not df.empty:
                    df["涨跌幅"] = ((df["price"] - df["pre_close"]) / df["pre_close"] * 100).round(2)
                    df["涨跌额"] = (df["price"] - df["pre_close"]).round(2)
                    df["_sort"] = df["涨跌幅"].abs()
                    df = df.nlargest(tn, "_sort")
                    result = []
                    for _, row in df.iterrows():
                        result.append({
                            "代码": str(row.get("code", "")),
                            "名称": str(row.get("name", "")),
                            "最新价": _sf(row.get("price")),
                            "涨跌幅": _sf(row.get("涨跌幅")),
                            "涨跌额": _sf(row.get("涨跌额")),
                            "昨收": _sf(row.get("pre_close")),
                            "涨速": _sf(row.get("rise_speed")),
                        })
                    return jsonify({"data": result, "error": None})
    except Exception as e:
        _log.warning(f"TDX sectors: {e}")

    # Fallback to AKShare
    try:
        result = _safe_call(handle_sector_ranking, {"sector_type": st, "top_n": tn})
        if isinstance(result, dict) and not result.get("error"):
            items = result.get("data", result.get("ranking", []))
            return jsonify({"data": items if isinstance(items, list) else [], "error": None})
    except Exception as e:
        _log.warning(f"AKShare sectors fallback: {e}")

    return jsonify({"data": [], "error": "暂无板块数据"})


@app.route("/api/market/north_flow")
def api_north_flow():
    """North flow - try multiple sources"""
    days = min(int(request.args.get("days", 10)), 30)

    # Try AKShare handler first
    try:
        result = handle_north_flow({"days": days})
        if isinstance(result, dict) and not result.get("error"):
            data = result.get("data", result.get("北向资金", result.get("数据", [])))
            if data and len(data) > 0:
                return jsonify({"data": data, "error": None, "source": result.get("数据源", "AKShare")})
    except Exception as e:
        _log.warning(f"North flow AKShare: {e}")

    # Fallback: try AKShare directly with different API
    try:
        from mcp_finance.api import _get_ak
        ak = _get_ak()
        for sym in ["沪股通", "深股通", "港股通(沪)", "港股通(深)"]:
            try:
                df = ak.stock_hsgt_hist_em(symbol=sym)
                if df is not None and not df.empty:
                    df = df.tail(days)
                    data = []
                    for _, row in df.iterrows():
                        data.append({
                            "日期": str(row.get("日期", ""))[:10],
                            "渠道": sym or "沪深港通",
                            "净买额": _sf(row.get("当日成交净买额")),
                            "买入额": _sf(row.get("买入成交额")),
                            "卖出额": _sf(row.get("卖出成交额")),
                        })
                    if data:
                        return jsonify({"data": data, "error": None, "source": f"AKShare-{sym}"})
            except Exception:
                continue
    except Exception as e:
        _log.warning(f"North flow AKShare direct: {e}")

    # Fallback: try north flow without symbol
    try:
        from mcp_finance.api import _get_ak
        ak = _get_ak()
        df = ak.stock_hsgt_hist_em()
        if df is not None and not df.empty:
            df = df.tail(days)
            data = []
            for _, row in df.iterrows():
                data.append({
                    "日期": str(row.get("日期", ""))[:10],
                    "渠道": "沪深港通",
                    "净买额": _sf(row.get("当日成交净买额")),
                    "买入额": _sf(row.get("买入成交额")),
                    "卖出额": _sf(row.get("卖出成交额")),
                })
            if data:
                return jsonify({"data": data, "error": None, "source": "AKShare"})
    except Exception as e:
        _log.warning(f"North flow AKShare fallback: {e}")

    # Final fallback: try easy-tdx north flow if available
    try:
        from mcp_finance.api import _get_tdx
        tdx = _get_tdx()
        if tdx:
            df = tdx.get_north_flow()
            if df is not None and not df.empty:
                df = df.tail(days)
                data = _df_to_records_simple(df)
                if data:
                    return jsonify({"data": data, "error": None, "source": "TDX"})
    except Exception as e:
        _log.warning(f"North flow TDX: {e}")

    return jsonify({"data": [], "error": "暂无北向资金数据，请稍后重试"})


def _df_to_records_simple(df):
    """Simple DataFrame to records conversion."""
    import pandas as pd
    if df is None or df.empty: return []
    df = df.where(pd.notna(df), None)
    records = df.to_dict(orient="records")
    cleaned = []
    for row in records:
        cr = {}
        for k, v in row.items():
            if hasattr(v, "strftime"):
                cr[k] = v.strftime("%Y-%m-%d")
            elif hasattr(v, "item"):
                cr[k] = v.item()
            elif isinstance(v, float) and pd.isna(v):
                cr[k] = None
            else:
                cr[k] = v
        cleaned.append(cr)
    return cleaned


@app.route("/api/market/hot_stocks")
def api_hot_stocks():
    try:
        a_codes = [s["代码"] for s in HOT_STOCKS if s.get("市场") == "A股"]
        result = _safe_call(handle_batch_quotes, {"codes": a_codes, "market": "a"})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": True, "message": str(e)})


# ═══════════════ Stock APIs ═══════════════
@app.route("/api/realtime_quote")
def api_quote():
    code = request.args.get("code", "600519")
    market = request.args.get("market", "a")
    return jsonify(_safe_call(handle_realtime_quote, {"code": code, "market": market}))


@app.route("/api/kline")
def api_kline():
    code = request.args.get("code", "600519")
    market = request.args.get("market", "a")
    limit = int(request.args.get("limit", 120))
    return jsonify(_safe_call(handle_kline,
        {"code": code, "market": market, "ktype": "daily", "limit": limit, "adjust": "qfq"}))


@app.route("/api/search")
def api_search():
    kw = request.args.get("keyword", "").lower().strip()
    top_n = int(request.args.get("top_n", 10))
    matches = []
    for c, n in STOCK_MAPPING.items():
        if kw in c.lower() or kw in n.lower():
            matches.append({"code": c, "name": n})
            if len(matches) >= top_n:
                break
    return jsonify({"data": matches, "error": None})

@app.route("/api/financials")
def api_financials():
    """获取个股结构化财务数据"""
    code = request.args.get("code", "600519")
    market = request.args.get("market", "a")
    count = int(request.args.get("count", 4))
    return jsonify(_safe_call(handle_financials, {"code": code, "market": market, "count": count}))




# ═══════════════ Screener ═══════════════
@app.route("/api/screener", methods=["POST"])
def api_screener():
    d = request.get_json(silent=True) or {}
    args = {"top_n": int(d.get("top_n", 30))}
    field_map = {
        "min_gain": "min_gain", "max_gain": "max_gain",
        "min_volume_ratio": "min_volume_ratio", "min_turnover": "min_turnover",
        "max_pe": "max_pe", "max_pb": "max_pb",
        "min_market_cap": "min_market_cap", "min_roe": "min_roe", "min_pb": "min_pb"
    }
    for fk, ak in field_map.items():
        v = d.get(fk)
        if v is not None and v != "" and v != "None":
            args[ak] = float(v)

    raw = None

    # Fast path: TDX (always available, ~2s)
    try:
        from mcp_finance.api import _get_tdx
        from easy_tdx import Category
        import pandas as pd
        tdx = _get_tdx()
        if tdx:
            all_dfs = []
            for cat in [Category.SH, Category.SZ]:
                try:
                    df_cat = tdx.get_stock_quotes_list(cat, count=6000)
                    if df_cat is not None and not df_cat.empty:
                        all_dfs.append(df_cat)
                except Exception:
                    pass
            if all_dfs:
                df = pd.concat(all_dfs, ignore_index=True)
                matched = []
                for _, row in df.iterrows():
                    code = str(row.get("code", "")).zfill(6)
                    name = str(row.get("name", ""))
                    close = _sf(row.get("close"))
                    pre = _sf(row.get("pre_close"))
                    pct = None
                    if close and pre and pre != 0:
                        pct = round((close - pre) / pre * 100, 2)
                    turnover = _sf(row.get("turnover"))
                    amount = _sf(row.get("amount"))
                    vol_ratio = _sf(row.get("vol_ratio"))
                    if args.get("min_gain") and (pct is None or pct < args["min_gain"]):
                        continue
                    if args.get("max_gain") and pct and pct > args["max_gain"]:
                        continue
                    if args.get("min_turnover") and (turnover is None or turnover < args["min_turnover"]):
                        continue
                    if args.get("min_volume_ratio") and (vol_ratio is None or vol_ratio < args["min_volume_ratio"]):
                        continue
                    if args.get("min_market_cap") and (amount is None or amount < args["min_market_cap"] * 1e8):
                        continue
                    if args.get("max_pe") or args.get("max_pb") or args.get("min_roe") or args.get("min_pb"):
                        continue  # TDX lacks fundamental data, skip filter
                    matched.append({
                        "代码": code,
                        "名称": name,
                        "最新价": close,
                        "涨跌幅(%)": pct,
                        "换手率(%)": turnover,
                        "市盈率(动)": None,
                        "市净率(PB)": None,
                        "量比": vol_ratio,
                        "总市值(元)": None,
                        "振幅(%)": None,
                        "ROE(%)": None,
                    })
                    if len(matched) >= args.get("top_n", 30):
                        break
                raw = {"matched": matched, "count": len(matched), "total_scanned": len(df), "source": "TDX"}
    except Exception as e:
        _log.warning(f"TDX screener: {e}")

    # Fallback: AKShare (trading hours only, has PE/PB/ROE)
    if not raw or not raw.get("matched"):
        raw = _safe_call(handle_stock_screener, args)

    if isinstance(raw, dict) and "matched" in raw:
        items = raw.get("matched", [])
        normalized = []
        for it in items:
            normalized.append({
                "代码": it.get("代码", ""),
                "名称": it.get("名称", ""),
                "最新价": _sf(it.get("最新价")),
                "涨跌幅": _sf(it.get("涨跌幅") or it.get("涨跌幅(%)")),
                "换手率": _sf(it.get("换手率") or it.get("换手率(%)")),
                "市盈率": _sf(it.get("市盈率") or it.get("市盈率(动)")),
                "市净率": _sf(it.get("市净率") or it.get("市净率(PB)")),
                "量比": _sf(it.get("量比")),
                "总市值": _sf(it.get("总市值") or it.get("总市值(元)")),
                "振幅": _sf(it.get("振幅") or it.get("振幅(%)")),
                "ROE": _sf(it.get("ROE") or it.get("ROE(%)")),
                "毛利率": _sf(it.get("毛利率")),
                "净利率": _sf(it.get("净利率")),
                "营收增长率": _sf(it.get("营收增长率")),
            })
        # Tushare enrichment for TDX results (add PE/PB/ROE)
        if _ts_available() and normalized:
            try:
                codes = [it["代码"] for it in normalized]
                fin_data = _ts_fin_batch(codes)
                for it in normalized:
                    code = it["代码"]
                    if code in fin_data:
                        fd = fin_data[code]
                        if fd.get("pe") and not it.get("市盈率"): it["市盈率"] = fd["pe"]
                        if fd.get("pb") and not it.get("市净率"): it["市净率"] = fd["pb"]
                        if fd.get("roe"): it["ROE"] = fd["roe"]
                        if fd.get("总市值(元)"): it["总市值"] = fd["总市值(元)"]
            except Exception:
                pass

        return jsonify({
            "data": normalized,
            "error": None,
            "meta": {"count": raw.get("count", 0), "scanned": raw.get("total_scanned", 0),
                     "source": raw.get("source", "AKShare") + ("+Tushare" if _ts_available() else "")}
        })
    return jsonify(raw)


@app.route("/api/factor_screener", methods=["POST"])
def api_factor():
    """Multi-factor ranking - TDX fast path with AKShare fallback."""
    d = request.get_json(silent=True) or {}
    top_n = int(d.get("top_n", 30))
    min_mc = float(d.get("min_market_cap", 10))

    snap = None
    source = ""

    # Fast path: TDX snapshot (always available, ~1s)
    try:
        from mcp_finance.api import _get_tdx
        tdx = _get_tdx()
        if tdx:
            from easy_tdx import Category
            all_dfs = []
            for cat in [Category.SH, Category.SZ]:
                try:
                    df_cat = tdx.get_stock_quotes_list(cat, count=6000)
                    if df_cat is not None and not df_cat.empty:
                        all_dfs.append(df_cat)
                except Exception:
                    pass
            if all_dfs:
                import pandas as pd
                df = pd.concat(all_dfs, ignore_index=True)
                snap = []
                for _, row in df.iterrows():
                    code = str(row.get("code", "")).zfill(6)
                    name = str(row.get("name", ""))
                    close = _sf(row.get("close"))
                    pre_close = _sf(row.get("pre_close"))
                    pct_chg = None
                    if close and pre_close and pre_close != 0:
                        pct_chg = round((close - pre_close) / pre_close * 100, 2)
                    snap.append({
                        "代码": code,
                        "名称": name,
                        "最新价": close,
                        "涨跌幅": pct_chg,
                        "成交额": _sf(row.get("amount")),
                        "成交量": _sf(row.get("vol")),
                    })
                source = "TDX"
    except Exception as e:
        _log.warning(f"TDX snapshot: {e}")

    # Fallback: AKShare (only during trading hours, ~20s)
    if not snap:
        try:
            snap = get_all_a_stocks_snapshot()
            if snap:
                source = "AKShare"
        except Exception as e:
            _log.warning(f"AKShare snapshot: {e}")

    if not snap:
        return jsonify({"data": [], "error": "全市场数据不可用（非交易时段），请交易时段重试"})

    scored = []
    for s in snap:
        try:
            # Normalize field names (TDX vs AKShare)
            code = str(s.get("代码", s.get("code", "")))
            name = str(s.get("名称", s.get("name", "")))
            if not code or len(code) < 6:
                continue
            if "ST" in name or "*ST" in name:
                continue

            gain = _sf(s.get("涨跌幅", s.get("pct_chg"))) or 0
            price = _sf(s.get("最新价", s.get("price"))) or 0
            amount = _sf(s.get("成交额", s.get("amount"))) or 0
            volume = _sf(s.get("成交量", s.get("volume"))) or 0

            if amount < min_mc * 1e7:
                continue

            m_score = min(50, max(0, 30 + gain * 2.5))
            a_score = min(20, max(5, 10 + (math.log10(max(amount, 10000)) / 2 - 4)))
            p_score = min(15, max(3, 5 + math.log10(max(price, 0.1)) * 3))
            v_score = min(15, max(3, 5 + math.log10(max(volume, 100)) / 2))

            total = min(100, max(0, round(m_score + a_score + p_score + v_score, 1)))

            scored.append({
                "代码": code,
                "名称": name,
                "最新价": price,
                "涨跌幅": round(gain, 2),
                "市盈率": None,
                "市净率": None,
                "换手率": None,
                "总市值": amount,
                "成交额": amount,
                "综合评分": total,
                "动量得分": round(m_score),
                "价值得分": 0,
                "质量得分": 0,
                "增长得分": round(a_score),
                "波动得分": 0,
            })
        except Exception:
            continue

    scored.sort(key=lambda x: x["综合评分"], reverse=True)
    top = scored[:top_n]

    # Tushare enrichment: add PE/PB/ROE
    if _ts_available() and top:
        try:
            codes = [s["代码"] for s in top]
            fin_data = _ts_fin_batch(codes)
            for s in top:
                code = s["代码"]
                if code in fin_data:
                    fd = fin_data[code]
                    if fd.get("pe"): s["市盈率"] = fd["pe"]
                    if fd.get("pb"): s["市净率"] = fd["pb"]
                    if fd.get("总市值(元)"): s["总市值"] = fd["总市值(元)"]
        except Exception:
            pass

    try:
        return jsonify({
            "data": top,
            "error": None,
            "meta": {
                "count": len(top),
                "scanned": len(scored),
                "source": source,
                "note": "评分基于动量+活跃度，PE/PB/ROE 数据源: " + source + ("+Tushare" if _ts_available() else "")
            }
        })
    except Exception as e:
        _log.error(f"Factor screener: {traceback.format_exc()}")
        return jsonify({"data": [], "error": str(e)})

@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    d = request.get_json(silent=True) or {}
    args = {
        "code": d.get("code", "000001"),
        "strategy": d.get("strategy", "ma_cross"),
        "start_date": d.get("start_date", "2025-01-01"),
        # BUG-10 修复: 原来硬编码 "2026-06-24"，日期过期后所有未指定结束日期的回测静默使用过去日期
        # 修复为传 None，_run_single_backtest 会自动用 datetime.now()
        "end_date": d.get("end_date") or None,
        "initial_capital": float(d.get("initial_capital", 200000)),
        "generate_chart": False,
    }
    if d.get("fast_period") is not None: args["fast_period"] = int(d["fast_period"])
    if d.get("slow_period") is not None: args["slow_period"] = int(d["slow_period"])
    if d.get("slippage_type"): args["slippage_type"] = d["slippage_type"]
    if d.get("slippage_value"): args["slippage_value"] = float(d["slippage_value"])
    if d.get("strategy_config"): args["strategy_config"] = d["strategy_config"]

    result = _safe_call(handle_backtest, args)
    return jsonify(result)


@app.route("/api/optimize", methods=["POST"])
def api_optimize():
    d = request.get_json(silent=True) or {}
    args = {"code": d.get("code","000001"), "strategy": d.get("strategy","ma_cross"),
            "optimization_method": d.get("optimization_method","bayesian"), "metric": d.get("metric","sharpe")}
    for k in ("fast_min","fast_max","slow_min","slow_max","fast_step","slow_step","n_trials"):
        if k in d: args[k] = int(d[k])
    if d.get("start_date"): args["start_date"] = d["start_date"]
    if d.get("end_date"): args["end_date"] = d["end_date"]
    return jsonify(_safe_call(handle_optimize, args))


@app.route("/api/walk_forward", methods=["POST"])
def api_walk_forward():
    d = request.get_json(silent=True) or {}
    args = {
        "code": d.get("code", "000001"),
        "strategy": d.get("strategy", "ma_cross"),
        # BUG-11 修复: 加入 metric 参数，原来缺少导致用户无法指定优化目标
        "metric": d.get("metric", "sharpe"),
    }
    for k in ("train_years", "test_months", "step_months", "fast_min", "fast_max", "slow_min", "slow_max", "n_trials"):
        if k in d: args[k] = float(d[k]) if k == "train_years" else int(d[k])
    return jsonify(_safe_call(handle_walk_forward, args))


@app.route("/api/monte_carlo", methods=["POST"])
def api_monte_carlo():
    d = request.get_json(silent=True) or {}
    args = {"code": d.get("code","000001"), "strategy": d.get("strategy","ma_cross")}
    for k in ("fast_period","slow_period","n_simulations"):
        if k in d: args[k] = int(d[k])
    if d.get("start_date"): args["start_date"] = d["start_date"]
    if d.get("end_date"): args["end_date"] = d["end_date"]
    return jsonify(_safe_call(handle_monte_carlo, args))


# ═══════════════ Entry ═══════════════
def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"\n  mcp-finance Dashboard v6 -> http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()

