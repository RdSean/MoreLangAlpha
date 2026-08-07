# LangAlpha 架构审计

结论：可行，且很适合做成通用 Agent 平台。PTC、Flash、workspace/sandbox、MCP、Skills、SSE、后台子 Agent、检查点与前端聊天工作台本身并不依赖金融领域；金融能力主要是以一组完整产品垂直切片叠加在其上。整体改造难度为中高，但不是架构重写。

README 的核心价值是通用的：持久 workspace 与 PTC 执行模型可直接保留，[README.md](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/README.md:115)。金融工具、行情工作台、数据源和领域 Skills 则应移除或重置，[README.md](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/README.md:43)。

| 区域 | 耦合程度 | 处理建议 |
|---|---:|---|
| PTC、sandbox、文件系统、MCP 生成、子 Agent、Skills 加载、SSE | 低 | 原样保留，作为平台内核 |
| Flash/PTC 原生工具列表 | 低 | 删除金融列表，保留 Web、文件、代码、秘书能力 |
| MCP 内置金融服务器和 `data_client` | 中 | 整块删除；默认 `mcp.servers: []`，保留用户自定义 MCP |
| 服务启动、路由、缓存、价格触发 | 中 | 删除金融启动钩子、路由和缓存服务，保留通用 scheduler |
| 用户资料与提示词 | 中 | 删除 portfolio/watchlist，保留通用偏好与 memory |
| Dashboard/MarketView/TradingView | 高 | 删除市场工作台；保留 Dashboard grid、聊天、文件和 workspace UI 框架 |
| 数据库迁移 | 中 | 已部署实例需正式退役迁移；新项目应重建干净基线 |

金融功能确实进入了应用骨架，但边界仍然可控：

- Agent 工厂中金融工具集中在一个列表，PTC 和 Flash 都是明确删除点：[agent.py](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/src/ptc_agent/agent/agent.py:576)、[flash/agent.py](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/src/ptc_agent/agent/flash/agent.py:135)。
- 沙箱同步仍硬编码上传 `data_client` 与 `market_protocol`，这是一个隐藏耦合点，必须一并移除：[sandbox/_shared.py](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/src/ptc_agent/core/sandbox/_shared.py:30)。
- 用户资料虚拟文件把 portfolio/watchlist 注入了通用文件系统；应改为仅通用 `preferences.json`，或干脆使用现有 long-term memory：[user_data.py](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/src/ptc_agent/agent/backends/user_data.py:1)、[user_profile.md.j2](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/src/ptc_agent/agent/prompts/templates/components/user_profile.md.j2:28)。
- 图表选择甚至进入了聊天请求模型，因此移除 MarketView 时要同时删除该上下文类型和两条 chat handler 注入链：[additional_context.py](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/src/server/models/additional_context.py:19)。
- 服务装配层直接启动价格监控、市场洞察和新闻轮询，并注册市场、SEC、投资组合等路由；这些不是内核，但需成组清理：[setup.py](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/src/server/app/setup.py:553)、[setup.py](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/src/server/app/setup.py:1047)。
- 前端的 `MarketView`、TradingView 组件和大部分 Dashboard widgets 是主要工作量；但路由壳、React Query、组件库、文件查看器、聊天与 dashboard grid 都可以保留：[Main.tsx](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/web/src/components/Main/Main.tsx:12)、[widgets/index.ts](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/web/src/pages/Dashboard/widgets/index.ts:1)。

建议按以下顺序开展：

1. 定义“通用基线”：PTC 默认工具为代码、bash、文件、Web 搜索/抓取、`ShowWidget`、Todo；Flash 为 Web、秘书、轻量 Skills。保留定时/一次性自动化，删除价格触发自动化和 `PriceMonitorService`。
2. 删除金融后端垂直切片：`src/data_client`、`src/market_protocol`、`src/tools/market_data`、`src/tools/sec`、`src/tools/market_watch`、金融 MCP servers、行情/新闻/洞察/投资组合/观察列表 API 与缓存。
3. 重置 Skills 与 prompts：保留 `pdf/docx/pptx/xlsx/html-report/inline-widget/web-scraping/secretary/run-workflow/automation`，重写 `ui-design` 为通用产物设计；删除 DCF、财报、估值、晨报、行情和图表标注 Skills。[registry.py](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/src/ptc_agent/agent/middleware/skills/registry.py:117)
4. 前端收敛为 workspace-first：移除 `/market`、市场新闻详情、TradingView、金融 Dashboard widgets、引用卡片和行情 SSE；保留 Chat、Workspaces、Files、MCP、Vault、Subagent 监控、通用 Automations。Dashboard 可先只保留“最近线程、workspace、运行中的自动化、Agent 会话”。
5. 清理依赖、配置、文档和测试：移除 `yfinance`、`edgartools`、`mplfinance`、`exchange-calendars` 等金融依赖，删掉 FMP/Yahoo/gintlix 配置与 setup wizard 选项，并重写 README 为通用研究与生产力 Agent。

数据库是唯一需要先做产品决策的部分。初始迁移把 watchlist、portfolio、market insights 与通用表混在一起：[001_initial_schema.py](/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/migrations/versions/001_initial_schema.py:163)。没有已部署数据时，建议重建干净的迁移基线；已有部署时，保留历史迁移不动，新增一次退役迁移，先停用价格自动化并导出数据，再删除领域表和约束。

工作量预估：仅“隐藏/禁用金融 UI 与工具”约 3–5 个工作日；推荐的干净改造约 2–4 周，包含后端删除、前端收敛、数据库迁移、测试与真实 PTC/Flash/SSE 验证。核心 Agent 框架本身风险低，主要风险在历史回放、前端路由/类型依赖、以及已部署数据库的数据处置。

本次为只读审计，工作区未做修改。
