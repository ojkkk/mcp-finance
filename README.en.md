<h1 align="center">📈 mcp-stock-cn</h1>
<p align="center">
  <strong>China A-Share Stock Market MCP Server</strong><br>
  Real-time quotes, technical indicators, stock screening, alerts & interactive charts for AI assistants
</p>

<p align="center">
  <a href="README.md">🇨🇳 中文</a> •
  <a href="https://github.com/ojkkk/mcp-stock-cn">GitHub</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/MCP-1.4+-purple?logo=modelcontextprotocol" alt="MCP 1.4+">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome">
  <img src="https://img.shields.io/badge/data-3%20sources-red" alt="3 Data Sources">
</p>

> 🇨🇳 Chinese stock market data at your AI's fingertips — no proxy, no API key, just works in China.

---

## ✨ Why mcp-stock-cn?

**The problem**: Generic web search gives you stale, unstructured stock data. AI can't compute indicators, screen stocks, or monitor alerts from HTML pages.

**The solution**: mcp-stock-cn gives AI a **real-time, structured, computable** A-share data source:

- 📊 **Real-time Quotes** — Dual-source (Tencent + EastMoney), auto-failover
- 📈 **Technical Analysis** — 9 indicators computed locally, 10+ signal patterns
- 🔍 **Stock Screener** — Multi-condition screening across all A-shares
- 🔔 **Alerts** — Price/indicator triggers → DingTalk / WeCom / ServerChan push
- 🕯️ **K-line Charts** — Interactive Plotly HTML, candles + MA + MACD/KDJ/RSI
- 💾 **Historical Data** — Baostock quant-grade K-lines (daily/weekly/monthly/minute)

---

## 📋 Requirements

- **Python** 3.9 or higher
- Virtual environment recommended (venv / conda)

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/ojkkk/mcp-stock-cn.git
cd mcp-stock-cn

# 2. (Recommended) Create virtual environment
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# 3. Install
pip install -e .
```

### Configuration

<details>
<summary><b>Claude Desktop</b></summary>

```json
{
  "mcpServers": {
    "mcp-stock-cn": {
      "command": "python",
      "args": ["-m", "cn_stock.server"]
    }
  }
}
```
</details>

<details>
<summary><b>Codex</b></summary>

```bash
codex mcp add mcp-stock-cn -- python -m cn_stock.server
```
</details>

<details>
<summary><b>Cursor / VS Code</b></summary>

```json
{
  "mcpServers": {
    "mcp-stock-cn": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "cn_stock.server"]
    }
  }
}
```
</details>

---

## 🛠️ All 12 Tools

### 📊 Market Data

| Tool | Description | Required |
|------|-------------|----------|
| `get_realtime_quote` | Real-time quote for a stock or index | `code` |
| `get_kline` | K-line data (daily/weekly/monthly/60min, adj.) | `code` |
| `get_financials` | Financials (revenue, net profit, ROE, etc.) | `code` |
| `get_market_indices` | Major indices (SSE, SZSE, ChiNext, CSI300, STAR50) | — |
| `get_sector_ranking` | Sector/concept/region ranking by change% | — |
| `get_north_flow` | Northbound / Southbound capital flow | — |
| `search_stock` | Fuzzy search by code or name | `keyword` |
| `batch_quotes` | Batch query multiple stocks | `codes` |

### 📈 Technical Analysis

| Tool | Description | Required |
|------|-------------|----------|
| `get_technical_indicators` | 9 indicators + auto signal detection | `code` |

**Indicators**: MA(5/10/20/60/120/250), MACD(DIF/DEA/BAR), KDJ(K/D/J), RSI(6/14/24), BOLL(upper/mid/lower), WR, BIAS

**Auto-detected signals**: Golden/Death cross (MA, MACD), MACD bar reversal, KDJ overbought/oversold, RSI extremes (>80/<20), bullish/bearish MA alignment

### 🔍 Stock Screener

| Tool | Description | Required |
|------|-------------|----------|
| `stock_screener` | Multi-condition A-share screening | ≥1 condition |

**Filters**: gain%, volume ratio, turnover%, P/E, market cap

### 🔔 Alerts

| Tool | Description | Required |
|------|-------------|----------|
| `set_alert` | Price/indicator triggers + push notifications | `code` |

**Channels**: 🟢 DingTalk bot &nbsp; 🟢 WeCom bot &nbsp; 🟢 ServerChan (WeChat push)

> Environment variables: `DINGTALK_WEBHOOK_URL` / `WECOM_WEBHOOK_URL` / `SERVERCHAN_SENDKEY`

<details>
<summary><b>⚙️ Alert Setup Guide (click to expand)</b></summary>

### Option 1: DingTalk Bot (Recommended)

1. Create a DingTalk group, go to Group Settings → **Smart Group Assistant** → **Add Bot** → **Custom Bot**
2. Security: choose **"Custom Keyword"**, enter `stock` (股票)
3. Copy the Webhook URL

**Windows (permanent):**
```cmd
setx DINGTALK_WEBHOOK_URL "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
```

**Restart Codex / Claude Desktop.**

### Option 2: WeCom Bot

Same steps as DingTalk — create group, add bot, get webhook URL:

```cmd
setx WECOM_WEBHOOK_URL "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
```

### Option 3: ServerChan (WeChat Push)

1. Visit https://sct.ftqq.com/, scan QR code with WeChat
2. Get your SendKey

```cmd
setx SERVERCHAN_SENDKEY "SCT_YOUR_KEY"
```

### Test

Tell AI: *"Alert me if Moutai gains over 3%, push to DingTalk"*

### Persistent Monitoring

Run `run_monitor.py` in the background for persistent monitoring:

```bash
python run_monitor.py
```

The script checks your watchlist every 60 seconds and pushes alerts when conditions trigger. Built-in cooldown prevents duplicate notifications.

**Configure your watchlist** by editing `WATCHLIST` in `run_monitor.py`:

```python
WATCHLIST = [
    {
        "code": "600519",          # Moutai
        "rules": {
            "price_below": 1500,   # Alert if drops below 1500
            "macd_death": True,    # MACD death cross
        },
        "channel": ["dingtalk"],
    },
]
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `INTERVAL_SECONDS` | Check interval (seconds) | 60 |
| `COOLDOWN_MINUTES` | Cooldown for same alert (minutes) | 30 |
| `MAX_CONSECUTIVE_ERRORS` | Exit after N consecutive errors | 10 |

</details>

### 🕯️ Charting

| Tool | Description | Required |
|------|-------------|----------|
| `plot_kline` | Interactive Plotly K-line HTML chart | `code` |

**Features**: Candlestick + MA5/10/20/60 overlay + Volume + optional MACD/KDJ/RSI subplots, dark theme, zoom/pan/hover

> ⚠️ **This is NOT a PNG image!** `plot_kline` generates an **interactive HTML file** — you MUST open it in a browser.
> 
> Files are saved to `%TEMP%/mcp-stock-cn-charts/`. Open in browser to: 🔍 zoom｜ ✋ pan｜ 👆 hover for OHLC values.
> 
> Plotly.js is **embedded inline (~3MB)** — works completely offline.

### 🧪 API Diagnostics

| Tool | Description | Required |
|------|-------------|----------|
| `test_data_sources` | Check Baostock / EastMoney / Tencent connectivity | — |

Say **"test data sources"** to run diagnostics.

---

## 💬 Examples

| Use Case | Ask AI |
|----------|--------|
| Real-time quote | "What's the price of Kweichow Moutai (600519)?" |
| Technical analysis | "Analyze BYD's technical indicators — any golden crosses?" |
| Financials | "What's CATL's revenue and ROE trend?" |
| Screening | "Screen all A-shares: gain > 3%, volume ratio > 1.5, turnover > 5%" |
| Alerts | "Alert me if Moutai drops below 1800 or MACD death cross, push to DingTalk" |
| Chart | "Plot Moutai's last 120 days with MACD and RSI" |
| Capital flow | "How much northbound money flowed in this week?" |

---

## 📡 Data Sources

| Source | Purpose | Reliability | Credits |
|--------|---------|-------------|---------|
| **Tencent Finance** `qt.gtimg.cn` | Real-time quotes | ⭐⭐⭐⭐⭐ | Tencent QQ public API |
| **EastMoney** `push2.eastmoney.com` | K-lines, sectors, capital flow | ⭐⭐⭐⭐ | [EastMoney](https://www.eastmoney.com/) |
| **EastMoney** `datacenter.eastmoney.com` | Financial data | ⭐⭐⭐⭐⭐ | [EastMoney Data Center](https://data.eastmoney.com/) |
| **Baostock** `baostock.com` | Historical K-lines (quant-grade) | ⭐⭐⭐⭐⭐ | [Baostock](http://baostock.com/) free securities data |
| **EastMoney** `searchadapter.eastmoney.com` | Stock search | ⭐⭐⭐⭐⭐ | EastMoney search API |

> 🇨🇳 All domestic APIs — no proxy, no API key required.
> 🔄 Triple-source auto-failover: **Baostock → EastMoney → Tencent** for maximum reliability.

---

## 🏗️ Project Structure

```
mcp-stock-cn/
├── pyproject.toml
├── README.md              (中文)
├── README.en.md           (English)
├── cn_stock/
│   ├── __init__.py
│   ├── api.py             # API layer (3-source failover)
│   ├── data.py            # 200+ stock mappings & sectors
│   ├── indicators.py      # 9 technical indicators + signals
│   ├── screener.py        # Market-wide stock screening
│   ├── monitor.py         # Alerts + DingTalk/WeChat push
│   ├── chart.py           # Plotly interactive K-line charts
│   └── server.py          # MCP Server (12 tools + resources)
```

---

## 🧭 Known Limitations & Roadmap

### Current Limitations
- ⏳ **Intraday tick data** not yet supported
- ⏳ **Minute K-line range** limited to recent 5 days (Baostock restriction)
- ⏳ **Hong Kong / US stocks** not covered yet

### Planned
- [ ] Hong Kong stock real-time quotes
- [ ] Individual stock money flow (retail/institutional)
- [ ] Backtesting framework integration (Backtrader / vnpy)
- [ ] Intraday chart / tick-level data
- [ ] Docker one-click deployment

> PRs and Issues are always welcome!

---

## 🙏 Credits

- [**EastMoney**](https://www.eastmoney.com/) — Real-time quotes, financial data, sector rankings
- [**Tencent Finance**](https://finance.qq.com/) — Reliable real-time quote API
- [**Baostock**](http://baostock.com/) — Free & open historical A-share data platform
- [**Plotly**](https://plotly.com/python/) — Powerful interactive charting library
- [**MCP (Model Context Protocol)**](https://modelcontextprotocol.io/) — Standard protocol for AI tool calling

---

## 📝 License

[MIT](LICENSE)

---

<p align="center">
  ⭐ Star this repo if you find it useful!<br>
  <sub>PRs welcome — especially for new indicators, data sources, and push channels.</sub>
</p>

<p align="center">
  <a href="README.md">🇨🇳 阅读中文版本</a>
</p>