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
        allowed = {"daily", "weekly", "monthly", "minute60"}
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
    min_roe: Optional[float] = Field(default=None, ge=-100, le=100, description="（暂不可用）最低净资产收益率 ROE(%)")
    min_main_inflow: Optional[float] = Field(default=None, description="（暂不可用）最低主力净流入（万元）")
    min_dividend: Optional[float] = Field(default=None, ge=0, le=100, description="（暂不可用）最低股息率(%)")
    top_n: int = Field(default=50, ge=1, le=200)


class BacktestParams(StockCodeModel):
    strategy: str = Field(default="ma_cross", description="策略名称")
    fast_period: int = Field(default=5, ge=2, le=250)
    slow_period: int = Field(default=20, ge=3, le=500)
    start_date: Optional[str] = Field(default=None, description="开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="结束日期 YYYY-MM-DD")
    initial_capital: float = Field(default=100000.0, ge=1000, le=1e9)
    generate_chart: bool = Field(default=True)

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in {"ma_cross", "macd_signal", "rsi_signal", "kdj_signal", "boll_signal"}:
            raise ValueError("strategy 必须是 ma_cross/macd_signal/rsi_signal/kdj_signal/boll_signal")
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

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v: str) -> str:
        if v not in {"sharpe", "return", "mdd", "win_rate"}:
            raise ValueError("metric 必须是 sharpe/return/mdd/win_rate")
        return v

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in {"ma_cross", "macd_signal", "rsi_signal", "kdj_signal", "boll_signal"}:
            raise ValueError("strategy 必须是 ma_cross/macd_signal/rsi_signal/kdj_signal/boll_signal")
        return v


class PlotKlineParams(StockCodeModel):
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
