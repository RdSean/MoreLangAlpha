# 变更日志

## 2026-08-07

### 通用 Agent 工具边界

- PTC 与 Flash 默认工具集移除 SEC、行情、期权、股票筛选和价格监控能力，保留代码执行、文件系统、搜索抓取、Skills、MCP、工作区与子 Agent 机制。
- 默认 MCP 配置移除 FMP、Yahoo Finance、Alpha Vantage 等金融服务；用户仍可通过工作区自定义 MCP 接入通用外部能力。
- sandbox 不再同步 `data_client` 与 `market_protocol` 两套金融内部包。
- 内置子 Agent 改为通用角色，`equity-analyst` 更名为 `analyst`，并同步更新默认提示词与配置。
- 删除默认提示词中的金融工具和市场监控引导，防止模型调用已移除能力。
