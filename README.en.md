<h1 align="center"> mcp-finance</h1>
<p align="center">
  <strong>All-Market Real-time Quotes MCP Server</strong><br>
  A-shares, HK stocks, US stocks, futures — quotes, indicators, screening, backtesting, alerts & interactive charts for AI assistants
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

> Real-time multi-market data at your AI's fingertips — A-shares, HK, US, futures, via easy-tdx (TDX TCP) + AKShare.

---

## Why mcp-finance?

**The problem**: Generic web search gives you stale, unstructured stock data. AI can't compute indicators, screen stocks, or monitor alerts from HTML pages.

**The solution**: mcp-finance gives AI a **real-time, structured, computable** multi-market data source:

- **Multi-Market** — A-shares + HK stocks + US stocks + China futures in one MCP Server
- **Dual Data Source** — easy-tdx (TDX TCP, millisecond-level) + AKShare (financials/sectors), stable and reliable
- **Technical Analysis** — 9 indicators computed locally, 10+ signal patterns
- **Stock Screener** — 11-dimension screening (gain, volume, turnover, PE, PB, ROE, market cap, etc.)
- **Backtesting** — Backtrader event-driven engine, 5 strategies (MA/MACD/RSI/KDJ/BOLL) with Buy & Hold benchmark
- **Optimization** — Grid-scan parameter combinations for optimal strategy settings
- **Alerts** — Price/indicator triggers DingTalk / WeCom / ServerChan push
- **K-line Charts** — Interactive Plotly HTML, candles + MA + MACD/KDJ/RSI
- **Premium Data** — Dragon Tiger Board, Block Trades, Margin Trading

---

## Requirements

- **Python** 3.10 or higher
- Virtual environment recommended (venv / conda)
- easy-tdx requires access to TDX market servers (default ports 7709/7727)

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/ojkkk/mcp-finance.git
cd mcp-finance

# 2. (Recommended) Create virtual environment
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# 3. Install
pip install -e .
```

**Core Dependencies**: `mcp` / `pydantic` / `easy-tdx` / `akshare` / `plotly` / `numpy` / `pandas` / `backtrader`

> easy-tdx connects to TDX servers via TCP for millisecond real-time data; AKShare supplements financial/sector data.

### Configuration

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
      "type": "stdio",
      "command": "python",
      "args": ["-m", "mcp_finance.server"]
    }
  }
}
```
</details>

---

## All Tools (20+)

### Market Data (All Markets)

| Tool | Description | Required |
|------|-------------|----------|
| `get_realtime_quote` | Real-time quote (A-shares/HK/US/futures) | `code` |
| `get_kline` | K-line data (daily/weekly/monthly, adj.) | `code` |
| `get_financials` | A-share financials (revenue, net profit, ROE) | `code` |
| `get_market_indices` | Major indices (A-shares/HK/US) | — |
| `get_sector_ranking` | A-share sector/concept ranking | — |
| `get_north_flow` | Northbound / Southbound capital flow | — |
| `search_stock` | Fuzzy search (A-shares/HK/US) | `keyword` |
| `get_futures_list` | China futures contracts snapshot | — |
| `batch_quotes` | Batch query multiple stocks | `codes` |

### Technical Analysis

| Tool | Description | Required |
|------|-------------|----------|
| `get_technical_indicators` | 9 indicators + auto signal detection | `code` |

**Indicators**: MA(5/10/20/60/120/250), MACD(DIF/DEA/BAR), KDJ(K/D/J), RSI(6/14/24), BOLL(upper/mid/lower), WR, BIAS

**Auto-detected signals**: Golden/Death cross (MA, MACD), MACD bar reversal, KDJ overbought/oversold, RSI extremes (>80/<20), bullish/bearish MA alignment

### Stock Screener

| Tool | Description | Required |
|------|-------------|----------|
| `stock_screener` | Multi-condition A-share screening | 1 condition |

**Filters (11 dimensions)**: gain%, volume ratio, turnover%, P/E, P/B, market cap, ROE, main capital inflow, dividend yield, amplitude, max gain

### Backtesting & Optimization

| Tool | Description | Required |
|------|-------------|----------|
| `backtest_strategy` | Strategy backtest (5 strategies + benchmark) | `code` |
| `optimize_strategy` | Parameter grid-scan optimization | `code` |

**Strategies**: ma_cross, macd_signal, rsi_signal, kdj_signal, boll_signal
**Engine**: Backtrader event-driven engine. A-share rules: T+1 / price-limit filtering / commission + stamp tax

### Alerts

| Tool | Description | Required |
|------|-------------|----------|

**Conditions**: price above/below, gain threshold, MACD golden/death cross, MA golden/death cross, RSI extremes
**Channels**: DingTalk / WeCom / ServerChan

### Charts

| Tool | Description | Required |
|------|-------------|----------|
| `plot_kline` | Interactive K-line HTML (candles + MA + MACD/KDJ/RSI) | `code` |

> **Not a PNG image!** Generates an interactive HTML file — open in browser for zoom/pan/hover.

### Premium Data

| Tool | Description | Required |
|------|-------------|----------|
| `get_dragon_tiger` | Dragon Tiger Board daily details | — |
| `get_block_trades` | Block trade details | — |
| `get_margin_trading` | Margin trading & securities lending | — |

### Diagnostics

| Tool | Description |
|------|-------------|
| `test_data_sources` | Test all data sources (A/HK/US/futures) |

---

## Examples

| Use Case | Ask AI |
|----------|--------|
| A-share quote | "What's the price of Moutai (600519)?" |
| HK quote | "How much is Tencent (00700) in HK?" |
| US quote | "What's AAPL stock price? And NVDA?" |
| Futures | "Show me rebar futures prices" |
| Technical analysis | "Analyze BYD's indicators — any golden crosses?" |
| Financials | "What's CATL's revenue and ROE trend?" |
| Screening | "Screen A-shares: gain > 3%, volume ratio > 1.5, ROE > 10%" |
| Backtesting | "Backtest Midea with MA(5,20) vs Buy & Hold for 2024" |
| Optimization | "Find the best MA parameters for Midea" |
| Alerts | "Alert me if Moutai drops below 1800 or MACD death cross" |
| Chart | "Plot Moutai's last 120 days with MACD and RSI" |
| Futures list | "List all active futures contracts" |

---

## Data Sources

| Source | Description | Coverage |
|--------|-------------|----------|
| **easy-tdx** | TDX TCP protocol, millisecond real-time, no API key | A/HK/US/Futures K-lines + quotes + sectors + flows |
| **AKShare** | Open-source financial data library (Sina/Tonghuashun) | Financials, Dragon Tiger, Block Trades, Margin Trading |

> easy-tdx connects directly to TDX market servers (port 7709) with millisecond latency and no rate limits.
> AKShare serves as a supplement for financial data and premium content not covered by easy-tdx.

---

## Project Structure

```
mcp-finance/
  pyproject.toml
  README.md              (Chinese)
  README.en.md           (English)
  mcp_finance/
    __init__.py
    api.py               # easy-tdx + AKShare dual data source layer
    data.py              # 230+ stock mappings (A/HK/US) & sectors
    indicators.py        # 9 indicators + signals (pure Python)
    screener.py          # Market-wide screening (11 dimensions)
    backtest.py          # Backtrader event-driven backtesting + optimization
    akshare_data.py      # Backward-compat re-export
    chart.py             # Plotly interactive K-line charts
    server.py            # MCP Server (20+ tools + resources)
    errors.py            # Unified error types
    logging_config.py    # Structured logging
    validators.py        # Pydantic validation
    cache.py             # TTL cache
    pybroker_strategy.py # PyBroker ML strategy (experimental)
  tests/
    test_indicators.py   # Indicator unit tests
    test_screener.py     # Screener unit tests
```

---

## Known Limitations & Roadmap

### Current Limitations
- **Intraday tick data** — Not yet exposed (easy-tdx already supports it)
- **US/HK financials** — Basic quotes & K-lines only; advanced data to be expanded
- **Futures minute bars** — Daily-level only

### v0.6.0 Update
- [x] **easy-tdx primary source** — Millisecond TDX TCP real-time quotes, default priority
- [x] **Auto-compute change %/amount** — Fallback calculation from close/pre_close for AKShare
- [x] **Import deadlock fix** — Lazy imports moved to module-level, eliminated 120s timeout
- [x] **Process leak fix** — Stale MCP server processes no longer accumulate
- [x] **try/except/finally fixes** — 4 structural errors + thread pool leak resolved
- [x] **PyBroker ML strategy** — Walkforward Analysis + technical feature engineering
- [x] **Backtrader engine** — Event-driven, 5 strategies, A-share rules adapted


---

## Credits

- [**easy-tdx**](https://github.com/handsomejustin/easy-tdx) — Open-source TDX TCP protocol client, millisecond multi-market data
- [**AKShare**](https://akshare.akfamily.xyz/) — Open-source financial data library
- [**Backtrader**](https://www.backtrader.com/) — Event-driven backtesting framework
- [**Plotly**](https://plotly.com/python/) — Interactive charting
- [**MCP**](https://modelcontextprotocol.io/) — Standard protocol for AI tool calling

---

## License

[MIT](LICENSE)

---

<p align="center">
   Star this repo if you find it useful!<br>
  <sub>PRs welcome — new indicators, data sources, push channels...</sub>
</p>

<p align="center">
  <a href="README.md"> 阅读中文版本</a>
</p>