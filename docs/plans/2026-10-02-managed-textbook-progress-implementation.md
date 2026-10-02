# Managed Textbook Semantic Progress Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 向教材托管 PTC Agent 注入一个受限的语义进度工具，并在教材工作台中组合数据库真值、Agent 阶段和有界工具明细，形成可恢复且不误报完成状态的活动时间线。

**Architecture:** 新工具只向 LangGraph custom stream 发送无业务身份的 `report_progress` artifact；教育 managed task contract 声明每类 item 可用的有限阶段，`BookActivityObserver` 绑定 attempt 身份、校验阶段并映射中文说明。job/item 快照继续作为状态和计数真值，前端主时间线合并快照与活动，通用工具事件默认折叠。

**Tech Stack:** Python 3.13、LangChain tools、LangGraph custom stream、FastAPI、async psycopg、PostgreSQL、Redis、React 19、TypeScript、React Query、Vitest、Playwright。

---

## 0. 执行前提

- 依据：[详细设计](2026-10-02-managed-textbook-progress-design.md)、[总设计](2026-09-30-more-to-skills-design.md)、[总实施计划](2026-09-30-more-to-skills-implementation.md)。
- 在 `feature/more-to-skills-textbook-refactor` worktree 中实施；Task 4 提交 `bb29d347` 已完成，本计划作为 Task 4A，在 Task 5 工作台活动面板前执行。
- 不修改 `plugins/langalpha_local/skills/more-to-skills/`；不恢复旧 `.langalpha/progress.jsonl`、progress helper 或旧教育进度表。
- 不向当前开发数据库应用迁移。本功能不需要 schema migration；数据库集成继续使用 `TEST_DB_NAME=langalpha_test`。
- 每个任务先写失败测试，再写最小实现；每个任务通过聚焦检查后更新 `CHANGELOG.md` 并原子提交。

## Task 1：建立无业务身份的 PTC 进度工具

**Files:**
- Create: `src/ptc_agent/agent/tools/report_progress.py`
- Create: `tests/unit/ptc_agent/agent/tools/test_report_progress.py`
- Modify: `src/ptc_agent/agent/tools/__init__.py`
- Modify: `src/ptc_agent/agent/managed_execution.py`
- Modify: `src/ptc_agent/agent/agent.py:159-212`
- Modify: `tests/unit/ptc_agent/test_managed_textbook_execution_policy.py`

**Step 1: Write the failing tool tests**

覆盖以下行为：

```python
@pytest.mark.asyncio
async def test_report_progress_emits_only_a_bounded_stage(monkeypatch):
    emitted = []
    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: emitted.append)
    tool = create_report_progress_tool()

    result = await tool.ainvoke({"stage": "structure_organizing"})

    assert result == "Progress reported."
    assert emitted == [{
        "artifact_type": "report_progress",
        "artifact_id": "structure_organizing",
        "status": "running",
        "payload": {"stage": "structure_organizing"},
    }]


@pytest.mark.asyncio
async def test_report_progress_rejects_free_text_and_continues_without_writer(...):
    ...
```

拒绝空值、超过 64 字符、空格、连字符、路径字符和非 `^[a-z][a-z0-9_]*$` 的 stage。`get_stream_writer()` 或 writer 调用失败时返回固定的 `Progress reporting unavailable; continue the task.`，不得抛出异常终止 Agent。

**Step 2: Run the tests and confirm failure**

Run:

```bash
uv run pytest tests/unit/ptc_agent/agent/tools/test_report_progress.py -q
```

Expected: FAIL because `create_report_progress_tool` does not exist.

**Step 3: Implement the minimal stream tool**

实现 factory，工具只接收 `stage`，不接收 message、job/item/attempt ID、计数、路径或 metadata。使用 `get_stream_writer()` 发出设计中的 artifact；所有 writer 异常只记 debug 日志并返回固定继续说明。

不要在工具中导入 education 模块或数据库。阶段的业务白名单由 observer 处理，使 PTC 工具保持通用、小型和无状态。

**Step 4: Add an explicit managed-policy capability**

在 `ManagedExecutionPolicy` 增加默认关闭的字段：

```python
enable_progress_reporting: bool = False
```

`education_book_policy()` 显式设为 `True`。`_build_managed_policy_tools()` 仅在该字段开启时调用 `create_report_progress_tool()`；普通 `PTCAgent.create_agent()` 的工具集合不变。

扩充 policy 测试：

- 教材 policy 开启进度能力；
- 工具面包含且只包含一个 `report_progress`；
- 手工构造默认 policy 时不包含该工具；
- MCP、Vault、subagent 和宿主目录限制不变。

**Step 5: Run focused checks**

Run:

```bash
uv run pytest tests/unit/ptc_agent/agent/tools/test_report_progress.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py -q
uv run ruff check src/ptc_agent/agent/tools/report_progress.py src/ptc_agent/agent/agent.py src/ptc_agent/agent/managed_execution.py tests/unit/ptc_agent/agent/tools/test_report_progress.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py
```

Expected: all tests pass and Ruff reports no errors.

**Step 6: Update changelog and commit**

```bash
git add CHANGELOG.md src/ptc_agent/agent/tools/report_progress.py src/ptc_agent/agent/tools/__init__.py src/ptc_agent/agent/managed_execution.py src/ptc_agent/agent/agent.py tests/unit/ptc_agent/agent/tools/test_report_progress.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py
git commit -m "feat(ptc): add managed progress reporting tool"
```

## Task 2：定义教育阶段词表和 managed task contract

**Files:**
- Create: `src/server/services/education_book_progress.py`
- Create: `tests/unit/server/services/test_education_book_progress.py`
- Modify: `src/server/services/education_book_jobs.py:197-275,428-449`
- Modify: `tests/unit/server/services/test_education_book_jobs.py`

**Step 1: Write failing stage-contract tests**

为 `structure`、`material` 和 `supplementary` item 构造最小输入，断言：

```python
assert progress_contract(structure_item) == {
    "tool": "report_progress",
    "allowed_stages": [
        "structure_reading",
        "structure_organizing",
        "structure_splitting",
        "structure_validating",
    ],
}
assert progress_message("structure_organizing", item_kind="structure") == (
    "正在整理章节层级"
)
assert progress_message("material_writing", item_kind="structure") is None
```

再断言 `build_execution_task()` 把相应 contract 写入 `task.json`，但不写 message、job identity 或计数；`managed_item_prompt()` 明确要求读取 `progress.allowed_stages`、只在进入真实阶段时调用一次、漏报不阻断任务。

**Step 2: Run and confirm failure**

```bash
uv run pytest tests/unit/server/services/test_education_book_progress.py tests/unit/server/services/test_education_book_jobs.py -q
```

Expected: new module/functions and task progress contract are absent.

**Step 3: Implement the fixed catalog**

在 `education_book_progress.py` 定义不可变 mapping：

```python
STAGE_MESSAGES_BY_ITEM_KIND = {
    "structure": {
        "structure_reading": "正在阅读教材结构线索",
        "structure_organizing": "正在整理章节层级",
        "structure_splitting": "正在切分知识点",
        "structure_validating": "正在校验教材结构",
    },
    "material": {
        "material_reading": "正在阅读知识点原文",
        "material_organizing": "正在组织讲义内容",
        "material_writing": "正在撰写讲义",
        "material_validating": "正在校验讲义产物",
    },
    "supplementary": {
        "supplementary_reading": "正在汇总全书讲义",
        "supplementary_organizing": "正在整理全书附加材料",
        "supplementary_validating": "正在校验附加材料",
    },
}
```

提供只读查询函数，不让调用者直接修改全局 mapping。`build_execution_task()` 只写当前 item 的阶段列表；prompt 不复制中文文案，避免模型把自由文本当协议。

**Step 4: Run focused tests and lint**

```bash
uv run pytest tests/unit/server/services/test_education_book_progress.py tests/unit/server/services/test_education_book_jobs.py -q
uv run ruff check src/server/services/education_book_progress.py src/server/services/education_book_jobs.py tests/unit/server/services/test_education_book_progress.py tests/unit/server/services/test_education_book_jobs.py
```

Expected: all pass.

**Step 5: Update changelog and commit**

```bash
git add CHANGELOG.md src/server/services/education_book_progress.py src/server/services/education_book_jobs.py tests/unit/server/services/test_education_book_progress.py tests/unit/server/services/test_education_book_jobs.py
git commit -m "feat(education): define managed textbook progress stages"
```

## Task 3：将受限阶段投影到有界活动账本

**Files:**
- Modify: `src/server/services/education_book_activity.py:54-273`
- Modify: `src/server/services/education_book_jobs.py:762-773`
- Modify: `tests/unit/server/services/test_education_book_activity.py`
- Modify: `tests/unit/server/services/test_education_book_jobs.py`
- Modify: `tests/integration/test_education_book_activity_stream.py`

**Step 1: Replace the permissive progress test with failing whitelist tests**

新增并调整测试，要求：

- `BookActivityObserver` 构造时必须接收 `item_kind`；
- `structure_organizing` 在 structure item 中写为服务端中文 message；
- 相同 stage 一秒内合并，不同 stage 可以立即写入；
- material stage 不能进入 structure item；
- 只有 `payload.message`、没有合法 `payload.stage` 的旧自由文案被忽略；
- 未知 stage 被忽略且不消耗活动预算；
- attempt fence、预算耗尽和 `activity_status=unavailable` 行为保持不变。

**Step 2: Add failing tests for duplicate tool noise**

一次 `report_progress` 调用会同时产生 `tool_calls`、artifact 和 `tool_call_result`。测试必须断言公开活动只保留 artifact 映射后的业务阶段，不出现：

```text
Running report_progress
Finished report_progress
```

observer 在收到该工具开始时记录被抑制的 `tool_call_id`，结果事件按 ID 忽略；其他 Read/Bash 工具仍正常投影。

**Step 3: Run and confirm failure**

```bash
uv run pytest tests/unit/server/services/test_education_book_activity.py tests/unit/server/services/test_education_book_jobs.py -q
```

Expected: current observer still trusts free `message` and emits progress-tool noise.

**Step 4: Implement strict projection**

- 将当前 `message = payload.get("message")` 改为 `stage` 白名单查询；
- metadata 只保存 `{"stage": stage}`；
- artifact ID 由工具固定为 stage，observer 不接受模型自定义 event key；
- `_progress_at` 继续按 stage 节流；
- `launch_book_item()` 用 `item["kind"]` 构建 observer；
- 隐藏 progress 工具自己的 start/result 通用事件。

不要让无效阶段触发 `_disable_details()`；只有真实数据库写入失败才将 activity 标记 unavailable。

**Step 5: Prove PostgreSQL recovery behavior**

扩充集成测试：合法阶段落入 `education_book_activity_events`，数据库只保存服务端中文 message 和 stage；断线后 `after_seq` 能补齐；非法阶段不产生 seq；预算统计和终态豁免不变。

Run:

```bash
TEST_DB_NAME=langalpha_test uv run pytest tests/integration/test_education_book_activity_stream.py -q
```

Expected: all pass without applying migration 082 to the development database.

**Step 6: Run focused regression and commit**

```bash
uv run pytest tests/unit/server/services/test_education_book_activity.py tests/unit/server/services/test_education_book_jobs.py tests/unit/server/services/runs/test_sse_producer.py -q
uv run ruff check src/server/services/education_book_activity.py src/server/services/education_book_jobs.py tests/unit/server/services/test_education_book_activity.py tests/unit/server/services/test_education_book_jobs.py tests/integration/test_education_book_activity_stream.py
```

```bash
git add CHANGELOG.md src/server/services/education_book_activity.py src/server/services/education_book_jobs.py tests/unit/server/services/test_education_book_activity.py tests/unit/server/services/test_education_book_jobs.py tests/integration/test_education_book_activity_stream.py
git commit -m "feat(education): project managed textbook progress stages"
```

## Task 4：冻结工作台可恢复活动 API 的真值字段

**Files:**
- Modify: `src/server/app/education/book_models.py:194-231`
- Rewrite as part of the new facade: `src/server/app/education/textbooks.py`
- Modify: `tests/unit/server/app/education/test_book_models.py`
- Modify: `tests/unit/server/app/education/test_textbooks.py`
- Modify: `tests/integration/test_education_book_activity_stream.py`

**Step 1: Write failing DTO tests**

`BookJobItemResponse` 必须返回 `kind`，使前端能区分 material 与 supplementary。`BookActivityPageResponse` 必须完整表达 repository 已返回的快照：

```python
class BookActivityPageResponse(_StrictModel):
    job_id: str
    status: BookJobStatus
    events: list[BookActivityEventResponse]
    high_water_seq: int
    activity_status: BookActivityStatus
    cursor_expired: bool
    has_more: bool
```

测试 supplementary 不进入讲义 N/M 计数；structure item 不产生虚假知识点分母。

**Step 2: Add failing route/SSE tests**

为冻结契约 `GET /api/v1/education/book-jobs/{job_id}/events?after_seq=N` 添加测试：

- 非家长/跨家庭返回 403 或 404，不泄露 job；
- 首帧是 PG 快照；
- 事件按 seq 严格递增；
- `has_more` 时连续补页，不等待 Redis；
- `cursor_expired` 要求客户端刷新 job 快照；
- `activity_status` 变化即使没有新 event 也发帧；
- job 终态且游标追上 high-water 后结束。

**Step 3: Implement the route around `BookActivityService.pages()`**

路由只做权限绑定、SSE framing 和断连取消；不要复制 activity service 的 Redis/PG 循环。每个 data payload 使用 `BookActivityPageResponse` 验证，不回传内部 `budget_class` 或 `activity_bytes`。

**Step 4: Run API and integration tests**

```bash
uv run pytest tests/unit/server/app/education/test_book_models.py tests/unit/server/app/education/test_textbooks.py tests/integration/test_education_book_activity_stream.py -q
```

Expected: all pass.

**Step 5: Update changelog and commit**

```bash
git add CHANGELOG.md src/server/app/education/book_models.py src/server/app/education/textbooks.py tests/unit/server/app/education/test_book_models.py tests/unit/server/app/education/test_textbooks.py tests/integration/test_education_book_activity_stream.py
git commit -m "feat(education): expose recoverable textbook activity stream"
```

## Task 5：在新工作台实现分层活动时间线

**Files:**
- Create: `web/src/pages/Education/components/BookActivityPanel.tsx`
- Create: `web/src/pages/Education/components/BookActivityPanel.css` only if the workbench stylesheet cannot express the layout cleanly
- Create: `web/src/pages/Education/__tests__/BookActivityPanel.test.tsx`
- Modify/Create with overall Task 5: `web/src/pages/Education/TextbookWorkbenchPage.tsx`
- Rewrite with overall Task 5: `web/src/pages/Education/api.ts`
- Rewrite with overall Task 5: `web/src/pages/Education/queries.ts`
- Rewrite with overall Task 5: `web/src/pages/Education/types.ts`
- Modify: `web/src/lib/queryKeys.ts`
- Modify: relevant locale files under `web/src/locales/`

**Step 1: Write failing projection tests before rendering**

把纯数据投影保持在组件旁的可测试函数中。给定 job/items/events，断言：

- `material` 成功数为讲义完成数，`supplementary` 不进入 N/M；
- 当前 item 是 running item，不从最后一条 progress 猜测；
- 当前语义阶段取该 item 最新合法 progress event；
- 服务端终态按 item/job 状态渲染，不使用 Agent message 判成功；
- tool events 进入折叠明细，主线不重复显示；
- `activity_status=unavailable` 显示“活动暂不可用”，任务状态仍来自 job；
- structure 运行中不显示知识点百分比。

**Step 2: Write failing interaction tests**

覆盖：

- 活动面板默认关闭，`?activity=<job-id>` 打开；
- 展开/收起工具明细不改变 URL 历史或正文滚动；
- SSE 断开显示“正在重连”，不显示失败；
- 重新连接使用最后已确认 `high_water_seq`；
- `cursor_expired` 先刷新 job/workbench 快照，再从新游标订阅；
- 页面后台恢复后重新获取快照；
- 375px 下活动面板不覆盖取消按钮、正文或目录抽屉。

**Step 3: Implement bounded SSE consumption**

在 `api.ts` 提供一个可取消的 stream reader，按 SSE `id/event/data` 解析 page snapshot。React Query 保存 job/workbench 真值；活动事件按 `seq` 去重并限制为服务端允许的窗口，不建立每 KP 的 polling。

Redis/SSE 暂时不可用时采用有限退避并重新读取 job snapshot。浏览器端不能自行把断线、超时或 `activity_status=unavailable` 改写为 job failed。

**Step 4: Implement the visual hierarchy**

主面板只显示：

1. 已完成的服务端里程碑；
2. 当前 job/item 和准确的材料计数；
3. 当前 item 最新语义阶段；
4. 失败、取消和 activity unavailable 的明确状态。

Read/Bash/ExecuteCode 等工具活动放在同 item 的“运行明细”折叠区。使用 Lucide 状态图标；当前行使用稳定高度和 spinner，完成行使用 check，失败行使用 alert。不要复刻旧四阶段 stepper，也不要显示 OCR 或“学习状态分析”等当前流程没有执行的阶段。

**Step 5: Run frontend tests**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/BookActivityPanel.test.tsx src/pages/Education/__tests__/TextbookWorkbenchPage.test.tsx
pnpm typecheck
pnpm build
```

Expected: tests, typecheck, Vite build and critical-path check pass.

**Step 6: Browser verification**

启动后端 `8000` 和前端 `0.0.0.0:5177`，使用桌面和 375px 视口检查：

- structure 运行、成功、失败；
- 单条材料、批量部分成功、supplementary；
- 活动折叠、取消、断线重连、后台标签恢复；
- 长知识点标题和 512 字符活动不会溢出或遮挡按钮；
- LAN 可访问 `http://<host>:5177`。

**Step 7: Update changelog and commit**

```bash
git add CHANGELOG.md web/src/pages/Education web/src/lib/queryKeys.ts web/src/locales
git commit -m "feat(web): add textbook activity timeline"
```

## Task 6：全量回归与文档收口

**Files:**
- Modify: `CHANGELOG.md`
- Update if implementation diverged: `docs/plans/2026-10-02-managed-textbook-progress-design.md`
- Update: `docs/plans/2026-09-30-more-to-skills-cleanup-audit.md` only if any old progress file survives or a new cleanup dependency appears

**Step 1: Run backend focused suites**

```bash
uv run pytest tests/unit/ptc_agent/agent/tools/test_report_progress.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py tests/unit/server/services/test_education_book_progress.py tests/unit/server/services/test_education_book_activity.py tests/unit/server/services/test_education_book_jobs.py tests/unit/server/services/runs/test_sse_producer.py tests/unit/server/app/education/test_book_models.py tests/unit/server/app/education/test_textbooks.py -q
TEST_DB_NAME=langalpha_test uv run pytest tests/integration/test_education_book_activity_stream.py tests/integration/test_education_book_jobs_db.py -q
```

**Step 2: Run broad static and unit verification**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest tests/unit -q
cd web && pnpm lint && pnpm typecheck && pnpm build
git diff --check
```

Expected: all commands pass. Record exact counts in `CHANGELOG.md`; do not claim integration coverage if PostgreSQL dependencies were unavailable.

**Step 3: Verify non-regression boundaries**

- 普通 PTC/Flash 工具清单不含教材进度工具；
- `more-to-skills` 文件摘要没有变化；
- 没有新增 progress 表、JSONL 或 Redis durable ledger；
- 没有输出 reasoning、工具参数/结果、路径或教材正文；
- 不修改、删除或重建现有 Docker containers、volumes、networks；
- 未向开发数据库应用 migration 082。

**Step 4: Request code review and commit final corrections**

Use `superpowers:requesting-code-review`, address verified findings with `superpowers:receiving-code-review`, rerun affected checks, then make an atomic final commit if corrections were required.
