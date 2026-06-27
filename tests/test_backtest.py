"""backtest.py 单元测试 — 纯函数部分，不依赖 backtrader/network

覆盖第三轮修复的 C3（mdd 优化方向反转）和 L2（_get_stock_name 后缀剥离）。
回测引擎本身（_run_single_backtest）依赖 backtrader，留作集成测试。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

# backtrader 可能未安装，单独测试不依赖它的纯函数
try:
    from mcp_finance.backtest import _extract_metric, _get_stock_name, _STRATEGY_LABELS
    HAS_BT = True
except ImportError:
    HAS_BT = False

pytestmark = pytest.mark.skipif(not HAS_BT, reason="backtrader 依赖链未安装")


class TestExtractMetric:
    """C3 修复验证：mdd 应返回 -abs(mdd)，配合 maximize 选最小回撤"""

    def test_sharpe(self):
        assert _extract_metric({"夏普比率": 1.5}, "sharpe") == 1.5

    def test_return(self):
        assert _extract_metric({"总收益率(%)": 25.3}, "return") == 25.3

    def test_mdd_returns_negative(self):
        """mdd 应返回负值（-abs），更负=回撤更大，maximize 选最不负=最小回撤"""
        val = _extract_metric({"最大回撤(%)": -15.3}, "mdd")
        assert val == -15.3
        assert val < 0  # 必须为负

    def test_mdd_positive_input(self):
        """即使输入正数 mdd，也应取负"""
        val = _extract_metric({"最大回撤(%)": 15.3}, "mdd")
        assert val == -15.3

    def test_win_rate(self):
        assert _extract_metric({"胜率(%)": 60}, "win_rate") == 60

    def test_sortino(self):
        assert _extract_metric({"索提诺比率": 2.1}, "sortino") == 2.1

    def test_calmar(self):
        assert _extract_metric({"卡玛比率": 1.8}, "calmar") == 1.8

    def test_unknown_metric_fallback_return(self):
        """未知 metric 应回退到总收益率"""
        assert _extract_metric({"总收益率(%)": 10}, "unknown") == 10

    def test_mdd_direction_consistency():
        """C3 核心验证：两个回撤，小的（-5）应在 maximize 下优于大的（-15）"""
        small_dd = _extract_metric({"最大回撤(%)": -5}, "mdd")   # -5
        big_dd = _extract_metric({"最大回撤(%)": -15}, "mdd")    # -15
        # maximize 选最大值，-5 > -15，所以选 small_dd（回撤更小）✅
        assert max(small_dd, big_dd) == small_dd


class TestGetStockName:
    """L2 修复验证：剥离 .SH/.SZ/.HK/.US 后缀"""

    def test_bare_code(self):
        name = _get_stock_name("600519")
        assert "茅台" in name or name == "600519"

    def test_sh_suffix(self):
        name1 = _get_stock_name("600519.SH")
        name2 = _get_stock_name("600519")
        assert name1 == name2

    def test_sz_suffix(self):
        name1 = _get_stock_name("000001.SZ")
        name2 = _get_stock_name("000001")
        assert name1 == name2

    def test_us_suffix(self):
        name1 = _get_stock_name("AAPL.US")
        name2 = _get_stock_name("AAPL")
        assert name1 == name2

    def test_hk_suffix(self):
        name1 = _get_stock_name("00700.HK")
        name2 = _get_stock_name("00700")
        assert name1 == name2

    def test_dash_separator(self):
        """也支持 - 分隔符"""
        name1 = _get_stock_name("600519-SH")
        name2 = _get_stock_name("600519")
        assert name1 == name2

    def test_unknown_code_returns_code(self):
        assert _get_stock_name("UNKNOWN") == "UNKNOWN"


class TestStrategyLabels:
    """策略标签映射完整性"""

    def test_known_strategies_have_labels(self):
        for s in ["ma_cross", "macd_signal", "rsi_signal", "kdj_signal", "boll_signal"]:
            assert s in _STRATEGY_LABELS

    def test_label_is_string(self):
        for label in _STRATEGY_LABELS.values():
            assert isinstance(label, str)
            assert len(label) > 0
