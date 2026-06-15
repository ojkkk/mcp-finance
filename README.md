<h1 align="center">📈 mcp-stock-cn</h1>
<p align="center">
  <strong>中国 A 股实时行情 MCP Server</strong><br>
  让 AI 助手直接查询 A 股行情、计算技术指标、筛选股票、盯盘告警、生成 K 线图表
</p>

<p align="center">
  <a href="README.en.md">🇺🇸 English</a> •
  <a href="https://github.com/ojkkk/mcp-stock-cn">GitHub</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/MCP-1.4+-purple?logo=modelcontextprotocol" alt="MCP 1.4+">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen" alt="PRs Welcome">
  <img src="https://img.shields.io/badge/data-3%20sources-red" alt="3 Data Sources">
</p>

---

## ✨ 为什么选 mcp-stock-cn？

> ⚠️ 百度搜到的股票数据是静态网页，AI 无法直接做技术分析、筛选、对比。

mcp-stock-cn 给了 AI 一个**实时、结构化、可计算**的 A 股数据源：

- 📊 **实时行情** — 腾讯财经 + 东方财富双源，自动容错
- 📈 **技术分析** — 9 大指标本地计算，金叉死叉自动识别
- 🔍 **条件选股** — 全市场 A 股按涨跌幅/量比/换手率/PE/市值筛选
- 🔔 **盯盘告警** — 价格突破/金叉死叉/超买超卖 → 钉钉/微信推送
- 🕯️ **K线图表** — Plotly 交互式 HTML，蜡烛图+均线+MACD/KDJ/RSI
- 💾 **历史数据** — Baostock 量化级 K 线，日/周/月/分钟全覆盖

---

## 📋 环境要求

- **Python** 3.9 或更高版本
- 建议使用虚拟环境（venv / conda）安装

---

## 🚀 快速开始

```bash
# 1. 克隆
git clone https://github.com/ojkkk/mcp-stock-cn.git
cd mcp-stock-cn

# 2. 推荐：创建虚拟环境
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# 3. 安装
pip install -e .
```

### 配置

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

或 `.codex.yaml`:

```yaml
mcp:
  servers:
    mcp-stock-cn:
      command: python
      args: ["-m", "cn_stock.server"]
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

## 🛠️ 全部工具 (12 个)

### 📊 基础行情

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `get_realtime_quote` | 个股/指数实时行情 | `code` |
| `get_kline` | K 线数据（日/周/月/60分 + 前/后复权） | `code` |
| `get_financials` | 财务数据（营收/净利润/ROE/毛利率/资产负债率） | `code` |
| `get_market_indices` | 上证/深证/创业板/沪深300/科创50 实时行情 | — |
| `get_sector_ranking` | 行业/概念/地域板块涨幅排行 | — |
| `get_north_flow` | 北向/南向资金日流向 | — |
| `search_stock` | 按代码或名称模糊搜索 | `keyword` |
| `batch_quotes` | 批量查询多只股票行情 | `codes` |

### 📈 技术分析

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `get_technical_indicators` | 9 指标一键计算 + 信号识别 | `code` |

**计算的指标**：
MA(5/10/20/60/120/250)、MACD(DIF/DEA/柱)、KDJ(K/D/J)、RSI(6/14/24)、
BOLL(上/中/下轨)、WR(威廉)、BIAS(乖离率)

**自动识别的信号**：
✅ 均线金叉/死叉 &nbsp; ✅ MACD金叉/死叉 &nbsp; ✅ MACD柱转正/转负
✅ KDJ超买/超卖 &nbsp; ✅ RSI严重超买(>80)/超卖(<20)
✅ RSI偏高(>70)/偏低(<30) &nbsp; ✅ 均线多头/空头排列

### 🔍 条件选股

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `stock_screener` | 全市场多维度筛选 | 至少一个条件 |

**支持的筛选条件**：涨跌幅、量比、换手率、市盈率、总市值

### 🔔 盯盘告警

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `set_alert` | 条件告警 + 消息推送 | `code` |

**告警条件**：价格突破/跌破、涨跌幅阈值、MACD/均线金叉死叉、RSI超买超卖

**推送渠道**：🟢 钉钉机器人 &nbsp; 🟢 企业微信机器人 &nbsp; 🟢 Server酱(微信)

> 环境变量: `DINGTALK_WEBHOOK_URL` / `WECOM_WEBHOOK_URL` / `SERVERCHAN_SENDKEY`

<details>
<summary><b>🔧 告警配置详细说明（点击展开）</b></summary>

### 方式一：钉钉机器人（推荐）

1. 打开钉钉，建一个群
2. 群设置 → **智能群助手** → **添加机器人** → **自定义机器人**
3. 安全设置选 **"自定义关键词"**，填 `股票`
4. 复制 `https://oapi.dingtalk.com/robot/send?access_token=xxx` 这段 URL

**Windows 永久配置：**
```cmd
setx DINGTALK_WEBHOOK_URL "https://oapi.dingtalk.com/robot/send?access_token=你的token"
```

**重启 Codex / Claude 后生效。**

### 方式二：企业微信机器人

建群 → 添加群机器人 → 拿到 Webhook URL：

```cmd
setx WECOM_WEBHOOK_URL "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
```

### 方式三：Server酱（微信推送）

1. 打开 https://sct.ftqq.com/ 微信扫码登录
2. 拿到 SendKey

```cmd
setx SERVERCHAN_SENDKEY "SCT你的key"
```

### 测试告警

配置好后对 AI 说：

> *"帮我盯着茅台，涨超 3% 就钉钉通知我"*

AI 会调用 `set_alert(code="600519", gain_above=3, push_channel="dingtalk")`，钉钉群就会收到消息。

### 持续盯盘脚本

`set_alert` 是**一次性的**（你问一次它检查一次）。要实现真正的后台持续盯盘，可以跑 `run_monitor.py`：

```bash
python run_monitor.py
```

脚本每 60 秒检查一次自选股，触发条件自动推送，内置冷却机制避免重复骚扰。

**配置自选股**：编辑 `run_monitor.py` 里的 `WATCHLIST`：

```python
WATCHLIST = [
    {
        "code": "600519",
        "rules": {
            "price_below": 1500,    # 跌破 1500 告警
            "macd_death": True,     # MACD 死叉告警
        },
        "channel": ["dingtalk"],
    },
    {
        "code": "300750",
        "rules": {"gain_above": 5},
        "channel": ["dingtalk", "wecom"],
    },
]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `INTERVAL_SECONDS` | 检查间隔（秒） | 60 |
| `COOLDOWN_MINUTES` | 同一条件冷却时间（分钟） | 30 |
| `MAX_CONSECUTIVE_ERRORS` | 连续出错退出阈值 | 10 |

> **Windows 开机自启**：把 `python run_monitor.py` 放到任务计划程序即可。

</details>

### 🕯️ K线图表

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `plot_kline` | Plotly 交互式 K 线 HTML | `code` |

**图表包含**：蜡烛图 + MA5/10/20/60 均线 + 成交量 + MACD/KDJ/RSI 副图（可选）
**交互**：缩放、平移、悬停查看数值，深色主题，保存为 HTML 在浏览器打开

> ⚠️ **这不是 PNG 图片！** `plot_kline` 生成的是 **交互式 HTML 文件**，必须用浏览器打开。
> 
> 文件默认保存在 `%TEMP%/mcp-stock-cn-charts/` 目录下。
> 打开后你可以：🔍 滚轮缩放 ｜ ✋ 拖拽平移 ｜ 👆 悬停查看每根 K 线的 OHLC 数值。
> 
> Plotly.js 已内嵌在 HTML 中（~3MB），**完全离线可用，无需联网**。

### 🧪 API 诊断

| 工具 | 说明 | 必填参数 |
|------|------|----------|
| `test_data_sources` | 逐项检测 Baostock / 东方财富 / 腾讯数据源是否可用 | — |

在对话中说 **"测试数据源"**，AI 会调用 `test_data_sources` 返回各数据源状态。

---

## 💬 使用示例

| 场景 | 你可以问 AI |
|------|-------------|
| 📊 实时行情 | "茅台今天多少钱？大盘怎么样？" |
| 📈 K线数据 | "宁德时代最近 60 天日 K，后复权" |
| 🧮 技术分析 | "帮我看看比亚迪的技术指标，有没有金叉？RSI 超卖没有？" |
| 📋 财务分析 | "恒瑞医药最近几期营收和 ROE 趋势" |
| 💰 资金面 | "这周北向资金是流入还是流出？" |
| 🔍 选股 | "全市场扫描：涨超 3%、量比 > 1.5、换手率 > 5%" |
| 🔔 盯盘 | "盯着茅台，跌破 1800 或 MACD 死叉就钉钉通知我" |
| 🕯️ 画图 | "画一张茅台最近 120 天的 K 线图，带上 MACD 和 RSI" |
| 🏭 板块 | "今天哪个行业板块涨得最好？" |

---

## 📡 数据源

| 源 | 用途 | 可用性 | 致谢 |
|----|------|--------|------|
| **腾讯财经** `qt.gtimg.cn` | 实时行情 | ⭐⭐⭐⭐⭐ | 腾讯(QQ) 公开行情接口 |
| **东方财富** `push2.eastmoney.com` | K线/板块/资金流/全市场 | ⭐⭐⭐⭐ | [东方财富网](https://www.eastmoney.com/) |
| **东方财富** `datacenter.eastmoney.com` | 财务数据 | ⭐⭐⭐⭐⭐ | [东方财富数据中心](https://data.eastmoney.com/) |
| **Baostock** `baostock.com` | 历史 K 线（量化级） | ⭐⭐⭐⭐⭐ | [Baostock](http://baostock.com/) 免费证券数据平台 |
| **东方财富** `searchadapter.eastmoney.com` | 股票搜索 | ⭐⭐⭐⭐⭐ | 东方财富搜索接口 |

> 🇨🇳 全部国内 API，无需代理，无需 API Key。
> 🔄 三数据源自动降级：**Baostock → 东方财富 → 腾讯**，确保尽可能返回数据。

---

## 🏗️ 项目结构

```
mcp-stock-cn/
├── pyproject.toml
├── README.md              # 中文文档
├── README.en.md           # English documentation
├── cn_stock/
│   ├── __init__.py
│   ├── api.py             # API 封装（三数据源容错）
│   ├── data.py            # 200+ 股票映射 & 行业分类
│   ├── indicators.py      # 9 大技术指标 + 信号识别
│   ├── screener.py        # 全市场条件筛选
│   ├── monitor.py         # 告警监控 + 钉钉/微信推送
│   ├── chart.py           # Plotly 交互式 K 线图
│   └── server.py          # MCP Server（12 tools + resources）
```

---

## 🧭 已知限制 & 路线图

### 当前不足
- ⏳ **分时数据缺失**：暂不支持盘内分时（Tick 级）数据
- ⏳ **分钟 K 线范围有限**：Baostock 分钟 K 线只保留近 5 个交易日
- ⏳ **港股/美股**：目前仅覆盖 A 股

### 计划中

> 📖 完整的发展方向详细报告请见 [DEVELOPMENT_REPORT.md](./DEVELOPMENT_REPORT.md)

**🥇 P0 — 高优先级（短期可落地）**
- [ ] **策略回测 MCP Tool** — 接入 Backtrader 或自研轻量版，AI 对话式回测
- [ ] **选股器大升级** — 从 5 维扩展到 20+ 维（技术面/资金面/基本面/形态面）
- [ ] **AKShare 第四数据源** — 兼容 A 股数据生态，接入龙虎榜/大宗交易/两融

**🥈 P1 — 中优先级（中期差异化）**
- [ ] 港股实时行情支持（腾讯财经已有部分港股数据）
- [ ] 个股资金流向（主力/散户净流入）
- [ ] Web Dashboard（FastAPI + 轻量前端看板）
- [ ] 多 Agent 协作分析（多维度结构化研报）

**🥉 P2 — 长期探索**
- [ ] 形态识别增强（威科夫/头肩顶/杯柄等）
- [ ] 分时图 / Tick 级数据
- [ ] Docker 一键部署 + PyPI 发布
- [ ] MCP Resources 扩展（新闻舆情、研报摘要）

> 欢迎提 PR 或 Issue 贡献新功能！

---

## 🙏 致谢

- [**东方财富网**](https://www.eastmoney.com/) — 提供实时行情、财务数据、板块排行等接口
- [**腾讯财经**](https://finance.qq.com/) — 提供稳定可靠的实时行情 API
- [**Baostock**](http://baostock.com/) — 免费、开源的历史 A 股数据平台，量化分析标配
- [**Plotly**](https://plotly.com/python/) — 提供强大的交互式图表能力
- [**MCP (Model Context Protocol)**](https://modelcontextprotocol.io/) — AI 工具调用标准协议

---

## 📝 License

[MIT](LICENSE)

---

<p align="center">
  ⭐ 如果这个项目对你有用，请给一个 Star！<br>
  <sub>欢迎提交 PR 和 Issue — 新指标、新数据源、新推送渠道……</sub>
</p>

<p align="center">
  <a href="README.en.md">🇺🇸 Read this in English</a>
</p>