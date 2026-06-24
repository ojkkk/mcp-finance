<h1 align="center">mcp-finance</h1>
<p align="center">
  <strong>MCP Server for Global Financial Markets</strong><br>
   29 tools · 3 markets · Millisecond-level quotes
</p>

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="https://github.com/ojkkk/mcp-finance">GitHub</a> ·
  <a href="https://pypi.org/project/mcp-markets/">PyPI</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/MCP-1.4+-purple" alt="MCP">
  <img src="https://img.shields.io/badge/version-0.9.4-orange" alt="v0.9.0">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT">
</p>

---

## Overview

`mcp-finance` is an MCP server that gives AI assistants (Claude / Codex / Cursor) access to real-time financial data across **A-shares, HK, US, and futures markets**. Built on **easy-tdx** (millisecond-level) + **AKShare** + **yfinance** triple data source with 29 tools covering quotes, K-line, technical indicators, screening, backtesting, and analysis.

---

## Install

```bash
pip install mcp-markets
```

Requires Python 3.10+. Core dependencies: `easy-tdx` `akshare` `plotly` `backtrader` `pandas` `numpy` `pydantic`.

---

## MCP Client Setup

### Claude Desktop

Edit `claude_desktop_config.json`:

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

### Codex

```bash
codex mcp add mcp-finance -- python -m mcp_finance.server
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

## Tools (29 total)

### Quotes
| Tool | Description | Coverage |
|------|-------------|----------|
| `get_realtime_quote` | Real-time quote for single stock | A / HK / US / Futures |
| `batch_quotes` | Batch quotes | A / HK / US |
| `get_market_indices` | Major indices | SSE / SZSE / HSI / DJI / NASDAQ / SPX |
| `get_futures_list` | Futures contracts list | China commodity + index futures |
| `search_stock` | Stock search (local, ms-level) | A / HK / US |

### K-line
| Tool | Description | Coverage |
|------|-------------|----------|
| `get_kline` | Daily/weekly/monthly K-line with adjust | A / HK / US / Futures |
| `get_minute_kline` | Minute-level K-line (1/5/15/30/60min) | A-shares only |

### Technical Analysis
| Tool | Description |
|------|-------------|
| `get_technical_indicators` | MA / MACD / KDJ / RSI / BOLL / WR / BIAS with signal detection |
| `plot_kline` | Interactive K-line chart (candlestick + MA + MACD/KDJ/RSI subplots) |
| `comparison_chart` | Multi-stock normalized comparison chart |

### Financials & Market
| Tool | Description |
|------|-------------|
| `get_financials` | Core financial data (revenue, net profit, ROE, etc.) |
| `get_sector_ranking` | Industry/concept sector performance ranking |
| `get_north_flow` | Northbound / Southbound capital flow |
| `get_dragon_tiger` | Dragon & Tiger board daily details |
| `get_block_trades` | Block trade records |
| `get_margin_trading` | Margin trading data |

### Fund Flow & Ownership
| Tool | Description |
|------|-------------|
| `get_fund_flow` | Main capital net inflow (easy-tdx real-time) |
| `get_institutional_holdings` | Top 10 shareholders |

### Macro & Research
| Tool | Description |
|------|-------------|
| `get_macro_data` | GDP / CPI / PMI / Money Supply / FX Reserves |
| `get_research_reports` | Analyst reports with ratings & earnings forecasts |

### Screening
| Tool | Description |
|------|-------------|
| `stock_screener` | Multi-condition screener (gain, volume ratio, PE, PB, ROE, etc.) |
| `factor_screener` | 5-factor scoring (momentum, value, quality, growth, volatility) |

### Backtesting
| Tool | Description |
|------|-------------|
| `backtest_strategy` | 8 strategies (MA cross, MACD, RSI, KDJ, BOLL, Turtle, Vol Trend, Mean Reversion) |
| `optimize_strategy` | Grid search parameter optimization |
| `portfolio_backtest` | Multi-stock portfolio backtest (custom weights) |

### Analysis
| Tool | Description |
|------|-------------|
| `analyze_stock` | Comprehensive analysis with 0-100 score |
| `compare_stocks` | Multi-stock comparison & ranking |
| `correlation_matrix` | Correlation matrix with low-correlation pairs |

### System
| Tool | Description |
|------|-------------|
| `test_data_sources` | Diagnose all data source availability |

---

## Usage Examples

| Task | Prompt |
|------|--------|
| Quote | "What is Moutai (600519) trading at?" |
| K-line chart | "Plot 120-day K-line for 600519 with MACD and RSI" |
| Technical | "Analyze BYD technical indicators, any golden cross?" |
| Fund flow | "What is Moutai main capital inflow today?" |
| Screen | "A-shares with gain >3%, volume ratio >1.5, PE <30" |
| Factor | "Top 20 A-shares by 5-factor score" |
| Backtest | "Backtest MA(5,20) crossover on Midea for 2024" |
| Optimize | "Find optimal MA params for Midea" |
| Portfolio | "Equal-weight backtest for Moutai + CATL + CMB last year" |
| Analyze | "Give me a full analysis report for 600519" |
| Compare | "Compare Moutai vs Wuliangye vs Luzhou Laojiao vs Fenjiu" |
| Correlation | "Correlation between Moutai and Wuliangye?" |
| Macro | "Latest year CPI data for China" |
| Research | "Latest analyst reports for 600519" |
| HK/US | "What is Tencent (00700) / Apple (AAPL) trading at?" |

---

## Data Sources

| Source | Description | Latency |
|--------|-------------|---------|
| **easy-tdx** | Direct TCP connection to TDX servers for quotes/K-line/fund flow | <1ms |
| **AKShare** | Sina/Tonghuashun/Eastmoney for financials/sectors/dragon-tiger/research | ~1s |
| **yfinance** | Yahoo Finance fallback for HK/US stocks | ~1s |

---

## Project Structure

```
mcp_finance/
  server.py           MCP routing & tool registration
  api.py              Triple data source layer
  api_extended.py      Minute K-line / Fund flow / Institutional / Macro / Research
  analysis.py          Stock scoring / Multi-factor / Comparison
  portfolio.py         Portfolio backtest / Correlation matrix
  indicators.py        9 technical indicators + signal detection
  backtest.py          Backtrader backtesting engine
  chart.py             Plotly interactive charts / Comparison charts
  screener.py          Stock screener
  cache.py             TTL memory + disk cache
  validators.py        Pydantic parameter validation
  errors.py            Unified error types
  logging_config.py    Logging configuration
tests/
  test_indicators.py   Indicator unit tests
  test_screener.py     Screener unit tests
```

---

## Development

```bash
git clone https://github.com/ojkkk/mcp-finance.git
cd mcp-finance
pip install -e ".[dev]"
pytest tests/ -v
```

---

## License

MIT
