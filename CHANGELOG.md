# Changelog

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
