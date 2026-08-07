# 变更日志

## 2026-08-07

### 通用工作区仪表盘

- `/dashboard` 改为通用工作区概览，提供对话、自动化和工作区文件三个可用入口，并展示近期会话与工作区状态。
- 工作区文件入口会直接打开对应 Agent 工作区的文件面板；不再依赖金融 Dashboard 的经典/自定义布局和偏好设置。
- 将仍被聊天、设置和引导流程使用的确认对话框、上下文预览、OAuth 和用户 API 迁移至通用路径，避免后续删除金融 Dashboard 时破坏应用壳层。

### 金融前端公开入口移除

- 主导航移除行情中心，公开路由不再加载 `/market` 与 `/news/:id`；旧地址统一回落至通用工作区仪表盘。
- 删除对应的侧栏中英文文案，并为 Dashboard、Chat、Automations 与 Settings 的通用路由建立回归测试。

### 金融运行时与自动化移除

- 服务端不再注册市场数据、K 线、SEC、财经新闻、经济日历、投资组合、观察列表、财经洞察、图表标注和行情 WebSocket 路由。
- 启动与关闭生命周期移除市场数据订阅、价格监控、财经洞察和财经新闻刷新服务，保留通用自动化调度、Vault、MCP、SSE 与工作区服务。
- 初始 PostgreSQL schema 删除 watchlist、portfolio、market insights、图表标注相关表和投资偏好字段；相关历史 migration 改为保持 revision 连续性的空迁移。
- 自动化仅支持 `cron` 与 `once`，移除价格触发的请求模型、Agent 工具参数、执行分支、数据库查询与监控服务。
- 使用隔离 PostgreSQL 实际验证 migration `upgrade head`、约束内容和 `downgrade base`，随后已清理该临时容器与卷。

### 通用 Agent 工具边界

- PTC 与 Flash 默认工具集移除 SEC、行情、期权、股票筛选和价格监控能力，保留代码执行、文件系统、搜索抓取、Skills、MCP、工作区与子 Agent 机制。
- 默认 MCP 配置移除 FMP、Yahoo Finance、Alpha Vantage 等金融服务；用户仍可通过工作区自定义 MCP 接入通用外部能力。
- sandbox 不再同步 `data_client` 与 `market_protocol` 两套金融内部包。
- 内置子 Agent 改为通用角色，`equity-analyst` 更名为 `analyst`，并同步更新默认提示词与配置。
- 删除默认提示词中的金融工具和市场监控引导，防止模型调用已移除能力。
