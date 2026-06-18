<h1 align="center"> mcp-finance</h1>
<p align="center">
  <strong>All-Market Real-time Quotes MCP Server</strong><br>
  A-shares, HK stocks, US stocks, futures — quotes, indicators, screening, backtesting & interactive charts for AI assistants
</p>

<p align="center">
  <a href="README.md"> 中文</a> 
  <a href="https://github.com/ojkkk/mcp-finance">GitHub</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.4+-purple?logo=modelcontextprotocol" alt="MCP 1.4+">
  <img src="https://img.shields.io/badge/version-0.6.0-orange" alt="Version 0.6.0">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/data-easy--tdx%20%2B%20AKShare-blue" alt="Dual Data Source">
</p>

---

## Why mcp-finance?

mcp-finance gives AI a **real-time, structured, computable** multi-market data source:

- **Multi-Market** — A-shares + HK stocks + US stocks + China futures in one MCP Server
- **Dual Data Source** — easy-tdx TDX TCP protocol (millisecond) + AKShare (financials/sectors)
- **Technical Analysis** — 9 indicators computed locally in pure Python, auto signal detection
- **Stock Screener** — Full A-share market screening across 11 dimensions
- **Strategy Backtesting** — Backtrader event-driven engine with 5 strategies + parameter optimization
- **K-line Charts** — Plotly interactive HTML charts with candlestick + MA + MACD/KDJ/RSI subplots
- **Advanced Data** — Dragon & Tiger, block trades, margin trading, north-bound flow

---

## Install

```bash
# PyPI (recommended)
pip install mcp-finance

# Or from source
git clone https://github.com/ojkkk/mcp-finance.git
cd mcp-finance
pip install -e .
```

**Requires**: Python 3.10+, easy-tdx, akshare, plotly, pandas, numpy, backtrader, pydantic, mcp

---

## Configuration

<details>
<summary><b>Claude Desktop</b></summary>

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
</details>

<details>
<summary><b>Codex</b></summary>

```bash
codex mcp add mcp-finance -- python -m mcp_finance.server
```
</details>

<details>
<summary><b>Cursor / VS Code</b></summary>

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
</details>

---

## All Tools (17)

### Market Data

| Tool | Description | Required |
|------|-------------|----------|
| `get_realtime_quote` | Real-time quote (A/HK/US/Futures) | `code` |
| `get_kline` | K-line data daily/weekly/monthly | `code` |
| `get_financials` | A-share financials (revenue, ROE, etc.) | `code` |
| `get_market_indices` | Market indices (A/HK/US) | — |
| `get_sector_ranking` | A-share sector/concept rankings | — |
| `get_north_flow` | North/South-bound fund flows | — |
| `get_futures_list` | China futures contracts list | — |
| `batch_quotes` | Batch query multiple stocks | `codes` |

### Technical Analysis

| Tool | Description | Required |
|------|-------------|----------|
| `get_technical_indicators` | 9 indicators + signal detection | `code` |

Indicators: MA(5/10/20/60/120/250), MACD, KDJ, RSI(6/14/24), BOLL, WR, BIAS

Signals: golden/death cross, overbought/oversold, MACD bar reversal, MA alignment

### Stock Screener

| Tool | Description | Required |
|------|-------------|----------|
| `stock_screener` | Multi-dimension A-share screening | >= 1 filter |

Filters: gain%, volume ratio, turnover%, PE, PB, market cap

### Backtesting

| Tool | Description | Required |
|------|-------------|----------|
| `backtest_strategy` | Single strategy backtest + stats | `code` |
| `optimize_strategy` | Grid search parameter optimization | `code` |

Strategies: MA cross, MACD signal, RSI signal, KDJ signal, BOLL signal

### Charts

| Tool | Description | Required |
|------|-------------|----------|
| `plot_kline` | Interactive K-line HTML chart | `code` |

> Generates an interactive HTML file — open in browser for zoom/pan/hover

### Advanced Data

| Tool | Description |
|------|-------------|
| `get_dragon_tiger` | Daily Dragon & Tiger board |
| `get_block_trades` | Block trade details |
| `get_margin_trading` | Margin trading data |

### Diagnostics

| Tool | Description |
|------|-------------|
| `test_data_sources` | Test all data source availability |

---

## Examples

| Scenario | Tell your AI |
|----------|-------------|
| A-share quote | "Check Moutai (600519) latest price" |
| HK stock | "What's Tencent (00700) trading at?" |
| US stock | "AAPL current price?" |
| Futures | "Show me rebar futures quotes" |
| K-line | "Get Moutai daily K-line for last 60 days" |
| Technical | "Analyze BYD indicators, any golden cross?" |
| Financials | "Hengrui Pharma recent revenue and ROE trend" |
| Fund flow | "Is north-bound flow net buying this week?" |
| Screener | "Scan A-shares: gain>3%, vol ratio>1.5, PE<50, PB<5" |
| Backtest | "Backtest Midea with MA(5,20) in 2024 vs buy&hold" |
| Optimize | "Find best MA params for Midea" |
| Chart | "Plot Moutai 120-day K-line with MACD and RSI" |
| Sectors | "Which sector is leading today?" |
| Futures list | "List all futures contracts" |

---

## Data Sources

| Source | Description | Coverage |
|--------|-------------|----------|
| **easy-tdx** | TDX TCP protocol, millisecond quotes | A/HK/US/Futures real-time quotes & K-lines |
| **AKShare** | Open-source financial data API | Financials, Dragon & Tiger, block trades, margin, north flow |

easy-tdx is the primary source (millisecond latency); automatically falls back to AKShare when unavailable.

---

## Project Structure

```
mcp-finance/
  pyproject.toml
  README.md              # Chinese
  README.en.md           # English
  LICENSE                # MIT
  mcp_finance/
    __init__.py           # Version
    server.py             # MCP Server router (17 tools + resources)
    api.py                # easy-tdx + AKShare dual-source layer
    data.py               # 230+ stock symbol mapping
    indicators.py         # 9 indicators + signal detection
    screener.py           # Multi-dimension stock screener
    backtest.py           # Backtrader backtesting + optimization
    chart.py              # Plotly interactive K-line charts
    pybroker_strategy.py  # PyBroker ML strategy (experimental)
    errors.py             # Unified error types
    validators.py         # Pydantic parameter validation
    cache.py              # TTL cache
    logging_config.py     # Structured logging
    akshare_data.py       # Backward-compat re-export layer
  tests/
    test_indicators.py    # Indicator unit tests
    test_screener.py      # Screener unit tests
```

---

## Credits

- [**easy-tdx**](https://github.com/handsomejustin/easy-tdx) — Open-source TDX TCP client
- [**AKShare**](https://akshare.akfamily.xyz/) — Open-source financial data library
- [**Backtrader**](https://www.backtrader.com/) — Event-driven backtesting framework
- [**Plotly**](https://plotly.com/python/) — Interactive charting
- [**MCP**](https://modelcontextprotocol.io/) — Standard AI tool-calling protocol

---

## License

[MIT](LICENSE)
