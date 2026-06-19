<h1 align="center"> mcp-finance</h1>
<p align="center">
  <strong>面向 AI 助手的全市场金融数据 MCP Server</strong><br>
  A股/港股/美股/期货 — 实时行情、K线、技术指标、条件选股、策略回测、盯盘告警、交互式图表
</p>

<p align="center">
  <a href="README.en.md"> English</a> ·
  <a href="https://github.com/ojkkk/mcp-finance">GitHub</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.4+-purple?logo=modelcontextprotocol" alt="MCP 1.4+">
  <img src="https://img.shields.io/badge/version-0.7.0-orange" alt="Version 0.7.0">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/data-easy--tdx%20%2B%20AKShare-blue" alt="Dual Data Source">
  <img src="https://github.com/ojkkk/mcp-finance/actions/workflows/ci.yml/badge.svg" alt="CI Status">
</p>

---

## 能力矩阵

| 类别 | 工具 | 覆盖市场 |
|------|------|----------|
| **实时行情** | `get_realtime_quote` | A股/港股/美股/期货 |
| **K线数据** | `get_kline` | A股/港股/美股/期货（日/周/月，前/后复权） |
| **财务数据** | `get_financials` | A股（营收/净利润/ROE/毛利率等） |
| **大盘指数** | `get_market_indices` | A股/港股/美股 |
| **板块排行** | `get_sector_ranking` | A股行业/概念 |
| **资金流向** | `get_north_flow` | 北向/南向资金 |
| **股票搜索** | `search_stock` | A股/港股/美股（纯本地，毫秒级） |
| **批量查询** | `batch_quotes` | A股/港股/美股 |
| **期货列表** | `get_futures_list` | 国内期货主力合约 |
| **技术指标** | `get_technical_indicators` | MA/MACD/KDJ/RSI/BOLL/WR/BIAS + 信号识别 |
| **条件选股** | `stock_screener` | 全市场 11 维度筛选（涨跌幅/量比/换手率/PE/PB/市值等） |
| **策略回测** | `backtest_strategy` | Backtrader 引擎，5 种策略 + 买入持有基准 |
| **参数优化** | `optimize_strategy` | 网格扫描（组合数上限 200） |
| **盯盘告警** | `set_alert` | 一次性条件检查，支持钉钉/企业微信/Server酱 |
| **K线图表** | `plot_kline` | Plotly 交互式 HTML（蜡烛图+均线+MACD/KDJ/RSI） |
| **龙虎榜** | `get_dragon_tiger` | 每日明细 |
| **大宗交易** | `get_block_trades` | 逐笔明细 |
| **融资融券** | `get_margin_trading` | 沪深两市 |
| **ML回测** | `pybroker_backtest` | 实验性均值比较信号回测 |
| **数据诊断** | `test_data_sources` | 全数据源可用性测试 |

---

## 快速开始

```bash
# 安装
pip install mcp-finance  # or: pip install -e ".[dev]"
```

**核心依赖**：`mcp` / `pydantic` / `easy-tdx` / `akshare` / `plotly` / `numpy` / `pandas` / `backtrader`

### 配置 Claude Desktop

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

### 配置 Codex

```bash
codex mcp add mcp-finance -- python -m mcp_finance.server
```

### 配置 Cursor / VS Code

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

## 数据源

| 源 | 说明 | 覆盖范围 |
|----|------|----------|
| **easy-tdx** | 通达信 TCP 协议，毫秒级，无需 API Key | A 股实时行情+K线 |
| **AKShare (新浪)** | 开源金融数据接口 | 港股/美股行情+K线 |
| **AKShare (同花顺)** | 开源金融数据接口 | 财务数据/板块排行 |

> easy-tdx 直连通达信行情服务器（端口 7709），毫秒级响应，无速率限制。
> 所有网络调用均有 15 秒超时保护 + asyncio 层 90 秒兜底，防止线程池耗尽。

---

## 使用示例

| 场景 | 跟 AI 说 |
|------|----------|
| A股行情 | "查一下茅台(600519)的最新价和涨跌幅" |
| 港股行情 | "腾讯(00700)港股现在多少钱？" |
| 美股行情 | "AAPL 苹果股价多少？英伟达 NVDA 什么价？" |
| 期货行情 | "看看螺纹钢期货行情" |
| 技术分析 | "帮我分析比亚迪的技术指标，有没有金叉？RSI 超卖没有？" |
| 选股 | "涨超 3%、量比 > 1.5、换手率 > 5%、ROE > 10%" |
| 回测 | "双均线(5,20)回测美的集团 2024 年，和买入持有对比" |
| 参数优化 | "帮我找找美的集团双均线的最佳参数" |
| 画图 | "画一张茅台最近 120 天的 K 线图，带上 MACD 和 RSI" |

---

## 项目结构

```
mcp-finance/
  pyproject.toml          # 依赖与元数据
  README.md               # 中文文档
  README.en.md            # English docs
  CHANGELOG.md            # 版本变更记录
  .github/workflows/      # CI 配置
  run_monitor.py          # 独立盯盘进程
  mcp_finance/
    __init__.py            # 版本号
    api.py                 # easy-tdx + AKShare 双数据源
    data.py                # 股票映射 & 行业分类
    indicators.py          # 9 大技术指标 + 信号识别
    screener.py            # 条件筛选（11 维度）
    backtest.py            # Backtrader 回测引擎
    pybroker_strategy.py   # 实验性 ML 策略
    monitor.py             # 告警监控
    chart.py               # Plotly 交互式图表
    server.py              # MCP Server 路由
    cache.py               # TTL 缓存
    validators.py          # Pydantic 参数校验
    errors.py              # 统一错误类型
    logging_config.py      # 结构化日志
  tests/
    test_indicators.py     # 指标测试
    test_screener.py       # 选股器测试
```

---

## 开发

```bash
# 安装 dev 依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# lint
ruff check mcp_finance/
```

CI 状态：![CI](https://github.com/ojkkk/mcp-finance/actions/workflows/ci.yml/badge.svg)

---

## License

MIT

<p align="center">
  <a href="README.en.md">Read this in English</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>
