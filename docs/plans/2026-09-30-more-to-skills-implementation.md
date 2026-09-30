# more-to-skills 教材处理重构 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用 more-to-skills 原生产物实现结构入库、知识点导航、原文定位和按需讲义，移除旧教材加工协议与冗余配置。

**Architecture:** 沿用 PTC、Docker、任务 attempt 和现有 SSE 基础设施。教育服务直接导入固定 schema 的 book-structure.json，章节树存 JSONB，知识点和讲义保存最小查询记录；运行事件在 Redis 写入前精简。旧教材数据无需兼容，图书馆源资产及其他产品模块保留。

**Tech Stack:** Python 3.13、FastAPI、async psycopg、Alembic raw SQL、jsonschema、PostgreSQL、Redis、React 19、TypeScript、Vite、pnpm。

---

## 执行约束

- 设计依据：`docs/plans/2026-09-30-more-to-skills-design.md` 和用户 2026-09-30 的确认。
- 此文档仅为计划；用户当前要求先讨论和计划，不在本轮执行下面的代码或数据库操作。
- 工作目录：`/Users/seanlee/.config/superpowers/worktrees/langalpha/library-textbook-assets`；保留已有 Datalab 高级选项提交。
- 开始前读相关 AGENTS.md、检查 dirty 状态及最新迁移 head。新文件名为计划目标，遇到后续同名实现先检查再调整。
- 先验证真实行为，随后用精简的合成 fixture 固化契约。不提交私人教材、生成讲义、密码或本地运行文件。
- 每项实质变更通过对应检查后，更新中文 CHANGELOG，精确 git add 本项文件并原子提交。
- 不生成数据库依赖黑箱兼容层；删除范围由明确表、字段、接口和调用点列表限定。切换前确认受影响任务没有正在写入，必要时仅停止相应教材任务。

## Task 1：固定 skill、验收契约与删除范围

**Files**
- Create: `plugins/langalpha_local/skills/more-to-skills/`（复制用户技能所需文件，保留 LICENSE.md，排除缓存与生成物）。
- Create: `src/server/services/education_book_structure.py`。
- Create: `tests/unit/server/services/test_education_book_structure.py`。
- Inspect: `migrations/versions/066_add_textbook_structure_models.py`、`067_add_kp_lessons.py`、`068_add_structure_publications.py`、`069_add_learning_items_and_profiles.py`、`075_reset_textbook_pipeline.py`、`079_book_pipeline_package_import.py`、`080_education_job_progress.py`、`081_book_pipeline_checkpoint.py`。

1. 重新读取用户 skill 的 SKILL.md、README.md、SPEC.md、schema，核对用户本轮修改已纳入；记录固定内容摘要。
2. 对本地真实样例做只读 schema 校验及锚点/引用检查。若仍有两处 null，保留准确错误，测试在临时副本上按 schema 删除可选空字段，不动源文件，不静默放宽生产验收。
3. 梳理旧表的所有引用，输出精确的保留/替换/删除清单到设计文档；检查学生学习、作业和通用任务引用，不用 CASCADE 跨模块删除。
4. 用合成 fixture 覆盖递归节点、多节点 KP、一个节点对应多个 KP、空 chapters、扩展字段保留；失败用例覆盖 null 枚举、重复 ID、失效引用、越界行号和不安全输出路径。
5. 实现纯解析/校验函数，返回原始结构及确定性 KP 投影；结构任务显式要求 knowledge_points，字段语义遵从 skill，不添加旧 point_type/confidence 等要求。服务固定 schema，不信任任务改写的校验器。
6. 执行 `uv run pytest tests/unit/server/services/test_education_book_structure.py -q`，预期全部通过；提交技能和契约变更。

## Task 2：最小数据模型及直接导入

**Files**
- Create: `migrations/versions/082_more_to_skills_textbooks.py`（实施时确认 082 未占用，并从实际 head 接续）。
- Create: `src/server/database/education_books.py`。
- Create: `tests/integration/test_education_books_db.py`。
- Modify: `src/server/services/education_book_structure.py`。
- Inspect/reuse: `src/server/database/education_textbooks.py`、`src/server/services/education_textbook_source_snapshots.py`。

1. 在独立测试数据库验证新建库及当前 head 升级路径。DDL 使用 raw SQL，建立设计中的 structure、KP、material 三类记录和必要索引/FK，不为每个目录节点额外建表。
2. 结构导入事务写入完整 JSONB 和 KP 投影，绑定现有图书馆源快照；KP 的 unit/nodes/blocks 原样保留。存储技术 ID 不改写 skill 的 ID。
3. 增加 attempt 条件更新与相同请求幂等检查；失败必须无半套结构和 KP。不迁移旧教材数据，不误删仍由其他模块使用的记录。
4. 实现讲义文件归档后原子更新 material 与目标 KP content_file；验证不会覆盖别的 KP，旧 attempt 返回不能覆盖当前结果。
5. 用真实样例临时副本验证导入及计数；fixture 和教材内容不提交到仓库。
6. 执行 `uv run pytest tests/integration/test_education_books_db.py -q`，预期事务、唯一性、引用及旧 attempt 拒绝测试全部通过；提交数据模型和导入变更。

## Task 3：统一任务、目录和图书馆资产接入

**Files**
- Create: `src/server/services/education_book_jobs.py`、`src/server/services/education_book_storage.py`。
- Create: `tests/unit/server/services/test_education_book_jobs.py`、`tests/unit/server/services/test_education_book_storage.py`。
- Modify: `src/server/services/education_managed_runs.py`、`src/ptc_agent/agent/managed_execution.py`、`src/ptc_agent/core/sandbox/ptc_sandbox.py`。
- Inspect/reuse: `src/server/services/education_textbook_source_snapshots.py`、`src/server/services/education_textbook_snapshot_reads.py`、`src/ptc_agent/agent/agent.py`。
- Existing regression: `tests/unit/ptc_agent/test_managed_textbook_execution_policy.py`。

1. 定义一种教材执行配置、两种业务操作：structure、materials；保留现有 root run/checkpointer/attempt 运行机制，取消各类教材 Agent 人格和 processing profile 分支。
2. 统一输入根、work、outputs 和技能根；不要把最终 JSON schema 验收误用为辅助脚本/中间文件的写入限制。
3. 保留正常 Bash、ExecuteCode、Read/Write/Edit 能力。Agent 可在 work 内新建脚本或修改技能脚本副本；固定源文档和服务验收 schema 不被更改。
4. 暂存图书馆 Markdown 和必要图片，保持字节/行号及相对路径，利用已有清单读取相关对象，不枚举其他对象。安装 jsonschema，禁止校验静默跳过。
5. 结构操作调用更新后的 Structure Only，完成后由 Task 1/2 的代码导入，不再要求四套 JSON、章节知识材料或进度日志。
6. 材料操作输入已保存结构、KP IDs、原文/图片及技能要求的邻近上下文。调用 Reading Material Only，直接归档 chapters 文件；选中多条时顺序处理，某条失败不清除其他条。
7. 从当前输出目录发现并归档技能产生的可选附加文件，清单由服务生成；不让可选附加材料缺失阻止结构任务完成。
8. 执行 `uv run pytest tests/unit/server/services/test_education_book_jobs.py tests/unit/server/services/test_education_book_storage.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py -q`；再做 Docker smoke：自编 Python 脚本、图片读取、任意起点讲义、取消与迟到结果。
9. 提交统一运行和产物接入变更。

## Task 4：精简 Timeline 和有界持久事件

**Files**
- Create: `src/server/services/education_book_activity.py`。
- Create: `tests/unit/server/services/test_education_book_activity.py`、`tests/integration/test_education_book_activity_stream.py`。
- Modify: `src/server/services/runs/sse_producer.py`、`src/server/services/education_book_jobs.py`。
- Inspect/reuse: `src/server/services/education_generation_progress.py`、`src/server/database/education_textbooks.py` 现有事件与 attempt 逻辑。

1. 找到运行消息、工具调用和工具结果的既有流入口；添加可选通用事件投影接点，教材含义留在 education_book_activity，不改变普通 PTC/Flash full profile。
2. 在 accumulator、Redis writer 之前过滤原始 token/delta、大段参数/结果和内部推理，只生成精简 activity。不能通过关闭 education_compact 恢复全量流。
3. 持久事件使用 job/attempt、单调 seq、稳定活动 ID、类型、时间、短说明及必要目标 ID；复用一份 ledger，避免与旧进度表并行双写同一业务事实。
4. 添加合并、长度限制、速率和总预算；保留错误/业务终态及工具活动汇总。重连按 seq 补齐去重；心跳不逐条持久化。
5. 工具结束不触发业务完成；结构入库和讲义归档后由服务发成功事件。可选 report_progress 仅补充公开说明，禁止以其缺失阻止导入。
6. 压力验证：150001 raw delta 不产生线性持久行/字节增长；大量短工具活动也受预算约束；跨 worker 重连、cancel、过期 attempt、重复事件不产生重复完成或错误状态。
7. 执行 `uv run pytest tests/unit/server/services/test_education_book_activity.py tests/integration/test_education_book_activity_stream.py -q`，保留既有 producer/full-profile 回归并提交。

## Task 5：API、知识点导航和原文阅读

**Files**
- Modify: `src/server/app/education/textbooks.py`、`src/server/services/education_textbooks.py`。
- Modify: `web/src/pages/Education/TextbookStructurePage.tsx`、`BookProcessingPage.tsx`、`StudentTextbookLearningPage.tsx`、`queries.ts`、`types.ts`。
- Modify: `web/src/pages/Education/components/EducationMarkdown.tsx`。
- Create: `web/src/pages/Education/__tests__/MoreToSkillsTextbook.test.tsx`。
- Modify: `web/src/pages/Education/__tests__/BookProcessingPage.test.tsx`。
- Modify: `tests/unit/server/app/education/test_textbooks.py`。

1. API 暴露结构、KP/材料状态、原文范围、图书馆资产和任务活动；创建结构/材料任务保留家长授权，学生只读其授权教材及讲义。
2. 默认左栏按 unit 分组呈现 KP，支持切换原书递归目录；unit 缺省时按 schema 允许的情况提供未分组区，不臆造节点。
3. 未生成讲义仍能看结构/原文；点击任意 KP 可以生成，支持深度与用户要求、选中全部。无需前文讲义或人工接受候选点。
4. Markdown 渲染关联源行范围以支持全文跳转及片段展示；保留授权图片解析，不在浏览器读取 source.path 的宿主机路径。
5. Timeline 使用 SSE 和持久游标，刷新可恢复；有真实计数则展示计数，否则展示状态与耗时，不虚构百分比。
6. 删除拆分/合并/候选审阅/旧阶段按钮和多余 profile 配置；讲义重做期间仍可读取已成功材料，失败不清空材料。
7. 执行 `uv run pytest tests/unit/server/app/education/test_textbooks.py -q`；在 web 目录执行 `pnpm test src/pages/Education/__tests__/MoreToSkillsTextbook.test.tsx src/pages/Education/__tests__/BookProcessingPage.test.tsx`、`pnpm typecheck`；提交。

## Task 6：删除旧流程与冗余表

**Files（先核实调用引用，再精确删除/重写）**
- Remove: `plugins/langalpha_local/skills/book-to-skill/`。
- Remove/replace: `src/server/services/education_lesson_jobs.py`、`education_book_pipeline_jobs.py`、`education_book_package.py`、`education_book_asset_jobs.py`、`education_progress_collector.py`。
- Remove obsolete paths: `education_structure_jobs.py`、`education_teaching_storage.py`、候选审阅/结构拆分服务及专用模型、路由、测试。
- Modify: `src/server/database/education_textbooks.py`、相关前端 API 与类型、`plugins/README.md`。
- Create: 清理迁移（按 Task 1 的精确表/列/FK 清单，选择实施时可用的下一个 Alembic revision）。

1. 新入口打通后切换所有教材生产/消费调用；不保留旧 skill 与新 skill 双通道。
2. 逐项解除旧表引用，执行明确的教材数据删除和 DDL 清理。保留或改接仍被学生学习入口需要的最小关系，不删除普通作业、家庭或图书馆数据。
3. 删除 progress helper 的暂存、JSONL reader、日志事件必达门禁，以及旧 package 四份投影与章节 checkpoint 业务协议。保留通用 PTC checkpoint。
4. 搜索运行代码 `book-to-skill|progress.jsonl|book_package.json|candidate_review`，逐项说明剩余命中；新 skill 的许可署名和历史变更日志允许保留，不做无差别字符串替换。
5. 将旧测试删除或替换为新行为测试，不留下仅为废弃接口继续过测的兼容代码。
6. 验证新建库、已有库升级、API 导入、学生授权、取消和失败恢复；提交精确清理。

## Task 7：端到端验收与交付

1. 检查准确的进程、端口和 worktree；已有 8000/5177 服务时确认其代码目录后按需要更新，不启动冲突实例。
2. 通过真实图书馆产物跑结构分析：含图片的 Markdown → 标准 JSON → 可浏览目录和 KP；不生成讲义时 chapters 为空不报错。
3. 直接选择中间 KP 生成讲义，验证前文未生成也成功；检查图片、邻近引用、跳回原文位置和 content_file 更新。
4. 选择多条或全部时，验证顺序执行、已完成材料可读、失败/取消只影响未完成项；刷新重连后不丢失、不重复显示完成事件。
5. 验证 Agent 在真实 Docker 内编写/调整辅助脚本，且最终服务 schema 无法被任务内修改绕过。记录真实模型执行结果，不以模拟测试替代。
6. 在依赖就绪的环境运行 `uv run pytest tests/unit -q`、相关 integration suites、`make lint`；web 运行 `pnpm test`、`pnpm typecheck`、`pnpm build`。区分已有基线问题与本次回归，不宣称未运行检查已通过。
7. 保证前端监听 `0.0.0.0:5177`；检查 `http://192.168.3.240:5177/education` 和后端 health，并在浏览器实测教材页面、图片、原文跳转、Timeline。
8. 更新中文 CHANGELOG、记录检查结果并原子提交；列出确实删除的旧教材数据范围、不可恢复性及仍保留的源资产。不得将任何文档计划描述为已实施。
