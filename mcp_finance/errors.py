"""统一错误类型定义"""


class StockError(Exception):
    """mcp-stock-cn 基础异常"""
    def __init__(self, message: str, code: str = "UNKNOWN"):
        self.message = message
        self.code = code
        super().__init__(message)


class DataSourceError(StockError):
    """数据源不可用（网络、限流等）"""
    def __init__(self, message: str, source: str = ""):
        self.source = source
        super().__init__(message, code="DATA_SOURCE_ERROR")


class InvalidCodeError(StockError):
    """无效的股票代码或名称"""
    def __init__(self, code: str):
        self.code_str = code
        super().__init__(f"未找到股票: {code}", code="INVALID_CODE")


class NoDataError(StockError):
    """请求的数据为空（非交易日等）"""
    def __init__(self, message: str = "暂无数据"):
        super().__init__(message, code="NO_DATA")


class BacktestError(StockError):
    """回测引擎异常"""
    def __init__(self, message: str):
        super().__init__(message, code="BACKTEST_ERROR")


class AlertError(StockError):
    """告警系统异常"""
    def __init__(self, message: str):
        super().__init__(message, code="ALERT_ERROR")


def format_error_response(error: StockError) -> dict:
    """将 StockError 格式化为统一的 JSON 响应"""
    return {
        "error": True,
        "code": error.code,
        "message": error.message,
    }
