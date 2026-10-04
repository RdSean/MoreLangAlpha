# 教材异步准备与全屏计时 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** “添加并分析”快速返回，同一教材工作台可恢复地显示准备进度、加工计时和整页时间线，覆盖结构与讲义。

**Architecture:** 为现有 structure item 增加模型前准备阶段；PG 持久保存来源状态、attempt 和分段计时，worker 执行复制/校验，Redis 仅唤醒 SSE。前端工作台通过 query 参数切换整页处理/阅读/紧凑活动，共用一份订阅和计时数据，不恢复旧路由、不另建消息队列。

**Tech Stack:** FastAPI、async psycopg、Alembic raw SQL、现有 S3/MinIO 适配、PTC/runtime ledger/checkpoint、React 19、React Query、Lucide/shared Loader、Vitest、Playwright。

---

## 状态、依据和执行纪律

- 2026-10-05：设计和计划已审阅，用户授权在当前 worktree 连续实施。A0–A4 已完成契约、数据库基础、快速受理、后台准备/恢复及持久计时统计；A5–A7 待实施。未升级开发库、未启动付费模型验收。
- 依据：[设计](2026-10-04-textbook-async-preparation-timeline-design.md)及两轮 SB3 实测记录。此增量不改原 Task 8 完成结论。
- Worktree：`/Users/seanlee/.config/superpowers/worktrees/langalpha/more-to-skills-textbook-refactor`；分支当前 `feature/more-to-skills-textbook-refactor`。下面精确文件路径相对此目录。
- 读取根目录、src/server 与 web 的 AGENTS.md；界面遵守 DESIGN.md。保留用户修改的业务动作文档和未追踪 PDF，不重置、不纳入提交。
- 当前迁移 head 已核对为 083_textbook_deletion_cleanup；实施前再次检查 head，084 命名仅在没有其他迁移时采用。
- 先真实定位边界，再写聚焦失败回归，运行确认失败，再实现最小改动并确认通过。每个实质验证通过的 task 更新中文 CHANGELOG，显式文件原子提交，不一次提交所有半成品。
- 不复制/打印/提交 .env 或浏览器凭据，不操作未知 Docker/volume。存储沿用用户确认的 localhost:9000 与当前 .env；仅访问明确教材/测试前缀，保留图书馆原件。

## Task A0：冻结 DTO、时间口径和状态转换

状态：已完成公共 DTO。后端 18 passed、前端契约 3 passed、pnpm typecheck、改动 Ruff 通过。计时投影/真实边界验证在 A4/A5 实施，不将 DTO 测试称为工作流验收。

**Files:**
- Modify: `src/server/app/education/book_models.py`。
- Modify: `web/src/pages/Education/types.ts`。
- Test: `tests/unit/server/app/education/test_book_models.py`。
- Create: `web/src/pages/Education/__tests__/BookProcessingContracts.test.ts`。

1. 增加失败用例：pending 来源不能伪装 FrozenBookSource、重复受理可区分复用、ready digest 必填、单条/批量不能用源资源数当完成份数、缺失计时不能返回 0。
2. Run: `uv run pytest tests/unit/server/app/education/test_book_models.py -q`；在 web 运行 `pnpm exec vitest run src/pages/Education/__tests__/BookProcessingContracts.test.ts`。预期新契约回归先失败。
3. 增量定义 source_status/selected_source/source_frozen_at、执行 phase、准备计数、server_now、当前 attempt timing_summary 和 paginated attempt stats。CreateBookResponse 保留 textbook_id/job_id，增加 accepted_new/reused 的明确定义；既有 ready 来源字段不混入未验证 metadata。
4. 定义有限服务 phase：initial_queue/source_freezing/runtime_queue/sandbox_preparation/input_staging/ptc_execution/finalization；恢复 finalization 独立 segment。公开字段禁止 raw object key、run 输入、私有推理和凭据。
5. UI 标注 PTC执行而非纯模型思考；Agent 动作只带 report_at。写死本轮总用时含等待、retry 从新 queued_at 起算、附加材料单列等测试。
6. 重跑上述测试确认通过；更新 CHANGELOG 并提交本 task。若实现要调整契约，先回写设计，不能靠 any/宽松 payload 绕过。

## Task A1：迁移与数据库准备/计时账本

状态：已完成。隔离PG教材回归38 passed，双连接准备容量补测1 passed，相关单测66 passed；Ruff通过。旧另建数据库的迁移对照用例后续排除。084仅在测试库升级，开发库未迁移。来源IO和恢复故障矩阵归A2/A3，phase测量和统计聚合归A4。

代码证据调整：`retry_book_job()`原有回归要求新建job且仅复制未完成item，保留该入口；request_round递增并以previous_job_id串联，不能仅从新job.total_items推导原批次N/M。A4/A5负责串联成功份数与当前轮计时样本。新增家庭级受理幂等表，避免不同来源复用同一受理键未被原textbook级唯一约束捕获。

**Files:**
- Create: `migrations/versions/084_textbook_preparation_timing.py`（实施时核对 head）。
- Create: `src/server/database/education_book_timing.py`。
- Modify: `src/server/database/education_books.py`。
- Modify: `src/server/database/education_book_jobs.py`。
- Test: `tests/integration/test_education_books_db.py`。
- Test: `tests/integration/test_education_book_jobs_db.py`。

1. 在隔离库新增失败用例：早期绑定教材、ready 完整性 CHECK、同来源并发唯一、同幂等键异参冲突、旧来源可读、claim/retry queued_at、不同 attempt 不覆盖计时和 ready 指针。
2. Run: `TEST_DB_NAME=langalpha_test uv run python -c 'from dotenv import load_dotenv; load_dotenv(); import pytest; raise SystemExit(pytest.main(["-m","integration","tests/integration/test_education_books_db.py","tests/integration/test_education_book_jobs_db.py","-q"]))'`。先确认连接目标且测试仅重建 langalpha_test；skip 不算通过。
3. 添加 source_status 与 nullable 未验证字段/ready CHECK；允许精确 source attempt 子前缀，既有固定前缀不迁移对象。旧 source_frozen_at/phase timings 留空，不从教材创建时间推导。
4. 添加 item execution_phase/queued_at、job request_round/round_accepted_at；手动 retry 加请求轮次，自动准备恢复只加 attempt。仍保持 structure/material/supplementary 三种 kind 和现有业务计数。初始 structure total_items 仍为 1，准备不是第二个成功 item。
5. 新增 attempts（item_id/attempt 唯一、所属请求轮次、token 唯一、queued/claimed/terminal、phase/progress summary、固定来源清单身份）与 phase_spans（segment_id 唯一、attempt FK、phase/start/end/status/measured_ms），索引覆盖当前 attempt/历史分页；删除由教材 job/item cascade，不影响共享 run/checkpoint。
6. claim/phase 更新均带当前 token/status/取消条件；prepare 并发原子门控默认全部署1，不让两个 worker 在查询活跃数后各自插入。关键状态短事务，IO 不在事务中。
7. get_book_job_for_parent 只投影当前 attempt 紧凑计时；历史 SQL 用稳定 item/attempt 游标分页，避免逐 item N+1。统计权限 JOIN 家庭家长成员。
8. 重跑集成与 DTO 测试，确认准备失败不变成 partially_succeeded、ready 来源在结构失败后保留。更新 CHANGELOG、提交；开发库尚不升级，等关联消费者一起完成。

## Task A2：快速受理和冻结后台化

状态：受理与冻结辅助函数已完成，调度接入归A3。聚焦后端68 passed，隔离PG工作台投影2 passed，Ruff/diff检查通过。禁止对象IO的受理回归先失败后通过；固定清单冻结与资源计数为内存存储回归，未进行真实MinIO验收或付费模型调用。

**Files:**
- Modify: `src/server/services/education_textbook_source_snapshots.py`。
- Modify: `src/server/services/education_textbooks.py`。
- Modify: `src/server/app/education/textbooks.py`。
- Test: `tests/unit/server/services/test_education_textbook_source_snapshots.py`。
- Test: `tests/unit/server/services/test_education_managed_textbooks.py`。
- Test: `tests/unit/server/app/education/test_textbooks.py`。
- Test: `tests/integration/test_education_books_db.py`。

1. 失败回归用延迟/禁止调用的 storage spy，证明 POST 不执行 get_bytes/upload_bytes、Docker 或模型调用，仍完成权限、主产物、元数据、路径、来源完成状态检查。
2. Run: `uv run pytest tests/unit/server/services/test_education_textbook_source_snapshots.py tests/unit/server/services/test_education_managed_textbooks.py tests/unit/server/app/education/test_textbooks.py -q`。预期旧同步复制行为在新测试中失败。
3. 拆分元数据 preflight 和数据冻结。请求原子保存 pinned bundle descriptor +教材/structure job/item；快返回 202。不得遗漏主产物匹配、SHA 来源和 parser 身份，清单在重试期间不可偷偷换成最新解析。
4. 改 freeze helper 支持 attempt 私有前缀、进度 callback、取消检查和持久候选登记；完成资源必须写入+读回校验后递增。最终规范化结果用 fence 提交 source ready，并原子保存计时窗口/里程碑。
5. 复用同来源已完成时不冻结、不新建 job；ACK 丢失后重发复用原 ID。source pending/failed 的工作台也能读取安全元数据，source GET 在非 ready 时返回明确状态，不访问空 key。
6. 更新 source DTO/list、图书馆使用情况查询与原文读取保护；新旧 ready prefix、asset relative path、主文件哈希验证全部回归。
7. 单测和隔离数据库复跑，更新 CHANGELOG、提交。此时不启动开发 worker 搭配尚未升级 schema。

## Task A3：准备调度、租约、取消、恢复和清理

状态：已完成。服务单测62 passed；隔离PG与真实localhost:9000 MinIO组合52 passed、1个另建数据库的旧对照用例排除；Ruff通过。来源上传后SIGKILL真实子进程接管、PUT/ready COMMIT确认丢失、取消迟到上传、IO收尾锁、旧token及ready来源保护均有回归。审查修复GET错误误结清候选；新增085保留运行准备阶段的workspace/thread历史，开发库未迁移。未绑定open-run崩溃由既有runtime恢复器收尾，未单独注入该窗口或运行付费模型。

**Files:**
- Create: `src/server/services/education_book_preparation.py`。
- Modify: `src/server/services/education_book_jobs.py`。
- Modify: `src/server/services/education_book_recovery.py`。
- Modify: `src/server/database/education_book_jobs.py`。
- Modify: `src/server/database/education_book_deletion.py`。
- Modify: `src/server/services/education_book_storage.py`。
- Test: `tests/unit/server/services/test_education_book_jobs.py`。
- Create: `tests/unit/server/services/test_education_book_preparation.py`。
- Test: `tests/unit/server/services/test_education_book_deletion.py`。
- Test: `tests/integration/test_education_book_jobs_db.py`。
- Test: `tests/integration/test_education_book_storage_faults.py`。

1. 先新增失败测试：长准备不阻塞巡检、ready 前没有 PTC reservation/graph、global prep 上限、无 run 的准备不会被旧 recovery 误失败、双 worker claim fence、ready 后旧来源复用。
2. Run: `uv run pytest tests/unit/server/services/test_education_book_preparation.py tests/unit/server/services/test_education_book_jobs.py tests/unit/server/services/test_education_book_deletion.py -q`。
3. 在原服务扫描中调度有界准备任务，状态/lease/取消真值只在 PG；本地任务集合只负责本进程 IO 收尾，不承担跨 worker liveness。准备完成后进入 runtime_queue，等待现有容量时继续恢复/取消。不同阶段的 claim 不意外增一轮模型 attempt。
4. recovery 显式分支 preparing_source/runtime_queue/preparing_runtime/executing/finalizing；no-run lease 过期原子 fence，再收尾中断 attempt 并重排新 attempt。已有 run 的恢复、模型完成后重放提交继续原契约，不因本功能重跑已完成 graph。
5. IO 前登记候选键并协调删除锁；失败/取消/worker退出只清理未引用的本 attempt 前缀。ready 指针及 referenced 源文件在结构失败后不能被候选清理删除。取消与迟到写/提交/cleaner 竞态逐项测试。
6. 存储故障集成使用原 opt-in 命令：`TEST_DB_NAME=langalpha_test RUN_EDUCATION_ASSET_MINIO_TESTS=1 uv run python -c 'from dotenv import load_dotenv; load_dotenv(); import pytest; raise SystemExit(pytest.main(["-m","integration","tests/integration/test_education_book_storage_faults.py","-q"]))'`。只操作测试私有前缀，串行，不能用开发教材测试 delete。
7. 补真实子进程中断准备/跨进程接管；同时验证仅已结束且 IO 已收尾任务可删，图书馆原文件/解析记录不变。更新 CHANGELOG、提交。

## Task A4：持久分段计时、准备活动和快照 API

状态：已完成。相关单测120 passed；隔离PG与真实localhost:9000 MinIO组合74 passed、1个另建数据库的旧对照用例排除；Ruff/diff检查通过。新增086记录等待和终态事务边界；实际workflow消费至terminal回调、恢复提交独立窗口、准确准备计数及活动预算、同连接快照、跨轮完成数与本轮样本均有回归。独立审查补齐中断开放段、恢复重连前边界和首次来源计时缺失的partial投影。计时状态从持久区间推导，attempt表的默认timing_status字段不作为API真值；缺失不补造。开发库未迁移、前端未接入，不宣称付费模型或真实UI工作流通过。

**Files:**
- Modify: `src/server/services/education_book_timing.py`。
- Modify: `src/server/services/education_book_jobs.py`。
- Modify: `src/server/services/education_book_recovery.py`。
- Modify: `src/server/database/education_book_activity.py`。
- Modify: `src/server/services/education_book_activity.py`。
- Modify: `src/server/database/education_book_timing.py`（Task A1 创建）。
- Modify: `src/server/app/education/textbooks.py`、`src/server/app/education/book_models.py`。
- Test: `tests/unit/server/services/test_education_book_timing.py`。
- Test: `tests/unit/server/services/test_education_book_activity.py`。
- Create: `tests/integration/test_education_book_timing.py`。
- Test: `tests/integration/test_education_book_activity_stream.py`。

1. 写失败回归：准确服务边界、同 segment 重复结束不重复累计、恢复另段、异常/取消耗时、不同 queued_at 重试、未知不为零、已提交事实不被计时故障改为失败。
2. Run: `uv run pytest tests/unit/server/services/test_education_book_timing.py tests/unit/server/services/test_education_book_activity.py -q`。测试注入 wall/monotonic，不以真实 sleep 编写抖动断言。
3. `book_phase` 继续保留原日志，增加教育局部 phase recorder；source、sandbox、staging、workflow 实际开始/结束、finalization 记录 segment。包装托管 workflow，普通 PTC middleware/LLM 不引入教育统计规则。
4. 提交成功事实、来源 ready/终态与必要边界同事务或可恢复地关联；非关键 duration 写失败返回 partial/unavailable，不凭相减补齐。跨进程来源恢复和验收等待用独立窗口，不复用 monotonic 原点。
5. 固定准备总资源数/verified 数快照，成功进度至多每秒合并1条服务事件；预算满仍更新准确快照。保留 2KiB/512字符和现有子预算；invalid/stale callback 不改计数。Redis 失效由 PG 补齐。
6. GET job 提供当前 round 计时和 server_now；新 `GET /book-jobs/:jobId/statistics` 提供紧凑批量汇总与游标分页 attempt 明细。本轮中位/最长耗时样本只取本轮成功 material attempt，N/M 仍含保留的上轮成功项，两者不混称。只返回公共区间和数值，不查询 LangSmith；检查跨家庭/学生拒绝。
7. 用同一确定性时钟/串行结构样本对比日志、快照、SSE、terminal 时间，检查父子阶段不双算；执行相关隔离集成，更新 CHANGELOG、提交。

## Task A5：工作台整页时间线与共用计时组件

状态：实现与组件/mock回归已完成。全教育146 passed，连同图书馆入口165 passed；pnpm build、改动TS/TSX ESLint和diff检查通过，首屏357.9kB gzip。核心受理/路由/共享时钟回归先失败再通过；补齐恢复累计片段、partial缺口、默认panel持久化、N/N来源清单状态、quote布局fence、终态历史按需订阅、阅读位置及记录分页。自审补回查看历史job时current_job的5秒工作台快照巡检，当前任务结束即停，不新增SSE。202跳转实际由DocumentsPage/DocumentDetailPage拥有，按证据小改两处，另提取共享useBookLiveActivity保持布局切换状态。保留既有工具告警；父代理两阶段复核、真实浏览器/亮暗/移动端与端到端验收待A6，开发库未迁移、未启新服务、未调用付费模型，不将mock测试称为真实工作流通过。

审查修正：补齐教材/job归属、服务阶段状态与PTC节点下的Agent上报、批量可靠终态/旧版可读、首份提交与目录缓存竞态；最近执行项计时缺失不借用前项。根据浏览器反馈调整窄屏目录抽屉、标题分行及超长标题边界，补回紧凑诊断分页。教育155 passed、改动ESLint/build/diff检查通过，首屏358.0kB gzip；独立复审及A6浏览器、真实PG/MinIO与HTTP验收继续由主任务记录，不宣称付费模型通过。

复审补测：首份成功而下一份queued时，非终态当前项优先queued，服务节点保持等待且无attempt不显示前项计时；terminal才选择最近执行项。initial_queue文案按structure/material/supplementary区分来源等待与执行等待。三项新增回归先失败后通过，相关47 passed及改动ESLint/build/diff检查通过；全量与端到端验收由主任务汇总。

**Files:**
- Create: `web/src/pages/Education/components/BookProcessingView.tsx`。
- Create: `web/src/pages/Education/components/BookTimingSummary.tsx`。
- Create: `web/src/pages/Education/components/bookTimingProjection.ts`。
- Create: `web/src/pages/Education/components/useBookElapsedTime.ts`。
- Modify: `web/src/pages/Education/TextbookWorkbenchPage.tsx`、`web/src/pages/Education/TextbookWorkbenchPage.css`。
- Modify: `web/src/pages/Education/components/BookActivityPanel.tsx`、`web/src/pages/Education/components/bookActivityProjection.ts`、`web/src/pages/Education/components/BookLiveActivity.tsx`、`web/src/pages/Education/components/BookSourceDialog.tsx`。
- Modify: `web/src/pages/Education/api.ts`、`web/src/pages/Education/queries.ts`、`web/src/pages/Education/types.ts`、`web/src/lib/queryKeys.ts`。
- Create: `web/src/pages/Education/__tests__/BookProcessingView.test.tsx`、`web/src/pages/Education/__tests__/BookTimingSummary.test.tsx`。
- Modify: `web/src/pages/Education/__tests__/TextbookWorkbenchPage.test.tsx`、`web/src/pages/Education/__tests__/BookSourceDialog.test.tsx`、`web/src/pages/Education/__tests__/BookActivityPanel.test.tsx`、`web/src/pages/Education/__tests__/BookActivityQueries.test.tsx`。

1. 先写失败测试：202 后进入处理视图、已完成复用进入阅读、source pending 正确文案、panel=processing 刷新恢复、退出保留 kp/view、没有第二 SSE、Agent动作不自动打完成勾、终态不强制跳转。
2. 在 web Run: `pnpm exec vitest run src/pages/Education/__tests__/BookProcessingView.test.tsx src/pages/Education/__tests__/BookTimingSummary.test.tsx src/pages/Education/__tests__/TextbookWorkbenchPage.test.tsx src/pages/Education/__tests__/BookSourceDialog.test.tsx`。
3. 建立纯 timing/activity projection 供整页与面板共用；格式遵循 locale formatter，时钟采用 server_now + performance.now 的单页1秒tick。后台暂停，断线显示最后确认截止值，重新连通校时；终态停止，旧任务未记录，retry 切换新 attempt 不串计时。
4. 在原路由增加 panel=processing，与 activity/kp/node/view 共存；只切换渲染布局，保留导航和阅读位置。结构没有目录时默认整页；ready书正常阅读，生成后可返回阅读，成功批量部分可立即打开讲义。
5. 纵向 timeline、有限服务里程碑、动作子记录、当前知识点和安全计数；计时摘要默认紧凑，详细 phase 和诊断可展开。工具名只在诊断，准备状态不冒称“解析文档”。使用现有 Loader、Lucide、主题 token，正文长标题换行。
6. 最近活动分清工具/存储确认/租约健康；名句仍小池按真实新活动触发，5秒冷却不排队，准备阶段可显示，回放/断线/后台/终态不刷新。计时不触发 quote API。
7. 大批次已完成组折叠/分页，历史只按需取 statistics；默认不把所有1000条诊断挂到整页，保持旧事件/缓存上限。用户向上阅读不抢滚动，增加显式跟随最新。
8. 重跑全教育前端测试、`pnpm build`、改动 ESLint。更新 CHANGELOG、提交；无实际服务迁移授权前不宣称真实工作流可用。

## Task A6：故障/权限/计时一致性与真实界面验收

**Files:**
- Modify: `web/e2e/education-textbook-workbench.spec.js`。
- Create: `web/e2e/education-textbook-processing.spec.js`。
- Test: 上述 PG/存储/活动/timing 集成。
- Create: `docs/plans/2026-10-04-textbook-async-preparation-timeline-results.md`（只有实际验证后写结果）。

1. 专用 fixture/mock 验证慢资源复制下 HTTP 不阻塞、verified计数单调、N/N后仍等待manifest、full timeline/compact/read共用数据；不用真实模型伪造精确每动作时长。
2. 按真实存储/PG 故障矩阵串行验收：source上传响应丢失、ready COMMIT ACK丢失、准备SIGKILL、双worker接管、旧回调、取消上传、budget满、Redis停用、活动 unavailable、metrics partial，原文和图书馆来源不丢失。
3. 两种主题与375/768/1440宽度截图；检查canvas/DOM非空、页面无横溢、长标题、键盘焦点、44px操作区、屏幕阅读器、reduced-motion；计时秒变不导致布局抖动，不自动抢滚动。
4. 确认工作tree/PID/数据库与MinIO目标后，按批准发布安排一次性升级关联 schema/后端/前端，停旧worker避免混跑。若开发库仍有活跃任务，先等待收尾，不在其准备/提交中替换契约。
5. 后端8000、前端 `pnpm dev --host 0.0.0.0 --port 5177`，检查本机/LAN。用户授权后专用真实结构任务+单讲义+小批次；确认 UI 分段与PG/log一致、旧讲义重做失败仍可读。禁止自动删除现有SB3、付费重跑或复制家长凭据。
6. 全量回归：`uv run pytest tests/unit -q`，隔离教材集成，web `pnpm test`/`pnpm build`，`make lint`、改动检查和 `git diff --check`。浏览器mock和真实结果分别记录；未测/skip/既有失败如实列出。
7. 验收结果记录受理延迟、准备规模/耗时、PTC执行、验收提交、资源恢复、模型质量未验收边界；更新 CHANGELOG、提交，不把性能/界面通过等同于结构语义质量通过。

## Task A7：收口、关联文档与回退说明

**Files:** 本设计/计划、结果记录、`docs/plans/2026-09-30-more-to-skills-implementation.md` 与 CHANGELOG。

1. 核对每项要求与验证证据，完成项逐 task 更新，不一次性预勾。
2. 原计划只补独立增量链接，不改变原 Task8 日期或完成依据；不编辑用户未提交的业务动作细则。界面整页与来源提前登记是本设计明确的增量覆盖，禁止两份说明同时说“永远只侧栏/创建前必须全部复制”。
3. 回退：新UI可切回紧凑阅读视图，但老后端不能读取pending来源；必须先暂停新受理、等待/明确收尾活跃准备任务再回退。不能直接downgrade删除pending/attempt计时记录。迁移回退检查真实数据并拒绝不满足条件的降级，不以清空教材代替兼容。
4. 留下下一阶段独立议题：SB3语义切分质量、LangSmith上传完整性、长期负载；本轮不捆绑模型参数或Skill改动。最终仅在真实证据齐全后标记该增量完成。

## 审阅确认点

1. 是否采用原结构 item 的准备子阶段，而非新增队列/加工页？
2. 是否接受生成后进入整页时间线，但可随时返回阅读，完成后手动进入结果、不强制跳转？
3. 首版统计是否限定可靠的服务区间，Agent业务动作只显示时间戳，纯LLM耗时/tokens另行处理？
4. 首版中断准备以新 attempt 重新复制，已ready来源保留，是否满足恢复预期？
