<h1 align="center"> mcp-finance</h1>
<p align="center">
  <strong>All-Market Financial Data MCP Server for AI Assistants</strong><br>
  A-shares, HK, US stocks, futures — real-time quotes, K-lines, technical indicators, screening, backtesting, alerts & interactive charts
</p>

<p align="center">
  <a href="README.md"> 中文</a> ·
  <a href="https://github.com/ojkkk/mcp-finance">GitHub</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.4+-purple?logo=modelcontextprotocol" alt="MCP 1.4+">
  <img src="https://img.shields.io/badge/version-0.7.0-orange" alt="Version 0.7.0">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/data-easy--tdx%20%2B%20AKShare-blue" alt="Dual Data Source">
</p>

> Real-time multi-market data at your AI's fingertips — A-shares, HK, US, futures, via easy-tdx (TDX TCP) + AKShare.

---

## Capability Matrix

| Category | Tool | Markets |
|----------|------|---------|
| **Real-time Quotes** | `get_realtime_quote` | A/HK/US/Futures |
| **K-line Data** | `get_kline` | A/HK/US/Futures (daily/weekly/monthly, adjusted) |
| **Financials** | `get_financials` | A-shares (revenue, net profit, ROE) |
| **Market Indices** | `get_market_indices` | A/HK/US |
| **Sector Ranking** | `get_sector_ranking` | A-share industry/concept |
| **Capital Flow** | `get_north_flow` | Northbound/Southbound |
| **Stock Search** | `search_stock` | A/HK/US (local mapping, millisecond) |
| **Batch Quotes** | `batch_quotes` | A/HK/US |
| **Futures List** | `get_futures_list` | China futures main contracts |
| **Technical Indicators** | `get_technical_indicators` | MA/MACD/KDJ/RSI/BOLL/WR/BIAS + signals |
| **Stock Screener** | `stock_screener` | 11-dimension screening |
| **Strategy Backtest** | `backtest_strategy` | Backtrader, 5 strategies + Buy & Hold |
| **Param Optimization** | `optimize_strategy` | Grid scan (max 200 combos) |
| **Alerts** | `set_alert` | One-shot condition check, DingTalk/WeCom |
| **K-line Charts** | `plot_kline` | Interactive Plotly HTML |
| **Dragon Tiger** | `get_dragon_tiger` | Daily board details |
| **Block Trades** | `get_block_trades` | Transaction details |
| **Margin Trading** | `get_margin_trading` | SH + SZ exchanges |
| **ML Backtest** | `pybroker_backtest` | Experimental mean-signal backtest |
| **Diagnostics** | `test_data_sources` | Full data source availability test |

---

## Quick Start

```bash
pip install mcp-finance  # or: pip install -e ".[dev]"
```

**Core Dependencies**: `mcp` / `pydantic` / `easy-tdx` / `akshare` / `plotly` / `numpy` / `pandas` / `backtrader`

### Claude Desktop

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

### Cursor / VS Code

```json
{
  "mcpServers": {
    "mcp-finance": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "mcp_finance.server"]
    }
  }
}
```

---

## Data Sources

| Source | Description | Coverage |
|--------|-------------|----------|
| **easy-tdx** | TDX TCP protocol, millisecond, no API key | A-share quotes + K-lines |
| **AKShare (Sina)** | Open-source financial data | HK/US quotes + K-lines |
| **AKShare (THS)** | Open-source financial data | Financials, sector rankings |

> easy-tdx connects directly to TDX market servers (port 7709). All network calls have 15s thread-level timeout + 90s asyncio-level timeout protection.

---

## Examples

| Use Case | Ask AI |
|----------|--------|
| A-share quote | "What's Moutai (600519) price?" |
| HK quote | "How much is Tencent (00700) in HK?" |
| US quote | "What's AAPL stock price? And NVDA?" |
| Technical analysis | "Analyze BYD's indicators — any golden crosses?" |
| Screening | "Screen: gain > 3%, turnover > 5%, ROE > 10%" |
| Backtesting | "Backtest Midea (000333) with MA(5,20) vs Buy & Hold for 2024" |
| Optimization | "Find best MA parameters for Midea" |
| Chart | "Plot Moutai's last 120 days with MACD and RSI" |

---

## Project Structure

```
mcp-finance/
  pyproject.toml
  README.md               (Chinese)
  README.en.md            (English)
  CHANGELOG.md
  .github/workflows/      # CI
  run_monitor.py
  mcp_finance/
    __init__.py
    api.py                 # easy-tdx + AKShare dual source
    data.py                # Stock mappings & sectors
    indicators.py          # 9 indicators + signals
    screener.py            # 11-dimension screener
    backtest.py            # Backtrader engine
    pybroker_strategy.py   # Experimental ML strategy
    monitor.py             # Alerting
    chart.py               # Plotly charts
    server.py              # MCP Server router
    cache.py               # TTL cache
    validators.py          # Pydantic validation
    errors.py              # Error types
    logging_config.py      # Structured logging
  tests/
    test_indicators.py
    test_screener.py
```

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check mcp_finance/
```

---

## License

MIT

<p align="center">
  <a href="README.md"> 阅读中文版本</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>
