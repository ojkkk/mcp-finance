#  mcp-finance 发展路线报告

> 更新日期：2026-06-17 | 版本：v0.4.0
> 审查范围：全部 13 个源码模块 + README + pyproject.toml

---

## 1. 项目架构总览

```
mcp-finance/
  pyproject.toml          # 项目元数据（AKShare 统一依赖）
  README.md / README.en.md # 双语文档（全市场覆盖）
  run_monitor.py          # 独立盯盘进程
  mcp_finance/
    __init__.py         # 版本号
    server.py           # MCP Server（20+ tools + resources）
    api.py              # AKShare 统一数据层（A股/港股/美股/期货）
    data.py             # 200+股票映射 + 行业分类
    indicators.py       # 9大技术指标 + 信号识别（纯Python）
    screener.py         # 多维度选股（11维度）
    backtest.py         # vectorbt 回测引擎（5种策略）
    akshare_data.py     # 向后兼容 re-export 层
    monitor.py          # 告警 + 钉钉/企微/Server酱推送
    chart.py            # Plotly 交互图表
    errors.py           # 统一错误类型
    logging_config.py   # 结构化日志
    validators.py       # Pydantic 参数校验
    cache.py            # TTL 缓存
  tests/
    test_indicators.py  # 技术指标单元测试
    test_screener.py    # 选股器单元测试
```

**代码量统计：~3500 行（不含注释和空行），含单元测试。**

---

## 2. 核心优势

| 优势 | 详情 |
|------|------|
|  **全市场覆盖** | A股 + 港股 + 美股 + 国内期货，单一 MCP Server |
|  **统一数据源** | AKShare 一站式管理，零多源复杂度 |
|  **纯 Python 指标** | 无 TA-Lib 依赖，安装门槛低，可审计 |
|  **向量化回测** | vectorbt 引擎，5 种策略，万倍速度 |
|  **零外部 HTTP 依赖** | 数据获取通过 AKShare，无直接 HTTP 调用 |
|  **Plotly 交互图** | 蜡烛图+均线+MACD/KDJ/RSI，专业美观 |
|  **告警推送** | 钉钉/企业微信/Server酱 三通道 |
|  **文档质量** | 双语 README + 发展报告 + 代码注释完整 |
|  **单元测试** | indicators + screener 核心模块已覆盖 |

---

## 3. v0.4.0 重大更新

### 3.1 统一数据源：AKShare
- **移除** Baostock、东方财富、腾讯财经等独立数据源
- **统一** 所有数据获取通过 AKShare 懒加载
- **简化** api.py 从 ~900 行多源容错 → ~500 行统一接口

### 3.2 全市场扩展
- **A股**：实时行情、K线（日/周/月+复权）、财务数据、板块排行
- **港股**：实时行情、K线、指数（恒生/恒生科技/国企）
- **美股**：实时行情、K线、指数（道琼斯/纳斯达克/标普500）
- **期货**：实时行情、K线、合约列表、持仓量

### 3.3 工具扩展（17 → 20+）
- 新增 `get_futures_list` — 期货合约实时行情列表
- 所有行情/K线/搜索工具新增 `market` 参数（a/hk/us/futures）
- `get_market_indices` 扩展支持港股/美股指数
- `test_data_sources` 诊断覆盖全市场数据源

### 3.4 代码质量提升
- server.py 完全重写：清晰结构，566 行
- 统一错误处理（errors.py）
- 结构化日志（logging_config.py）
- Pydantic 参数校验（validators.py）
- TTL 缓存（cache.py）
- 单元测试覆盖 indicators + screener

---

## 4. 已知限制

| 限制 | 说明 |
|------|------|
| 分时数据 | 暂不支持盘内 Tick 级数据 |
| 美股/港股深度 | 财务数据、板块排行等高级功能仅 A 股 |
| 期货分钟K线 | 仅支持日线级别 |
| 选股器 | 仅支持 A 股全市场筛选 |
| Screener 字段 | ROE/股息率/主力净流入暂通过 AKShare 间接获取 |

---

## 5. 发展路线

###  P0 — 已完成
- [x] 策略回测 MCP Tool（vectorbt 向量化引擎）
- [x] 选股器 11 维度扩展
- [x] 全市场覆盖（A股+港股+美股+期货）
- [x] 统一数据源 AKShare
- [x] 单元测试覆盖核心模块
- [x] server.py 完全重构
- [x] 结构化日志 + 统一错误处理

###  P1 — 中期目标（1-2 月）
- [ ] 港股/美股财务数据与高级分析
- [ ] 个股资金流向（主力/散户净流入）
- [ ] Web Dashboard（FastAPI + 轻量前端）
- [ ] 多 Agent 协作分析（结构化研报）
- [ ] 选股器港股/美股扩展
- [ ] 回测引擎多市场支持（港股/美股）

###  P2 — 长期探索（3-6 月）
- [ ] 形态识别（头肩顶/双底/杯柄等）
- [ ] 分时图 / Tick 级数据
- [ ] 数字货币行情
- [ ] ETF/可转债数据
- [ ] Docker 一键部署 + PyPI 发布
- [ ] MCP Resources 扩展（新闻舆情、研报摘要）
- [ ] 模拟组合管理

---

## 6. 与竞品对比

| 维度 | mcp-finance | mcp-aktools | akshare-one-mcp | stock-mcp |
|------|:---:|:---:|:---:|:---:|
| 数据源 | AKShare 统一 | AKShare | AKShare | AKShare |
| 市场覆盖 | A股+港股+美股+期货 | A股+港股+美股+加密 | 部分 | 部分 |
| HTTP 依赖 | 0（通过AKShare） | requests | requests | requests |
| 回测引擎 |  vectorbt 5策略 |  |  |  |
| 技术指标 | 9个本地计算 | 依赖AKShare | 依赖AKShare | 部分 |
| 告警推送 | 钉钉/企微/Server酱 |  |  |  |
| 交互图表 |  Plotly |  |  |  |
| 选股器 | 11维筛选 |  |  |  |
| 单元测试 |  indicators+screener |  |  |  |

> **核心差异化优势：** 全市场覆盖 + 回测引擎 + 本地指标计算 + 告警推送 + 选股器 + 交互图表 + 单元测试

---

## 7. 技术架构亮点

```
MCP Client (Claude/Codex/Cursor)
    |
    v
server.py (路由分发 + 格式化)
    |
    +-- api.py (AKShare 统一数据层)
    |     |-- get_realtime_quote_a/hk/us/futures
    |     |-- get_kline_a/hk/us/futures
    |     |-- get_financials_a / get_market_indices
    |     |-- get_sector_ranking / get_north_flow
    |     |-- get_dragon_tiger / get_block_trades / get_margin_trading
    |     +-- get_futures_list / search_stocks / batch_quotes
    |
    +-- indicators.py (纯Python指标计算)
    +-- screener.py (11维选股)
    +-- backtest.py (vectorbt回测)
    +-- monitor.py (告警推送)
    +-- chart.py (Plotly图表)
    +-- errors.py / validators.py / cache.py / logging_config.py
```

---

## 8. 总结

mcp-finance v0.4.0 完成了从"A股专用多数据源工具"到"全市场统一数据源平台"的跃升：

1. **数据源简化** — 从 4 源容错到 AKShare 统一后端
2. **市场扩展** — A股   A股+港股+美股+期货
3. **工具增强** — 17 工具   20+ 工具，新增期货列表、cross-market 参数
4. **质量提升** — 零测试   单元测试、结构化日志、参数校验、缓存、统一错误处理

下一步重点：港股/美股深度数据、Web Dashboard、PyPI 发布。
