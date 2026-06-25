"""FastAPI Dashboard Server v3 — multi-source financial data web interface.
Complete rewrite with proper error handling and data normalization.
"""
from __future__ import annotations
import json, os, sys, traceback, math
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from mcp_finance.api import (
    handle_realtime_quote, handle_kline, handle_market_indices,
    handle_sector_ranking, handle_batch_quotes,
)
from mcp_finance.screener import handle_stock_screener
from mcp_finance.backtest import handle_backtest, handle_optimize, handle_walk_forward, handle_monte_carlo
from mcp_finance.analysis import handle_factor_screener
from mcp_finance.data import STOCK_MAPPING, HOT_STOCKS
from mcp_finance.logging_config import get_logger

logger = get_logger(__name__)
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="mcp-finance", version="3.0", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ═══════════════════════ Helpers ═══════════════════════
def _sf(v):
    try:
        if v is None: return None
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except: return None

def _safe_json(data):
    if isinstance(data, dict): return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)): return [_safe_json(v) for v in data]
    if hasattr(data, "item"): return data.item()
    if hasattr(data, "tolist"): return data.tolist()
    if isinstance(data, (int, float, str, bool, type(None))): return data
    return str(data)

def _ok(result): return JSONResponse({"data": _safe_json(result), "error": None})
def _err(msg): return JSONResponse({"data": None, "error": str(msg)})


# ═══════════════════════ Pages ═══════════════════════
@app.get("/", response_class=HTMLResponse)
async def index(): return HTMLResponse((TEMPLATE_DIR / "index.html").read_text("utf-8"))
@app.get("/screener", response_class=HTMLResponse)
async def screener_page(): return HTMLResponse((TEMPLATE_DIR / "screener.html").read_text("utf-8"))
@app.get("/backtest", response_class=HTMLResponse)
async def backtest_page(): return HTMLResponse((TEMPLATE_DIR / "backtest.html").read_text("utf-8"))


# ═══════════════════════ Market ═══════════════════════
@app.get("/api/market/indices")
async def api_indices(market: str = "a"):
    try:
        result = handle_market_indices({"market": market})
        return _ok(result)
    except Exception as e:
        return _err(str(e))

@app.get("/api/market/sectors")
async def api_sectors(type: str = "industry", top_n: int = 15):
    """Sector ranking: TDX for real-time prices, filtered by broad type."""
    try:
        from mcp_finance.api import _get_tdx
        tdx = _get_tdx()
        if tdx:
            df = tdx.get_board_list()
            if df is not None and not df.empty:
                df = df[df["price"] > 1].copy()
                df["涨跌幅"] = ((df["price"] - df["pre_close"]) / df["pre_close"] * 100).round(2)
                df["涨跌额"] = (df["price"] - df["pre_close"]).round(2)
                # Filter by broad type: industry boards typically start with 88, concept with 88 too
                # TDX boards don't have a clean type field, so we just sort by abs change
                df["_sort"] = df["涨跌幅"].abs()
                df = df.nlargest(top_n, "_sort")
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
                return _ok(result)
    except Exception as e:
        logger.warning(f"TDX sector: {e}")
    # Fallback to AKShare handler
    try:
        result = handle_sector_ranking({"sector_type": type, "top_n": top_n})
        return _ok(result)
    except Exception as e:
        return _err(str(e))

@app.get("/api/market/north_flow")
async def api_north_flow(days: int = 10):
    """North flow from AKShare stock_hsgt_hist_em, filtered to non-null values."""
    try:
        from mcp_finance.api import _get_ak
        ak = _get_ak()
        result = []
        for symbol in ["沪股通", "深股通"]:
            try:
                df = ak.stock_hsgt_hist_em(symbol=symbol)
                if df is not None and not df.empty:
                    # Get recent, filter out rows with null net flow
                    recent = df.tail(days * 2)  # get extra to account for nulls
                    count = 0
                    for _, row in recent.iterrows():
                        net = _sf(row.get("当日成交净买额"))
                        if net is not None:
                            result.append({
                                "日期": str(row["日期"])[:10],
                                "渠道": symbol,
                                "净买额": net,
                                "买入额": _sf(row.get("买入成交额")),
                                "卖出额": _sf(row.get("卖出成交额")),
                                "累计净买额": _sf(row.get("历史累计净买额")),
                                "资金流入": _sf(row.get("当日资金流入")),
                                "持股市值": _sf(row.get("持股市值")),
                            })
                            count += 1
                            if count >= days: break
            except Exception:
                pass
        if result:
            return _ok(result)
    except Exception as e:
        logger.warning(f"North flow: {e}")
    return JSONResponse({"data": [], "error": None, "note": "暂无北向资金数据"})

@app.get("/api/market/hot_stocks")
async def api_hot_stocks():
    try:
        a_codes = [s["代码"] for s in HOT_STOCKS if s.get("市场") == "A股"]
        result = handle_batch_quotes({"codes": a_codes, "market": "a"})
        return _ok(result)
    except Exception as e:
        return _err(str(e))


# ═══════════════════════ Stock ═══════════════════════
@app.get("/api/realtime_quote")
async def api_quote(code: str = "600519", market: str = "a"):
    try:
        result = handle_realtime_quote({"code": code, "market": market})
        return _ok(result)
    except Exception as e:
        return _err(str(e))

@app.get("/api/kline")
async def api_kline(code: str = "600519", market: str = "a", limit: int = 120):
    try:
        result = handle_kline({"code": code, "market": market, "ktype": "daily", "limit": limit, "adjust": "qfq"})
        return _ok(result)
    except Exception as e:
        return _err(str(e))

@app.get("/api/search")
async def api_search(keyword: str = "", top_n: int = 10):
    kw = keyword.lower().strip()
    matches = []
    for code, name in STOCK_MAPPING.items():
        if kw in code.lower() or kw in name.lower():
            matches.append({"code": code, "name": name})
            if len(matches) >= top_n: break
    return _ok(matches)


# ═══════════════════════ Screener ═══════════════════════
@app.post("/api/screener")
async def api_screener(request: Request):
    try:
        body = await request.json()
        args = {"top_n": int(body.get("top_n", 30))}
        for key in ["min_gain", "max_gain", "min_volume_ratio", "min_turnover",
                     "max_pe", "max_pb", "min_pb", "min_roe", "min_market_cap"]:
            v = body.get(key)
            if v is not None and v != "": args[key] = float(v)
        result = handle_stock_screener(args)
        # Normalize field names for frontend consumption
        items = result.get("matched", [])
        normalized = []
        for item in items:
            norm = {
                "代码": item.get("代码", ""),
                "名称": item.get("名称", ""),
                "最新价": _sf(item.get("最新价")),
                "涨跌幅": _sf(item.get("涨跌幅(%)")),
                "换手率": _sf(item.get("换手率(%)")),
                "市盈率": _sf(item.get("市盈率(动)")),
                "市净率": _sf(item.get("市净率(PB)")),
                "量比": _sf(item.get("量比")),
                "总市值": _sf(item.get("总市值(元)")),
                "振幅": _sf(item.get("振幅(%)")),
                "ROE": _sf(item.get("ROE(%)")),
            }
            normalized.append(norm)
        return JSONResponse({
            "data": normalized,
            "error": None,
            "meta": {"count": result.get("count", 0), "total_scanned": result.get("total_scanned", 0)}
        })
    except Exception as e:
        return _err(str(e))

@app.post("/api/factor_screener")
async def api_factor_screener(request: Request):
    try:
        body = await request.json()
        args = {"top_n": int(body.get("top_n", 30)), "min_market_cap": float(body.get("min_market_cap", 50))}
        result = handle_factor_screener(args)
        return _ok(result)
    except Exception as e:
        return _err(str(e))


# ═══════════════════════ Backtest ═══════════════════════
@app.post("/api/backtest")
async def api_backtest(request: Request):
    try:
        body = await request.json()
        args = {
            "code": body.get("code", "600519"),
            "strategy": body.get("strategy", "ma_cross"),
            "start_date": body.get("start_date"),
            "end_date": body.get("end_date"),
            "initial_capital": float(body.get("initial_capital", 100000)),
        }
        fp = body.get("fast_period"); sp = body.get("slow_period")
        if fp: args["fast_period"] = int(fp)
        if sp: args["slow_period"] = int(sp)
        result = handle_backtest(args)
        return _ok(result)
    except Exception as e:
        return _err(str(e))


# ═══════════════════════ Entry ═══════════════════════
def main():
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"\n  mcp-finance Dashboard -> http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

if __name__ == "__main__":
    main()
