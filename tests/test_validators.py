"""validators.py 单元测试 — 参数校验

覆盖第三轮修复的 H2（initial_capital 丢失）、H3（metric 枚举）、H4（Screener 缺字段）、L4（范围校验）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

# pydantic 是项目依赖，若未安装则跳过本测试
try:
    from mcp_finance.validators import (
        OptimizeParams, WalkForwardParams, MonteCarloParams,
        ScreenerParams, BacktestParams, validate_and_coerce,
    )
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

pytestmark = pytest.mark.skipif(not HAS_PYDANTIC, reason="pydantic 未安装")


class TestOptimizeParams:
    """H2/H3/L4 修复验证"""

    def test_initial_capital_accepted(self):
        """H2: initial_capital 不应被静默丢弃"""
        op = OptimizeParams(code="600519", initial_capital=200000)
        assert op.initial_capital == 200000

    def test_metric_sortino_accepted(self):
        """H3: metric 应接受 sortino/calmar"""
        for m in ["sharpe", "return", "mdd", "win_rate", "sortino", "calmar"]:
            op = OptimizeParams(code="600519", metric=m)
            assert op.metric == m

    def test_metric_invalid_rejected(self):
        with pytest.raises(Exception):
            OptimizeParams(code="600519", metric="invalid_metric")

    def test_fast_max_must_exceed_fast_min(self):
        """L4: fast_max 必须 > fast_min"""
        with pytest.raises(Exception):
            OptimizeParams(code="600519", fast_min=30, fast_max=10)

    def test_optimization_method_validated(self):
        with pytest.raises(Exception):
            OptimizeParams(code="600519", optimization_method="random")

    def test_code_required(self):
        with pytest.raises(Exception):
            OptimizeParams()


class TestWalkForwardParams:
    def test_initial_capital_accepted(self):
        """H2: WF 应接受 initial_capital"""
        wf = WalkForwardParams(code="600519", initial_capital=300000)
        assert wf.initial_capital == 300000

    def test_metric_all_six(self):
        for m in ["sharpe", "return", "mdd", "win_rate", "sortino", "calmar"]:
            wf = WalkForwardParams(code="600519", metric=m)
            assert wf.metric == m

    def test_ranges_validated(self):
        with pytest.raises(Exception):
            WalkForwardParams(code="600519", fast_min=50, fast_max=30)


class TestMonteCarloParams:
    def test_initial_capital_accepted(self):
        """H2: MC 应接受 initial_capital"""
        mc = MonteCarloParams(code="600519", initial_capital=150000)
        assert mc.initial_capital == 150000

    def test_n_simulations_bounds(self):
        with pytest.raises(Exception):
            MonteCarloParams(code="600519", n_simulations=50)  # < 100
        with pytest.raises(Exception):
            MonteCarloParams(code="600519", n_simulations=99999)  # > 10000


class TestScreenerParams:
    """H4 修复验证：补充的 3 个财务筛选字段"""

    def test_gross_margin_accepted(self):
        sp = ScreenerParams(min_gross_margin=30.0)
        assert sp.min_gross_margin == 30.0

    def test_net_margin_accepted(self):
        sp = ScreenerParams(min_net_margin=10.0)
        assert sp.min_net_margin == 10.0

    def test_revenue_growth_accepted(self):
        sp = ScreenerParams(min_revenue_growth=15.0)
        assert sp.min_revenue_growth == 15.0

    def test_all_three_combined(self):
        sp = ScreenerParams(min_gross_margin=30, min_net_margin=10, min_revenue_growth=15)
        assert sp.min_gross_margin == 30
        assert sp.min_net_margin == 10
        assert sp.min_revenue_growth == 15


class TestBacktestParams:
    def test_slow_must_exceed_fast(self):
        with pytest.raises(Exception):
            BacktestParams(code="600519", fast_period=20, slow_period=10)

    def test_strategy_validated(self):
        with pytest.raises(Exception):
            BacktestParams(code="600519", strategy="nonexistent")

    def test_initial_capital_bounds(self):
        with pytest.raises(Exception):
            BacktestParams(code="600519", initial_capital=100)  # < 1000


class TestValidateAndCoerce:
    def test_string_int_coerced(self):
        """LLM 传字符串类型整数应被自动转换"""
        result = validate_and_coerce(BacktestParams, {
            "code": "600519",
            "fast_period": "5",
            "slow_period": "20",
        })
        assert result["fast_period"] == 5
        assert result["slow_period"] == 20
        assert isinstance(result["fast_period"], int)
