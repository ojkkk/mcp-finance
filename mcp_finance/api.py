"""
AKShare 统一数据封装层

全市场数据源：A股 / 期货 / 港股 / 美股 / 指数 / 板块 / 资金流向
统一通过 akshare 获取，懒加载 + 自动重试 + 错误处理
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
import pandas as pd

_ak = None
_ak_checked = False

# ── 数据缓存 ────────────────────────────────────────────────────
_spot_cache: dict[str, tuple[float, Any]] = {}  # {market: (timestamp, df)}

def _cached_spot(market="a"):
    """带缓存的实时行情获取，避免重复下载全市场数据"""
    import time as _time
    global _spot_cache
    ttl = 5.0  # 5 秒缓存
    now = _time.time()
    if market in _spot_cache:
        ts, df = _spot_cache[market]
        if now - ts < ttl:
            return df
    ak = _get_ak()
    if market == "a":
        df = _cached_spot("a")
    elif market == "hk":
        df = _cached_spot("hk")
    elif market == "us":
        df = _cached_spot("us")
    else:
        return None
    _spot_cache[market] = (now, df)
    return df

def _get_ak():
    global _ak, _ak_checked
    if _ak is not None: return _ak
    if not _ak_checked:
        try:
            import akshare as ak
            _ak = ak
        except ImportError:
            raise ImportError("akshare 未安装，请运行: pip install akshare")
        _ak_checked = True
    if _ak is None: raise ImportError("akshare 未安装")
    return _ak

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


# ================================================================
# 1. 实时行情
# ================================================================

def get_realtime_quote_a(code):
    """A股实时行情"""
    ak = _get_ak()
    try:
        df = _cached_spot("a")
        row = df[df["代码"] == code]
        if row.empty:
            try:
                df_idx = ak.stock_zh_index_spot_em()
                row_idx = df_idx[df_idx["代码"] == code]
                if not row_idx.empty:
                    r = row_idx.iloc[0]
                    return {
                        "代码": code, "名称": r.get("名称", ""),
                        "最新价": _safe_float(r.get("最新价")),
                        "涨跌幅": _safe_float(r.get("涨跌幅")),
                        "涨跌额": _safe_float(r.get("涨跌额")),
                        "成交量(手)": _safe_float(r.get("成交量")),
                        "成交额(元)": _safe_float(r.get("成交额")),
                        "今开": _safe_float(r.get("今开")),
                        "昨收": _safe_float(r.get("昨收")),
                        "最高": _safe_float(r.get("最高")),
                        "最低": _safe_float(r.get("最低")),
                        "市场": "A股指数", "数据源": "AKShare",
                    }
            except Exception:
                pass
            return {"error": f"未找到股票 {code}"}
        r = row.iloc[0]
        return {
            "代码": code, "名称": r.get("名称", ""),
            "最新价": _safe_float(r.get("最新价")),
            "涨跌幅": _safe_float(r.get("涨跌幅")),
            "涨跌额": _safe_float(r.get("涨跌额")),
            "成交量(手)": _safe_float(r.get("成交量")),
            "成交额(元)": _safe_float(r.get("成交额")),
            "振幅": _safe_float(r.get("振幅")),
            "换手率": _safe_float(r.get("换手率")),
            "量比": _safe_float(r.get("量比")),
            "市盈率": _safe_float(r.get("市盈率-动态")),
            "市净率": _safe_float(r.get("市净率")),
            "总市值": _safe_float(r.get("总市值")),
            "流通市值": _safe_float(r.get("流通市值")),
            "今开": _safe_float(r.get("今开")),
            "昨收": _safe_float(r.get("昨收")),
            "最高": _safe_float(r.get("最高")),
            "最低": _safe_float(r.get("最低")),
            "60日涨跌幅": _safe_float(r.get("60日涨跌幅")),
            "年初至今涨跌幅": _safe_float(r.get("年初至今涨跌幅")),
            "市场": "A股", "数据源": "AKShare",
        }
    except Exception as e:
        return {"error": f"获取A股行情失败: {e}"}


def get_realtime_quote_hk(code):
    """港股实时行情"""
    ak = _get_ak()
    try:
        df = _cached_spot("hk")
        row = df[df["代码"] == code]
        if row.empty:
            return {"error": f"未找到港股 {code}"}
        r = row.iloc[0]
        return {
            "代码": code, "名称": r.get("名称", ""),
            "最新价": _safe_float(r.get("最新价")),
            "涨跌幅": _safe_float(r.get("涨跌幅")),
            "涨跌额": _safe_float(r.get("涨跌额")),
            "今开": _safe_float(r.get("今开")),
            "昨收": _safe_float(r.get("昨收")),
            "最高": _safe_float(r.get("最高")),
            "最低": _safe_float(r.get("最低")),
            "成交量": _safe_float(r.get("成交量")),
            "成交额": _safe_float(r.get("成交额")),
            "换手率": _safe_float(r.get("换手率")),
            "市盈率": _safe_float(r.get("市盈率")),
            "市场": "港股", "数据源": "AKShare",
        }
    except Exception as e:
        return {"error": f"获取港股行情失败: {e}"}


def get_realtime_quote_us(code):
    """美股实时行情"""
    ak = _get_ak()
    try:
        df = _cached_spot("us")
        row = df[df["代码"] == code]
        if row.empty:
            return {"error": f"未找到美股 {code}"}
        r = row.iloc[0]
        return {
            "代码": code, "名称": r.get("名称", ""),
            "最新价": _safe_float(r.get("最新价")),
            "涨跌幅": _safe_float(r.get("涨跌幅")),
            "涨跌额": _safe_float(r.get("涨跌额")),
            "今开": _safe_float(r.get("今开")),
            "昨收": _safe_float(r.get("昨收")),
            "最高": _safe_float(r.get("最高")),
            "最低": _safe_float(r.get("最低")),
            "成交量": _safe_float(r.get("成交量")),
            "成交额": _safe_float(r.get("成交额")),
            "振幅": _safe_float(r.get("振幅")),
            "换手率": _safe_float(r.get("换手率")),
            "市盈率": _safe_float(r.get("市盈率")),
            "总市值": _safe_float(r.get("总市值")),
            "市场": "美股", "数据源": "AKShare",
        }
    except Exception as e:
        return {"error": f"获取美股行情失败: {e}"}


def get_realtime_quote_futures(code):
    """期货实时行情"""
    ak = _get_ak()
    try:
        df = ak.futures_zh_spot()
        if "symbol" in df.columns:
            row = df[df["symbol"] == code]
        elif "代码" in df.columns:
            row = df[df["代码"] == code]
        else:
            row = df[df.iloc[:, 0] == code]
        if row.empty:
            return {"error": f"未找到期货 {code}"}
        r = row.iloc[0]
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
    except Exception as e:
        return {"error": f"获取期货行情失败: {e}"}


# ================================================================
# 2. K线数据
# ================================================================

def get_kline_a(code, period="daily", adjust="qfq", limit=120):
    """A股 K线"""
    ak = _get_ak()
    period_map = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=limit * 3)).strftime("%Y%m%d")
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period=period_map.get(period, "daily"),
            start_date=start, end_date=end, adjust=adjust,
        )
        if df is None or df.empty:
            return []
        records = []
        for _, row in df.tail(limit).iterrows():
            records.append({
                "日期": str(row.get("日期", ""))[:10],
                "开盘价": _safe_float(row.get("开盘")),
                "收盘价": _safe_float(row.get("收盘")),
                "最高价": _safe_float(row.get("最高")),
                "最低价": _safe_float(row.get("最低")),
                "成交量(手)": _safe_float(row.get("成交量")),
                "成交额(元)": _safe_float(row.get("成交额")),
                "涨跌幅": _safe_float(row.get("涨跌幅")),
                "换手率": _safe_float(row.get("换手率")),
            })
        return records
    except Exception as e:
        return [{"error": f"获取A股K线失败: {e}"}]


def get_kline_hk(code, period="daily", limit=120):
    """港股 K线"""
    ak = _get_ak()
    period_map = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=limit * 3)).strftime("%Y%m%d")
    try:
        df = ak.stock_hk_hist(
            symbol=code, period=period_map.get(period, "daily"),
            start_date=start, end_date=end, adjust="",
        )
        if df is None or df.empty:
            return []
        records = []
        for _, row in df.tail(limit).iterrows():
            records.append({
                "日期": str(row.get("日期", ""))[:10],
                "开盘价": _safe_float(row.get("开盘")),
                "收盘价": _safe_float(row.get("收盘")),
                "最高价": _safe_float(row.get("最高")),
                "最低价": _safe_float(row.get("最低")),
                "成交量(手)": _safe_float(row.get("成交量")),
                "成交额(元)": _safe_float(row.get("成交额")),
                "涨跌幅": _safe_float(row.get("涨跌幅")),
            })
        return records
    except Exception as e:
        return [{"error": f"获取港股K线失败: {e}"}]


def get_kline_us(code, period="daily", limit=120):
    """美股 K线"""
    ak = _get_ak()
    period_map = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=limit * 3)).strftime("%Y%m%d")
    try:
        df = ak.stock_us_hist(
            symbol=code, period=period_map.get(period, "daily"),
            start_date=start, end_date=end, adjust="",
        )
        if df is None or df.empty:
            return []
        records = []
        for _, row in df.tail(limit).iterrows():
            records.append({
                "日期": str(row.get("日期", ""))[:10],
                "开盘价": _safe_float(row.get("开盘")),
                "收盘价": _safe_float(row.get("收盘")),
                "最高价": _safe_float(row.get("最高")),
                "最低价": _safe_float(row.get("最低")),
                "成交量(手)": _safe_float(row.get("成交量")),
                "成交额(元)": _safe_float(row.get("成交额")),
                "涨跌幅": _safe_float(row.get("涨跌幅")),
            })
        return records
    except Exception as e:
        return [{"error": f"获取美股K线失败: {e}"}]


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
        df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
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
    """获取大盘指数行情"""
    ak = _get_ak()
    result = []
    if market == "a":
        try:
            df = ak.stock_zh_index_spot_em()
            target = list(INDEX_CODES_A.values())
            for _, row in df.iterrows():
                code = str(row.get("代码", ""))
                if code in target:
                    for name, c in INDEX_CODES_A.items():
                        if c == code:
                            result.append({
                                "名称": name, "代码": code,
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
                            break
        except Exception as e:
            return [{"error": f"获取A股指数失败: {e}"}]
    elif market == "hk":
        try:
            df = ak.stock_hk_index_spot_em()
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
                df = ak.index_us_stock_sina(symbol=code)
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
            except Exception:
                pass
    if not result:
        return [{"error": f"未获取到 {market} 市场指数数据"}]
    return result


# ================================================================
# 5. 板块排行
# ================================================================

def get_sector_ranking(market="a", sector_type="industry", top_n=10):
    """获取板块涨幅排行"""
    ak = _get_ak()
    if market == "a":
        try:
            if sector_type == "industry":
                df = ak.stock_board_industry_name_em()
            elif sector_type == "concept":
                df = ak.stock_board_concept_name_em()
            else:
                df = ak.stock_board_industry_name_em()
            if df is None or df.empty:
                return []
            if "涨跌幅" in df.columns:
                df = df.sort_values("涨跌幅", ascending=False)
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
    try:
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        if df is not None and not df.empty:
            records = _df_to_records(df.tail(days))
            return {"类型": "北向资金(沪深港通)", "最近天数": len(records), "数据": records, "数据源": "AKShare"}
    except Exception:
        pass
    try:
        df = ak.stock_hsgt_hist_em(symbol="北上")
        if df is not None and not df.empty:
            records = _df_to_records(df.tail(days))
            return {"类型": "北向资金(沪深港通)", "最近天数": len(records), "数据": records, "数据源": "AKShare"}
    except Exception:
        pass
    return {"提示": "暂无北向资金数据", "数据": []}


# ================================================================
# 7. 股票搜索
# ================================================================

def search_stocks(market, keyword, top_n=10):
    """搜索股票（全市场）"""
    ak = _get_ak()
    result = []
    if market == "a":
        try:
            df = _cached_spot("a")
            mask = df["代码"].str.contains(keyword, na=False) | df["名称"].str.contains(keyword, na=False)
            for _, row in df[mask].head(top_n).iterrows():
                result.append({"代码": row.get("代码", ""), "名称": row.get("名称", ""),
                    "最新价": _safe_float(row.get("最新价")), "涨跌幅": _safe_float(row.get("涨跌幅")),
                    "总市值": _safe_float(row.get("总市值")), "市场": "A股"})
        except Exception:
            pass
    if market == "hk":
        try:
            df = _cached_spot("hk")
            mask = df["代码"].str.contains(keyword, na=False) | df["名称"].str.contains(keyword, na=False)
            for _, row in df[mask].head(top_n).iterrows():
                result.append({"代码": row.get("代码", ""), "名称": row.get("名称", ""),
                    "最新价": _safe_float(row.get("最新价")), "涨跌幅": _safe_float(row.get("涨跌幅")), "市场": "港股"})
        except Exception:
            pass
    if market == "us":
        try:
            df = _cached_spot("us")
            mask = df["代码"].str.contains(keyword, na=False) | df["名称"].str.contains(keyword, na=False)
            for _, row in df[mask].head(top_n).iterrows():
                result.append({"代码": row.get("代码", ""), "名称": row.get("名称", ""),
                    "最新价": _safe_float(row.get("最新价")), "涨跌幅": _safe_float(row.get("涨跌幅")), "市场": "美股"})
        except Exception:
            pass
    if not result and market == "a":
        from mcp_finance.data import STOCK_MAPPING
        for code, name in STOCK_MAPPING.items():
            if keyword.upper() in code.upper() or keyword in name:
                result.append({"代码": code, "名称": name, "市场": "A股(本地)"})
                if len(result) >= top_n: break
    return result


# ================================================================
# 8. 批量行情
# ================================================================

def get_batch_quotes_a(codes):
    """批量获取A股行情"""
    ak = _get_ak()
    try:
        df = _cached_spot("a")
        result = []
        for code in codes:
            row = df[df["代码"] == code]
            if not row.empty:
                r = row.iloc[0]
                result.append({"代码": code, "名称": r.get("名称", ""),
                    "最新价": _safe_float(r.get("最新价")), "涨跌幅": _safe_float(r.get("涨跌幅")),
                    "涨跌额": _safe_float(r.get("涨跌额")), "今开": _safe_float(r.get("今开")),
                    "昨收": _safe_float(r.get("昨收")), "最高": _safe_float(r.get("最高")),
                    "最低": _safe_float(r.get("最低")), "成交量(手)": _safe_float(r.get("成交量")),
                    "成交额(元)": _safe_float(r.get("成交额")), "市盈率": _safe_float(r.get("市盈率-动态"))})
        return result
    except Exception as e:
        return [{"error": f"批量查询失败: {e}"}]


# ================================================================
# 9. 龙虎榜 / 大宗交易 / 两融
# ================================================================

def get_dragon_tiger(date=None):
    """龙虎榜每日明细"""
    ak = _get_ak()
    try:
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        df = ak.stock_lhb_detail_daily_sina(date=date)
        if df.empty:
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
            df = ak.stock_dzjy_mrmx(symbol=symbol, start_date=start, end_date=end)
        else:
            df = ak.stock_dzjy_mrtj(start_date=start, end_date=end)
        records = _df_to_records(df) if not df.empty else []
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
                df_sh = ak.stock_margin_detail_sse(date=date)
                result["上海"] = _df_to_records(df_sh)
                result["上证个股数"] = len(df_sh)
            except Exception:
                result["上海"] = []
        if market in ("sz", "all"):
            try:
                df_sz = ak.stock_margin_detail_szse(date=date)
                result["深圳"] = _df_to_records(df_sz)
                result["深证个股数"] = len(df_sz)
            except Exception:
                result["深圳"] = []
        return result
    except Exception as e:
        return {"error": f"获取两融数据失败: {e}"}


# ================================================================
# 10. 期货列表
# ================================================================

def get_futures_list():
    """获取期货合约列表"""
    ak = _get_ak()
    try:
        df = ak.futures_zh_spot()
        if df is not None and not df.empty:
            return _df_to_records(df)
        return []
    except Exception as e:
        return [{"error": f"获取期货列表失败: {e}"}]


# ================================================================
# 11. 全市场A股快照（供选股器使用）
# ================================================================

def get_all_a_stocks_snapshot():
    """获取全市场A股快照"""
    ak = _get_ak()
    try:
        df = _cached_spot("a")
        if df is None or df.empty:
            return []
        return _df_to_records(df)
    except Exception:
        return []


# ================================================================
# 12. 测试数据源
# ================================================================

def test_data_sources():
    """测试所有数据源是否可用"""
    ak = _get_ak()
    results = {"测试时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "数据源": {}}
    tests = [
        ("A股行情", lambda: _cached_spot("a")),
        ("A股指数", lambda: ak.stock_zh_index_spot_em()),
        ("港股", lambda: _cached_spot("hk")),
        ("美股", lambda: _cached_spot("us")),
        ("期货", lambda: ak.futures_zh_spot()),
        ("北向资金", lambda: ak.stock_hsgt_north_net_flow_in_em(symbol="北上")),
    ]
    for name, fn in tests:
        try:
            df = fn()
            results["数据源"][name] = "OK" if not df.empty else "EMPTY"
        except Exception as e:
            results["数据源"][name] = f"FAIL: {e}"
    return results


# ================================================================
# MCP Tool Handler 函数
# ================================================================

from mcp_finance.errors import InvalidCodeError, NoDataError, StockError
from mcp_finance.logging_config import get_logger

_logger = get_logger(__name__)


def handle_realtime_quote(arguments):
    """统一实时行情 handler"""
    code = arguments["code"]
    market = arguments.get("market", "a")
    fn_map = {"a": get_realtime_quote_a, "hk": get_realtime_quote_hk, "us": get_realtime_quote_us, "futures": get_realtime_quote_futures}
    fn = fn_map.get(market)
    if fn is None:
        raise InvalidCodeError(f"不支持的市场类型: {market}")
    result = fn(code)
    if "error" in result:
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
    count = arguments.get("count", 4)
    data = get_financials_a(code, count=count)
    if "error" in data:
        raise NoDataError(f"未找到 {code} 的财务数据")
    return data


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


def handle_search_stock(arguments):
    """搜索股票 handler"""
    keyword = arguments["keyword"]
    market = arguments.get("market", "a")
    top_n = min(arguments.get("top_n", 10), 50)
    results = search_stocks(market=market, keyword=keyword, top_n=top_n)
    if not results:
        raise NoDataError(f"未找到匹配股票: {keyword}")
    return results


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
