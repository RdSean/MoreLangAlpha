# more-to-skills 学科适配前备份

2026-10-03，在 `feature/more-to-skills-textbook-refactor` 上、任何学科适配修改之前硬拷贝。

- 来源：`plugins/langalpha_local/skills/more-to-skills/`。
- 备份：本目录下 `more-to-skills/`，36 个受版本管理文件；包含 Skill、reference、schema、工具、解析包与许可。
- 逐个 `cmp` 验证与来源字节一致；不复制 `.ruff_cache` 等本地生成物，不使用软链接。
- 基线提交：`0aad84f8d`。
- `SKILL.md` 文件 SHA-256：`e4c0bf105941529687c80ee543c5c1f0c9322ad2e60d17ced006e39c780bfda4`。
- 服务冻结的目录内容身份：`3c6d34c78ec1c88ed4ddb5a0a0b8fcd91f64ae12c785732915135a21bc1cb062`。
- schema SHA-256：`601bced7331cb5eac37ead5a8c3f13ed55382f4afa05d2e4227b6ee04d7eb6d1`。

备份位于 `docs/`，不属于宿主 Skill 搜索目录或教材 sandbox staging 目录，不作为可发现的第二份 Skill 启用。后续只修改运行目录，本备份保持原样。

如需回退，先排空使用新版冻结身份的教材任务，再审阅备份与运行目录的差异，恢复对应文件并移除本轮新 reference，重新核对冻结身份和测试锁定；不能只覆盖 `SKILL.md` 或修改历史任务哈希。此处不自动执行恢复，不回滚已成功材料或其他业务数据。
