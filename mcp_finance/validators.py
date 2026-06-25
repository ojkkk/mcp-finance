"""工具参数校验 — 基于 Pydantic 模型的输入验证"""

from __future__ import annotations
import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── 工具函数 ──

def _is_valid_stock_code(code: str) -> bool:
    """检查是否为有效的 A 股代码格式 (6位数字)"""
    return bool(re.match(r"^\d{6}$", code))


def _is_valid_date(date_str: str) -> bool:
    """检查是否为有效日期格式 YYYY-MM-DD"""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _is_valid_date_compact(date_str: str) -> bool:
    """检查是否为有效日期格式 YYYYMMDD"""
    try:
        datetime.strptime(date_str, "%Y%m%d")
        return True
    except ValueError:
        return False


# ── Pydantic 模型 ──

class StockCodeModel(BaseModel):
    """股票代码基础模型"""
    code: str = Field(..., description="6位股票代码", min_length=1, max_length=20)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("股票代码不能为空")
        return v


class KlineParams(StockCodeModel):
    ktype: str = Field(default="daily", description="K线类型")
    adjust: str = Field(default="qfq", description="复权方式")
    limit: int = Field(default=120, ge=1, le=800, description="返回条数")

    @field_validator("ktype")
    @classmethod
    def validate_ktype(cls, v: str) -> str:
        allowed = {"daily", "weekly", "monthly"}
        if v not in allowed:
            raise ValueError(f"ktype 必须是 {allowed} 之一")
        return v

    @field_validator("adjust")
    @classmethod
    def validate_adjust(cls, v: str) -> str:
        allowed = {"qfq", "bfq", "hfq"}
        if v not in allowed:
            raise ValueError(f"adjust 必须是 {allowed} 之一")
        return v


class FinancialsParams(StockCodeModel):
    market: str = Field(default="a", description="市场: a/hk/us")
    count: int = Field(default=4, ge=1, le=20, description="返回期数")


class SectorRankingParams(BaseModel):
    sector_type: str = Field(default="industry", description="板块类型")
    top_n: int = Field(default=10, ge=1, le=50)

    @field_validator("sector_type")
    @classmethod
    def validate_sector_type(cls, v: str) -> str:
        allowed = {"industry", "concept", "region"}
        if v not in allowed:
            raise ValueError(f"sector_type 必须是 {allowed} 之一")
        return v


class NorthFlowParams(BaseModel):
    days: int = Field(default=5, ge=1, le=30, description="最近几天")



class TechnicalIndicatorsParams(StockCodeModel):
    market: str = Field(default="a", description="市场: a/hk/us")
    days: int = Field(default=120, ge=30, le=800, description="K线条数")
    ktype: str = Field(default="daily", description="K线类型")

    @field_validator("ktype")
    @classmethod
    def validate_ktype(cls, v: str) -> str:
        if v not in {"daily", "weekly", "monthly"}:
            raise ValueError("ktype 必须是 daily/weekly/monthly")
        return v


class ScreenerParams(BaseModel):
    min_gain: Optional[float] = Field(default=None, ge=-100, le=100)
    max_gain: Optional[float] = Field(default=None, ge=-100, le=100)
    min_volume_ratio: Optional[float] = Field(default=None, ge=0)
    min_turnover: Optional[float] = Field(default=None, ge=0, le=100)
    max_pe: Optional[float] = Field(default=None, ge=0)
    min_market_cap: Optional[float] = Field(default=None, ge=0)
    min_pb: Optional[float] = Field(default=None, ge=0)
    max_pb: Optional[float] = Field(default=None, ge=0)
    min_roe: Optional[float] = Field(default=None, ge=-100, le=100, description="最低净资产收益率 ROE(%) — 通过财务缓存获取")
    top_n: int = Field(default=50, ge=1, le=200)


class BacktestParams(StockCodeModel):
    strategy: str = Field(default="ma_cross", description="策略名称")
    fast_period: int = Field(default=5, ge=2, le=250)
    slow_period: int = Field(default=20, ge=3, le=500)
    start_date: Optional[str] = Field(default=None, description="开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="结束日期 YYYY-MM-DD")
    initial_capital: float = Field(default=100000.0, ge=1000, le=1e9)
    generate_chart: bool = Field(default=True)
    slippage_type: str = Field(default="fixed_perc", description="滑点模型")
    slippage_value: float = Field(default=0.001, ge=0.0, le=0.1)
    strategy_config: Optional[dict] = Field(default=None, description="自定义策略配置")

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in {"ma_cross", "macd_signal", "rsi_signal", "kdj_signal", "boll_signal", "turtle", "vol_trend", "mean_rev", "custom"}:
            raise ValueError("strategy 必须是 ma_cross/macd_signal/rsi_signal/kdj_signal/boll_signal/turtle/vol_trend/mean_rev/custom")
        return v

    @field_validator("fast_period")
    @classmethod
    def validate_fast_period(cls, v: int) -> int:
        if v < 2:
            raise ValueError("fast_period 必须 >= 2")
        return v

    @model_validator(mode="after")
    def validate_periods(self):
        if self.slow_period <= self.fast_period:
            raise ValueError(f"slow_period({self.slow_period}) 必须大于 fast_period({self.fast_period})")
        if self.start_date and not _is_valid_date(self.start_date):
            raise ValueError(f"start_date 格式错误: {self.start_date}，应为 YYYY-MM-DD")
        if self.end_date and not _is_valid_date(self.end_date):
            raise ValueError(f"end_date 格式错误: {self.end_date}，应为 YYYY-MM-DD")
        return self


class OptimizeParams(StockCodeModel):
    strategy: str = Field(default="ma_cross")
    fast_min: int = Field(default=5, ge=2, le=200)
    fast_max: int = Field(default=20, ge=3, le=250)
    fast_step: int = Field(default=5, ge=1, le=50)
    slow_min: int = Field(default=20, ge=3, le=400)
    slow_max: int = Field(default=60, ge=5, le=500)
    slow_step: int = Field(default=10, ge=1, le=50)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    metric: str = Field(default="sharpe")
    optimization_method: str = Field(default="grid", description="优化方法")
    n_trials: int = Field(default=50, ge=10, le=200)

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v: str) -> str:
        if v not in {"sharpe", "return", "mdd", "win_rate"}:
            raise ValueError("metric 必须是 sharpe/return/mdd/win_rate")
        return v

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in {"ma_cross", "macd_signal", "rsi_signal", "kdj_signal", "boll_signal", "turtle", "vol_trend", "mean_rev", "custom"}:
            raise ValueError("strategy 必须是 ma_cross/macd_signal/rsi_signal/kdj_signal/boll_signal/turtle/vol_trend/mean_rev/custom")
        return v


class PlotKlineParams(StockCodeModel):
    market: str = Field(default="a", description="市场: a/hk/us")
    days: int = Field(default=120, ge=10, le=800)
    ktype: str = Field(default="daily")
    show_macd: bool = True
    show_kdj: bool = False
    show_rsi: bool = False

    @field_validator("ktype")
    @classmethod
    def validate_ktype(cls, v: str) -> str:
        if v not in {"daily", "weekly", "monthly"}:
            raise ValueError("ktype 必须是 daily/weekly/monthly")
        return v


# ── 新增工具校验 (方向2-6) ──

class MinuteKlineParams(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    freq: str = Field(default="5")
    limit: int = Field(default=240, ge=1, le=800)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("股票代码不能为空")
        return v

    @field_validator("freq")
    @classmethod
    def validate_freq(cls, v: str) -> str:
        if v not in {"1", "5", "15", "30", "60"}:
            raise ValueError("freq 必须是 1/5/15/30/60")
        return v


class FundFlowParams(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    days: int = Field(default=5, ge=1, le=60)


class InstitutionalHoldingsParams(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)


class MacroDataParams(BaseModel):
    indicator: str = Field(default="cpi")
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("indicator")
    @classmethod
    def validate_indicator(cls, v: str) -> str:
        if v not in {"gdp", "cpi", "pmi", "money_supply", "fx_reserve"}:
            raise ValueError("indicator 必须是 gdp/cpi/pmi/money_supply/fx_reserve")
        return v


class ResearchReportsParams(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    limit: int = Field(default=10, ge=1, le=50)


class AnalyzeStockParams(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)


class CompareStocksParams(BaseModel):
    codes: list[str] = Field(..., min_length=2, max_length=10)


class FactorScreenerParams(BaseModel):
    top_n: int = Field(default=30, ge=1, le=100)
    min_market_cap: float = Field(default=50, ge=0)


class PortfolioBacktestParams(BaseModel):
    codes: list[str] = Field(..., min_length=1, max_length=20)
    weights: Optional[list[float]] = Field(default=None)
    initial_capital: float = Field(default=100000, ge=1000, le=1e9)
    days: int = Field(default=250, ge=20, le=800)


class CorrelationMatrixParams(BaseModel):
    codes: list[str] = Field(..., min_length=2, max_length=20)
    days: int = Field(default=120, ge=20, le=800)


class ComparisonChartParams(BaseModel):
    codes: list[str] = Field(..., min_length=2, max_length=10)
    days: int = Field(default=120, ge=10, le=800)



def validate_and_coerce(model_cls: type[BaseModel], arguments: dict[str, Any]) -> dict[str, Any]:
    """验证参数并返回清洗后的字典，失败则抛出 StockError"""
    from mcp_finance.errors import StockError

    try:
        model = model_cls(**arguments)
        return model.model_dump(exclude_none=False)
    except Exception as e:
        # 提取 Pydantic 校验错误信息
        errors = []
        if hasattr(e, "errors"):
            for err in e.errors():
                loc = ".".join(str(x) for x in err.get("loc", []))
                msg = err.get("msg", "")
                errors.append(f"{loc}: {msg}")
        error_msg = "; ".join(errors) if errors else str(e)
        raise StockError(f"参数校验失败: {error_msg}", code="VALIDATION_ERROR")


class RealtimeQuoteParams(BaseModel):
    code: str = Field(..., description="股票代码或名称", min_length=1, max_length=20)
    market: str = Field(default="a", description="市场: a/hk/us/futures")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("股票代码不能为空")
        return v


class MarketIndicesParams(BaseModel):
    market: str = Field(default="a", description="市场: a/hk/us")

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        if v not in {"a", "hk", "us"}:
            raise ValueError("market 必须是 a/hk/us")
        return v


class BatchQuotesParams(BaseModel):
    codes: list[str] = Field(..., description="股票代码列表", min_length=1, max_length=50)
    market: str = Field(default="a", description="市场: a/hk/us")

    @field_validator("codes")
    @classmethod
    def validate_codes(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("codes 不能为空")
        return [c.strip() for c in v if c.strip()]


class DragonTigerParams(BaseModel):
    date: Optional[str] = Field(default=None, description="日期 YYYYMMDD，如 '20250613'")
    
    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _is_valid_date_compact(v):
            raise ValueError(f"date 格式错误: {v}，应为 YYYYMMDD")
        return v


class BlockTradesParams(BaseModel):
    symbol: Optional[str] = Field(default=None, description="股票代码，留空返回全市场")
    start_date: Optional[str] = Field(default=None, description="开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="结束日期 YYYY-MM-DD")
    
    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _is_valid_date(v):
            raise ValueError(f"start_date 格式错误: {v}，应为 YYYY-MM-DD")
        return v
    
    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _is_valid_date(v):
            raise ValueError(f"end_date 格式错误: {v}，应为 YYYY-MM-DD")
        return v


class MarginTradingParams(BaseModel):
    date: Optional[str] = Field(default=None, description="日期 YYYYMMDD，如 '20250613'")
    market: str = Field(default="all", description="市场: sh/sz/all")
    
    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _is_valid_date_compact(v):
            raise ValueError(f"date 格式错误: {v}，应为 YYYYMMDD")
        return v


class SearchStockParams(BaseModel):
    keyword: str = Field(..., description="搜索关键词（代码或名称）", min_length=1, max_length=50)
    market: str = Field(default="a", description="市场: a/A股, hk/港股, us/美股")
    top_n: int = Field(default=10, ge=1, le=100, description="最多返回条数")

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("搜索关键词不能为空")
        return v


# BUG-18 修复: 添加 WalkForwardParams 和 MonteCarloParams 验证器
# 原来这两个工具没有注册到 _TOOL_VALIDATORS，LLM 传来的字符串类型整数参数不会被自动转换

_VALID_STRATEGIES = {"ma_cross", "macd_signal", "rsi_signal", "kdj_signal", "boll_signal",
                     "turtle", "vol_trend", "mean_rev", "custom"}
_VALID_METRICS = {"sharpe", "return", "mdd", "win_rate", "sortino", "calmar"}


class WalkForwardParams(BaseModel):
    code: str = Field(..., description="股票代码", min_length=1, max_length=20)
    strategy: str = Field(default="ma_cross", description="策略名称")
    train_years: float = Field(default=2.0, ge=0.5, le=10.0, description="训练窗口年数")
    test_months: int = Field(default=6, ge=1, le=24, description="测试窗口月数")
    step_months: int = Field(default=6, ge=1, le=12, description="滑动步长月数")
    fast_min: int = Field(default=3, ge=2, le=100, description="快线参数最小值")
    fast_max: int = Field(default=40, ge=3, le=200, description="快线参数最大值")
    slow_min: int = Field(default=10, ge=3, le=200, description="慢线参数最小值")
    slow_max: int = Field(default=120, ge=5, le=500, description="慢线参数最大值")
    metric: str = Field(default="sharpe", description="优化目标")
    n_trials: int = Field(default=30, ge=5, le=100, description="每窗口贝叶斯优化次数")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return v.strip()

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in _VALID_STRATEGIES:
            raise ValueError(f"strategy 必须是 {sorted(_VALID_STRATEGIES)} 之一")
        return v

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v: str) -> str:
        if v not in _VALID_METRICS:
            raise ValueError(f"metric 必须是 {sorted(_VALID_METRICS)} 之一")
        return v

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.fast_max <= self.fast_min:
            raise ValueError("fast_max 必须大于 fast_min")
        if self.slow_max <= self.slow_min:
            raise ValueError("slow_max 必须大于 slow_min")
        return self


class MonteCarloParams(BaseModel):
    code: str = Field(..., description="股票代码", min_length=1, max_length=20)
    strategy: str = Field(default="ma_cross", description="策略名称")
    fast_period: int = Field(default=5, ge=2, le=250, description="快线周期")
    slow_period: int = Field(default=20, ge=3, le=500, description="慢线周期")
    start_date: Optional[str] = Field(default=None, description="开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="结束日期 YYYY-MM-DD")
    n_simulations: int = Field(default=1000, ge=100, le=10000, description="模拟次数")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return v.strip()

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in _VALID_STRATEGIES:
            raise ValueError(f"strategy 必须是 {sorted(_VALID_STRATEGIES)} 之一")
        return v

    @model_validator(mode="after")
    def validate_periods(self):
        if self.slow_period <= self.fast_period:
            raise ValueError(f"slow_period({self.slow_period}) 必须大于 fast_period({self.fast_period})")
        if self.start_date and not _is_valid_date(self.start_date):
            raise ValueError(f"start_date 格式错误: {self.start_date}，应为 YYYY-MM-DD")
        if self.end_date and not _is_valid_date(self.end_date):
            raise ValueError(f"end_date 格式错误: {self.end_date}，应为 YYYY-MM-DD")
        return self
