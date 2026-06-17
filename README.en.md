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
  <img src="https://img.shields.io/badge/version-0.4.0-orange" alt="Version 0.4.0">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome">
  <img src="https://img.shields.io/badge/data-AKShare-red" alt="AKShare Data">
</p>

> Global market data at your AI's fingertips — A-shares, HK, US, futures, all through AKShare.

---

## Why mcp-finance?

**The problem**: Generic web search gives you stale, unstructured stock data. AI can't compute indicators, screen stocks, or monitor alerts from HTML pages.

**The solution**: mcp-finance gives AI a **real-time, structured, computable** multi-market data source:

-  **Multi-Market** — A-shares + HK stocks + US stocks + China futures in one MCP Server
-  **Real-time Quotes** — AKShare unified data backend, stable and reliable
-  **Technical Analysis** — 9 indicators computed locally, 10+ signal patterns
-  **Stock Screener** — 11-dimension screening (gain, volume, turnover, PE, PB, ROE, market cap, etc.)
-  **Backtesting** — vectorbt-powered 5 strategies (MA/MACD/RSI/KDJ/BOLL) with Buy & Hold benchmark
-  **Optimization** — Grid-scan parameter combinations for optimal strategy settings
-  **Alerts** — Price/indicator triggers  DingTalk / WeCom / ServerChan push
-  **K-line Charts** — Interactive Plotly HTML, candles + MA + MACD/KDJ/RSI
-  **Premium Data** — Dragon Tiger Board, Block Trades, Margin Trading

---

## Requirements

- **Python** 3.10 or higher
- Virtual environment recommended (venv / conda)

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

**Core Dependencies**: `mcp` / `pydantic` / `akshare` / `plotly` / `numpy` / `pandas` / `vectorbt`

>  AKShare manages all data sources — zero config required.

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

A-share rules: T+1 / price-limit filtering / commission + stamp tax

### Alerts

| Tool | Description | Required |
|------|-------------|----------|
| `set_alert` | Set alert conditions + immediate evaluation | `code` |

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
| `test_data_sources` | Test all data sources (A/HK/US/futures/north-flow) |

---

## Examples

| Use Case | Ask AI |
|----------|--------|
| A-share quote | "What's the price of Moutai (600519)?" |
| HK quote | "How much is Tencent (00700) in HK?" |
| US quote | "What's AAPL stock price?" |
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

## Data Source

| Source | Description | Coverage |
|--------|-------------|----------|
| **AKShare** | Open-source financial data Python library | A-shares/HK/US/futures/indices/sectors/flows/premium-data |

>  Single source, unified API, zero config. Just `pip install`.
> AKShare (https://akshare.akfamily.xyz/) internally integrates EastMoney, Sina, Tencent and other data providers.

---

## Project Structure

```
mcp-finance/
  pyproject.toml
  README.md              (中文)
  README.en.md           (English)
  run_monitor.py         # Standalone monitoring daemon
  mcp_finance/
    __init__.py
    api.py               # AKShare unified data layer (all markets)
    data.py              # 200+ stock mappings & sectors
    indicators.py        # 9 indicators + signals (pure Python)
    screener.py          # Market-wide screening (11 dimensions)
    backtest.py          # vectorbt backtesting + optimization
    akshare_data.py      # Backward-compat re-export
    monitor.py           # Alerts + push notifications
    chart.py             # Plotly interactive K-line charts
    server.py            # MCP Server (20+ tools + resources)
    errors.py            # Unified error types
    logging_config.py    # Structured logging
    validators.py        # Pydantic validation
    cache.py             # TTL cache
  tests/
    test_indicators.py   # Indicator unit tests
    test_screener.py     # Screener unit tests
```

---

## Known Limitations & Roadmap

### Current Limitations
-  **Intraday tick data** not yet supported
-  **US/HK advanced data** — Currently basic quotes & K-lines; financials/sectors to be expanded
-  **Futures minute bars** — Daily-level only

### Planned

>  See [DEVELOPMENT_REPORT.md](./DEVELOPMENT_REPORT.md) for the comprehensive roadmap.

** P0 — High Priority (Done)**
- [x] **Backtesting Tool** — vectorbt-powered with parameter optimization
- [x] **Screener overhaul** — Expanded to 11 filter dimensions
- [x] **All-market coverage** — A-shares + HK + US + futures via AKShare
- [x] **Unified data source** — AKShare single backend, removed multi-source complexity
- [x] **Unit tests** — Core indicators + screener coverage

** P1 — Medium Priority**
- [ ] HK/US financial data & advanced analytics
- [ ] Individual stock money flow
- [ ] Web Dashboard (FastAPI + lightweight frontend)
- [ ] Multi-agent analysis

** P2 — Long-term**
- [ ] Pattern recognition
- [ ] Intraday / tick-level data
- [ ] Crypto support
- [ ] Docker + PyPI deployment
- [ ] News sentiment & research reports

> PRs and Issues are always welcome!

---

## Credits

- [**AKShare**](https://akshare.akfamily.xyz/) — One-stop open-source financial data library
- [**Plotly**](https://plotly.com/python/) — Powerful interactive charting
- [**MCP**](https://modelcontextprotocol.io/) — Standard protocol for AI tool calling
- [**vectorbt**](https://vectorbt.dev/) — Vectorized backtesting engine

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
