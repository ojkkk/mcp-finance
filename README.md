<h1 align="center"> mcp-finance</h1>
<p align="center">
  <strong>全市场实时行情 MCP Server</strong><br>
  让 AI 助手直接查询 A股/港股/美股/期货行情、计算技术指标、筛选股票、回测策略、盯盘告警、生成 K 线图表
</p>

<p align="center">
  <a href="README.en.md"> English</a> 
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

---

## 为什么选 mcp-finance？

> 百度搜到的股票数据是静态网页，AI 无法直接做技术分析、筛选、对比。

mcp-finance 给了 AI 一个**实时、结构化、可计算**的全市场数据源：

- **全市场覆盖** — A股 + 港股 + 美股 + 国内期货，一个 MCP Server 搞定
- **实时行情** — 基于 AKShare 统一数据源，稳定可靠
- **技术分析** — 9 大指标本地计算，金叉死叉自动识别
- **条件选股** — 全市场 A 股按 11 个维度筛选（涨跌幅/量比/换手率/PE/PB/ROE/主力净流入等）
- **策略回测** — 基于 vectorbt 向量化引擎，含双均线/MACD/RSI/KDJ/BOLL 策略回测 + 参数优化
- **参数优化** — 网格扫描参数组合，自动找最优参数（夏普/收益率/回撤/胜率多种目标）
- **盯盘告警** — 价格突破/金叉死叉/超买超卖  钉钉/微信推送
- **K线图表** — Plotly 交互式 HTML，蜡烛图+均线+MACD/KDJ/RSI
- **高级数据** — 龙虎榜/大宗交易/两融数据全覆盖

---

## 环境要求

- **Python** 3.10 或更高版本
- 建议使用虚拟环境（venv / conda）安装

---

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/ojkkk/mcp-finance.git
cd mcp-finance

# 2. 推荐：创建虚拟环境
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# 3. 安装
pip install -e .
```

**核心依赖**：`mcp` / `pydantic` / `akshare` / `plotly` / `numpy` / `pandas` / `vectorbt`

>  AKShare 统一管理所有数据源，无需额外配置

### 配置

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

或 `.codex.yaml`:

```yaml
mcp:
  servers:
    mcp-finance:
      command: python
      args: ["-m", "mcp_finance.server"]
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

## 全部工具 (20+ 个)

### 基础行情 (全市场)

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `get_realtime_quote` | 个股/指数实时行情 (A股/港股/美股/期货) | `code` |
| `get_kline` | K 线数据（日/周/月 + 前/后复权）(A股/港股/美股/期货) | `code` |
| `get_financials` | A股财务数据（营收/净利润/ROE/毛利率等） | `code` |
| `get_market_indices` | 大盘指数实时行情 (A股/港股/美股) | — |
| `get_sector_ranking` | A股行业/概念板块涨幅排行 | — |
| `get_north_flow` | 北向/南向资金日流向 | — |
| `search_stock` | 按代码或名称模糊搜索 (A股/港股/美股) | `keyword` |
| `get_futures_list` | 国内期货合约实时行情列表 | — |
| `batch_quotes` | 批量查询多只股票行情 | `codes` |

### 技术分析

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `get_technical_indicators` | 9 指标一键计算 + 信号识别 | `code` |

**计算的指标**：
MA(5/10/20/60/120/250)、MACD(DIF/DEA/柱)、KDJ(K/D/J)、RSI(6/14/24)、
BOLL(上/中/下轨)、WR(威廉)、BIAS(乖离率)

**自动识别的信号**：
均线金叉/死叉 &nbsp;  MACD金叉/死叉 &nbsp;  MACD柱转正/转负
 KDJ超买/超卖 &nbsp;  RSI严重超买(>80)/超卖(<20)
 RSI偏高(>70)/偏低(<30) &nbsp;  均线多头/空头排列

### 条件选股

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `stock_screener` | 全市场多维度筛选 | 至少一个条件 |

**支持的筛选条件（11 个维度）**：涨跌幅、量比、换手率、市盈率、市净率、ROE、总市值、主力净流入、股息率、振幅、最高涨跌幅

### 策略回测 & 优化

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `backtest_strategy` | 策略回测（5种策略+买入持有基准） | `code` |
| `optimize_strategy` | 参数扫描优化 | `code` |

**支持策略**：ma_cross(双均线交叉)、macd_signal(MACD金叉死叉)、rsi_signal(RSI超买超卖)、kdj_signal(KDJ金叉死叉)、boll_signal(BOLL突破)

A 股规则适配：T+1 / 涨跌停过滤 / 千一佣金 / 卖方印花税 / 整数手

### 盯盘告警

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `set_alert` | 设置条件告警+立即评估 | `code` |

**告警条件**：价格突破/跌破、涨跌幅阈值、MACD金叉死叉、均线金叉死叉、RSI超买超卖
**推送渠道**：钉钉机器人 / 企业微信 / Server酱(微信)

### 图表

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `plot_kline` | 交互式 K 线 HTML（蜡烛图+均线+MACD/KDJ/RSI） | `code` |

> **这不是PNG图片！** 生成的是交互式HTML文件，请用浏览器打开，支持缩放/平移/悬停查看数值

### 高级数据

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `get_dragon_tiger` | 龙虎榜每日明细 | — |
| `get_block_trades` | 大宗交易明细 | — |
| `get_margin_trading` | 融资融券（两融）数据 | — |

### 诊断

| 工具 | 说明 |
|------|------|
| `test_data_sources` | 诊断全市场数据源(A股/港股/美股/期货/北向资金)可用性 |

---

## 使用示例

| 场景 | 跟 AI 说 |
|------|----------|
| A股行情 | "查一下茅台(600519)的最新价和涨跌幅" |
| 港股行情 | "腾讯(00700)港股现在多少钱？" |
| 美股行情 | "AAPL 苹果股价多少？" |
| 期货行情 | "看看螺纹钢期货行情" |
| 技术分析 | "帮我分析比亚迪的技术指标，有没有金叉？RSI 超卖没有？" |
| 财务分析 | "恒瑞医药最近几期营收和 ROE 趋势" |
| 资金面 | "这周北向资金是流入还是流出？" |
| 选股 | "全市场扫描：涨超 3%、量比 > 1.5、换手率 > 5%、ROE > 10%" |
| 回测 | "帮我用双均线(5,20)回测美的集团 2024 年，跟买入持有对比" |
|  | "MACD 金叉死叉策略回测宁德时代，初始资金 50 万" |
| 参数优化 | "帮我找找美的集团双均线的最佳参数" |
| 盯盘 | "盯着茅台，跌破 1800 或 MACD 死叉就钉钉通知我" |
| 画图 | "画一张茅台最近 120 天的 K 线图，带上 MACD 和 RSI" |
| 板块 | "今天哪个行业板块涨得最好？" |
| 期货 | "列出所有期货合约的实时行情" |

---

## 数据源

| 源 | 说明 | 覆盖范围 |
|----|------|----------|
| **AKShare** | 开源金融数据接口，统一管理全部数据源 | A股/港股/美股/期货/指数/板块/资金流向/龙虎榜/两融 |

>  单一数据源、统一接口、零配置，pip install 即用。
> AKShare (https://akshare.akfamily.xyz/) 是开源金融数据 Python 库，内部整合了东方财富、新浪、腾讯等多个数据源。

---

## 项目结构

```
mcp-finance/
  pyproject.toml
  README.md              # 中文文档
  README.en.md           # English documentation
  run_monitor.py         # 独立盯盘进程
  mcp_finance/
    __init__.py
    api.py               # AKShare 统一数据封装层（全市场）
    data.py              # 200+ 股票映射 & 行业分类
    indicators.py        # 9 大技术指标 + 信号识别（纯Python）
    screener.py          # 全市场条件筛选（11 维度）
    backtest.py          # vectorbt 向量化回测引擎 + 参数优化
    akshare_data.py      # 向后兼容 re-export 层
    monitor.py           # 告警监控 + 钉钉/微信推送
    chart.py             # Plotly 交互式 K 线图
    server.py            # MCP Server（20+ tools + resources）
    errors.py            # 统一错误类型
    logging_config.py    # 结构化日志
    validators.py        # Pydantic 参数校验
    cache.py             # TTL 缓存
  tests/
    test_indicators.py   # 技术指标单元测试
    test_screener.py     # 选股器单元测试
```

---

## 已知限制 & 路线图

### 当前不足
-  **分时数据缺失**：暂不支持盘内分时（Tick 级）数据
-  **美股/港股数据丰富度**：目前覆盖基础行情和K线，财务/板块等高级功能待扩展
-  **期货分钟K线**：仅支持日线级别

### 计划中

>  完整的发展方向详细报告请见 [DEVELOPMENT_REPORT.md](./DEVELOPMENT_REPORT.md)

** P0 — 高优先级（短期可落地）**
- [x] **策略回测 MCP Tool** — 基于 vectorbt 向量化引擎，含参数优化 + A 股规则适配
- [x] **选股器大升级** — 从 5 维扩展到 11 维（新增 PB/ROE/主力净流入/股息率/振幅）
- [x] **全市场覆盖** — A股 + 港股 + 美股 + 期货，单一数据源 AKShare
- [x] **统一数据源** — 移除多数据源架构，AKShare 统一后端
- [x] **单元测试覆盖** — indicators + screener 核心模块

** P1 — 中优先级（中期差异化）**
- [ ] 港股/美股财务数据与高级分析
- [ ] 个股资金流向（主力/散户净流入）
- [ ] Web Dashboard（FastAPI + 轻量前端看板）
- [ ] 多 Agent 协作分析（多维度结构化研报）

** P2 — 长期探索**
- [ ] 形态识别增强（威科夫/头肩顶/杯柄等）
- [ ] 分时图 / Tick 级数据
- [ ] 数字货币行情支持
- [ ] Docker 一键部署 + PyPI 发布
- [ ] MCP Resources 扩展（新闻舆情、研报摘要）

> 欢迎提 PR 或 Issue 贡献新功能！

---

## 致谢

- [**AKShare**](https://akshare.akfamily.xyz/) — 开源金融数据接口库，一站式提供多市场数据
- [**Plotly**](https://plotly.com/python/) — 提供强大的交互式图表能力
- [**MCP (Model Context Protocol)**](https://modelcontextprotocol.io/) — AI 工具调用标准协议
- [**vectorbt**](https://vectorbt.dev/) — 向量化回测引擎

---

## License

[MIT](LICENSE)

---

<p align="center">
  如果这个项目对你有用，请给一个 Star！<br>
  <sub>欢迎提交 PR 和 Issue — 新指标、新数据源、新推送渠道……</sub>
</p>

<p align="center">
  <a href="README.en.md"> Read this in English</a>
</p>
