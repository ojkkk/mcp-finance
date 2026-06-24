"""mcp-finance Dashboard — 本地 Web 界面

基于 Flask 将 MCP Tools 的能力包装为可视化 Web Dashboard。
行情总览 / 板块热力图 / 选股器 / 回测结果展示
"""
from .app import app, main

__all__ = ["app", "main"]
