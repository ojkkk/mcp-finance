<h1 align="center">mcp-finance</h1>
<p align="center">
  <strong>MCP Server = 全市场金融数据</strong><br>
  A股/港股/美股/期货 · 行情/K线/指标/选股/回测/分析
</p>

<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="https://github.com/ojkkk/mcp-finance">GitHub</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/MCP-1.4+-purple" alt="MCP">
  <img src="https://img.shields.io/badge/version-0.9.0-orange" alt="v0.9.0">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT">
</p>

---

## 工具列表 (29 tools)

| 类别 | 工具 |
|------|------|
| 行情 | `get_realtime_quote` `batch_quotes` `get_market_indices` `get_futures_list` `search_stock` |
| K线 | `get_kline` `get_minute_kline` |
| 技术 | `get_technical_indicators` `plot_kline` `comparison_chart` |
| 财务 | `get_financials` |
| 市场 | `get_sector_ranking` `get_north_flow` `get_dragon_tiger` `get_block_trades` `get_margin_trading` |
| 资金 | `get_fund_flow` `get_institutional_holdings` |
| 宏观 | `get_macro_data`（GDP/CPI/PMI）|
| 研报 | `get_research_reports` |
| 选股 | `stock_screener` `factor_screener`（五因子打分）|
| 回测 | `backtest_strategy` `optimize_strategy` `portfolio_backtest` |
| 分析 | `analyze_stock`（综合评分）`compare_stocks`（横向对比）`correlation_matrix` |
| 系统 | `test_data_sources` |

---

## 安装配置

```bash
pip install mcp-markets
```

**Claude Desktop / Codex:**
```json
{
  "mcpServers": {
    "mcp-finance": {
      "command": "python",
      "args": ["-m", "mcp_finance.server"]
    }
  }
}
```

---

## 数据源

easy-tdx（通达信毫秒级）+ AKShare + yfinance 三源兜底。

---

## 使用示例

| 场景 | 跟 AI 说 |
|------|----------|
| 行情 | "查一下茅台最新价" |
| K线 | "画茅台最近120天K线图，带MACD" |
| 选股 | "涨超3%、量比>1.5的A股" |
| 回测 | "双均线(5,20)回测美的集团2024年" |
| 分析 | "综合分析一下茅台" |
| 对比 | "对比茅台、五粮液、泸州老窖" |
| 组合 | "茅台+美的等权组合回测" |
| 宏观 | "最近CPI数据" |
| 研报 | "茅台最新研报" |

---

## 项目结构

```
mcp_finance/
  server.py        # MCP 路由
  api.py           # 三数据源封装
  api_extended.py  # 分钟K线/资金流/机构/宏观/研报
  analysis.py      # 综合评分/多因子/多股对比
  portfolio.py     # 组合回测/相关性
  indicators.py    # 技术指标
  backtest.py      # 回测引擎
  chart.py         # K线图/对比图
  screener.py      # 选股器
  cache.py         # 缓存
  validators.py    # 参数校验
```

---

## License

MIT
