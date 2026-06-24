<h1 align="center">mcp-finance</h1>
<p align="center">
  <strong>MCP Server for Global Financial Markets</strong><br>
  A-shares / HK / US / Futures · Quotes / K-line / Indicators / Screening / Backtesting / Analysis
</p>

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="https://github.com/ojkkk/mcp-finance">GitHub</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/MCP-1.4+-purple" alt="MCP">
  <img src="https://img.shields.io/badge/version-0.9.0-orange" alt="v0.9.0">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT">
</p>

---

## Tools (29 total)

| Category | Tools |
|----------|-------|
| Quotes | `get_realtime_quote` `batch_quotes` `get_market_indices` `get_futures_list` `search_stock` |
| K-line | `get_kline` `get_minute_kline` |
| Technical | `get_technical_indicators` `plot_kline` `comparison_chart` |
| Financials | `get_financials` |
| Market | `get_sector_ranking` `get_north_flow` `get_dragon_tiger` `get_block_trades` `get_margin_trading` |
| Fund Flow | `get_fund_flow` `get_institutional_holdings` |
| Macro | `get_macro_data` (GDP/CPI/PMI) |
| Research | `get_research_reports` |
| Screening | `stock_screener` `factor_screener` (5-factor scoring) |
| Backtesting | `backtest_strategy` `optimize_strategy` `portfolio_backtest` |
| Analysis | `analyze_stock` `compare_stocks` `correlation_matrix` |
| System | `test_data_sources` |

---

## Install

```bash
pip install mcp-markets
```

**Claude Desktop / Codex config:**
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

## Data Sources

easy-tdx (millisecond-level) + AKShare + yfinance triple fallback.

---

## Examples

| Task | Ask AI |
|------|--------|
| Quote | "What is Moutai (600519) latest price?" |
| Chart | "Plot 120-day K-line for 600519 with MACD" |
| Screen | "A-shares with gain >3% and volume ratio >1.5" |
| Backtest | "Backtest MA(5,20) crossover on 000333 for 2024" |
| Analyze | "Give me a full analysis of 600519" |
| Compare | "Compare 600519, 000858, 000568" |
| Portfolio | "Equal-weight portfolio backtest for 600519 + 000333" |
| Macro | "Latest CPI data for China" |
| Research | "Latest analyst reports for 600519" |

---

## Project Structure

```
mcp_finance/
  server.py        # MCP routing
  api.py           # Triple data source layer
  api_extended.py  # Minute K-line / Fund flow / Institutional / Macro / Research
  analysis.py      # Stock scoring / Multi-factor / Comparison
  portfolio.py     # Portfolio backtest / Correlation
  indicators.py    # Technical indicators
  backtest.py      # Backtesting engine
  chart.py         # K-line & comparison charts
  screener.py      # Stock screener
  cache.py         # Cache layer
  validators.py    # Parameter validation
```

---

## License

MIT
