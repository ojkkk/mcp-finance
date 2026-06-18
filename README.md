<h1 align="center"> mcp-finance</h1>
<p align="center">
  <strong>全市场实时行情 MCP Server</strong><br>
  AI 助手直接查询 A股/港股/美股/期货行情、计算技术指标、筛选股票、回测策略、生成 K 线图表
</p>

<p align="center">
  <a href="README.en.md"> English</a> 
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

## 为什么选 mcp-finance？

mcp-finance 给了 AI 一个**实时、结构化、可计算**的全市场数据源：

- **全市场覆盖** — A股 + 港股 + 美股 + 国内期货，一个 MCP Server 搞定
- **双数据源** — easy-tdx 通达信 TCP 协议（毫秒级）+ AKShare（财务/板块等补充）
- **技术分析** — 9 大指标纯 Python 本地计算，金叉死叉自动识别
- **条件选股** — 全市场 A 股按涨跌幅/量比/换手率/PE/PB/市值等 11 维度筛选
- **策略回测** — Backtrader 事件驱动引擎，5 种策略 + 参数网格优化
- **K线图表** — Plotly 交互式 HTML，蜡烛图+均线+MACD/KDJ/RSI，可缩放平移
- **高级数据** — 龙虎榜/大宗交易/两融/北向资金全覆盖

---

## 安装

```bash
# PyPI 安装（推荐）
pip install mcp-finance

# 或从源码安装
git clone https://github.com/ojkkk/mcp-finance.git
cd mcp-finance
pip install -e .
```

**依赖**：Python 3.10+, easy-tdx, akshare, plotly, pandas, numpy, backtrader, pydantic, mcp

---

## 配置

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

## 全部工具 (17 个)

### 基础行情

| 工具 | 说明 | 必填 |
|------|------|------|
| `get_realtime_quote` | 个股实时行情 (A股/港股/美股/期货) | `code` |
| `get_kline` | K线数据 日/周/月 + 前/后复权 | `code` |
| `get_financials` | A股财务数据（营收/净利润/ROE等） | `code` |
| `get_market_indices` | 大盘指数 (A股/港股/美股) | — |
| `get_sector_ranking` | A股行业/概念板块涨幅排行 | — |
| `get_north_flow` | 北向/南向资金日流向 | — |
| `get_futures_list` | 国内期货合约实时行情列表 | — |
| `batch_quotes` | 批量查询多只股票行情 | `codes` |

### 技术分析

| 工具 | 说明 | 必填 |
|------|------|------|
| `get_technical_indicators` | 9 指标一键计算 + 信号识别 | `code` |

计算指标：MA(5/10/20/60/120/250)、MACD、KDJ、RSI(6/14/24)、BOLL、WR、BIAS

自动信号：金叉/死叉（均线/MACD/KDJ）、超买超卖（KDJ/RSI）、MACD柱转正/负、均线多头/空头排列

### 条件选股

| 工具 | 说明 | 必填 |
|------|------|------|
| `stock_screener` | 全市场 11 维度筛选 A 股 | 至少一个条件 |

支持条件：涨跌幅 / 量比 / 换手率 / 市盈率 / 市净率 / 总市值 / ROE / 股息率 / 主力净流入

### 策略回测

| 工具 | 说明 | 必填 |
|------|------|------|
| `backtest_strategy` | 单策略回测 + 绩效统计 | `code` |
| `optimize_strategy` | 参数网格优化，自动找最优参数 | `code` |

支持策略：双均线交叉 / MACD金叉死叉 / RSI超买超卖 / KDJ金叉死叉 / BOLL突破

### 图表

| 工具 | 说明 | 必填 |
|------|------|------|
| `plot_kline` | 交互式 K 线 HTML（蜡烛图+均线+副图） | `code` |

> 生成的是交互式HTML文件，浏览器打开支持缩放/平移/悬停查看数值

### 高级数据

| 工具 | 说明 |
|------|------|
| `get_dragon_tiger` | 龙虎榜每日明细 |
| `get_block_trades` | 大宗交易明细 |
| `get_margin_trading` | 融资融券（两融）数据 |

### 诊断

| 工具 | 说明 |
|------|------|
| `test_data_sources` | 诊断全市场数据源可用性 |

---

## 使用示例

| 场景 | 跟 AI 说 |
|------|----------|
| A股行情 | "查一下茅台(600519)的最新价和涨跌幅" |
| 港股行情 | "腾讯(00700)港股现在多少钱？" |
| 美股行情 | "AAPL 苹果股价多少？" |
| 期货行情 | "看看螺纹钢期货行情" |
| K线数据 | "给我茅台最近 60 天的日 K 线，前复权" |
| 技术分析 | "帮我分析比亚迪的技术指标，有没有金叉？RSI 超卖没有？" |
| 财务分析 | "恒瑞医药最近几期营收和 ROE 趋势" |
| 资金面 | "这周北向资金是流入还是流出？" |
| 选股 | "全市场扫描：涨超 3%、量比 > 1.5、换手率 > 5%、PE < 50" |
| 回测 | "用双均线(5,20)回测美的集团 2024 年，跟买入持有对比" |
| 参数优化 | "帮我找找美的集团双均线的最佳参数" |
| 画图 | "画一张茅台最近 120 天的 K 线图，带上 MACD 和 RSI" |
| 板块 | "今天哪个行业板块涨得最好？" |
| 期货列表 | "列出所有期货合约的实时行情" |

---

## 数据源

| 源 | 说明 | 覆盖 |
|----|------|------|
| **easy-tdx** | 通达信 TCP 协议，毫秒级实时行情 | A股/港股/美股/期货 实时报价+K线 |
| **AKShare** | 开源金融数据接口 | 财务数据/龙虎榜/大宗交易/两融/北向资金 |

easy-tdx 优先（毫秒级），不可用时自动降级到 AKShare。

---

## 项目结构

```
mcp-finance/
  pyproject.toml
  README.md              # 中文
  README.en.md           # English
  LICENSE                # MIT
  mcp_finance/
    __init__.py           # 版本号
    server.py             # MCP Server 路由 (17 tools + resources)
    api.py                # easy-tdx + AKShare 双数据源封装
    data.py               # 230+ 股票代码名称映射
    indicators.py         # 9 大技术指标 + 信号识别
    screener.py           # 全市场条件选股
    backtest.py           # Backtrader 回测引擎 + 参数优化
    chart.py              # Plotly 交互式 K 线图
    pybroker_strategy.py  # PyBroker ML 策略（实验性）
    errors.py             # 统一错误类型
    validators.py         # Pydantic 参数校验
    cache.py              # TTL 缓存
    logging_config.py     # 结构化日志
    akshare_data.py       # 向后兼容 re-export 层
  tests/
    test_indicators.py    # 技术指标单元测试
    test_screener.py      # 选股器单元测试
```

---

## 致谢

- [**easy-tdx**](https://github.com/handsomejustin/easy-tdx) — 开源通达信 TCP 协议行情客户端
- [**AKShare**](https://akshare.akfamily.xyz/) — 开源金融数据接口库
- [**Backtrader**](https://www.backtrader.com/) — 事件驱动回测框架
- [**Plotly**](https://plotly.com/python/) — 交互式图表
- [**MCP**](https://modelcontextprotocol.io/) — AI 工具调用标准协议

---

## License

[MIT](LICENSE)
