# 教材业务动作时间线实施与验收

日期：2026-10-03。分支：`feature/more-to-skills-textbook-refactor`。依据：[业务动作开发细则](2026-10-03-textbook-business-activity.md)。本增量已交付，不代表总 Task 8 完成。

## 已交付行为

- `report_progress(stage, action=None)` 保留 stage-only；材料下发八项跨学科可选动作。工具仅验证标识符，教育 observer 绑定 item、校验组合并生成受控中文，不接受模型标题/身份/计数/自由说明。不同动作独立节流，进度只表示声明进入动作。
- PostgreSQL 原 job/item 锁事务增加工具子预算 800 条/768 KiB；总预算保持 1000 条/1 MiB。工具耗尽仍允许语义写入，省略摘要合并，终态/fence/持久 unavailable 规则不变。无新增表或迁移。
- 授权快照提供知识点标题；前端按 item 与 seq 分组、保留回退和终态历史，缺失标题/对象安全回退。当前对象不从阅读选中项猜测。工具诊断默认不挂载，键盘可展开，切换任务重置。
- 显示缓存优先保留业务，消费游标独立推进；终态分页、旧订阅隔离、移动省略摘要保持一份，401/403/404 清除缓存/游标并停止订阅。
- Skill 只增加 18 行通用可选约定及局部提醒，managed prompt 对齐任务词表。没有重写学科模板、内容深度、脚本/schema 或运行主干。没有工具/契约或工具不可用仍继续材料工作。

后端契约/预算/title：`a4fb1bc9d`。前端历史/诊断/游标：`26a4e0882`。Skill、提示及本验收记录在后续原子提交收口。

## Skill 发布与场景

修改实际 Skill 前只读核对开发库 queued/running 教材任务为 0，不取消用户任务，不修改旧任务摘要或绕过身份校验。新 Skill manifest：`46ca820bfd66b3adaba0b8cbd405e71af27276caf891202c8376a3897c961495`；schema 摘要仍为 `601bced7331cb5eac37ead5a8c3f13ed55382f4afa05d2e4227b6ee04d7eb6d1`，版本仍为 2.1.0。暂存/只读封存及身份测试通过。

独立 Agent 修改前后按数学短摘要、语言两个原例、无工具、不可用、图表有无、原例/辅助例、跨阶段/目录外动作和回退作只读提示应用。修改后可选择少量适用动作，无工具不报告，不可用停止报告且继续；不为填动作清单扩写。修改前基线在显式限制下也没有额外例题，因此这里只证明说明和本次应用一致，不能宣称观察到真实模型由违规到合规。

## 真实加工

沿用用户指定家长账号的现有模型配置，由正常教育服务解析，不复制模型凭据。新建两页验收 PDF，经图书馆正常上传、anydoc-local 解析、冻结来源和真实模型结构加工得到两个知识点；不是伪造通过结构。教材 `c8aee1f2-f086-46e4-b054-f211bf85a9ae`，结构 job `6170f0b1-e063-4e1a-b7cf-6e79336dcd98`。没有重做用户自己的教材。

| 场景 | job | 实际语义报告 | 普通工具事件 / 对应开始调用 | item 耗时 | 内容范围 |
|---|---|---|---|---|---|
| 数学 definition-only，summary，正文最多 80 英文词 | `6d645a76-0f01-4109-8e5d-4cadefc9a779` | reading_context → stage-only writing → checking_sources，共 3 条 | 38 / 19 | 94.06 秒 | 45 个空白分隔词，只有位值定义与十进制倍率说明，无例子、练习、词表或图片 |
| 语言 summary，只解释 unhappy/rewrite | `58cce20c-ccc2-4cd8-9d71-9ef884e01f8b` | stage-only reading → organizing_explanation → explaining_source_examples → checking_sources，共 4 条 | 36 / 18 | 58.39 秒 | 58 个空白分隔词，只解释 un-/re- 与两个原例，无新增例词、练习、词表或图片 |

两项均 succeeded，完成来自产物校验及数据库提交。报告不要求走完八项，数学没有报告概念 action 也正常；未发生图表/练习/辅助例不要求覆盖。数据库公开字段与完整 HTTP SSE 回放逐条一致：数学 43 条、语言 42 条。actual report_progress 调用自身的开始/结果噪声不进入工具明细。

实际 agent-browser 打开 5177 工作台核对桌面和 375px。阅读页停留在数学知识点时，语言任务历史仍以语言 item 标题分组；动作中性标记、服务提交为成功标记，默认无 Bash/Edit 行，展开诊断后可读。375px document scrollWidth=innerWidth=375。刷新重新回放受控动作及标题；长标题/HTML 字面文本、键盘、诊断默认关闭与 reader URL/scroll 保持另由 Playwright 验证。

真实 API/browser 沿用 OSS trusted backend identity，不冒充现有家长普通 cookie 登录证据；普通 cookie 相关原 Task 8 项仍未完成。私人登录态、测试脚本、PDF/截图/原始日志不提交。

## 验证

- 新行为先失败再实现：action tool/observer 初始 11 项失败；业务 UI 初始 7 项失败，预算/title 新增失败后通过。新增诊断重置、缺失对象、取消与授权失效回归，并经独立只读代码复核，无剩余重大问题。
- 后端聚焦七套：119 passed；教材 jobs/books/activity 真 PostgreSQL 三套串行：45 passed，包括工具行数/字节上限、并发/新 observer、终态与标题授权。没有对开发库做故障注入或测试 schema 重建。
- 全量后端：7928 passed、8 deselected、1 xfailed。改动 Python Ruff check/format 通过；make lint 通过，前端 0 error/55 既有 warning。
- 前端聚焦 Panel/Queries/Workbench：49 passed；工作台 Chromium：11 passed，含桌面/375px 完成后回放、诊断键盘/默认 DOM 隐藏、长标题安全、断流重连、静默/不可用、后台恢复、关闭面板与旧响应。
- 前端 typecheck/build/critical path 通过，关键路径 356.4 kB gz；改动文件 ESLint 通过。全量前端：2592 passed、1 failed，仍为 Plugins connectReturn 的 storage-throws 既有失败，不修改无关模块。首次 E2E 两条旧“历史阶段必须消失”断言按新设计更新后全套通过。

## 证据限制

历史 stage-only 真实讲义有 62/54 个普通工具事件与 4 条进度，但与本次新来源/summary 要求不同，不作为同材料同深度配对性能比较。两项新 run 的 conversation_usages 记录数均为 0，runtime metadata 只记录 default preset，无可用持久 token 数据；不推算额外 token 或声称零开销。少量样本不保证所有模型都及时选择动作，白名单也不能证明声明真实。

新工具上限的压力证据来自真实 PostgreSQL 并发/预算集成测试；此前 150001 raw delta 的 PG/Redis/browser 组合实验仍只证明旧版本，没有重跑，不把“1000 工具”当新版本预期。

总 Task 8/语义 Task 6 的真实 MinIO/COMMIT ACK、模型完成结果的跨进程提交恢复、家长 cookie 添加和普通产品完整 live 矩阵继续未完成。原 .env/agent_config.yaml、共享 PostgreSQL/Redis/MinIO 与本机挂载数据保留。5177/8000 本机及 LAN HTTP 200；只关闭本次验收浏览器，不合并/推送或清除开发 worktree。
