# 托管教材执行优化记录

2026-10-03，worktree `more-to-skills-textbook-refactor`。用户已批准第一轮执行契约与提示优化；学科模板和 SB3/持续负载属于后续阶段。

## 基线与切换

- 基线代码：`7fff42cc5`。用户提供 graph trace `f55f5ae6-6c76-465b-a702-c3c47c3da0e8`，graph 79.71s，14 次模型调用合计 71.17s；此计时沿用用户分析。
- 开发库只读核对：job `1129c084-ee90-4ca7-af57-30b9e01c53f5`，execution `4c6cf80a-0d4b-4cb7-ba2b-5f5b24287d39`，run 与 trace 同 ID，深度 `lesson`，要求“给小学生进行讲解。使用中文”。
- started `2026-10-03T09:39:01.452847Z`、finished `09:40:26.217314Z`，业务开始到提交 84.764s；包含 sandbox/staging/graph/收尾，不能与 graph 相加。首次请求/冻结、独立模型配置和推理强度待核对，不从时间差推断精确分段。
- 来源 SHA256 `ea1304d40631ef98be9d691f01e09e3b8adedc590a589061ede7b538653c3530`；旧 Skill SHA256 `d80660ca11693cb11003a33e923bc1faa52430fda6e287cb44b56817d1c5d7ef`；结构 schema SHA256 `601bced7331cb5eac37ead5a8c3f13ed55382f4afa05d2e4227b6ee04d7eb6d1`。
- 开始开发前 jobs/items queued/running 为 0，conversation responses in_progress 为 0。精确停止原后端 reloader PID 51658，避免自动重载中间版本；共享 Docker 和数据不变。前端保留，最终恢复 8000。

## P1：材料交付

- 失败用例先执行：4 failed，准确捕获 v1、材料冗余结构输出与职责说明缺失；修改后原聚焦三套 43 passed。
- task schema v2 明确 Agent/host 职责：结构任务保留结构输出，单篇/supplementary 只交付指定材料。输入结构、邻近来源与图片 staging 保留；finalizer 原本只读取材料，无需放松验收。
- Skill 仅增加可选宿主职责例外与简短交付说明，独立 Mode 3 和结构校验保持；教学模板尚未改。新冻结 Skill SHA256 `3c6d34c78ec1c88ed4ddb5a0a0b8fcd91f64ae12c785732915135a21bc1cb062`，更新现有 digest 锁定测试，schema hash 不变。
- 其余任务与真实小样本仍在执行，暂不宣称第一轮完成或已证明提速。
- 加入结构与 managed policy 回归后五套 83 passed；改动 Python Ruff 通过，格式化完成。

## P2：托管系统提示

- 新增通用 managed_system 模板，可信 managed policy 选择；按能力说明文件、代码、shell、图片、web 与可选进度。教材业务说明仍在教育任务与 Skill。
- 移除托管运行中的金融身份、通用 agent.md 工作流和未启用的 Vault 指引，同时关闭 WorkspaceContextMiddleware、MarketWatchMiddleware 与用户金融数据计数注入。普通运行继续原装配路径。
- 实际执行目录放在 RuntimeContextMiddleware 的缓存断点之后；两个不同 execution 的静态提示相同，lean 为 detailed 子集。源文不授予工具能力，输入与 Skill 只读规则保留。
- 初始新接口/渲染测试 6 failed、1 passed；实现后提示/契约/runtime/普通输出格式 80 passed。新增实际 create_agent 装配、动态上下文与两套缓存回归后聚焦 45 passed，1 既有 Pydantic copy 弃用 warning；改动 Ruff 通过。
- 真实模型耗时和内容行为仍待 P4 验证，提示长度变化不等同于已证明提速。
