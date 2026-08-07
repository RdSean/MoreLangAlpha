# LangAlpha

LangAlpha 是以 workspace 为中心的通用 Agent 平台，支持 PTC 程序化执行、Flash
快速会话、sandbox、Skills、MCP、自动化、文件产物和来源追踪。

核心运行时不绑定特定行业。每个 workspace 对应一个持久 sandbox；对话、运行状态
和检查点存入 PostgreSQL，SSE 通过 Redis 支持断线重连。用户可从 workspace 配置
通用 MCP 服务，并将凭证保存到 Vault。

快速启动、架构和开发命令请参见仓库根目录的 [README](../README.md)。
