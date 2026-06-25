"""
三数据源封装层：easy-tdx (主) + AKShare (辅) + yfinance (兜底)

全市场数据源：A股 / 期货 / 港股 / 美股 / 指数 / 板块 / 资金流向
- easy-tdx (通达信TCP协议): 毫秒级A股实时行情+K线，日均线/周/月
- AKShare (新浪/同花顺): 港股、美股、财务数据、板块排行、龙虎榜等
- yfinance (Yahoo Finance): 港股/美股 K线+行情兜底（AKShare 失败时降级）

设计原则：
  - A股实时行情/K线优先走 easy-tdx（毫秒级，无超时风险）
  - 港股/美股走 AKShare 新浪 daily 接口 → yfinance 兜底
  - 财务/板块/龙虎榜走 AKShare 同花顺/新浪源
  - 全市场快照用 easy-tdx get_stock_quotes_list（秒级）或 AKShare 新浪
  - 所有接口都有 try/except 兜底，确保不崩溃
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
import os, threading
import pandas as pd

from mcp_finance.logging_config import get_logger as _get_logger
_api_logger = _get_logger(__name__)


from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import atexit
# ── 共享线程池 ──────────────────────────────────────────────────
# _API_EXECUTOR: 业务请求池（行情/K线/AKShare 网络调用等）
# _tdx_init_lock + threading.Thread: 用于 easy-tdx 懒加载初始化，防止 TCP 挂死污染业务池
_API_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix='mcp-finance-api')
_tdx_init_lock = threading.Lock()
atexit.register(lambda: _API_EXECUTOR.shutdown(wait=False))
# ── 网络超时工具（通用）─────────────────────────────────────────────
# 所有 AKShare 网络调用必须通过此工具，防止线程池耗尽
_NET_TIMEOUT = 15  # 默认网络超时（秒），可通过 MCP_FINANCE_TIMEOUT 环境变量覆盖

def _call_with_net_timeout(func, timeout=None):
    """通用网络调用超时保护 — 线程池执行，最多等 timeout 秒

    如果超时，返回 None（不抛异常，调用方自行降级）。
    使用 ThreadPoolExecutor 替代裸 Thread，超时后 future.cancel()
    可通知线程停止，避免泄漏线程长期占用资源。
    """
    import os as _os
    t = timeout or int(_os.environ.get("MCP_FINANCE_TIMEOUT", str(_NET_TIMEOUT)))
    try:
        future = _API_EXECUTOR.submit(func)
        return future.result(timeout=t)
    except FuturesTimeoutError:
        future.cancel()
        return None
    except Exception:
        return None



# ── easy-tdx 客户端（懒加载）──────────────────────────────────────
_tdx_client = None

def _get_tdx():
    """懒加载 easy-tdx 统一客户端（5s 超时保护，防止 TCP 挂死）
    
    使用 threading.Thread + 5s join 超时保护，防止 TCP 阻塞污染业务线程池。
    双重检查锁防止并发重复初始化。
    """
    global _tdx_client
    if _tdx_client is not None:
        return _tdx_client

    with _tdx_init_lock:
        if _tdx_client is not None:
            return _tdx_client

        import threading as _th
        result = [None]
        error = [None]

        def _init():
            try:
                from easy_tdx import UnifiedTdxClient, Market, Period, Adjust
                client = UnifiedTdxClient()
                client.Market = Market
                client.Period = Period
                client.Adjust = Adjust
                result[0] = client
            except Exception as e:
                error[0] = e

        t = _th.Thread(target=_init, daemon=True, name="tdx-init")
        t.start()
        t.join(timeout=5)
        if t.is_alive():
            raise TimeoutError("easy-tdx 连接通达信服务器超时 (5s)")
        if error[0] is not None:
            if isinstance(error[0], ConnectionError):
                raise error[0]
            raise ConnectionError(f"easy-tdx 连接通达信服务器失败: {error[0]}")
        _tdx_client = result[0]
    return _tdx_client

def _tdx_market(code: str):
    """根据股票代码返回 easy-tdx Market 枚举"""
    from easy_tdx import Market
    if code.startswith(("6", "9")):
        return Market.SH
    elif code.startswith(("0", "2", "3")):
        return Market.SZ
    elif code.startswith(("4", "8")):
        return Market.BJ
    return Market.SZ


# ── 代码格式转换 ──────────────────────────────────────────────────
def _to_sina_code(code: str) -> str:
    """将裸代码（如 600519）转为新浪格式前缀代码（如 sh600519）"""
    code = code.strip()
    if len(code) >= 2 and code[:2].lower() in ('sh', 'sz', 'bj'):
        return code.lower()
    if code.startswith('6') or code.startswith('9'):
        return f"sh{code}"
    elif code.startswith('0') or code.startswith('3') or code.startswith('2'):
        return f"sz{code}"
    elif code.startswith('4') or code.startswith('8'):
        return f"bj{code}"
    return code


# ── 数据源配置 ──────────────────────────────────────────────────
_SPOT_CACHE_TTL = 600.0  # 10 分钟，减少全市场快照重拉频率  # 全市场快照缓存 5 分钟

from mcp_finance.cache import TTLCache
_spot_cache = TTLCache(default_ttl=_SPOT_CACHE_TTL)
_spot_cache_lock = threading.Lock()


def _get_ak():
    """直接导入 akshare，不做任何包装"""
    try:
        import akshare as ak
        return ak
    except ImportError:
        raise ImportError("akshare 未安装，请运行: pip install akshare")


def _get_yf():
    """懒加载 yfinance"""
    try:
        import yfinance as yf
        return yf
    except ImportError:
        raise ImportError("yfinance 未安装，请运行: pip install yfinance")




def _get_ts():
    """Lazy-load tushare (requires TUSHARE_TOKEN env var).

    Returns pro_api() if token is set and valid, None otherwise.
    Callers should gracefully fall back to TDX/AKShare.
    """
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        return None
    try:
        import tushare as ts
        ts.set_token(token)
        return ts.pro_api()
    except ImportError:
        return None
    except Exception:
        return None
def _lookup_name(code: str, market: str = "a") -> str:
    """多数据源名称查找：STOCK_MAPPING → HOT_STOCKS → yfinance info"""
    from mcp_finance.data import STOCK_MAPPING, HOT_STOCKS
    name = STOCK_MAPPING.get(code, "")
    if name:
        return name
    for s in HOT_STOCKS:
        if s["代码"] == code:
            return s["名称"]
    # yfinance 兜底
    try:
        yf = _get_yf()
        ticker = yf.Ticker(code)
        info = ticker.info
        name = info.get("longName") or info.get("shortName") or ""
        if name:
            return name
    except Exception:
        pass
    return ""


# ── easy-tdx 调用超时工具 ─────────────────────────────────────────
def _call_tdx_with_timeout(func, timeout=10):
    """统一 easy-tdx 调用超时保护（防止 TCP 挂死）"""
    import threading as _t
    result = [None]
    done = [False]
    def _target():
        try:
            result[0] = func()
            done[0] = True
        except Exception:
            pass
    th = _t.Thread(target=_target, daemon=True)
    th.start()
    th.join(timeout=timeout)
    return result[0] if done[0] else None


def _resample_kline(df, period, date_col="date"):
    """将日线 DataFrame 聚合为周线或月线

    Args:
        df: 日线 DataFrame
        period: "weekly" 或 "monthly"
        date_col: 日期列名

    Returns:
        聚合后的 DataFrame (reset_index)
    """
    df[date_col] = pd.to_datetime(df[date_col])
    df.set_index(date_col, inplace=True)
    rule = "W" if period == "weekly" else "ME"
    df = df.resample(rule).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum", "amount": "sum",
    }).dropna().reset_index()
    return df


def _safe_float(val):
    if val is None: return None
    try: return round(float(val), 2)
    except: return None


def _df_to_records(df, limit=None):
    if df is None or df.empty: return []
    df = df.where(pd.notna(df), None)
    if limit: df = df.tail(limit)
    records = df.to_dict(orient="records")
    cleaned = []
    for row in records:
        cr = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                cr[k] = v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v)
            elif hasattr(v, "item"): cr[k] = v.item()
            elif isinstance(v, float) and pd.isna(v): cr[k] = None
            else: cr[k] = v
        cleaned.append(cr)
    return cleaned


# ── 统一磁盘缓存（K线）─────────────────────────────────────
from mcp_finance.cache import CacheManager
_kline_cache = CacheManager(
    disk_dir=os.path.join(os.path.dirname(__file__), ".kline_cache"),
    disk_ttl=21600,  # 6 小时
)

# ================================================================
# 0. 实时行情 — 单股查询（不拉全市场）
# ================================================================


def _get_single_quote(code, market="a"):
    """单股实时行情 — easy-tdx 优先（5s 超时保护），AKShare 新浪兜底"""
    if market == "a":
        # ── 策略1: easy-tdx 实时报价（线程池超时 5s，防止 TCP 挂死）──
        def _tdx_fetch():
            tdx = _get_tdx()
            mkt = _tdx_market(code)
            return tdx.get_stock_quotes([(mkt, code)])

        tdx_result = None
        try:
            future = _API_EXECUTOR.submit(_tdx_fetch)
            try:
                tdx_result = future.result(timeout=5)
            except (FuturesTimeoutError, Exception) as e:
                _api_logger.warning("easy-tdx 实时行情超时或异常: %s [%s]", type(e).__name__, code)
                pass  # 超时或异常，走策略2
        except Exception as e:
            _api_logger.warning("easy-tdx 实时行情 submit 异常: %s [%s]", type(e).__name__, code)
            pass  # submit 本身异常也走策略2

        if tdx_result is not None and not tdx_result.empty:
            r = tdx_result.iloc[0].to_dict()
            r["总市值"] = _safe_float(r.get("total_market_cap_ab"))
            return r

        # ── 策略2: AKShare 单日 K线（秒级，仅拉取单只股票）──
        try:
            ak = _get_ak()
            sina_code = _to_sina_code(code)
            df = _call_with_net_timeout(lambda: ak.stock_zh_a_daily(symbol=sina_code, adjust="qfq"))
            if df is not None and not df.empty:
                r = df.iloc[-1].to_dict()
                if "名称" not in r or not r.get("名称"):
                    from mcp_finance.data import STOCK_MAPPING
                    r["名称"] = STOCK_MAPPING.get(code, "")
                return r
        except Exception as e:
            _api_logger.warning("AKShare A股行情降级失败: %s [%s]", e, code)
        return None
    # ── 港股/美股：AKShare Sina _daily 接口 ──
    ak = _get_ak()
    try:
        fn_map = {"hk": lambda: ak.stock_hk_daily(symbol=code, adjust=""),
                  "us": lambda: ak.stock_us_daily(symbol=code, adjust="")}
        fn = fn_map.get(market)
        if fn:
            df = fn()
            if df is not None and not df.empty:
                r = df.iloc[-1].to_dict()
                from mcp_finance.data import STOCK_MAPPING, HOT_STOCKS
                if len(df) >= 2:
                    r["pre_close"] = df.iloc[-2]["close"]
                # 先查 STOCK_MAPPING (A股)，再查 HOT_STOCKS (港股/美股)
                name = STOCK_MAPPING.get(code, "")
                if not name:
                    for s in HOT_STOCKS:
                        if s["代码"] == code:
                            name = s["名称"]
                            break
                r["名称"] = r.get("名称", name)
                return r
    except Exception as e:
        _api_logger.warning("AKShare 港股/美股行情失败: %s [%s]", e, code)

    # ── 策略3: yfinance 兜底（港股/美股） ──
    try:
        yf = _get_yf()
        ticker = yf.Ticker(code)
        df = ticker.history(period="5d")
        if df is not None and not df.empty:
            r = df.iloc[-1].to_dict()
            # yfinance 返回的列与 AKShare 不同，映射一下
            r["close"] = r.get("Close")
            r["open"] = r.get("Open")
            r["high"] = r.get("High")
            r["low"] = r.get("Low")
            r["volume"] = r.get("Volume")
            if len(df) >= 2:
                r["pre_close"] = df.iloc[-2]["Close"]
            r["名称"] = _lookup_name(code, market)
            return r
    except Exception as e:
        _api_logger.warning("yfinance 港股/美股行情降级失败: %s [%s]", e, code)

    return None


def _parse_kline_row(row):
    """将 K 线行转为实时行情字典（统一字段名）

    支持多种列名格式:
    - 新浪中文: '最新价','涨跌幅','今开','昨收','最高','最低','成交量','成交额'
    - 新浪日K英文: 'close','open','high','low','volume','amount'
    - easy-tdx: 'close','open','high','low','vol','amount','name'
    - 东方财富中文: '收盘','开盘','最高','最低','成交量','成交额'
    """
    close = row.get("最新价") or row.get("收盘") or row.get("close")
    pre_close = row.get("昨收") or row.get("pre_close") or row.get("prev_close")
    volume = row.get("成交量") or row.get("volume") or row.get("vol")
    amount = row.get("成交额") or row.get("amount")
    name = row.get("名称") or row.get("name")
    turnover = row.get("换手率") or row.get("turnover")

    close_val = _safe_float(close)
    pre_close_val = _safe_float(pre_close)
    if close_val is not None and pre_close_val is not None and pre_close_val != 0:
        change_pct = _safe_float(row.get("涨跌幅") or row.get("pct_change")) or round((close_val - pre_close_val) / pre_close_val * 100, 2)
        change_amt = _safe_float(row.get("涨跌额")) or round(close_val - pre_close_val, 2)
    else:
        change_pct = _safe_float(row.get("涨跌幅") or row.get("pct_change"))
        change_amt = _safe_float(row.get("涨跌额"))

    return {
        "最新价": close_val,
        "涨跌幅": change_pct,
        "涨跌额": change_amt,
        "成交量(手)": _safe_float(volume),
        "成交额(元)": _safe_float(amount),
        "今开": _safe_float(row.get("今开") or row.get("开盘") or row.get("open")),
        "昨收": pre_close_val,
        "最高": _safe_float(row.get("最高") or row.get("high")),
        "最低": _safe_float(row.get("最低") or row.get("low")),
        "名称": name or "",
        "换手率": _safe_float(turnover),
    }


# 全市场快照加载状态: None=未加载, True=加载中, False=加载完成
_all_stocks_loading = False
_all_stocks_loading_lock = threading.Lock()

def _fetch_all_a_stocks_cache():
    """获取全市场 A 股快照（仅用于选股器，60s 超时保护）

    直接调用 ak.stock_zh_a_spot()，用线程超时保护防止永久挂死。
    结果缓存 10 分钟，防止缓存惊群。
    注意：此函数拉取全市场 ~5000 只股票，可能需 20-30 秒。
    """
    global _all_stocks_loading
    cache_key = "all_a_stocks"

    # 1. 快速检查缓存
    cached = _spot_cache.get(cache_key)
    if cached is not None:
        return cached

    # 2. 防止缓存惊群: 如果已有请求在加载中，等待它完成
    with _all_stocks_loading_lock:
        if _all_stocks_loading:
            # 已有线程在加载，等待最多 65s（60s fetch + 5s margin）
            _api_logger.info("全市场快照加载中，等待已有请求完成...")
            for _ in range(65):
                time.sleep(1)
                cached = _spot_cache.get(cache_key)
                if cached is not None:
                    return cached
            _api_logger.warning("全市场快照等待超时，返回 None")
            return None
        _all_stocks_loading = True

    try:
        df = None
        try:
            future = _API_EXECUTOR.submit(lambda: _get_ak().stock_zh_a_spot())
            try:
                df = future.result(timeout=60)
            except FuturesTimeoutError:
                future.cancel()
            except Exception as e:
                _api_logger.warning("全市场快照 future.result 异常: %s", e)
                pass
        except Exception as e:
            _api_logger.warning("全市场快照 submit 异常: %s", e)
            pass

        if df is not None and not df.empty:
            _spot_cache.set(cache_key, df, ttl=_SPOT_CACHE_TTL)
        return df
    finally:
        with _all_stocks_loading_lock:
            _all_stocks_loading = False

# ================================================================
# 1. 实时行情（单只股票）
# ================================================================

def get_realtime_quote_a(code):
    """A股实时行情 — 用最近日 K 线查询，不拉全市场"""
    ak = _get_ak()
    try:
        row = _get_single_quote(code, market="a")
        if row is not None:
            q = _parse_kline_row(row)
            # 查找股票名称
            name = row.get("名称", "")
            if not name:
                from mcp_finance.data import STOCK_MAPPING
                name = STOCK_MAPPING.get(code, "")
            # easy-tdx 返回的数据有 'market' 原始字段，AKShare 没有
            data_source = "easy-tdx" if "market" in row and isinstance(row.get("market"), (int, float)) else "AKShare-日K(昨收)"
            result = {
                "代码": code, "名称": name,
                "最新价": q["最新价"], "涨跌幅": q["涨跌幅"],
                "涨跌额": q["涨跌额"],
                "成交量(手)": q["成交量(手)"],
                "成交额(元)": q["成交额(元)"],
                "今开": q["今开"], "昨收": q["昨收"],
                "最高": q["最高"], "最低": q["最低"],
                "市场": "A股", "数据源": data_source,
            }
            return result
    except Exception as e:
        _api_logger.warning("A股实时行情获取失败: %s [%s]", e, code)
        pass

    # 兜底：本地数据
    from mcp_finance.data import STOCK_MAPPING
    if code in STOCK_MAPPING:
        return {
            "代码": code, "名称": STOCK_MAPPING[code],
            "最新价": None, "涨跌幅": None, "涨跌额": None,
            "今开": None, "昨收": None, "最高": None, "最低": None,
            "成交量(手)": None, "成交额(元)": None,
            "市场": "A股", "数据源": "本地(离线)",
            "提示": "实时行情数据源暂不可用，显示本地缓存的名称信息",
        }

    return {"error": f"未找到股票 {code}，请检查代码是否正确"}
def _get_realtime_quote_overseas(code: str, market: str) -> dict:
    """港股/美股实时行情统一函数"""
    market_label = "港股" if market == "hk" else "美股"
    try:
        row = _get_single_quote(code, market=market)
        if row is not None:
            q = _parse_kline_row(row)
            return {
                "代码": code, "名称": row.get("名称", ""),
                "最新价": q["最新价"],
                "涨跌幅": q["涨跌幅"],
                "涨跌额": q["涨跌额"],
                "今开": q["今开"],
                "昨收": q["昨收"],
                "最高": q["最高"],
                "最低": q["最低"],
                "成交量": q["成交量(手)"],
                "成交额": q["成交额(元)"],
                "市场": market_label, "数据源": "AKShare-K线",
            }
        return {"error": f"未找到{market_label} {code}"}
    except Exception as e:
        return {"error": f"获取{market_label}行情失败: {e}"}


def get_realtime_quote_hk(code):
    """港股实时行情 — 用最近日 K 线查询"""
    return _get_realtime_quote_overseas(code, market="hk")


def get_realtime_quote_us(code):
    """美股实时行情 — 用最近日 K 线查询"""
    return _get_realtime_quote_overseas(code, market="us")


def get_realtime_quote_futures(code):
    """期货实时行情"""
    ak = _get_ak()
    try:
        df = ak.futures_zh_spot(symbol=code, market="CF", adjust="0")
        if df is not None and not df.empty:
            r = df.iloc[0]
            return {
                "代码": code,
                "名称": r.get("name", r.get("名称", "")),
                "最新价": _safe_float(r.get("trade", r.get("最新价"))),
                "涨跌幅": _safe_float(r.get("changepercent", r.get("涨跌幅"))),
                "涨跌额": _safe_float(r.get("change", r.get("涨跌额"))),
                "今开": _safe_float(r.get("open", r.get("今开"))),
                "昨收": _safe_float(r.get("settlement", r.get("昨收"))),
                "最高": _safe_float(r.get("high", r.get("最高"))),
                "最低": _safe_float(r.get("low", r.get("最低"))),
                "成交量": _safe_float(r.get("volume", r.get("成交量"))),
                "持仓量": _safe_float(r.get("position", r.get("持仓量"))),
                "市场": "期货", "数据源": "AKShare",
            }
        return {"error": f"未找到期货 {code}"}
    except Exception as e:
        return {"error": f"获取期货行情失败: {e}"}


# ================================================================
# 2. K线数据
# ================================================================

def get_kline_a(code, period="daily", adjust="qfq", limit=120):
    """A股 K线 — easy-tdx 优先（毫秒级），AKShare 新浪兜底，带磁盘缓存 6h"""
    cached = _kline_cache.get(f"kline:{code}:{period}:{adjust}", layer="disk")
    if cached and len(cached) >= limit:
        return cached[-limit:]

    # 校验 period
    if period not in {"daily", "weekly", "monthly"}:
        return [{"error": f"不支持的K线类型: {period}，支持 daily/weekly/monthly"}]


    records = []

    # ── 策略1: easy-tdx（毫秒级，10s 超时保护）──
    try:
        def _tdx_fetch():
            tdx = _get_tdx()
            p = {"daily": tdx.Period.DAILY, "weekly": tdx.Period.WEEKLY, "monthly": tdx.Period.MONTHLY}.get(period, tdx.Period.DAILY)
            a = {"qfq": tdx.Adjust.QFQ, "hfq": tdx.Adjust.HFQ}.get(adjust, tdx.Adjust.NONE)
            return tdx.get_stock_kline(_tdx_market(code), code, period=p, count=limit, adjust=a)
        df = _call_tdx_with_timeout(_tdx_fetch, timeout=10)
        if df is not None and not df.empty:
            for _, row in df.tail(limit).iterrows():
                records.append({
                    "日期": str(row.get("datetime", ""))[:10],
                    "开盘价": _safe_float(row.get("open")),
                    "收盘价": _safe_float(row.get("close")),
                    "最高价": _safe_float(row.get("high")),
                    "最低价": _safe_float(row.get("low")),
                    "成交量(手)": _safe_float(row.get("vol") or row.get("volume")),
                    "成交额(元)": _safe_float(row.get("amount")),
                    "涨跌幅": _safe_float(row.get("pct_change")),
                    "换手率": _safe_float(row.get("turnover")),
                })
    except Exception as e:
        _api_logger.warning("A股K线 easy-tdx 获取失败: %s [%s]", e, code)
        pass

    # ── 策略2: AKShare 新浪 daily ──
    if not records:
        try:
            ak = _get_ak()
            sina_code = _to_sina_code(code)
            df = ak.stock_zh_a_daily(symbol=sina_code, adjust=adjust)
            if df is not None and not df.empty:
                if period in ("weekly", "monthly"):
                    df = _resample_kline(df, period)
                for _, row in df.tail(limit).iterrows():
                    records.append({
                        "日期": str(row.get("date", ""))[:10],
                        "开盘价": _safe_float(row.get("open")),
                        "收盘价": _safe_float(row.get("close")),
                        "最高价": _safe_float(row.get("high")),
                        "最低价": _safe_float(row.get("low")),
                        "成交量(手)": _safe_float(row.get("volume")),
                        "成交额(元)": _safe_float(row.get("amount")),
                        "涨跌幅": None,
                        "换手率": None,
                    })
        except Exception as e:
            _api_logger.warning("A股K线 AKShare 获取失败: %s [%s]", e, code)
            pass

    # 如果缓存有部分数据，尝试合并新旧数据
    if cached and records:
        cached_dates = {r["日期"] for r in cached}
        new_records = [r for r in records if r["日期"] not in cached_dates]
        records = cached + new_records
        # 按日期排序
        records.sort(key=lambda x: x.get("日期", ""))

    if records:
        _kline_cache.set(f"kline:{code}:{period}:{adjust}", records, layer="disk")
        return records[-limit:]
    return [{"error": f"获取A股K线失败: {code}"}]


def get_kline_hk(code, period="daily", limit=120):
    """港股 K线 — AKShare 新浪 data（TDX 不支持港股），带磁盘缓存 6h"""
    # 校验 period
    if period not in {"daily", "weekly", "monthly"}:
        return [{"error": f"不支持的K线类型: {period}，支持 daily/weekly/monthly"}]
    cached = _kline_cache.get(f"kline:{code}:{period}:", layer="disk")
    if cached and len(cached) >= limit:
        return cached[-limit:]

    records = []
    # 仅 AKShare 新浪（TDX 协议不支持港股 K 线）
    try:
        ak = _get_ak()
        df = _call_with_net_timeout(lambda: ak.stock_hk_daily(symbol=code, adjust="qfq"))
        if df is not None and not df.empty:
            if period in ("weekly", "monthly"):
                df = _resample_kline(df, period)
            for _, row in df.tail(limit).iterrows():
                records.append({
                    "日期": str(row.get("date", ""))[:10],
                    "开盘价": _safe_float(row.get("open")),
                    "收盘价": _safe_float(row.get("close")),
                    "最高价": _safe_float(row.get("high")),
                    "最低价": _safe_float(row.get("low")),
                    "成交量(手)": _safe_float(row.get("volume")),
                    "成交额(元)": _safe_float(row.get("amount")),
                    "涨跌幅": None,
                })
    except Exception as e:
        _api_logger.warning("港股/美股K线获取失败: %s [%s]", e, code)
        pass

    # ── yfinance 兜底（AKShare 港股失败时）──
    if not records:
        try:
            yf = _get_yf()
            ticker = yf.Ticker(code)
            yf_period = "1y" if limit > 120 else "6mo" if limit > 60 else "3mo"
            yf_df = ticker.history(period=yf_period)
            if yf_df is not None and not yf_df.empty:
                yf_df = yf_df.tail(limit)
                for idx, row in yf_df.iterrows():
                    records.append({
                        "日期": str(idx.date()) if hasattr(idx, 'date') else str(idx)[:10],
                        "开盘价": _safe_float(row.get("Open")),
                        "收盘价": _safe_float(row.get("Close")),
                        "最高价": _safe_float(row.get("High")),
                        "最低价": _safe_float(row.get("Low")),
                        "成交量(手)": _safe_float(row.get("Volume")),
                        "成交额(元)": None,
                        "涨跌幅": None,
                    })
                records.reverse()
        except Exception as e:
            _api_logger.warning("yfinance 港股K线降级失败: %s [%s]", e, code)
            pass

    if records:
        _kline_cache.set(f"kline:{code}:{period}:", records, layer="disk")
        return records[-limit:]
    return [{"error": f"获取港股K线失败: {code}"}]


def get_kline_us(code, period="daily", limit=120):
    """美股 K线 — AKShare 新浪 data（TDX 不支持美股），带磁盘缓存 6h"""
    # 校验 period
    if period not in {"daily", "weekly", "monthly"}:
        return [{"error": f"不支持的K线类型: {period}，支持 daily/weekly/monthly"}]
    cached = _kline_cache.get(f"kline:{code}:{period}:", layer="disk")
    if cached and len(cached) >= limit:
        return cached[-limit:]

    records = []
    try:
        ak = _get_ak()
        # 美股数据量较大，使用 30s 超时
        df = _call_with_net_timeout(lambda: ak.stock_us_daily(symbol=code, adjust="qfq"), timeout=30)
        if df is None or df.empty:
            # 降级: 东方财富美股历史数据 (格式: 市场代码.股票代码, 105=NASDAQ, 106=NYSE)
            for prefix in ("105", "106"):
                try:
                    df = _call_with_net_timeout(lambda p=prefix: ak.stock_us_hist(symbol=f"{p}.{code}", period=period if period in ("daily", "weekly", "monthly") else "daily"))
                    if df is not None and not df.empty:
                        break
                except Exception:
                    continue
        if df is not None and not df.empty:
            # 兼容 stock_us_daily (英文列名) 和 stock_us_hist (中文列名)
            has_en_cols = "date" in df.columns
            date_col = "date" if has_en_cols else "日期"
            open_col = "open" if has_en_cols else "开盘"
            close_col = "close" if has_en_cols else "收盘"
            high_col = "high" if has_en_cols else "最高"
            low_col = "low" if has_en_cols else "最低"
            vol_col = "volume" if has_en_cols else "成交量"
            amt_col = "amount" if has_en_cols else "成交额"

            if period in ("weekly", "monthly") and has_en_cols:
                df[date_col] = pd.to_datetime(df[date_col])
                df.set_index(date_col, inplace=True)
                rule = "W" if period == "weekly" else "ME"
                df = df.resample(rule).agg({
                    open_col: "first", high_col: "max", low_col: "min",
                    close_col: "last", vol_col: "sum",
                }).dropna().reset_index()
            for _, row in df.tail(limit).iterrows():
                records.append({
                    "日期": str(row.get(date_col, ""))[:10],
                    "开盘价": _safe_float(row.get(open_col)),
                    "收盘价": _safe_float(row.get(close_col)),
                    "最高价": _safe_float(row.get(high_col)),
                    "最低价": _safe_float(row.get(low_col)),
                    "成交量(手)": _safe_float(row.get(vol_col)),
                    "成交额(元)": _safe_float(row.get(amt_col)),
                    "涨跌幅": None,
                })
    except Exception as e:
        _api_logger.warning("港股/美股K线获取失败: %s [%s]", e, code)
        pass

    # ── yfinance 兜底（AKShare 美股失败时）──
    if not records:
        try:
            yf = _get_yf()
            ticker = yf.Ticker(code)
            yf_period = "1y" if limit > 120 else "6mo" if limit > 60 else "3mo"
            yf_df = ticker.history(period=yf_period)
            if yf_df is not None and not yf_df.empty:
                yf_df = yf_df.tail(limit)
                for idx, row in yf_df.iterrows():
                    records.append({
                        "日期": str(idx.date()) if hasattr(idx, 'date') else str(idx)[:10],
                        "开盘价": _safe_float(row.get("Open")),
                        "收盘价": _safe_float(row.get("Close")),
                        "最高价": _safe_float(row.get("High")),
                        "最低价": _safe_float(row.get("Low")),
                        "成交量(手)": _safe_float(row.get("Volume")),
                        "成交额(元)": None,
                        "涨跌幅": None,
                    })
                records.reverse()
        except Exception as e:
            _api_logger.warning("yfinance 美股K线降级失败: %s [%s]", e, code)
            pass

    if records:
        _kline_cache.set(f"kline:{code}:{period}:", records, layer="disk")
        return records[-limit:]
    return [{"error": f"获取美股K线失败: {code}"}]


def get_kline_futures(code, period="daily", limit=120):
    """期货 K线"""
    ak = _get_ak()
    try:
        df = ak.futures_main_sina(symbol=code)
        if df is None or df.empty:
            df = ak.futures_zh_daily_sina(symbol=code)
        if df is None or df.empty:
            return []
        records = []
        for _, row in df.tail(limit).iterrows():
            records.append({
                "日期": str(row.get("日期", ""))[:10],
                "开盘价": _safe_float(row.get("开盘价")),
                "收盘价": _safe_float(row.get("收盘价")),
                "最高价": _safe_float(row.get("最高价")),
                "最低价": _safe_float(row.get("最低价")),
                "成交量(手)": _safe_float(row.get("成交量")),
                "持仓量": _safe_float(row.get("持仓量")),
            })
        return records
    except Exception as e:
        return [{"error": f"获取期货K线失败: {e}"}]


# ================================================================
# 3. 财务数据
# ================================================================

def get_financials_a(code, count=4):
    """A股财务数据 — 返回结构化分类指标 + 历史明细"""
    from mcp_finance.financials import get_financial_indicators
    
    # 1. 获取结构化核心指标（来自东方财富 stock_financial_abstract, 缓存24h）
    fin = get_financial_indicators(code)
    
    indicators = {}
    if fin and not fin.get("_error"):
        indicators = {
            "核心指标": {
                "营业总收入(元)": fin.get("revenue"),
                "归母净利润(元)": fin.get("net_profit"),
                "基本每股收益": fin.get("eps"),
                "每股净资产": fin.get("bvps"),
                "每股经营现金流": fin.get("cfps"),
                "净资产(元)": fin.get("equity"),
                "经营现金流净额(元)": fin.get("operating_cf"),
            },
            "盈利能力": {
                "ROE(%)": fin.get("roe"),
                "ROA(%)": fin.get("roa"),
                "毛利率(%)": fin.get("gross_margin"),
                "销售净利率(%)": fin.get("net_margin"),
                "营业利润率(%)": fin.get("operating_margin"),
            },
            "成长能力": {
                "营收增长率(%)": fin.get("revenue_growth"),
                "净利润增长率(%)": fin.get("net_profit_growth"),
            },
            "财务风险": {
                "资产负债率(%)": fin.get("debt_ratio"),
                "流动比率": fin.get("current_ratio"),
                "速动比率": fin.get("quick_ratio"),
            },
            "营运能力": {
                "总资产周转率": fin.get("asset_turnover"),
                "存货周转率": fin.get("inventory_turnover"),
            },
        }
    
    # 2. 获取历史明细（来自同花顺 stock_financial_abstract_ths）
    history = {"数据": [], "数据源": "AKShare-同花顺"}
    try:
        ak = _get_ak()
        df = _call_with_net_timeout(lambda: ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期"))
        if df is not None and not df.empty:
            df = df.tail(count)
            history["数据"] = _df_to_records(df)
            history["期数"] = len(df)
    except Exception:
        pass
    
    error_note = fin.get("_error", "") if fin else "no_cache"
    result = {
        "股票代码": code,
        "财务指标": indicators,
        "历史明细": history,
        "数据源": "AKShare-东方财富+同花顺",
    }
    if error_note:
        result["_note"] = f"部分指标获取异常: {error_note}"
    return result


# ================================================================
# 4. 大盘指数
# ================================================================

INDEX_CODES_A = {
    "上证指数": "000001", "深证成指": "399001", "创业板指": "399006",
    "沪深300": "000300", "科创50": "000688",
    "上证50": "000016", "中证500": "000905", "中证1000": "000852",
}
INDEX_CODES_HK = {"恒生指数": "HSI", "恒生科技": "HSTECH", "国企指数": "HSCEI"}
INDEX_CODES_US = {"道琼斯": ".DJI", "纳斯达克": ".IXIC", "标普500": ".INX"}


def get_market_indices(market="a"):
    """获取大盘指数行情（A股 easy-tdx 优先，AKShare 新浪兜底）"""
    ak = _get_ak()
    result = []
    if market == "a":
        # ── 策略1: easy-tdx 逐指数查询（优先）──
        for name, code in INDEX_CODES_A.items():
            try:
                row = _get_single_quote(code, market="a")
                if row and isinstance(row, dict) and not row.get("error"):
                    result.append({
                        "名称": name, "代码": code,
                        "最新价": _safe_float(row.get("最新价", row.get("close", row.get("price", row.get("last_price", row.get("last_close")))))),
                        "涨跌幅": _safe_float(row.get("涨跌幅", row.get("change_pct", row.get("涨跌比例")))),
                        "涨跌额": _safe_float(row.get("涨跌额", row.get("change"))),
                        "今开": _safe_float(row.get("今开", row.get("open"))),
                        "昨收": _safe_float(row.get("昨收", row.get("pre_close", row.get("preclose")))),
                        "最高": _safe_float(row.get("最高", row.get("high"))),
                        "最低": _safe_float(row.get("最低", row.get("low"))),
                        "成交量": _safe_float(row.get("成交量", row.get("volume"))),
                        "成交额": _safe_float(row.get("成交额", row.get("amount"))),
                    })
                    # 异常值检测：上证/深证/创业板/沪深300/科创50 正常值应 > 100，若获取到明显错误的值则丢弃
                    if result and result[-1]["最新价"] is not None and result[-1]["最新价"] < 100 and code in ("000001", "399001", "399006", "000300", "000688", "000016", "000905", "000852"):
                        result.pop()  # 删除异常条目，后续由 AKShare 兜底
            except Exception:
                pass

        # ── 策略2: AKShare 新浪源兜底（补全 easy-tdx 拿不到的指数）──
        if len(result) < len(INDEX_CODES_A):
            try:
                df = _call_with_net_timeout(lambda: ak.stock_zh_index_spot_sina())
                if df is not None and not df.empty:
                    existing_codes = {r["代码"] for r in result}
                    target = list(INDEX_CODES_A.values())
                    name_lookup = {c: n for n, c in INDEX_CODES_A.items()}
                    for _, row in df.iterrows():
                        raw_code = str(row.get("代码", ""))
                        code = raw_code.replace("sh", "").replace("sz", "").replace("bj", "") if raw_code[:2] in ("sh", "sz", "bj") else raw_code
                        if code in target and code not in existing_codes:
                            result.append({
                                "名称": name_lookup[code], "代码": code,
                                "最新价": _safe_float(row.get("最新价")),
                                "涨跌幅": _safe_float(row.get("涨跌幅")),
                                "涨跌额": _safe_float(row.get("涨跌额")),
                                "今开": _safe_float(row.get("今开")),
                                "昨收": _safe_float(row.get("昨收")),
                                "最高": _safe_float(row.get("最高")),
                                "最低": _safe_float(row.get("最低")),
                                "成交量": _safe_float(row.get("成交量")),
                                "成交额": _safe_float(row.get("成交额")),
                            })
            except Exception as e:
                _api_logger.warning("指数行情 AKShare 兜底获取失败: %s", e)
                pass
    elif market == "hk":
        try:
            df = _call_with_net_timeout(lambda: ak.stock_hk_index_spot_sina())
            for _, row in df.iterrows():
                name = str(row.get("名称", ""))
                for idx_name, idx_code in INDEX_CODES_HK.items():
                    if idx_name in name:
                        result.append({
                            "名称": idx_name, "代码": idx_code,
                            "最新价": _safe_float(row.get("最新价")),
                            "涨跌幅": _safe_float(row.get("涨跌幅")),
                            "涨跌额": _safe_float(row.get("涨跌额")),
                        })
                        break
        except Exception as e:
            return [{"error": f"获取港股指数失败: {e}"}]
    elif market == "us":
        for name, code in INDEX_CODES_US.items():
            try:
                df = _call_with_net_timeout(lambda: ak.index_us_stock_sina(symbol=code))
                if df is not None and not df.empty:
                    r = df.iloc[-1]
                    result.append({
                        "名称": name, "代码": code,
                        "最新价": _safe_float(r.get("close", r.get("收盘价"))),
                        "涨跌幅": _safe_float(r.get("涨跌幅")),
                        "开盘价": _safe_float(r.get("open", r.get("开盘价"))),
                        "最高价": _safe_float(r.get("high", r.get("最高价"))),
                        "最低价": _safe_float(r.get("low", r.get("最低价"))),
                        "成交量": _safe_float(r.get("volume", r.get("成交量"))),
                    })
            except Exception as e:
                _api_logger.warning("美股指数行情获取失败: %s", e)
                pass
    if not result:
        return [{"error": f"未获取到 {market} 市场指数数据"}]
    return result


# ================================================================
# 5. 板块排行（改用同花顺数据源）
# ================================================================

def get_sector_ranking(market="a", sector_type="industry", top_n=10):
    """获取板块涨幅排行（同花顺 summary 数据源，带涨跌幅/净流入）"""
    ak = _get_ak()
    if market == "a":
        try:
            if sector_type == "industry":
                df = _call_with_net_timeout(lambda: ak.stock_board_industry_summary_ths())
            elif sector_type == "concept":
                # 概念板块: 先用东方财富，不行降级到同花顺概念名称列表
                df = _call_with_net_timeout(lambda: ak.stock_board_concept_name_em())
                if df is None or df.empty:
                    df = _call_with_net_timeout(lambda: ak.stock_board_concept_name_ths())
            elif sector_type == "region":
                df = _call_with_net_timeout(lambda: ak.stock_board_industry_summary_ths())
            else:
                df = _call_with_net_timeout(lambda: ak.stock_board_industry_summary_ths())
            if df is None or df.empty:
                return []
            result = _df_to_records(df.head(top_n))
            # 字段名归一化映射
            _SECTOR_FIELD_MAP = {
                "板块": "名称", "板块名称": "名称", "概念名称": "名称", "name": "名称",
                "板块代码": "代码", "code": "代码",
                "最新价": "最新价", "current_price": "最新价",
                "涨跌幅": "涨跌幅", "涨幅": "涨跌幅", "pct_change": "涨跌幅",
                "涨跌额": "涨跌额", "change": "涨跌额",
                "总市值": "总市值", "total_market_cap": "总市值",
                "换手率": "换手率", "turnover_rate": "换手率",
                "市盈率": "市盈率", "PE": "市盈率", "pe_ratio": "市盈率",
                "上涨家数": "上涨家数", "up_num": "上涨家数",
                "下跌家数": "下跌家数", "down_num": "下跌家数",
                "总成交量": "总成交量", "成交量": "成交量", "volume": "成交量",
                "总成交额": "总成交额", "成交额": "成交额", "amount": "成交额",
                "净流入": "净流入", "net_flow": "净流入",
                "均价": "均价", "avg_price": "均价",
                "领涨股": "领涨股", "leader": "领涨股",
                "排名": "排名", "rank": "排名",
                "序号": "排名",
            }
            normalized = []
            for r in result:
                nr = {}
                for orig_k, orig_v in r.items():
                    mapped_k = _SECTOR_FIELD_MAP.get(orig_k, orig_k)
                    nr[mapped_k] = orig_v
                nr["市场"] = "A股"
                normalized.append(nr)
            return normalized
        except Exception as e:
            return [{"error": f"获取板块排行失败: {e}"}]
    return []


# ================================================================
# 6. 资金流向
# ================================================================

def get_north_flow(days=5):
    """北向/南向资金流向"""
    ak = _get_ak()
    # 尝试多个接口
    for sym in ["北向资金", "沪港通资金", ""]:
        try:
            if sym:
                df = _call_with_net_timeout(lambda s=sym: ak.stock_hsgt_hist_em(symbol=s))
            else:
                df = _call_with_net_timeout(lambda: ak.stock_hsgt_hist_em())
            if df is not None and not df.empty:
                records = _df_to_records(df.tail(days))
                return {"类型": "北向资金(沪深港通)", "最近天数": len(records), "数据": records, "数据源": "AKShare"}
        except Exception as e:
            _api_logger.warning("北向资金获取失败(sym=%s): %s", sym, e)
            pass
    return {"提示": "暂无北向资金数据", "数据": []}


# ================================================================
# 7. 股票搜索
# ================================================================

# ================================================================
# 8. 批量行情
# ================================================================

def get_batch_quotes_a(codes):
    """批量获取A股行情 — 并行查询，提升多股查询速度"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    result_dict = {}

    def _fetch_one(code):
        row = _get_single_quote(code, market="a")
        return code, row

    with ThreadPoolExecutor(max_workers=min(len(codes), 5)) as pool:
        futures = {pool.submit(_fetch_one, code): code for code in codes}
        for future in as_completed(futures):
            try:
                code, row = future.result()
                if row is not None:
                    q = _parse_kline_row(row)
                    name = row.get("名称", "")
                    if not name:
                        from mcp_finance.data import STOCK_MAPPING
                        name = STOCK_MAPPING.get(code, "")
                    result_dict[code] = {
                        "代码": code, "名称": name,
                        "最新价": q["最新价"], "涨跌幅": q["涨跌幅"],
                        "涨跌额": q["涨跌额"],
                        "今开": q["今开"], "昨收": q["昨收"],
                        "最高": q["最高"], "最低": q["最低"],
                        "成交量(手)": q["成交量(手)"],
                        "成交额(元)": q["成交额(元)"],
                    }
            except Exception as e:
                _api_logger.warning("批量行情单股查询失败: %s", e)
                pass

    result = [result_dict[c] for c in codes if c in result_dict]
    if not result:
        return [{"error": "批量查询失败: 所有股票数据不可用"}]
    return result


# ================================================================
# 9. 龙虎榜 / 大宗交易 / 两融
# ================================================================

def get_dragon_tiger(date=None):
    """龙虎榜每日明细"""
    ak = _get_ak()
    try:
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        df = _call_with_net_timeout(lambda: ak.stock_lhb_detail_daily_sina(date=date))
        if df is None or df.empty:
            return {"日期": date, "数据": [], "提示": "当日无龙虎榜数据或非交易日"}
        records = _df_to_records(df)
        return {"日期": date, "上榜数": len(records), "数据": records, "数据源": "AKShare"}
    except Exception as e:
        return {"error": f"获取龙虎榜失败: {e}"}


def get_block_trades(symbol=None, start_date=None, end_date=None):
    """大宗交易数据"""
    ak = _get_ak()
    try:
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        if symbol:
            df = _call_with_net_timeout(lambda: ak.stock_dzjy_mrmx(symbol=symbol, start_date=start, end_date=end))
        else:
            df = _call_with_net_timeout(lambda: ak.stock_dzjy_mrtj(start_date=start, end_date=end))
        records = _df_to_records(df) if (df is not None and not df.empty) else []
        return {"时间范围": f"{start_date} ~ {end_date}", "股票": symbol or "全市场", "成交笔数": len(records), "数据": records, "数据源": "AKShare"}
    except Exception as e:
        return {"error": f"获取大宗交易失败: {e}"}


def get_margin_trading(market="all", date=None):
    """融资融券（两融）数据"""
    ak = _get_ak()
    try:
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        result = {"日期": date, "数据源": "AKShare"}
        if market in ("sh", "all"):
            try:
                df_sh = _call_with_net_timeout(lambda: ak.stock_margin_detail_sse(date=date))
                result["上海"] = _df_to_records(df_sh)
                result["上证个股数"] = len(df_sh) if df_sh is not None else 0
            except Exception:
                result["上海"] = []
                result["上证个股数"] = 0
        if market in ("sz", "all"):
            try:
                df_sz = _call_with_net_timeout(lambda: ak.stock_margin_detail_szse(date=date))
                result["深圳"] = _df_to_records(df_sz)
                result["深证个股数"] = len(df_sz) if df_sz is not None else 0
            except Exception:
                result["深圳"] = []
                result["深证个股数"] = 0
        return result
    except Exception as e:
        return {"error": f"获取两融数据失败: {e}"}


# ================================================================
# 10. 期货列表
# ================================================================

def get_futures_list():
    """获取国内期货主力合约列表（新浪数据源）"""
    ak = _get_ak()
    try:
        df = _call_with_net_timeout(lambda: ak.futures_display_main_sina())
        if df is not None and not df.empty:
            records = []
            for _, row in df.iterrows():
                records.append({
                    "代码": str(row.get("symbol", "")),
                    "名称": str(row.get("name", "")),
                    "交易所": str(row.get("exchange", "")),
                    "市场": "期货",
                })
            return records
        return []
    except Exception as e:
        return [{"error": f"获取期货列表失败: {e}"}]


# ================================================================
# 11. 全市场A股快照（供选股器使用）
# ================================================================

def get_all_a_stocks_snapshot():
    """获取全市场A股快照"""
    try:
        df = _fetch_all_a_stocks_cache()
        if df is None or df.empty:
            return []
        return _df_to_records(df)
    except Exception:
        return []


# ================================================================

def get_main_inflow_batch(codes: list[str]) -> dict[str, float | None]:
    """批量获取主力净流入（通过 easy-tdx get_stock_quotes）

    Args:
        codes: 6位股票代码列表

    Returns:
        {code: main_net_amount (元), ...}  — 查不到的 code 值为 None
    """
    if not codes:
        return {}

    # 代码 → 市场映射
    def _code_to_market(c: str) -> int | None:
        # 先根据前缀判断（AKShare 返回的代码带 "sh"/"sz"/"bj" 前缀）
        if c.startswith("bj"):
            return 2  # BJ
        clean = c.replace("sh", "").replace("sz", "").replace("bj", "")
        if clean.startswith("60") or clean.startswith("68"):
            return 1  # SH
        elif clean.startswith(("00", "30")):
            return 0  # SZ
        elif clean.startswith(("8", "4", "9")):
            return 2  # BJ / B股
        return None

    stocks = []
    for code in codes:
        mkt = _code_to_market(code)
        if mkt is not None:
            stocks.append((mkt, code))

    if not stocks:
        return {c: None for c in codes}

    result: dict[str, float | None] = {c: None for c in codes}

    try:
        tdx = _get_tdx()
    except Exception as e:
        _api_logger.warning("TDX 连接失败，主力净流入不可用: %s", e)
        return result

    # easy-tdx get_stock_quotes 支持批量，但不宜一次太多
    batch_size = 50
    for i in range(0, len(stocks), batch_size):
        batch = stocks[i:i + batch_size]
        try:
            df = tdx.get_stock_quotes(batch)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    c = str(row.get("code", ""))
                    val = row.get("main_net_amount")
                    if c and val is not None:
                        try:
                            result[c] = float(val)
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            _api_logger.warning("主力净流入批量查询失败: %s", e)
            continue

    return result

# ================================================================
# 12. 搜索股票（纯本地映射，无网络调用）
# ================================================================

def search_stocks(market: str, keyword: str, top_n: int = 10) -> list[dict]:
    """搜索股票 — 纯本地映射，毫秒级返回，无网络调用风险

    覆盖 150+ A股 + 10+ 港股 + 10+ 美股。
    """
    from mcp_finance.data import STOCK_MAPPING, HOT_STOCKS
    kw_upper = keyword.upper().strip()
    result = []

    # 收集所有候选股
    candidates: list[tuple[str, str, str]] = []  # (code, name, market_label)

    # 归一化 market 参数：支持中文别名
    m = market.strip().lower()
    if m in ("a", "a股"):
        _market = "a"
    elif m in ("hk", "港股"):
        _market = "hk"
    elif m in ("us", "美股"):
        _market = "us"
    else:
        _market = "all"

    if _market == "a":
        for code, name in STOCK_MAPPING.items():
            candidates.append((code, name, "A股"))
        # HOT_STOCKS 也包含额外A股
        for s in HOT_STOCKS:
            if s["市场"] == "A股":
                candidates.append((s["代码"], s["名称"], "A股"))
    elif _market == "hk":
        for s in HOT_STOCKS:
            if s["市场"] == "港股":
                candidates.append((s["代码"], s["名称"], "港股"))
    elif _market == "us":
        for s in HOT_STOCKS:
            if s["市场"] == "美股":
                candidates.append((s["代码"], s["名称"], "美股"))
    else:
        # all: 包含 A 股 + 港股 + 美股
        market_labels = {"A股": "A股", "港股": "港股", "美股": "美股"}
        for s in HOT_STOCKS:
            label = market_labels.get(s["市场"])
            if label:
                candidates.append((s["代码"], s["名称"], label))
        for code, name in STOCK_MAPPING.items():
            candidates.append((code, name, "A股"))

    # 去重
    seen: set[str] = set()
    for code, name, label in candidates:
        if code in seen:
            continue
        if kw_upper in code.upper() or keyword.strip() in name:
            seen.add(code)
            result.append({"代码": code, "名称": name, "市场": label})
            if len(result) >= top_n:
                break
    return result


# ================================================================
# 13. 测试数据源
# ================================================================

def test_data_sources():
    """测试所有数据源是否可用 — 分组测试 easy-tdx（优先）和 AKShare（兜底）"""
    ak = _get_ak()
    results = {"测试时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "数据源": {}}
    today = datetime.now().strftime("%Y%m%d")

    # ── easy-tdx 数据源 ──
    tdx_tests = [
        ("easy-tdx A股行情", lambda: _get_single_quote("600519", market="a")),
        ("easy-tdx A股K线", lambda: get_kline_a("600519", limit=1)),
    ]
    for name, fn in tdx_tests:
        try:
            r = fn()
            if r is None:
                results["数据源"][name] = "EMPTY"
            elif isinstance(r, dict):
                results["数据源"][name] = "OK" if not r.get("error") else f"FAIL: {r['error']}"
            elif isinstance(r, list):
                results["数据源"][name] = "OK" if len(r) > 0 else "EMPTY"
            else:
                results["数据源"][name] = "OK"
        except Exception as e:
            results["数据源"][name] = f"FAIL: {type(e).__name__}: {str(e)[:80]}"

    # ── AKShare 数据源 ──
    ak_tests = [
        ("AKShare A股指数(新浪)", lambda: _call_with_net_timeout(lambda: ak.stock_zh_index_spot_sina())),
        ("AKShare 港股行情(daily)", lambda: _call_with_net_timeout(lambda: ak.stock_hk_daily(symbol="00700", adjust=""))),
        ("AKShare 美股行情(daily)", lambda: _call_with_net_timeout(lambda: ak.stock_us_daily(symbol="AAPL", adjust=""))),
        ("AKShare 行业板块(同花顺)", lambda: _call_with_net_timeout(lambda: ak.stock_board_industry_name_ths())),
        ("AKShare 概念板块(东方财富)", lambda: _call_with_net_timeout(lambda: ak.stock_board_concept_name_em())),
        ("AKShare 龙虎榜(新浪)", lambda: _call_with_net_timeout(lambda: ak.stock_lhb_detail_daily_sina(date=today))),
        ("AKShare 期货行情", lambda: _call_with_net_timeout(lambda: ak.futures_zh_spot(symbol="RB0", market="CF", adjust="0"))),
    ]
    for name, fn in ak_tests:
        try:
            df = fn()
            results["数据源"][name] = "OK" if (df is not None and not df.empty) else "EMPTY"
        except Exception as e:
            results["数据源"][name] = f"FAIL: {type(e).__name__}: {str(e)[:80]}"

    return results


# ================================================================
# MCP Tool Handler 函数
# ================================================================

from mcp_finance.errors import InvalidCodeError, NoDataError, StockError

# 复用文件顶部的 logger
_logger = _api_logger


def _detect_market(code: str) -> str:
    """根据代码格式自动判断市场: a/hk/us/futures/unknown
    优先级: 显式市场后缀 > 数字位数规则 > 字母兜底
    """
    import re
    if not code or not isinstance(code, str):
        return "unknown"

    code = code.strip().upper()

    # 1. 优先匹配显式市场后缀（准确率最高）
    suffix_map = {
        ".SH": "a", ".SZ": "a", ".BJ": "a",
        ".HK": "hk",
        ".US": "us", ".O": "us", ".N": "us",
    }
    for suffix, market in suffix_map.items():
        if code.endswith(suffix):
            return market

    # 提取纯代码主体（去掉后缀部分）
    code_body = code.split(".")[0]

    # 2. 纯数字场景按位数判断
    if code_body.isdigit():
        length = len(code_body)
        if length == 6:
            return "a"       # 6位数字默认A股
        elif 3 <= length <= 5:
            return "hk"       # 3-5位数字默认港股（兼容省略前置零，如 700→00700）
        else:
            return "unknown"

    # 3. 含字母的非后缀场景，兜底为美股
    if re.search(r"[A-Z]", code_body):
        return "us"

    return "unknown"


def handle_realtime_quote(arguments):
    """统一实时行情 handler"""
    code_raw = arguments["code"]
    market = arguments.get("market", "") or _detect_market(code_raw)  # 用原始代码检测市场
    code = code_raw.strip().upper().split(".")[0]  # 去掉后缀
    # 港股纯数字代码补齐到5位
    if market == "hk" and code.isdigit() and len(code) < 5:
        code = code.zfill(5)
    fn_map = {"a": get_realtime_quote_a, "hk": get_realtime_quote_hk, "us": get_realtime_quote_us, "futures": get_realtime_quote_futures}
    fn = fn_map.get(market)
    if fn is None:
        raise InvalidCodeError(f"不支持的市场类型: {market}")
    result = fn(code)
    if "error" in result and "数据源" not in result:
        raise StockError(result["error"], code="API_ERROR")
    return result


def handle_kline(arguments):
    """K线数据 handler — 自动识别市场"""
    code_raw = arguments["code"]
    market = arguments.get("market", "") or _detect_market(code_raw)  # 用原始代码检测市场
    code = code_raw.strip().upper().split(".")[0]  # 去掉后缀
    # 港股纯数字代码补齐到5位
    if market == "hk" and code.isdigit() and len(code) < 5:
        code = code.zfill(5)
    ktype = arguments.get("ktype", "daily")
    limit = min(arguments.get("limit", 120), 800)
    adjust = arguments.get("adjust", "qfq")
    if market == "a":
        result = get_kline_a(code, period=ktype, adjust=adjust, limit=limit)
    elif market == "hk":
        result = get_kline_hk(code, period=ktype, limit=limit)
    elif market == "us":
        result = get_kline_us(code, period=ktype, limit=limit)
    elif market == "futures":
        result = get_kline_futures(code, period=ktype, limit=limit)
    else:
        raise InvalidCodeError(f"不支持的市场类型: {market}")
    if not result or (len(result) == 1 and "error" in result[0]):
        raise NoDataError(f"未获取到 {code} 的 K 线数据")
    _logger.info("K线: %s market=%s days=%d", code, market, len(result))
    return result


def handle_financials(arguments):
    """财务数据 handler — 自动识别市场"""
    code_raw = arguments["code"]
    market = arguments.get("market", "") or _detect_market(code_raw)  # 用原始代码检测市场
    code = code_raw.strip().upper().split(".")[0]  # 去掉后缀
    # 港股纯数字代码补齐到5位
    if market == "hk" and code.isdigit() and len(code) < 5:
        code = code.zfill(5)
    count = arguments.get("count", 4)
    if market == "a":
        data = get_financials_a(code, count=count)
        if "error" in data:
            raise NoDataError(f"未找到 {code} 的财务数据")
        return data
    elif market in ("hk", "us"):
        # 港股/美股: 尝试 AKShare 通用接口
        try:
            akshare = _get_ak()
            if market == "hk":
                df = _call_with_net_timeout(lambda: akshare.stock_hk_financial_indicator_em(symbol=code))
            else:
                df = _call_with_net_timeout(lambda: akshare.stock_financial_us_analysis_indicator_em(symbol=code, indicator="年报"))
            if df is not None and not df.empty:
                records = []
                for _, row in df.head(count).iterrows():
                    records.append({str(k): (None if pd.isna(v) else v) for k, v in row.items()})
                return {"数据": records, "市场": market, "数据源": "AKShare", "提示": "港股/美股财务数据来自AKShare,字段与A股不同"}
        except Exception as e:
            _api_logger.warning("港股/美股财务数据获取失败: %s [%s]", e, code)
            pass

        # ── yfinance 兜底 ──
        try:
            yf = _get_yf()
            ticker = yf.Ticker(code)
            info = ticker.info
            # 提取关键财务指标
            financials_data = {}
            if info:
                key_fields = {
                    "longName": "公司名称", "marketCap": "总市值",
                    "trailingPE": "市盈率(TTM)", "forwardPE": "前瞻市盈率",
                    "priceToBook": "市净率", "returnOnEquity": "净资产收益率(ROE)",
                    "revenueGrowth": "营收增长率", "earningsGrowth": "净利润增长率",
                    "profitMargins": "净利润率", "operatingMargins": "营业利润率",
                    "currentRatio": "流动比率", "debtToEquity": "资产负债率",
                    "dividendYield": "股息率", "payoutRatio": "分红率",
                    "freeCashflow": "自由现金流", "operatingCashflow": "经营性现金流",
                    "totalRevenue": "总营收", "grossProfits": "毛利润",
                    "ebitda": "EBITDA", "enterpriseValue": "企业价值",
                }
                for eng_key, cn_name in key_fields.items():
                    val = info.get(eng_key)
                    if val is not None:
                        financials_data[cn_name] = val
                # 尝试获取利润表
                try:
                    fs = ticker.financials
                    if fs is not None and not fs.empty:
                        fs_json = fs.head(count).to_dict()
                        financials_data["财务报表(利润表)"] = str(fs_json)
                except Exception:
                    pass
            if financials_data:
                return {
                    "数据": [financials_data],
                    "市场": market,
                    "数据源": "yfinance",
                    "提示": "港股/美股财务数据来自yfinance,字段可能与A股不同",
                }
        except Exception as e:
            _api_logger.warning("yfinance 财务数据兜底失败: %s [%s]", e, code)
            pass

        raise NoDataError(f"暂不支持 {market} 市场的财务数据查询,请使用其他工具")
    else:
        raise NoDataError(f"暂不支持 {market} 市场的财务数据查询")


def handle_market_indices(arguments=None):
    """大盘指数 handler"""
    if arguments is None:
        arguments = {}
    market = arguments.get("market", "a")
    indices = get_market_indices(market=market)
    if not indices or (len(indices) == 1 and "error" in indices[0]):
        raise NoDataError("获取大盘指数失败")
    return indices


def handle_sector_ranking(arguments):
    """板块排行 handler"""
    market = arguments.get("market", "a")
    sector_type = arguments.get("sector_type", "industry")
    top_n = min(arguments.get("top_n", 10), 50)
    data = get_sector_ranking(market=market, sector_type=sector_type, top_n=top_n)
    if not data:
        raise NoDataError("获取板块排行失败")
    return data


def handle_north_flow(arguments):
    """北向资金 handler"""
    days = min(arguments.get("days", 5), 30)
    data = get_north_flow(days=days)
    if "error" in data:
        raise NoDataError("获取北向资金数据失败")
    return data



def handle_batch_quotes(arguments):
    """批量行情 handler"""
    codes = arguments.get("codes", [])
    market = arguments.get("market", "a")
    if not codes:
        raise InvalidCodeError("请提供至少一个股票代码")
    if market == "a":
        quotes = get_batch_quotes_a(codes)
    else:
        fn = {"hk": get_realtime_quote_hk, "us": get_realtime_quote_us}.get(market, get_realtime_quote_a)
        quotes = [fn(c) for c in codes]
    if not quotes:
        raise NoDataError("获取批量行情失败")
    return quotes


def handle_dragon_tiger(arguments):
    """龙虎榜 handler"""
    result = get_dragon_tiger(date=arguments.get("date"))
    _logger.info("龙虎榜: date=%s", arguments.get("date", "today"))
    return result


def handle_block_trades(arguments):
    """大宗交易 handler"""
    result = get_block_trades(symbol=arguments.get("symbol"), start_date=arguments.get("start_date"), end_date=arguments.get("end_date"))
    _logger.info("大宗交易: symbol=%s", arguments.get("symbol", "全市场"))
    return result


def handle_margin_trading(arguments):
    """两融 handler"""
    result = get_margin_trading(market=arguments.get("market", "all"), date=arguments.get("date"))
    _logger.info("两融: market=%s", arguments.get("market", "all"))
    return result


def handle_futures_list(arguments=None):
    """期货列表 handler"""
    data = get_futures_list()
    if not data:
        raise NoDataError("获取期货列表失败")
    _logger.info("期货列表: count=%d", len(data))
    return data


def handle_test_data_sources(_args=None):
    """测试数据源 handler"""
    return test_data_sources()
