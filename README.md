<h1 align="center">mcp-finance</h1>
<p align="center">
  <strong>MCP Server for Global Financial Markets</strong><br>
   29+ tools · 3 markets · Millisecond-level quotes
</p>

<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="https://github.com/ojkkk/mcp-finance">GitHub</a> ·
  <a href="https://pypi.org/project/mcp-markets/">PyPI</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/MCP-1.4+-purple" alt="MCP">
  <img src="https://img.shields.io/badge/version-0.9.5-orange" alt="v0.9.0">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT">
</p>

---

## ⚠️ 重要免责声明

> **本工具仅供学习交流使用，所有数据仅供参考，不构成任何投资建议。**

### 数据与合规
- 数据来源于第三方公开接口与网页爬虫，**不作任何准确性、完整性、及时性的保证**
- **无自有数据源**，全部依赖第三方：
  - **easy-tdx** 依赖通达信公开 TCP 服务器，非官方 API
  - **AKShare** 受站点改版影响极大，接口随时可能失效
  - **yfinance** 依赖 Yahoo Finance 公开接口
  - **Tushare** 为第三方社区数据平台
- 数据**无合规授权**，个人非商用无问题，**企业商用存在明确版权与合规风险**

### 回测与决策
- 回测结果不代表未来表现，**历史收益不预示未来收益**
- 回测仅 8 种预设策略 + 简单网格扫描，**不支持自定义复杂策略、滑点/手续费精细化模拟**
- 使用者应独立判断并承担投资风险，**作者不对任何投资损失负责**

### 功能局限
- 财务数据仅覆盖核心指标，颗粒度粗，**无明细财报、一致预期、盈利预测等高阶基本面**
- 分钟 K 线仅支持 A 股，**港美股无高频数据**
- 回测能力偏入门级别，**无法满足专业量化需求**

### 使用前提
- **本工具定位为 AI 助手的金融数据学习工具，非专业交易/投资平台**
- 任何依赖本工具数据做出的投资决策，风险自负
- **强烈建议仅用于学习 MCP 协议开发、数据分析练习等非商业场景**

---

## 简介

`mcp-finance` 是一个面向 AI 助手（Claude / Codex / Cursor 等 MCP 客户端）的金融数据服务，基于 **easy-tdx**（通达信毫秒级） + **Tushare**（财务数据） + **AKShare** + **yfinance** 四数据源，覆盖 **A股、港股、美股、期货**四大市场，提供行情、K线、技术指标、选股、回测、分析等 29 个工具。

---

## 安装

```bash
pip install mcp-markets
```

Python 3.10+，核心依赖：`easy-tdx` `akshare` `plotly` `backtrader` `pandas` `numpy` `pydantic`。

---

## 配置 MCP 客户端

### Claude Desktop

编辑 `claude_desktop_config.json`：

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

### 可选：启用 Tushare 财务数据

[Tushare](https://tushare.pro) 提供 PE/PB/ROE、季度财报等基本面数据。免费版需要注册并获取积分后才能使用。

```bash
# 注册 https://tushare.pro → 获取 token → 设置环境变量
export TUSHARE_TOKEN=你的token   # Linux / Mac
set TUSHARE_TOKEN=你的token       # Windows CMD
$env:TUSHARE_TOKEN="你的token"    # Windows PowerShell
```

或在 MCP 客户端配置中传入：

```json
{
  "mcpServers": {
    "mcp-finance": {
      "command": "python",
      "args": ["-m", "mcp_finance.server"],
      "env": { "TUSHARE_TOKEN": "你的token" }
    }
  }
}
```

未设置或积分不足时，系统自动降级使用 AKShare / easy-tdx，不影响基础功能。

---

## 全部工具 (29)

### 行情
| 工具 | 说明 | 覆盖 |
|------|------|------|
| `get_realtime_quote` | 单股实时行情 | A股/港股/美股/期货 |
| `batch_quotes` | 批量行情查询 | A股/港股/美股 |
| `get_market_indices` | 大盘指数 | 上证/深证/恒生/道琼斯等 |
| `get_futures_list` | 期货主力合约列表 | 国内商品+股指期货 |
| `search_stock` | 股票搜索（本地毫秒级） | A股/港股/美股 |

### K线
| 工具 | 说明 | 覆盖 |
|------|------|------|
| `get_kline` | 日/周/月K线，支持前/后复权 | A股/港股/美股/期货 |
| `get_minute_kline` | 分钟K线（1/5/15/30/60分钟） | 仅A股 |

### 技术分析
| 工具 | 说明 |
|------|------|
| `get_technical_indicators` | MA/MACD/KDJ/RSI/BOLL/WR/BIAS + 金叉死叉/超买超卖信号 |
| `plot_kline` | 交互式K线图（蜡烛图+均线+MACD/KDJ/RSI副图） |
| `comparison_chart` | 多股走势对比图（归一化） |

### 财务与市场
| 工具 | 说明 |
|------|------|
| `get_financials` | 核心财务数据（营收/净利润/ROE等） |
| `get_sector_ranking` | 行业/概念板块涨幅排行 |
| `get_north_flow` | 北向/南向资金流向 |
| `get_dragon_tiger` | 龙虎榜每日明细 |
| `get_block_trades` | 大宗交易明细 |
| `get_margin_trading` | 融资融券数据 |

### 资金与机构
| 工具 | 说明 |
|------|------|
| `get_fund_flow` | 主力净流入（easy-tdx 实时） |
| `get_institutional_holdings` | 十大流通股东 |

### 宏观与研报
| 工具 | 说明 |
|------|------|
| `get_macro_data` | GDP / CPI / PMI / 货币供应量 / 外汇储备 |
| `get_research_reports` | 个股研报（机构评级/盈利预测） |

### 选股
| 工具 | 说明 |
|------|------|
| `stock_screener` | 全市场条件筛选（涨跌幅/量比/PE/PB/ROE等） |
| `factor_screener` | 五因子打分排名（动量/价值/质量/增长/波动） |

### 回测
| 工具 | 说明 |
|------|------|
| `backtest_strategy` | 8种策略回测（双均线/MACD/RSI/KDJ/BOLL/海龟/波动率/均值回归） |
| `optimize_strategy` | 参数网格扫描优化 |
| `portfolio_backtest` | 多股组合回测（支持自定义权重） |

### 分析
| 工具 | 说明 |
|------|------|
| `analyze_stock` | 综合评分（行情+技术+财务+均线 0-100分） |
| `compare_stocks` | 多股横向对比排名 |
| `correlation_matrix` | 相关性矩阵 + 低相关配对 |

### 系统
| 工具 | 说明 |
|------|------|
| `test_data_sources` | 诊断所有数据源可用性 |

---

## 使用示例

| 场景 | 对话示例 |
|------|----------|
| 查行情 | "茅台(600519)现在什么价？" |
| 画K线 | "画一张茅台120天日K线图，带上MACD和RSI" |
| 技术分析 | "分析比亚迪的技术指标，有没有金叉信号？" |
| 看资金 | "茅台今天主力净流入多少？" |
| 条件选股 | "涨超3%、量比>1.5、换手率>5%、PE<30的股票" |
| 多因子 | "五因子打分排名前20的A股" |
| 策略回测 | "双均线(5,20)回测美的集团2024年全年" |
| 参数优化 | "找美的集团双均线最优参数" |
| 投资组合 | "茅台+宁德+招行等权组合回测近一年" |
| 个股分析 | "给我一份茅台的综合分析报告" |
| 多股对比 | "对比茅台、五粮液、老窖、汾酒" |
| 相关性 | "茅台和五粮液的相关性？" |
| 宏观数据 | "最近一年CPI数据" |
| 看研报 | "茅台最新机构研报" |
| 港股美股 | "腾讯港股 / 苹果股票 什么价？" |

---


---

## Web Dashboard

`mcp-finance` 内置了一个本地 Web 界面，将 MCP Tools 的能力包装为可视化面板：

```bash
# 启动 Dashboard（默认 http://localhost:8080）
mcp-dashboard
# 或指定端口
mcp-dashboard --port 3000
```

### 功能页面

| 页面 | 说明 |
|------|------|
| **行情总览** | 大盘指数、热门股票、行业/概念/地域板块排行、北向资金流向、个股K线速查 |
| **选股器** | 多因子排行（综合评分+动量+活跃度）+ 条件选股（涨跌幅/换手率/量比/PE/PB/市值/ROE） |
| **策略回测** | 8 种策略（双均线/MACD/RSI/KDJ/BOLL/海龟/波动率趋势/均值回归），交互式权益曲线，交易记录明细 |

### 设计

- 双数据源：TDX（毫秒级行情+选股） + AKShare（财务/PE/PB/ROE，仅交易时段）
- 选股器优先使用 TDX（~3s 全市场扫描），交易时段可切换 AKShare 获取完整财务数据
- 响应式 UI，shadcn-inspired 设计系统
- Plotly 交互式图表

## 数据源

| 数据源 | 说明 | 延迟 | 合规性 |
|--------|------|------|--------|
| **easy-tdx** | 通达信 TCP 直连，主力行情/K线/资金流向 | 毫秒级 | ⚠️ 协议逆向，仅供学习 |
| **Tushare** | PE/PB/ROE/季度财报，Token 鉴权（可选，需积分） | 免费版延迟15分钟 | ✅ Token 鉴权 |
| **AKShare** | 新浪/同花顺/东方财富，板块/龙虎榜/研报 | 秒级 | ⚠️ 网页爬虫，仅供学习 |
| **yfinance** | Yahoo Finance，港股美股兜底 | 秒级 | ⚠️ 非官方接口 |

---

## 项目结构

```
mcp_finance/
  server.py           MCP 路由与工具注册
  api.py              三数据源封装层
  api_extended.py      分钟K线 / 资金流向 / 机构持仓 / 宏观 / 研报
  analysis.py          综合评分 / 多因子选股 / 多股对比
  portfolio.py         组合回测 / 相关性矩阵
  indicators.py        9大技术指标 + 信号识别
  backtest.py          Backtrader 回测引擎
  chart.py             Plotly 交互式图表 / 对比图
  screener.py          全市场选股器
  cache.py             TTL 内存+磁盘缓存
  validators.py        Pydantic 参数校验
  errors.py            统一错误处理
  logging_config.py    日志配置
tests/
  test_indicators.py   指标单元测试
  test_screener.py     选股器单元测试
```

---

## 开发

```bash
git clone https://github.com/ojkkk/mcp-finance.git
cd mcp-finance
pip install -e ".[dev]"
pytest tests/ -v
```

---

---

## 局限与潜在风险

### 数据源的天然短板

- **无自有数据源**：全部依赖第三方公开接口与网页爬虫。TDX 依赖通达信公开服务器，AKShare 受站点改版影响极大，接口随时可能失效
- **无合规授权**：数据无官方商业授权，个人学习非商用无问题，**企业商用存在明确版权风险**
- **Tushare 需要积分**：免费注册后需通过贡献赚取积分才能调用 API，详见 [Tushare 积分规则](https://tushare.pro/document/1?doc_id=13)

### 专业深度不足

- **财务数据**：仅覆盖 PE/PB/ROE 等核心指标，颗粒度粗，无明细财报、一致预期、盈利预测等高阶基本面数据
- **高频数据**：分钟 K 线仅支持 A 股，港美股无高频数据
- **回测能力**：偏入门级别，仅 8 种预设策略，参数优化为简单网格扫描，不支持自定义复杂策略、滑点/手续费精细化模拟，无法满足专业量化需求

### 免责重申

> **本工具仅供学习交流，所有数据仅供参考。投资有风险，入市需谨慎。作者不对任何因使用本工具产生的投资损失承担责任。**

---

## License

MIT

