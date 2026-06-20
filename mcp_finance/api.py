"""
双数据源封装层：easy-tdx (主) + AKShare (辅)

全市场数据源：A股 / 期货 / 港股 / 美股 / 指数 / 板块 / 资金流向
- easy-tdx (通达信TCP协议): 毫秒级A股实时行情+K线，日均线/周/月
- AKShare (新浪/同花顺): 港股、美股、财务数据、板块排行、龙虎榜等

设计原则：
  - A股实时行情/K线优先走 easy-tdx（毫秒级，无超时风险）
  - 港股/美股走 AKShare 新浪 daily 接口
  - 财务/板块/龙虎榜走 AKShare 同花顺/新浪源
  - 全市场快照用 easy-tdx get_stock_quotes_list（秒级）或 AKShare 新浪
  - 所有接口都有 try/except 兜底
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
import os, json, threading
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
_SPOT_CACHE_TTL = 300.0  # 全市场快照缓存 5 分钟

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


# ── 缓存工具（兼容旧的 K 线磁盘缓存）─────────────────────────────
_KLINE_DISK_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".kline_cache")
_kline_lock = threading.Lock()


def _kline_cache_path(code: str, period: str, adjust: str) -> str:
    os.makedirs(_KLINE_DISK_CACHE_DIR, exist_ok=True)
    return os.path.join(_KLINE_DISK_CACHE_DIR, f"{code}_{period}_{adjust}.json")


def _kline_from_cache(code: str, period: str, adjust: str, max_age_hours: int = 6) -> list | None:
    """从磁盘缓存读 K 线，6 小时内的缓存有效"""
    import time as _time
    path = _kline_cache_path(code, period, adjust)
    with _kline_lock:
        if os.path.exists(path):
            age = _time.time() - os.path.getmtime(path)
            if age < max_age_hours * 3600:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass  # 损坏的缓存文件，忽略
    return None


def _kline_to_cache(code: str, period: str, adjust: str, data: list):
    path = _kline_cache_path(code, period, adjust)
    with _kline_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


def _cleanup_kline_cache(max_age_hours: int = 6):
    """清理过期的 K 线缓存文件"""
    import time as _time
    if not os.path.exists(_KLINE_DISK_CACHE_DIR):
        return
    now = _time.time()
    for fname in os.listdir(_KLINE_DISK_CACHE_DIR):
        fpath = os.path.join(_KLINE_DISK_CACHE_DIR, fname)
        try:
            if now - os.path.getmtime(fpath) > max_age_hours * 3600:
                os.remove(fpath)
        except OSError:
            pass

atexit.register(_cleanup_kline_cache)

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
                from mcp_finance.data import STOCK_MAPPING
                if len(df) >= 2:
                    r["pre_close"] = df.iloc[-2]["close"]
                r["名称"] = r.get("名称", STOCK_MAPPING.get(code, ""))
                return r
    except Exception as e:
        _api_logger.warning("AKShare 港股/美股行情失败: %s [%s]", e, code)

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


def _fetch_all_a_stocks_cache():
    """获取全市场 A 股快照（仅用于选股器，60s 超时保护）

    直接调用 ak.stock_zh_a_spot()，用线程超时保护防止永久挂死。
    结果缓存 5 分钟。
    注意：此函数拉取全市场 ~5000 只股票，可能需 20-30 秒。
    """
    cache_key = "all_a_stocks"
    # Double-checked locking: prevent concurrent cache stampede
    with _spot_cache_lock:
        cached = _spot_cache.get(cache_key)
        if cached is not None:
            return cached

    # Cache miss — fetch with timeout protection



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
        with _spot_cache_lock:
            _spot_cache.set(cache_key, df, ttl=_SPOT_CACHE_TTL)
    return df

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
    cached = _kline_from_cache(code, period, adjust)
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
        _kline_to_cache(code, period, adjust, records)
        return records[-limit:]
    return [{"error": f"获取A股K线失败: {code}"}]


def get_kline_hk(code, period="daily", limit=120):
    """港股 K线 — AKShare 新浪 data（TDX 不支持港股），带磁盘缓存 6h"""
    # 校验 period
    if period not in {"daily", "weekly", "monthly"}:
        return [{"error": f"不支持的K线类型: {period}，支持 daily/weekly/monthly"}]
    cached = _kline_from_cache(code, period, "")
    if cached and len(cached) >= limit:
        return cached[-limit:]

    records = []
    # 仅 AKShare 新浪（TDX 协议不支持港股 K 线）
    try:
        ak = _get_ak()
        df = _call_with_net_timeout(lambda: ak.stock_hk_daily(symbol=code, adjust=""))
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

    if records:
        _kline_to_cache(code, period, "", records)
        return records[-limit:]
    return [{"error": f"获取港股K线失败: {code}"}]


def get_kline_us(code, period="daily", limit=120):
    """美股 K线 — AKShare 新浪 data（TDX 不支持美股），带磁盘缓存 6h"""
    # 校验 period
    if period not in {"daily", "weekly", "monthly"}:
        return [{"error": f"不支持的K线类型: {period}，支持 daily/weekly/monthly"}]
    cached = _kline_from_cache(code, period, "")
    if cached and len(cached) >= limit:
        return cached[-limit:]

    records = []
    try:
        ak = _get_ak()
        df = _call_with_net_timeout(lambda: ak.stock_us_daily(symbol=code, adjust=""))
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

    if records:
        _kline_to_cache(code, period, "", records)
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
    """A股财务数据"""
    ak = _get_ak()
    try:
        df = _call_with_net_timeout(lambda: ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期"))
        if df is None or df.empty:
            return {"提示": f"未找到 {code} 的财务数据"}
        df = df.tail(count)
        return {
            "股票代码": code,
            "财务期数": len(df),
            "数据": _df_to_records(df),
            "数据源": "AKShare-同花顺",
        }
    except Exception as e:
        return {"error": f"获取财务数据失败: {e}"}


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
                        "最新价": _safe_float(row.get("最新价", row.get("close", row.get("price")))),
                        "涨跌幅": _safe_float(row.get("涨跌幅", row.get("change_pct", row.get("涨跌比例")))),
                        "涨跌额": _safe_float(row.get("涨跌额", row.get("change"))),
                        "今开": _safe_float(row.get("今开", row.get("open"))),
                        "昨收": _safe_float(row.get("昨收", row.get("pre_close", row.get("preclose")))),
                        "最高": _safe_float(row.get("最高", row.get("high"))),
                        "最低": _safe_float(row.get("最低", row.get("low"))),
                        "成交量": _safe_float(row.get("成交量", row.get("volume"))),
                        "成交额": _safe_float(row.get("成交额", row.get("amount"))),
                    })
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
    """获取板块涨幅排行（同花顺优先，概念板块东方财富降级）"""
    ak = _get_ak()
    if market == "a":
        try:
            if sector_type == "industry":
                df = _call_with_net_timeout(lambda: ak.stock_board_industry_name_ths())
            elif sector_type == "concept":
                df = _call_with_net_timeout(lambda: ak.stock_board_concept_name_ths())
                if df is None or df.empty:
                    # 降级: 东方财富概念板块
                    df = _call_with_net_timeout(lambda: ak.stock_board_concept_name_em())
            else:
                df = _call_with_net_timeout(lambda: ak.stock_board_industry_name_ths())
            if df is None or df.empty:
                return []
            # 同花顺返回的列名与东方财富不同，适配一下
            result = _df_to_records(df.head(top_n))
            for r in result:
                r["市场"] = "A股"
            return result
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
    for symbol_name in ["北上", "沪股通", "深股通"]:
        try:
            df = _call_with_net_timeout(lambda s=symbol_name: ak.stock_hsgt_hist_em(symbol=s))
            if df is not None and not df.empty:
                records = _df_to_records(df.tail(days))
                return {"类型": "北向资金(沪深港通)", "最近天数": len(records), "数据": records, "数据源": "AKShare"}
        except Exception as e:
            _api_logger.warning("北向资金获取失败: %s", e)
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

    if market == "a":
        for code, name in STOCK_MAPPING.items():
            candidates.append((code, name, "A股"))
        # HOT_STOCKS 也包含额外A股
        for s in HOT_STOCKS:
            if s["市场"] == "A股":
                candidates.append((s["代码"], s["名称"], "A股"))
    elif market == "hk":
        for s in HOT_STOCKS:
            if s["市场"] == "港股":
                candidates.append((s["代码"], s["名称"], "港股"))
    elif market == "us":
        for s in HOT_STOCKS:
            if s["市场"] == "美股":
                candidates.append((s["代码"], s["名称"], "美股"))
    else:
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


def handle_realtime_quote(arguments):
    """统一实时行情 handler"""
    code = arguments["code"]
    market = arguments.get("market", "a")
    fn_map = {"a": get_realtime_quote_a, "hk": get_realtime_quote_hk, "us": get_realtime_quote_us, "futures": get_realtime_quote_futures}
    fn = fn_map.get(market)
    if fn is None:
        raise InvalidCodeError(f"不支持的市场类型: {market}")
    result = fn(code)
    if "error" in result and "数据源" not in result:
        raise StockError(result["error"], code="API_ERROR")
    return result


def handle_kline(arguments):
    """K线数据 handler"""
    code = arguments["code"]
    market = arguments.get("market", "a")
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
    """财务数据 handler"""
    code = arguments["code"]
    market = arguments.get("market", "a")
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
                df = _call_with_net_timeout(lambda: akshare.stock_hk_financial_indicator(symbol=code))
            else:
                df = _call_with_net_timeout(lambda: akshare.stock_us_financial_indicator(symbol=code))
            if df is not None and not df.empty:
                records = []
                for _, row in df.head(count).iterrows():
                    records.append({str(k): (None if pd.isna(v) else v) for k, v in row.items()})
                return {"数据": records, "市场": market, "提示": "港股/美股财务数据来自AKShare,字段与A股不同"}
        except Exception as e:
            _api_logger.warning("港股/美股财务数据获取失败: %s [%s]", e, code)
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
