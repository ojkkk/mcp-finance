"""选股器模块单元测试"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_finance.screener import screen_stocks
from unittest.mock import patch, MagicMock


# 模拟东方财富 API 返回的行情数据
MOCK_STOCKS = [
    {"f12": "600519", "f14": "贵州茅台", "f2": "1800.00", "f3": "2.50", "f8": "0.50", "f9": "35.00",
     "f10": "1.20", "f20": "21000000000000", "f23": "12.00", "f37": "28.00", "f45": "1.80", "f62": "50000",
     "f7": "3.00", "f17": "1750.00", "f15": "1820.00", "f16": "1740.00", "f18": "1755.00"},
    {"f12": "300750", "f14": "宁德时代", "f2": "220.00", "f3": "5.00", "f8": "3.00", "f9": "45.00",
     "f10": "2.00", "f20": "5000000000000", "f23": "8.00", "f37": "18.00", "f45": "0.50", "f62": "80000",
     "f7": "6.00", "f17": "210.00", "f15": "225.00", "f16": "208.00", "f18": "209.50"},
    {"f12": "000333", "f14": "美的集团", "f2": "65.00", "f3": "-1.20", "f8": "1.20", "f9": "15.00",
     "f10": "0.80", "f20": "450000000000", "f23": "3.50", "f37": "22.00", "f45": "3.50", "f62": "-10000",
     "f7": "2.50", "f17": "66.00", "f15": "66.50", "f16": "64.50", "f18": "65.80"},
    {"f12": "688981", "f14": "中芯国际", "f2": "45.00", "f3": "12.00", "f8": "8.00", "f9": "120.00",
     "f10": "3.50", "f20": "200000000000", "f23": "6.00", "f37": "5.00", "f45": "None", "f62": "200000",
     "f7": "15.00", "f17": "41.00", "f15": "47.00", "f16": "40.50", "f18": "40.20"},
]


class TestScreenerFiltering:
    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_min_gain_filter(self, mock_fetch):
        """测试最低涨幅筛选"""
        mock_fetch.return_value = MOCK_STOCKS
        result = screen_stocks(min_gain=3.0)

        assert result["count"] > 0
        for stock in result["matched"]:
            assert stock["涨跌幅"] is not None
            assert stock["涨跌幅"] >= 3.0

    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_max_pe_filter(self, mock_fetch):
        """测试市盈率上限筛选"""
        mock_fetch.return_value = MOCK_STOCKS
        result = screen_stocks(max_pe=50)

        for stock in result["matched"]:
            assert stock["市盈率"] is not None
            assert stock["市盈率"] <= 50

    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_min_roe_filter(self, mock_fetch):
        """测试 ROE 下限筛选"""
        mock_fetch.return_value = MOCK_STOCKS
        result = screen_stocks(min_roe=20)

        for stock in result["matched"]:
            assert stock["ROE"] is not None
            assert stock["ROE"] >= 20

    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_multi_condition(self, mock_fetch):
        """测试多条件组合筛选"""
        mock_fetch.return_value = MOCK_STOCKS
        result = screen_stocks(min_gain=2.0, max_pe=50, min_roe=15, min_pb=1.0)

        for stock in result["matched"]:
            assert stock["涨跌幅"] >= 2.0
            assert stock["市盈率"] <= 50
            assert stock["ROE"] >= 15

    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_result_structure(self, mock_fetch):
        """测试返回数据结构完整性"""
        mock_fetch.return_value = MOCK_STOCKS
        result = screen_stocks()
        assert "matched" in result
        assert "count" in result
        assert "total_scanned" in result
        assert "conditions" in result
        for stock in result["matched"]:
            assert "代码" in stock
            assert "名称" in stock
            assert "涨跌幅" in stock

    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_empty_result(self, mock_fetch):
        """测试无匹配结果"""
        mock_fetch.return_value = MOCK_STOCKS
        result = screen_stocks(min_gain=50.0)  # 不可能有这么高的
        assert result["count"] == 0
        assert result["matched"] == []

    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_sorting_by_gain_desc(self, mock_fetch):
        """测试结果按涨幅降序排列"""
        mock_fetch.return_value = MOCK_STOCKS
        result = screen_stocks()
        if len(result["matched"]) >= 2:
            gains = [s["涨跌幅"] for s in result["matched"] if s["涨跌幅"] is not None]
            assert gains == sorted(gains, reverse=True)

    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_top_n_limit(self, mock_fetch):
        """测试 top_n 限制"""
        mock_fetch.return_value = MOCK_STOCKS
        result = screen_stocks(top_n=2)
        assert len(result["matched"]) <= 2


class TestScreenerEdgeCases:
    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_all_none_fields(self, mock_fetch):
        """测试字段为 None 时不崩溃"""
        mock_fetch.return_value = [{
            "f12": "000001", "f14": "测试股票",
            "f2": None, "f3": None, "f8": None, "f9": None,
            "f10": None, "f20": None, "f23": None, "f37": None,
            "f45": None, "f62": None, "f7": None,
            "f17": None, "f15": None, "f16": None, "f18": None,
        }]
        result = screen_stocks()
        assert result["total_scanned"] == 1

    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_empty_api_response(self, mock_fetch):
        """测试 API 返回空列表"""
        mock_fetch.return_value = []
        result = screen_stocks()
        assert result["matched"] == []
        assert result["total_scanned"] == 0


class TestHandlerFunctions:
    """测试 handler 函数"""
    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_handle_stock_screener(self, mock_fetch):
        mock_fetch.return_value = MOCK_STOCKS
        from mcp_finance.screener import handle_stock_screener
        result = handle_stock_screener({"min_gain": 5.0})
        assert result["count"] > 0
        for stock in result["matched"]:
            assert stock["涨跌幅"] >= 5.0

    @patch("mcp_finance.screener._fetch_all_a_stocks")
    def test_handle_empty_raises(self, mock_fetch):
        mock_fetch.return_value = MOCK_STOCKS
        from mcp_finance.screener import handle_stock_screener
        from mcp_finance.errors import NoDataError
        with pytest.raises(NoDataError):
            handle_stock_screener({"min_gain": 999.0})
