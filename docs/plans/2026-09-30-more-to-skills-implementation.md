# more-to-skills 教材处理重构 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在清理旧教材模型和页面后，用 more-to-skills 原生结构及材料建立一个可浏览、可按需加工、可恢复的教材工作台。

**Architecture:** 新教材模型不经过旧 package/candidate/publication 协议。保留正常 PTC/Flash、Docker、runtime ledger/checkpoint；教育模块持久记录业务任务、每项产物及精简活动，家长只使用列表与工作台两层。图书馆和学生功能改接新引用。

**Tech Stack:** Python 3.13、FastAPI、async psycopg、Alembic raw SQL、jsonschema、PostgreSQL、Redis、React 19、TypeScript、Vite、pnpm。

---

## 0. 执行规则与依赖

依据：[设计](2026-09-30-more-to-skills-design.md)、[清理清单](2026-09-30-more-to-skills-cleanup-audit.md)、[托管教材语义进度设计](2026-10-02-managed-textbook-progress-design.md)及其[实施计划](2026-10-02-managed-textbook-progress-implementation.md)。

Worktree：`/Users/seanlee/.config/superpowers/worktrees/langalpha/more-to-skills-textbook-refactor`，分支 `feature/more-to-skills-textbook-refactor`。开始实施或恢复任务时检查 dirty 状态、AGENTS.md、迁移 head、实际服务目录/端口。

顺序：任务 1 定义契约 → 任务 2 建立数据与导入 → 任务 3/4 接运行和活动 → 任务 4A 补语义进度发送端 → 任务 5/6 接工作台和所有消费者 → 任务 7 一次切换清理 → 任务 8 完整验收。新模块可在隔离数据库测试；不在一半消费者仍依赖旧表时把迁移应用到当前运行数据库。

语义进度独立计划只将其 Task 1–4 归入本计划 Task 4A；独立 Task 5 是本计划 Task 5 的活动面板细化，独立 Task 6 随本计划 Task 8 验收。不得要求 Task 4A 提前实现工作台或重写完整教材/学生门面。

每项经过相应行为检查后补最小回归、中文 CHANGELOG 和原子提交。实现新模块时不添加旧 schema 兼容读取，不留下永久 feature flag。删除范围必须满足清理清单，而不是“最少改几行能跑”。

### 当前检查点（2026-10-02）

**2026-10-03 增量已交付：** [教材业务动作时间线开发细则](2026-10-03-textbook-business-activity.md)的可选 action/工具预算、知识点标题分组/终态历史/隐藏诊断/独立游标及 Skill 可选报告已实施。两份专用数学/语言讲义真实提交，动作经 PG/SSE/browser 回放，未因上报扩写例题/词表；后端聚焦 119、PG 45、前端聚焦 49、工作台 Chromium 11 passed。详细范围与性能/身份验证限制见[增量验收记录](2026-10-03-textbook-business-activity-results.md)。不重开 Task 1–7，不改变提交/权限/恢复边界；总 Task 8 原未完成项保留。

Task 1–7 与 Task 4A 已交付。Task 7 已向开发库应用 `082_more_to_skills_textbooks`，并按升级前导出的私人资源清单清理旧教材；详细范围、保护计数、检查证据和未验收项见[切换记录](2026-10-02-more-to-skills-cutover-results.md)。Task 8 已开始但仍有真实存储/提交 ACK 故障、模型已完成结果的跨进程恢复提交及完整普通产品 live 链路未覆盖，不能将清理或局部真实加工成功等同于整个重构验收通过。

Task 8 已开始：真实模型结构和中间知识点讲义提交成功，语义阶段可回放，实际批量默认跳过已有讲义与 runtime 取消已验证；补齐 PostgreSQL 四项部分失败、独立连接 reconcile、事务回滚恢复与浏览器分页/静默/前台/关闭活动恢复测试。真实验收发现的服务收尾、UUID 投影和客户端缓存/终态分页问题已修正。详细证据及未完成边界见 [Task 8 记录](2026-10-02-more-to-skills-task8-results.md)，仍不得标记完整验收完成。

本批继续补验：普通 runtime 真实多进程 gate 分批 5/5、4/4；教材真实写锁 owner 被 SIGKILL 后由另一进程收敛失败，不双跑、不改变 attempt。150001 合成 delta 经真实 PG/Redis/浏览器过滤和回放保持有界，专用 Redis 断连后 HTTP SSE 由 PG 补齐终态。教材集成复跑 42 passed。临时进程/Redis 已收尾，共享数据和 5177/8000 不变；隔离库 schema 重建与活 worker 验收必须串行。真实 MinIO/COMMIT ACK、模型完成后跨进程恢复提交、家长 cookie 添加与完整普通产品 live 链仍待补，不将本批成功写为 Task 8 完成。

上一批补齐专用学生普通 cookie 的原文/图片/讲义、进度/笔记/总结、真实 Flash 追问和跨家庭/撤销链；浏览器登录、笔记/总结保存及 375px 已实测。修复学生列表 UUID 响应 500 与教材 directive 未进入聊天 metadata；后端全量 `7918 passed, 8 deselected, 1 xpassed`，教材 PG `42 passed`。仅撤销新增验收学生的教材授权，既有学生数据未改；未完成矩阵继续验收。

本机依赖继续沿用 `codex/library-textbook-assets` 的 `.env`/`agent_config.yaml`，对象存储以 `.env` 的 `localhost:9000` 为准，不使用可能变化的办公室 LAN 地址。5177/8000 由本 worktree 启动，基础设施原挂载与 volumes 保留。

## Task 1：固定新契约和对外 API

**Files**
- Create: plugins/langalpha_local/skills/more-to-skills/（仅技能代码/文档/必要资源，保留许可）。
- Create: src/server/services/education_book_structure.py、src/server/app/education/book_models.py。
- Create: tests/unit/server/services/test_education_book_structure.py。
- Modify: plugins/README.md；核对 pyproject.toml/uv.lock 与实际 Docker 依赖构建文件。

1. 固定更新后的 SKILL.md、README、SPEC、schema 与摘要，确保正式 schema 校验可用，不在运行时读取个人技能目录。
2. 对本地真实样例做只读检查。曾有的 title_source:null 必须给出 JSON 路径错误；不得放宽 schema 或改用户源样例。自动化用合成合法 fixture，真实全链验收使用届时实际通过固定 schema 的产物。
3. 明确解析函数的输入为可信源描述、原始 JSON、受控输出清单；返回完整 JSONB、KP 查询投影与告警。不需要模型生成数据库字段/manifest/hash。
4. 覆盖递归/未知扩展字段、多 nodes 引用、单节点多个 KP、无 unit、空 chapters、空 KP、1-based inclusive、line_offset 不重复转换、非法引用/重复 ID/重复 JSON 键/非有限数值/不支持的 schema major/越界/路径逃逸/缺失材料。
5. 冻结新的 API/DTO。下表路径均相对 /api/v1/education；kpId 使用新查询记录 UUID，返回的 skill_kp_id 用于工作台 URL。两者禁止混用。

| 方法/资源 | 契约 |
|---|---|
| GET/POST /textbooks | 列表；以 parse_job_id/primary_artifact_id/title 创建并排队分析，返回 textbook_id/job_id |
| GET /textbook-sources | 当前用户可读且已完成的主 Markdown 解析产物，单选 |
| GET /textbooks/:id | 工作台快照：来源、结构状态、材料计数、当前/最近任务，不返回全书讲义正文 |
| GET /textbooks/:id/structure | schema 结构及当前 content_file 投影、KP UUID 映射 |
| GET /textbooks/:id/source | 可信冻结原文，支持行范围；source_lines 的起止均包含 |
| GET /textbooks/:id/assets/:assetId | 授权源/材料图片，不暴露任意存储路径读取 |
| GET /textbooks/:id/knowledge-points/:kpId/material | 当前成功 Markdown 与生成元数据；无材料有明确空状态 |
| POST /textbooks/:id/jobs | structure 或 materials；冻结目标集合/深度/要求/请求幂等键 |
| GET /book-jobs/:jobId | job/item 状态、准确完成计数及高水位游标 |
| POST /book-jobs/:jobId/cancel | 停止真实运行和未启动 item，不回滚成功产物 |
| POST /book-jobs/:jobId/retry | 为失败/未执行项建立新任务；不重跑成功项 |
| GET /book-jobs/:jobId/events | after_seq SSE 回放/跟随，过期游标触发快照重取 |
| POST/DELETE /textbooks/:id/assignments | 家长显式分配/撤销学生访问，不创建发布快照 |

6. 学生既有 reading/items/progress/summary/chat API 保留能力但更新 DTO；细节由 Task 6 接线。旧 API 退役清单以审计文档为准。
7. 运行 uv run pytest tests/unit/server/services/test_education_book_structure.py -q；记录结果，提交。

## Task 2：新数据模型、来源和确定性导入

**Files**
- Create: migrations/versions/082_more_to_skills_textbooks.py（若 082 已占用，从实际 head 选择新的顺序号，不覆盖）。
- Create: src/server/database/education_books.py、education_book_jobs.py、education_learning.py。
- Create: src/server/services/education_book_storage.py。
- Modify: education_textbook_source_snapshots.py、education_textbook_snapshot_reads.py、education_book_structure.py。
- Create tests: tests/integration/test_education_books_db.py、tests/unit/server/services/test_education_book_storage.py、tests/unit/migrations/test_more_to_skills_textbooks.py。

1. 按清理清单建立完整目标 DDL：重建教材身份/授权等保留表的相关字段，建立 structures/KPs/materials/jobs/items/activity 六张新表，删除明确的旧教材表/约束。开发期间仅在隔离数据库执行此完整迁移。
2. 单来源冻结复用图书馆 bundle，改掉旧 version/position 前缀和旧 DB import；持久保存源 Markdown/图片清单及摘要、blocks、报告。保持原文行号及图片相对路径。
3. 教材创建与初始 job 入队在同一事务；重复请求/相同来源返回既有明确对象，不能因网络重试创建多本空教材。
4. 结构原子导入所有 nodes/KPs；空 chapters 合法，已有目标材料按同一存储流程导入。未知 schema 字段保留，KP 的 nodes 仍为多引用。
5. material 是当前可变指针的唯一真值；结构 API/导出确定性覆盖 content_file，不三处双写。通过事务与行锁/CAS防止重复提交。
6. 上传前记录候选键清单，写本 attempt 不可变对象，最后提交 material、item 状态和完成事件。注入上传失败、PG 提交失败、重复 finalise，确认旧材料可读且没有假成功。
7. 旧教材表/字段删除的最终应用留 Task 7；但迁移本身必须完整测试空库到新 head、081 到新 head 结果一致。
8. 运行 uv run pytest tests/unit/server/services/test_education_book_storage.py tests/unit/migrations/test_more_to_skills_textbooks.py tests/integration/test_education_books_db.py -q，预期引用、幂等、事务和 catalog 检查通过；提交。

## Task 3：正常 PTC 执行与逐项恢复

**Files**
- Create: src/server/services/education_book_jobs.py、education_book_recovery.py。
- Modify: education_managed_runs.py、src/ptc_agent/agent/managed_execution.py、agent.py、src/ptc_agent/core/session.py、core/sandbox/ptc_sandbox.py。
- Modify: src/server/services/runs/executor.py、src/server/app/setup.py、src/config/models.py、src/config/settings.py、config.yaml。
- Create tests: tests/unit/server/services/test_education_book_jobs.py、tests/integration/test_education_book_jobs_db.py。
- Rewrite: tests/unit/ptc_agent/test_managed_textbook_execution_policy.py、tests/unit/server/services/runs/test_education_teaching_timeout.py。

1. 一份教材 managed policy、统一 education_book managed kind，两种用户操作；保留父用户模型解析和正常图构建。移除旧五个 purpose、旧 fixed v2 textbook-chapter-worker 注册和 prompt，不影响普通 subagent。
2. 显式传 textbook/job/item/execution/run/attempt IDs；root 只使用 execution-id。统一 inputs、技能、work、outputs，不从路径推测 job_id。
3. Docker 实测自编/修改 Python 脚本、普通 Bash/ExecuteCode、图片多模态读取、只读来源与固定服务 schema。不能以能列出图片路径代替模型能读图。
4. 结构 item 使用 Structure Only；成功后调用 Task 2 原子导入。已成功结构不可由材料任务改写。
5. 每材料 item 只生成指定 KP，按 skill 读取块、脚注、图片、邻近答案和替代上下文；归档后一份即可被 UI 读取。缺前一讲义不阻断。
6. 同一本书仅一活动 job；批量持久化 target items 后顺序执行。全书请求的结构→材料后续意图必须持久化，结构提交后只创建一次后续任务，不靠前端在线或内存回调。明确要求“全部文件”时追加一次附加材料 item；“全部讲义”不强制 glossary 等。
7. item 含当前 attempt token、run/thread/workspace IDs、租约和结果。使用正常 RunCoordinator 终态，业务 finalise 只在匹配 attempt 下提交。
8. cancel 必须终止当前真实 run、终止待执行队列；已提交材料不回滚。重试创建失败/未执行集合的新任务。普通内容失败继续下一项，基础设施/凭据/全局来源失败停止余项。
9. recovery 服务接入已有维护周期：从 PG 待启动项和 runtime ledger 恢复；运行结束但 callback 未完成时幂等收尾，不能安全恢复的中断明确标为可重试。不要用进程内注册表作为事实源，也不要新增独立 Agent 引擎。
10. 故障注入排队后进程退出、上传后退出、提交后回调前退出、跨 worker cancel、重复请求及旧 attempt 返回。确认成功项不二次生成，下一项不永久卡住。
11. 运行 uv run pytest tests/unit/server/services/test_education_book_jobs.py tests/integration/test_education_book_jobs_db.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py tests/unit/server/services/runs/test_education_teaching_timeout.py -q，真实 Docker smoke 完成后提交。

## Task 4：有界公开活动与浏览器恢复

**Files**
- Create: src/server/services/education_book_activity.py。
- Modify: src/server/services/runs/sse_producer.py、新 book job/recovery 服务、book activity 数据库查询。
- Create tests: tests/unit/server/services/test_education_book_activity.py、tests/integration/test_education_book_activity_stream.py。
- Inspect/update when relevant: src/server/services/history 的事件分类及 tests/unit/server/services/history/test_event_ledger.py。

1. 在可 await 的流消费边界加入可选通用观察回调；教材投影在 education 模块。教育原始 delta 仍在 accumulator/Redis 之前被过滤，普通聊天 full profile 不变。
2. 映射公开说明、工具开始/结束短摘要、服务验收结果；不保存思维链/完整工具参数/输出。没有 report_progress 不影响业务成功。
3. 实现设计预算（1000 普通活动/1 MiB、单条 2 KiB/512 字符、同活动至少合并 1 秒）和唯一终态豁免；前端列表同样有界。超预算仅丢详细活动，不丢业务状态。
4. 完成事件随教材提交同事务，Redis 通知丢失从 PG 补齐。快照高水位/after_seq/去重、游标过期、断线重连、后台标签恢复、活动写入故障明确处理。
5. 专用教育 SSE 使用表为 durable home；如果引入任何通用 chat-wire 类型，则同步登记历史 replay 来源，不能跳过现有 ledger 约束。
6. 压测 150001 raw delta、大量短工具结果、很长文本、Redis 不可用、跨 worker 重连；同时测 PG 行/字节、Redis 条数/字节与浏览器渲染规模，不只测 DTO。
7. 运行 uv run pytest tests/unit/server/services/test_education_book_activity.py tests/integration/test_education_book_activity_stream.py -q，并执行 producer compact/full 与 event ledger 对应回归；提交。

## Task 4A：托管 PTC 语义进度发送端

**Files**
- Create: `src/ptc_agent/agent/tools/report_progress.py`、`src/server/services/education_book_progress.py`。
- Modify: managed policy/tool assembly、`education_book_jobs.py`、`education_book_activity.py`、book DTO/API。
- Create/update tests: PTC tool/policy、education progress/activity/job、activity API/SSE integration。

1. 按独立[实施计划](2026-10-02-managed-textbook-progress-implementation.md)的 Task 1–4 执行。向教材托管 PTC Agent 注入默认关闭、无数据库权限的 `report_progress(stage)`；普通 PTC/Flash 和其他 Skill 工具面不变。
2. structure/material/supplementary 使用各自有限 stage；阶段和中文文案由 education 模块维护。仅在 `task.json.progress` 提供工具名和当前 item 的允许阶段；已有任务身份/attempt/来源/输出字段保持原样，进度工具不接受业务 ID、完成数、路径、正文或自由展示文案。阶段可以漏报、重试和回退，不构成业务状态机。
3. observer 隐藏 `report_progress` 自身的通用工具开始/结束噪声，只保存经过白名单映射的业务阶段；预算耗尽后的省略计数使用相同阶段验证、节流及过滤规则。未知、跨 item、重复、迟到和写入失败均不改变业务状态。
4. job/item 快照是状态和计数真值；材料 N/M 只统计成功提交的 material items，supplementary 单列，结构提交前不显示知识点完成率。
5. 只补齐授权 `GET /book-jobs/:jobId` 任务快照与 `/book-jobs/:jobId/events` 活动页，冻结 DTO、SSE id 和权限/重连行为。活动页不冒充完整 job/items；客户端从已消费 seq 重连，不能直接使用服务器 high-water。完整教材/学生门面继续归 Task 5/6，不提前重写，不恢复旧 polling/progress DTO。
6. 完成 PTC、教育服务、必要 API、PostgreSQL activity stream 聚焦回归并提交后进入 Task 5；Task 4A 不以工作台或真实浏览器全链验收为完成前提。

## Task 5：新工作台及图书馆直达

**Files**
- Create: web/src/pages/Education/TextbookWorkbenchPage.tsx、TextbookWorkbenchPage.css。
- Create: web/src/pages/Education/components/BookNavigator.tsx、BookReader.tsx、BookActivityPanel.tsx、BookGenerationForm.tsx。
- Rewrite: TextbooksPage.tsx、Education/{api,queries,types,errorMessage}.ts。
- Modify: components/EducationMarkdown.tsx、web/src/lib/queryKeys.ts、Main/Main.tsx、Main/routeChunks.ts、Sidebar/AppSidebar.tsx、涉及的 locales。
- Modify: Documents/DocumentDetailPage.tsx、Documents/components/TeachingUsagePanel.tsx、Documents/{api,hooks,types}.ts。
- Create tests: web/src/pages/Education/__tests__/TextbookWorkbenchPage.test.tsx、BookNavigator.test.tsx、BookActivityPanel.test.tsx。
- Update: Documents/__tests__/DocumentDetailPage.test.tsx 及 TeachingUsagePanel 对应测试。

1. 按设计线框构建一个工作台；不基于旧候选/结构页保留大量条件分支。复用现有 UI/theme/Markdown 基础组件。
2. 新建教材使用共享单选来源面板与“添加并分析”；图书馆直接带入选中的成功解析产物，去空教材/版本/多来源步骤。
3. 左栏切换 KP/原书目录，搜索和折叠；主内容讲义/原文两个视图，生成表单原位展开；活动按需展示，不占第三层导航。活动主线组合服务端里程碑、数据库 item 计数和当前 Agent 语义阶段，Read/Bash 等工具事件默认收进可展开明细。
   活动面板按语义进度独立计划 Task 5 实施一次。以已成功合并事件的 `last_processed_seq` 恢复分页；首次/缓存丢失/游标过期从 0 重建有界活动。业务事件按每任务最多每秒一次合并刷新业务快照，活跃任务在可见页面每 5 秒兜底刷新；空事件、预算耗尽或活动 unavailable 也能更新当前项和 N/M。终态最终刷新、后台恢复、任务切换和迟到响应均按详细设计处理。
4. URL 维护 skill KP ID/node ID/view，转换为后端 UUID 时使用当前结构映射。返回/前进、深链、搜索/展开及正文滚动符合设计，异步事件不劫持当前阅读位置。
5. AST 源行映射做范围跳转/高亮；图片经授权 resolver；同书相对讲义链接未生成时打开目标原文。禁止任意 source.path 或任意 MinIO key 读取。
6. 批量显式进入选择模式，默认跳过已有讲义；重做列明数量。运行中可浏览、可取消；失败仅重试未完成；已有材料不会因错误消失。
7. 无 KP/无讲义/正在生成/部分失败/已取消/重连/活动不可用/无权限均有明确状态；切换 KP 不串 prompt。断线不等于任务失败，结构运行不显示虚假完成率，附加材料不计入讲义 N/M。键盘导航、焦点管理、可读字体与窄屏抽屉可操作。
8. 删除审计中五个旧页面及其专用组件、CSS、路由 chunk 和 polling/query keys；旧路径只返回静态重置说明，不能 fallback 旧页。
9. 在 web 运行 pnpm test src/pages/Education/__tests__/TextbookWorkbenchPage.test.tsx src/pages/Education/__tests__/BookNavigator.test.tsx src/pages/Education/__tests__/BookActivityPanel.test.tsx、pnpm typecheck、pnpm build；真实浏览器检查导航不跳页，提交。

## Task 6：学生功能、授权和图书馆使用查询闭环

**Files**
- Rewrite: src/server/app/education/textbooks.py、src/server/services/education_textbooks.py 的新门面；同步 setup.py router。
- Modify: src/server/services/document_teaching_usage.py、src/server/app/documents.py 相关 DTO/服务调用。
- Modify: education_learning_assets.py、education_learning_chat.py、education_learning_transcript.py、src/server/app/threads/messaging.py。
- Modify: web/src/pages/Education/StudentTextbookLearningPage.tsx、PersonalizedSummaryPage.tsx、components/PersonalNotebook.tsx、StudentLessonFollowUp.tsx。
- Create/update tests: tests/integration/test_education_book_learning_db.py、tests/unit/server/app/test_education_learning_thread_protection.py、tests/unit/server/services/test_education_learning_chat.py、tests/unit/server/app/education/test_learning_items.py、图书馆 teaching-usage 测试。

1. 工作台“给学生使用”只建立最小教材授权；清除 publication/revision/approval 流程。明确已分配学生读取最新成功材料，失败重做仍读旧材料。
2. 授权同时覆盖结构、原文、图片、材料和 Flash 上下文；撤销后全部入口拒绝，学生不能调用家长生成/配置/活动控制。
3. 进度、笔记、总结从新节点 ID/KP UUID 读取，不制造旧 Unit adapter；学生原有功能继续可用。
4. Flash 每轮由服务读授权材料并冻结当时内容依据，保持私人 Flash workspace 和既有 thread 保护。旧学习映射移除不能解除旧会话限制。
5. 重写 document_teaching_usage 的 JOIN/DTO，图书馆使用情况直达工作台；删除 content_version/publication 的 UI 和 TS 字段。
6. 从新 DB/API 跑通家长分配→学生阅读/笔记/追问→家长更新讲义→学生读取新内容→撤销访问；并检查其他家庭、猜测 KP UUID/图片 ID 被拒绝。
7. 跑所列聚焦测试及学生前端回归，提交。此任务未完成不得删旧表并宣称重构成功。

## Task 7：一次切换、旧代码和旧资源清理

**Files**
- Remove: 审计 A/B/D 明确删除的页面、服务、旧 skill 和专用组件/测试。
- Rewrite/remove: src/server/database/education_textbooks.py；旧查询全部转到新数据库模块后删除，不保留薄 wrapper 维持旧 API。
- Update: src/server/app/education/models.py、相关 OpenAPI/路由导出、配置、README、scripts/education_purge_prefix.py。
- Finalise migration: Task 2 的完整切换迁移。
- Test: 新迁移 integration/catalog、import layering、失效路由与消费者回归。

1. 在隔离数据库演练完整切换：记录旧依赖→处理 FK 循环→清理旧数据/表/字段→建立新表/授权引用。检查 pg_constraint 和最终 catalog；不改历史迁移、不复制 075 的 TRUNCATE CASCADE。
2. 列出并复核本次旧教材的准确 job/run/thread/workspace/sandbox/object key 清单。区分图书馆输入、家庭作业资产、普通 Flash/PTC 数据和教材派生产物。
3. 切换窗口只停旧教材入口，取消准确活动 run，终止/归档准确学习线程，收尾托管资源。不能先删 mapping 让受限线程变普通会话。
4. 应用新 schema 并同时切换完整后端/前端。不得留下新旧引擎选择开关、旧版本分支或 profile fallback。
5. 旧 SQL、API/query keys、五种 managed purpose/kind、fixed v2 worker、进度 helper/JSONL、package 多投影、候选审核、章节 checkpoint continuation 全部按清单逐项验收。
6. 按已知键清理旧教材派生对象与 run 缓存，保留源图书馆资产；异常归属单独列明。既有维护/恢复只引用新任务，不复活旧 job。
7. 运行生产路径残留检索，许可/历史迁移/历史文档只作为显式豁免；检查没有被删文件的 import 和旧路由懒加载。
8. 精确记录实际删除的数据和不可恢复性，按用户已授权的教材范围执行；提交清理与接线结果。

## Task 8：端到端验收矩阵

每行都需要自动化或真实行为证据；只读代码审查不算完成。

语义进度独立计划 Task 6 在此汇总执行，覆盖分页中途断线、无活动的 item 切换、预算耗尽后 stage 省略统计及已有任务契约保持。Task 4A 的阶段性交付不替代此处完整验收。

| 场景 | 必须观察的结果 |
|---|---|
| 图书馆一键添加 | 一个教材、一个初始任务，无额外版本/候选页 |
| 结构-only | schema/来源有效，树/KP 可读，chapters 空不失败 |
| 中间 KP 首次生成 | 前面没有讲义仍可生成，图片/脚注/邻近上下文可用 |
| 已有讲义重做失败 | 旧讲义仍可读，错误与重试准确 |
| 批量第 3 项失败 | 前两份立即可读，其他独立项按规则继续，计数来自已提交项 |
| 取消与迟到回调 | 当前 run 停止，后续未启动，迟到结果不覆盖 |
| 双击/两个标签页 | 幂等或明确冲突，不双跑、不重复记完成 |
| 上传/PG finalise 崩溃 | 无假成功，已提交不再生成，候选对象可准确收尾 |
| 关闭浏览器/换 worker | 任务继续；回来快照+游标补齐，不自动重做 |
| Redis 故障/150001 delta | 不写全量流，容量有界，PG 事实可恢复 |
| 任意节点/长文/图片 | 行号不偏移，relative link 合法，深链/返回保持阅读位置 |
| 学生与图书馆反查 | 新 DTO 正常，进度/笔记/追问继续，旧表无查询 |
| 权限撤销/跨家庭 | 原文、材料、图片、聊天上下文均拒绝未授权访问 |
| 旧路由与 catalog | 无旧页面/chunk/query，旧表和约束已退役 |
| 普通产品回归 | PTC/Flash/MCP/subagent/checkpoint、图书馆 Datalab、家庭作业不受损 |

执行基础检查：uv run pytest tests/unit -q、相关 DB/Docker/integration suites、make lint；web 执行 pnpm test、pnpm typecheck、pnpm build。多 worker 使用现有 scripts/multiworker_gate/ 中适用项及教材专用故障用例。记录已有基线失败，不把未运行的检查写成通过。

检查 8000/5177 的精确 PID/工作目录后再决定重启，前端必须监听 0.0.0.0:5177。实测 LAN health、/education、/textbooks、新工作台以及学生页面。真实 UI 验收用 375px 与桌面宽度、键盘、图片和活动重连；确认从列表打开后整段加工无需离开工作台。

交付包含：清理清单逐项结果、迁移/删除范围、真实生成与压力证据、未完成项（若有）和最终中文 CHANGELOG/原子提交。不能把“设计已写好”或“新路径跑通”当成整个重构完成。
