# LangAlpha

LangAlpha 是以 workspace 为中心的通用 Agent 平台，支持 PTC 程序化执行、Flash
快速会话、sandbox、Skills、MCP、自动化、文件产物和来源追踪。

核心运行时不绑定特定行业。每个 workspace 对应一个持久 sandbox；对话、运行状态
和检查点存入 PostgreSQL，SSE 通过 Redis 支持断线重连。用户可从 workspace 配置
通用 MCP 服务，并将凭证保存到 Vault。

平台内置家庭教育模块：家长创建本地家庭账户和作业，学生在自己的 Flash 会话与学习
页面中完成并提交作业。学生账户不具备 PTC sandbox、Vault、MCP 或自动化权限；教育
附件仅通过 FastAPI 写入私有 `education/` 对象前缀。

快速启动、架构和开发命令请参见仓库根目录的 [README](../README.md)。
