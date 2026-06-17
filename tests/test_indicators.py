"""技术指标模块单元测试"""

import pytest
import sys
import os

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_finance.indicators import (
    _sma, _ema, _highest, _lowest,
    calc_macd, calc_kdj, calc_rsi, calc_boll,
    calc_wr, calc_bias, compute_all_indicators,
    _cross,
)


class TestSMA:
    def test_basic(self):
        result = _sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert result == [None, None, 2.0, 3.0, 4.0]

    def test_single_element(self):
        result = _sma([5.0], 1)
        assert result == [5.0]

    def test_empty(self):
        result = _sma([], 5)
        assert result == []

    def test_all_none_before_period(self):
        result = _sma([10.0, 20.0, 30.0], 5)
        assert all(v is None for v in result)  # 数据不够 n 条

    def test_decimals(self):
        result = _sma([1.5, 2.5, 3.5], 2)
        assert result == [None, 2.0, 3.0]


class TestEMA:
    def test_basic(self):
        result = _ema([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == 2.0  # (1+2+3)/3 = 2.0
        assert result[3] is not None
        assert result[4] is not None

    def test_empty(self):
        assert _ema([], 5) == []


class TestHighestLowest:
    def test_highest(self):
        result = _highest([10.0, 20.0, 15.0, 25.0, 18.0], 3)
        assert result == [None, None, 20.0, 25.0, 25.0]

    def test_lowest(self):
        result = _lowest([10.0, 20.0, 15.0, 5.0, 18.0], 3)
        assert result == [None, None, 10.0, 5.0, 5.0]


class TestMACD:
    def test_basic(self):
        closes = [10.0 + i * 0.5 for i in range(50)]  # 上涨趋势
        result = calc_macd(closes, fast=12, slow=26, signal=9)
        assert "DIF" in result
        assert "DEA" in result
        assert "MACD" in result
        # DIF 应该 > 0（上涨趋势）
        last_dif = [v for v in result["DIF"] if v is not None][-1]
        assert last_dif > 0

    def test_downtrend(self):
        closes = [50.0 - i * 0.3 for i in range(50)]
        result = calc_macd(closes)
        last_dif = [v for v in result["DIF"] if v is not None][-1]
        assert last_dif < 0

    def test_length_match(self):
        closes = list(range(100))
        result = calc_macd(closes)
        assert len(result["DIF"]) == 100
        assert len(result["DEA"]) == 100
        assert len(result["MACD"]) == 100


class TestKDJ:
    def test_basic(self):
        n = 30
        highs = [20.0 + i * 0.3 for i in range(n)]
        lows = [8.0 + i * 0.2 for i in range(n)]
        closes = [15.0 + i * 0.25 for i in range(n)]
        result = calc_kdj(highs, lows, closes, n=9)
        assert "K" in result
        assert "D" in result
        assert "J" in result
        # 最后一个有效值在 0-100 附近
        last_k = [v for v in result["K"] if v is not None]
        assert len(last_k) > 0
        assert 0 <= last_k[-1] <= 100


class TestRSI:
    def test_uptrend_rsi_high(self):
        closes = [10.0 + i for i in range(20)]  # 持续上涨
        result = calc_rsi(closes, 14)
        last_rsi = [v for v in result if v is not None][-1]
        assert last_rsi > 90  # 极度超买

    def test_downtrend_rsi_low(self):
        closes = [100.0 - i for i in range(20)]  # 持续下跌
        result = calc_rsi(closes, 14)
        last_rsi = [v for v in result if v is not None][-1]
        assert last_rsi < 10  # 极度超卖


class TestBOLL:
    def test_basic(self):
        closes = [10.0 + i * 0.1 for i in range(30)]
        result = calc_boll(closes, n=20, k=2)
        assert "UPPER" in result
        assert "MID" in result
        assert "LOWER" in result
        last_upper = [v for v in result["UPPER"] if v is not None][-1]
        last_mid = [v for v in result["MID"] if v is not None][-1]
        last_lower = [v for v in result["LOWER"] if v is not None][-1]
        assert last_upper > last_mid > last_lower


class TestCross:
    def test_golden_cross(self):
        short = [10.0, 9.0, 11.0, 12.0]
        long = [9.0, 9.5, 10.0, 10.5]
        result = _cross(short, long, up=True)
        assert len(result) == 1
        assert result[0]["index"] in (2, 3)

    def test_death_cross(self):
        short = [10.0, 11.0, 9.5, 8.0]
        long = [9.0, 9.5, 10.0, 10.5]
        result = _cross(short, long, up=False)
        assert len(result) == 1

    def test_no_cross(self):
        short = [10.0, 12.0, 14.0]
        long = [5.0, 6.0, 7.0]
        result = _cross(short, long, up=False)
        assert len(result) == 0


class TestComputeAllIndicators:
    def test_basic(self):
        """集成测试：使用模拟 K 线数据"""
        klines = []
        for i in range(120):
            close = 100.0 + i * 0.5 + (i % 10) * 0.3
            klines.append({
                "日期": f"2024-01-{min(i + 1, 28):02d}",
                "开盘价": close - 0.2,
                "收盘价": close,
                "最高价": close + 0.5,
                "最低价": close - 0.3,
                "成交量(手)": 100000 + i * 1000,
            })
        dates = [k["日期"] for k in klines]
        result = compute_all_indicators(klines, dates)

        assert "snapshot" in result
        assert "signals" in result
        snap = result["snapshot"]
        assert snap["MA5"] is not None
        assert snap["MA20"] is not None
        assert snap["MACD_DIF"] is not None
        assert snap["RSI14"] is not None
        # 上涨趋势应该有金叉信号
        signal_types = [s["type"] for s in result["signals"]]
        assert len(signal_types) > 0
