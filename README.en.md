<h1 align="center">
  mcp-markets
</h1>

<p align="center">
  <strong>Global Financial Market MCP Server</strong><br>
  <em>AI-powered access to China A-Shares · HK · US Stocks · Futures</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/mcp-markets/"><img src="https://img.shields.io/pypi/v/mcp-markets?color=blue&label=PyPI" alt="PyPI"></a>
  <a href="https://pypi.org/project/mcp-markets/"><img src="https://img.shields.io/pypi/pyversions/mcp-markets?color=blue" alt="Python"></a>
  <a href="https://github.com/ojkkk/mcp-finance"><img src="https://img.shields.io/github/stars/ojkkk/mcp-finance?style=social" alt="Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT"></a>
  <br>
  <img src="https://img.shields.io/badge/tools-31-blueviolet" alt="31 Tools">
  <img src="https://img.shields.io/badge/A_Shares-%E2%9C%93-red" alt="A Shares">
  <img src="https://img.shields.io/badge/HK_Stocks-%E2%9C%93-orange" alt="HK">
  <img src="https://img.shields.io/badge/US_Stocks-%E2%9C%93-darkblue" alt="US">
  <img src="https://img.shields.io/badge/Futures-%E2%9C%93-teal" alt="Futures">
</p>

---

## Quick Start

`ash
pip install mcp-markets

# Run as MCP Server (for Claude / Codex / Cursor)
python -m mcp_finance.server

# Launch built-in Web Dashboard
mcp-dashboard              # http://localhost:8080
`

> Python 3.10+ · Zero config needed · Optional TUSHARE_TOKEN for advanced fundamentals

---

## Architecture

`mermaid
graph LR
    A["Data Sources"] --> B["easy-tdx<br/>TDX TCP · &lt;50ms"]
    A --> C["AKShare<br/>Sina/THS/EastMoney"]
    A --> D["yfinance<br/>Fallback"]
    A --> E["Tushare<br/>Fundamentals"]

    B --> F["31 MCP Tools"]
    C --> F
    D --> F
    E --> F

    F --> G["Quotes<br/>Real-time · Batch · K-line"]
    F --> H["Technical<br/>MA·MACD·KDJ·RSI·BOLL"]
    F --> I["Screening<br/>11-dim + 5-factor ranking"]
    F --> J["Backtesting<br/>9 strategies · Bayesian opt"]
    F --> K["Portfolio<br/>Comparison · Correlation"]
    F --> L["Fundamentals<br/>Financials · Research · Flow"]
    F --> M["Dashboard<br/>Flask Web · Dark theme"]

    style A fill:#1a1a2e,stroke:#e94560,color:#fff
    style F fill:#16213e,stroke:#0f3460,color:#fff
    style M fill:#e94560,color:#fff
`

---

## 31 MCP Tools

### Quote & Market Data

| Tool | Description | Source |
|------|-------------|--------|
| get_realtime_quote | Single stock real-time quote | easy-tdx → AKShare → yfinance |
| atch_quotes | Batch query multiple stocks | easy-tdx |
| get_kline | Daily/Weekly/Monthly K-line with adjust | easy-tdx / AKShare+yfinance |
| get_minute_kline | 1/5/15/30/60 min K-line (A-shares only) | easy-tdx |
| get_market_indices | A-share / HK / US market indices | easy-tdx → AKShare |
| get_futures_list | China commodity & index futures | AKShare Sina |
| search_stock | Fuzzy search by code or name | Local mapping |

### Technical Analysis

| Tool | Description |
|------|-------------|
| get_technical_indicators | MA·MACD·KDJ·RSI·BOLL·WR·BIAS + signal detection |
| plot_kline | Interactive candlestick HTML with indicators |

### Screening & Analysis

| Tool | Description |
|------|-------------|
| stock_screener | 11-dimension conditional screening |
| actor_screener | 5-factor ranking (momentum, value, quality, growth, volatility) |
| nalyze_stock | One-stop stock analysis (quote+tech+financials+score 0-100) |
| compare_stocks | Multi-stock comparison ranked by score |
| correlation_matrix | Return correlation matrix for diversification |

### Backtesting & Optimization

| Tool | Description | Strategies |
|------|-------------|------------|
| acktest_strategy | Single stock backtest | MA Cross · MACD · RSI · KDJ · BOLL · Turtle · Vol Trend · Mean Rev · Custom |
| optimize_strategy | Grid search / Optuna Bayesian optimization | Auto-pruning + parameter importance |
| portfolio_backtest | Multi-stock portfolio backtest | Custom weights / equal weight |

### Market Intelligence

| Tool | Description |
|------|-------------|
| get_sector_ranking | Industry/Concept sector rankings |
| get_north_flow | North/South-bound capital flow |
| get_fund_flow | Individual stock fund flow (ms-level via easy-tdx) |
| get_dragon_tiger | Dragon & Tiger list (brokerage buy/sell details) |
| get_block_trades | Block trade details |
| get_margin_trading | Margin trading & short selling data |
| get_macro_data | China macro economics (GDP/CPI/PMI/M2/FX reserves) |

### Fundamentals

| Tool | Description |
|------|-------------|
| get_financials | 5 categories, 19+ indicators (core/profitability/growth/risk/operations) |
| get_institutional_holdings | Top 10 shareholders & institutional holdings |
| get_research_reports | Analyst research reports (ratings + price targets) |
| comparison_chart | Multi-stock normalized comparison chart (interactive HTML) |
| 	est_data_sources | One-click diagnostic of all data sources |

---

## Web Dashboard

Built-in Flask dashboard with dark theme and Plotly interactive charts.

`ash
mcp-dashboard              # http://localhost:8080
mcp-dashboard 3000         # Custom port
`

| Page | Route | Features |
|------|-------|----------|
| **Market Overview** | / | Indices · Hot stocks · Sectors · North flow · K-line lookup |
| **Screener** | /screener | 5-factor ranking + 11-dim conditional screening |
| **Backtest** | /backtest | 9 strategies · Grid/Bayesian optimization · Walk-Forward · Monte Carlo |

---

## MCP Client Setup

<details>
<summary><b>Claude Desktop</b></summary>

`json
{
  "mcpServers": {
    "mcp-finance": {
      "command": "python",
      "args": ["-m", "mcp_finance.server"]
    }
  }
}
`
</details>

<details>
<summary><b>Codex</b></summary>

`ash
codex mcp add mcp-finance -- python -m mcp_finance.server
`
</details>

<details>
<summary><b>Cursor / VS Code</b></summary>

`json
{
  "mcpServers": {
    "mcp-finance": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "mcp_finance.server"]
    }
  }
}
`
</details>

> **Optional: Tushare** — Set TUSHARE_TOKEN=your_token env var for PE/PB/ROE data. [Register free](https://tushare.pro). Falls back gracefully without it.

---

## Development

`ash
git clone https://github.com/ojkkk/mcp-finance.git
cd mcp-finance
pip install -e ".[dev]"
pytest tests/ -v
ruff check mcp_finance/
`

---

## AI Conversation Examples

| Scenario | Natural Language Query |
|----------|----------------------|
| Quote | "What's the price of Kweichow Moutai (600519)?" |
| Technical | "Is Moutai's MACD golden cross? What's the RSI?" |
| Screening | "Find A-shares with gain >3%, volume ratio >1.5, PE <30" |
| Backtest | "Backtest MA cross (5,20) on Moutai for 2024" |
| Portfolio | "Backtest equal-weight portfolio of Moutai + CATL + CMB" |
| Analysis | "Give me a comprehensive analysis of Moutai" |
| Macro | "Show me recent CPI data for China" |

---

## Disclaimer

> **This tool is for educational purposes only. All data is for reference and does not constitute investment advice.**

- Data sourced from third-party public APIs and web scraping with **no guarantee of accuracy, completeness, or timeliness**
- **No proprietary data sources**; all data depends on easy-tdx (reverse-engineered TDX protocol), AKShare (web scraping), yfinance, and Tushare
- **No commercial data license**; personal non-commercial use is fine, **commercial use carries copyright and compliance risks**
- Backtest results do not predict future performance
- **The author bears no responsibility for any investment losses**

---

## License

MIT © [mcp-markets](https://github.com/ojkkk/mcp-finance)
