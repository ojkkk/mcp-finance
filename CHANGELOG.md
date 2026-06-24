# Changelog
## [0.8.0] - 2025-06
### 新增
- **yfinance 三数据源架构**：港股/美股 K线和行情加 yfinance 兜底，AKShare 失败时自动降级
- **港美股回测全支持**：`backtest_strategy` / `optimize_strategy` 自动识别 A 股(6位)/港股(5位)/美股(字母)代码
- **市场自动识别**：`_detect_market()` 支持后缀(.SH/.SZ/.HK)、3-5位数字港股、字母美股
- **港股代码自动补零**：`700` → `00700`
- **美股财务数据**：AKShare `stock_financial_us_analysis_indicator_em` + `stock_hk_financial_indicator_em` 正确 API 调用 + yfinance 兜底
- **HOT_STOCKS 美股扩充**：7 → 20 只（BABA, JD, PDD, AMD, INTC, NFLX 等）
### 优化
- **参数优化性能提升 125x**：`ProcessPoolExecutor` → `ThreadPoolExecutor`，K线 800→400，优化模式跳过冗余分析器，20 组合从 100s+ 降至 0.8s
- **optimize_strategy 独占 180s 超时**：不再被 90s 限制截断
- **position sizing 修复**：高价股 `int()` 截断导致 0 股 → 加守护逻辑 + 跳过原因记录
- **certifi 证书修复**：修复 yfinance SSL 连接问题
### 修复
- `chart.py` `_calc_ema` → `_ema` 拼写错误
- 港股 K线 `adjust=""` → `adjust="qfq"` 价格异常
- 北向资金 API 符号参数修正
- `handle_financials` AKShare API 名称更新
- `get_sector_ranking` 字段映射扩展
- `get_market_indices` 指数异常值检测
- `search_stocks` 中文市场别名 + 全市场搜索
- `_get_single_quote` 港美股名称 STOCK_MAPPING+HOT_STOCKS+yfinance 三重兜底
## [0.7.0] - 2025-06
### 新增
- easy-tdx 双数据源（通达信 TCP 协议，毫秒级 A 股行情）
- Backtrader 事件驱动回测引擎（替换 vectorbt）
- 策略回测参数优化组合数上限 200 组
- GitHub Actions CI 工作流
### 修复
- **分钟线静默回退 bug**：移除 validators 和工具描述中的 `minute60` 选项，K 线函数添加 `period` 显式校验
- **假异步修复**：17 个 handler 从 `async def` 改为同步 `def`，`call_tool` 改用 `asyncio.to_thread` 真正释放事件循环
- **线程池耗尽**：所有网络函数添加 `_call_with_net_timeout` 超时保护（15s），server.py 添加 90s `asyncio.wait_for` 兜底
- **easy-tdx 连接挂死**：`_get_tdx()` 和 `_get_single_quote` 添加 5s 线程超时，自动降级到 AKShare
- **backtest 权益曲线策略参数错配**：cerebro2 按策略类型分发参数（RSI/KDJ/BOLL）
- **search_stock HK 误标 A 股**：移除了对 `STOCK_MAPPING` 的误引
- **get_futures_list 硬编码 V2309**：改为 `futures_display_main_sina()` 返回 82 个主力合约
- **版本号去重**：server.py 改为 `from mcp_finance import __version__` 动态读取
### 优化
- `chart.py` Plotly.js 改为 CDN 加载，HTML 文件从 4.7MB → ~50KB
- `cache.py` TTLCache.set() 添加惰性过期 key 清理
- `replace_plotly.js` server.py 启动日志同步版本号
---
## [0.6.1] - 2025-06
### 新增
- 17 个 MCP 工具，双数据源容错（easy-tdx + AKShare）
- 策略回测引擎（5 种策略，Backtrader 事件驱动）
- K 线图交互式 HTML 输出
- 技术指标计算（MA/MACD/KDJ/RSI/BOLL）
- 选股器（11 维度多条件筛选）
- 全市场估值/指标界面
### 修复
- 美股行情/K线/搜索 全功能修复
- 搜索优化：纯本地映射搜索，无超时
- 回测策略参数错配 + 日期格式化异常修复
### 变更
- 数据源从纯 AKShare 扩展为 easy-tdx + AKShare 双数据源
- 回测引擎从 vectorbt 迁移到 Backtrader
---
## [0.4.0] - 2025-05
### 新增
- 港股/美股/期货数据源支持
- 龙虎榜/大宗交易/融资融券数据
- Pydantic 参数校验
- 盯盘告警（钉钉/企业微信/Server酱）
### 修复
- 东方财富 API 在某些网络环境不可达的问题，改用新浪/同花顺替代源
---
## [0.2.0] - 2025-04
### 新增
- 初始版本发布
- A 股实时行情 + K 线 + 财务数据
- 基于 AKShare 单数据源
- 基础 MCP Tool 接口
