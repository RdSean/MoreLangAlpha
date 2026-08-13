# 家庭教材 PTC 教学包实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让家长在已提取的冻结教材内容上启动可恢复的受管 PTC 长程任务，使用 `book-to-skill` 与 `the-knowledge-guy` 生成、审阅并发布面向中国学生的教学包，而不暴露对象存储或普通 PTC 工作区边界。

**Architecture:** 内容提取版本继续由 `education_textbook_versions` 表示；教学包成为内容版本的独立不可变子版本，含自己的章节材料和题集。教育服务创建隐藏、受限的 PTC workspace/thread，向 sandbox 的固定 `inputs/` 注入已授权内容，复用该隐藏 thread 的根运行账本、checkpoint、SSE、取消与恢复机制，再从固定 `outputs/` 回收并校验候选产物。MinIO 只有教育服务访问，正式资产均写入 `education/`。

**Tech Stack:** Python 3.13+, FastAPI, async psycopg3, Alembic, PostgreSQL, Redis SSE, LangGraph/PTC, private MinIO/S3-compatible storage, React 19, React Query, TypeScript, Vitest, Playwright.

---

### Task 1: 建立教学包版本与受管运行的持久化模型

**Files:**
- Create: `migrations/versions/030_add_education_teaching_packages.py`
- Modify: `src/server/database/education_textbooks.py`
- Modify: `src/server/app/education/models.py`
- Test: `tests/unit/server/database/test_education_teaching_packages.py`

**Step 1: 写失败的数据库契约测试**

覆盖以下不可回退的 SQL 契约：

```python
async def test_queue_teaching_package_freezes_a_reviewable_content_version(...):
    package = await queue_teaching_package(
        parent_user_id="parent-1", content_version_id="version-1"
    )
    assert package["status"] == "queued"
    assert package["content_version_id"] == "version-1"

async def test_package_attempt_has_one_root_ptc_run_and_linear_retry_chain(...):
    assert "UNIQUE (root_run_id)" in attempt_insert_sql
    assert "previous_attempt_id" in attempt_insert_sql

async def test_parent_detail_joins_only_same_household_teaching_packages(...):
    assert "memberships.role = 'parent'" in detail_sql
    assert "storage_key" not in selected_columns
```

**Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/unit/server/database/test_education_teaching_packages.py -q`

Expected: FAIL，因为教学包的表和查询尚不存在。

**Step 3: 编写 Alembic 迁移**

创建如下最小关系模型，所有对象以 UUID 外键保护：

```sql
CREATE TABLE education_teaching_packages (
    teaching_package_id UUID PRIMARY KEY,
    content_version_id UUID NOT NULL REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    status VARCHAR(32) NOT NULL CHECK (status IN ('queued','preparing','building_skill','generating_teaching','validating','review','failed','cancelled')),
    audience VARCHAR(64) NOT NULL DEFAULT 'zh-CN-students',
    input_manifest_sha256 VARCHAR(64) NOT NULL,
    book_to_skill_sha256 VARCHAR(64) NOT NULL,
    knowledge_guy_sha256 VARCHAR(64) NOT NULL,
    adapter_prompt_sha256 VARCHAR(64) NOT NULL,
    bundle_prefix TEXT,
    error_code VARCHAR(64),
    error_message TEXT,
    created_by_user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    UNIQUE (content_version_id, sequence)
);

CREATE TABLE education_teaching_jobs (... teaching_package_id UUID UNIQUE ...);
CREATE TABLE education_teaching_attempts (... job_id UUID ... previous_attempt_id UUID ... root_run_id UUID UNIQUE ...);
CREATE TABLE education_teaching_events (... attempt_id UUID ... sequence INTEGER ... phase VARCHAR(32) ... summary TEXT ... UNIQUE (attempt_id, sequence));
CREATE TABLE education_teaching_package_chapters (... teaching_package_id UUID ... content_chapter_id UUID ... teaching_material TEXT ...);
CREATE TABLE education_teaching_package_questions (... package_chapter_id UUID ... options JSONB ... correct_option VARCHAR(32) ...);
```

在 `education_textbook_publications` 添加 `teaching_package_id`。迁移必须先为每个既有内容版本建立 `review` 状态的 `legacy-local-v1` 教学包，将现有 `teaching_material` 和 `education_chapter_questions` 复制到包表，再为既有发布记录填入对应包并将新列设为 `NOT NULL`。不要删除旧字段或旧题表；它们在一次单独的、经验证的数据迁移后才可清理。

为 job、attempt、package 状态和父家庭详情查询增加局部索引；`downgrade()` 必须按依赖反向删除新增外键、表和列，不得删除旧教材数据。

**Step 4: 添加最小数据库函数**

在 `education_textbooks.py` 新增：

```python
async def queue_teaching_package(*, parent_user_id: str, content_version_id: str, hashes: TeachingInputHashes) -> dict[str, Any] | None: ...
async def claim_teaching_job(*, job_id: str) -> dict[str, Any] | None: ...
async def create_teaching_attempt(*, job_id: str, managed_workspace_id: str, managed_thread_id: str) -> dict[str, Any] | None: ...
async def record_teaching_event(*, attempt_id: str, phase: str, summary: str, chapter_id: str | None = None) -> None: ...
async def settle_teaching_attempt(*, attempt_id: str, root_run_id: str, status: str, ...) -> dict[str, Any] | None: ...
```

每个写入都以 package/job 状态和 `attempt_count` 的比较更新保护。`root_run_id` 指向 PTC 根 `conversation_responses`，不创建伪父 Agent 或 `subagent_runs` 行。

**Step 5: 运行数据库测试**

Run: `uv run pytest tests/unit/server/database/test_education_teaching_packages.py tests/unit/server/database/test_education_textbook_jobs.py -q`

Expected: PASS。

**Step 6: 更新变更日志并原子提交**

```bash
git add migrations/versions/030_add_education_teaching_packages.py src/server/database/education_textbooks.py src/server/app/education/models.py tests/unit/server/database/test_education_teaching_packages.py CHANGELOG.md
git commit -m 'feat(education): persist teaching package versions'
```

### Task 2: 将本地 PDF 提取收敛为纯内容版本

**Files:**
- Modify: `src/server/services/education_textbooks.py`
- Modify: `src/server/services/education_textbook_storage.py`
- Modify: `src/server/database/education_textbooks.py`
- Test: `tests/unit/server/services/test_education_textbooks.py`
- Test: `tests/unit/server/database/test_education_textbook_jobs.py`

**Step 1: 写失败的服务测试**

```python
@pytest.mark.asyncio
async def test_local_pdf_processing_persists_content_without_default_teaching_package(monkeypatch):
    completed = await process_textbook_job(job_id="job-1")
    assert completed["status"] == "completed"
    assert write_content_bundle.await_count == 1
    assert "teaching_material" not in completed_package["chapters"][0]

@pytest.mark.asyncio
async def test_content_version_cannot_publish_until_a_reviewed_teaching_package_is_selected(monkeypatch):
    with pytest.raises(TextbookTransitionError, match="teaching package"):
        await publish_version(...)
```

**Step 2: 运行并确认失败**

Run: `uv run pytest tests/unit/server/services/test_education_textbooks.py -q`

Expected: FAIL，当前 `build_local_pdf_package()` 仍生成教学材料和默认题集。

**Step 3: 拆分内容 bundle 写入**

将本地提取器输出限制为章节位置、标题、页码、Markdown 与内容对象键。新增
`write_textbook_content_bundle()`，写入：

```text
education/<household>/<slug>/v<content-sequence>/
  README.md
  manifest.json
  sources/
  chapters/
```

不得在新内容版本路径下写 `teaching/` 或题集。manifest 记录来源哈希、章节哈希、
提取器版本，但不包含 storage key 或 MinIO URL。原 `write_textbook_bundle()` 在迁移
期间只用于旧测试/历史兼容；新工作流不能调用它。

**Step 4: 强制发布选择经过审阅的教学包**

修改 `publish_textbook_version()`：锁定内容版本和目标教学包，确认两者属于同一家庭、
教学包的 `content_version_id` 相同、状态为 `review`，且有完整章节/题集。发布记录
冻结两个 UUID。学生读取查询应从 publication 的教学包章节/题目读取材料，不能再从
可变的内容版本默认字段读取。

**Step 5: 运行聚焦测试**

Run: `uv run pytest tests/unit/server/services/test_education_textbooks.py tests/unit/server/database/test_education_textbook_jobs.py -q`

Expected: PASS。

**Step 6: 更新变更日志并原子提交**

```bash
git add src/server/services/education_textbooks.py src/server/services/education_textbook_storage.py src/server/database/education_textbooks.py tests/unit/server/services/test_education_textbooks.py tests/unit/server/database/test_education_textbook_jobs.py CHANGELOG.md
git commit -m 'refactor(education): separate textbook content from teaching packages'
```

### Task 3: 为两个内置 Skills 增加无交互教材加工模式

**Files:**
- Modify: `skills/book-to-skill/SKILL.md`
- Modify: `skills/the-knowledge-guy/SKILL.md`
- Create: `skills/book-to-skill/reference/managed-textbook-contract.md`
- Create: `skills/the-knowledge-guy/reference/managed-textbook-contract.md`
- Test: `tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py`

**Step 1: 写失败的 Skill 契约测试**

```python
def test_book_to_skill_managed_mode_accepts_only_staged_markdown_manifest():
    assert "--managed-textbook" in book_to_skill_skill_md
    assert "/managed/textbook-job/<job>/inputs/manifest.json" in book_to_skill_skill_md
    assert "AskUserQuestion" not in managed_mode_block

def test_knowledge_guy_managed_mode_writes_only_schema_validated_outputs():
    assert "--managed-textbook" in knowledge_guy_skill_md
    assert "outputs/teaching-package.json" in knowledge_guy_skill_md
    assert "artifacts/" not in managed_mode_block
```

**Step 2: 运行并确认失败**

Run: `uv run pytest tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q`

Expected: FAIL，因为当前 Skills 只支持交互式 PDF/EPUB/HTML artifact 流程。

**Step 3: 增加 `book-to-skill --managed-textbook` 模式**

此模式不接收原 PDF、不读取 MinIO、不询问用户、不运行成本确认。它只读取服务端注入的：

```text
/managed/textbook-job/<job>/inputs/manifest.json
/managed/textbook-job/<job>/inputs/chapters/<position>-<slug>.md
```

它必须在 `/managed/textbook-job/<job>/work/knowledge-skill/` 生成中间知识技能，
并在 `outputs/book-skill-manifest.json` 写一个包含输入 manifest SHA-256、章节清单和
生成版本的机器可读摘要。禁止写 `artifacts/`、`~`、普通 `.agents/skills/` 或读取
未指定路径。

**Step 4: 增加 `the-knowledge-guy --managed-textbook` 模式**

此模式只读取该知识技能和任务 inputs，按章节产生唯一候选文件：

`/managed/textbook-job/<job>/outputs/teaching-package.json`

文件 schema 由 reference 定义。每章必须包含：

```json
{
  "content_chapter_id": "uuid",
  "content_sha256": "64-hex",
  "learning_objectives": ["..."],
  "knowledge_points": ["..."],
  "key_difficulties": ["..."],
  "prerequisites": ["..."],
  "teaching_material": "# ...",
  "questions": [{"position": 1, "prompt": "...", "options": {"A": "...", "B": "..."}, "correct_option": "A", "explanation": "...", "knowledge_point": "..."}]
}
```

它不生成 HTML、不写用户 memory、不启动自由问答、也不调用 web 工具。每一章完成后向
stdout 输出单行 `EDUCATION_PROGRESS` JSON，供受管运行适配器转为持久化事件。

**Step 5: 运行契约测试**

Run: `uv run pytest tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q`

Expected: PASS。

**Step 6: 更新变更日志并原子提交**

```bash
git add skills/book-to-skill/SKILL.md skills/the-knowledge-guy/SKILL.md skills/book-to-skill/reference/managed-textbook-contract.md skills/the-knowledge-guy/reference/managed-textbook-contract.md tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py CHANGELOG.md
git commit -m 'feat(skills): add managed textbook generation modes'
```

### Task 4: 实现受控输入注入、候选输出校验和教学包存储

**Files:**
- Create: `src/server/services/education_teaching_storage.py`
- Create: `src/server/services/education_teaching_validation.py`
- Modify: `src/server/services/education_textbook_storage.py`
- Test: `tests/unit/server/services/test_education_teaching_storage.py`
- Test: `tests/unit/server/services/test_education_teaching_validation.py`

**Step 1: 写失败的输入 staging 与校验测试**

```python
@pytest.mark.asyncio
async def test_stage_teaching_inputs_uploads_only_safe_manifest_and_frozen_chapters(mock_sandbox):
    await stage_teaching_inputs(job, mock_sandbox)
    uploaded_paths = [path for path, _ in mock_sandbox.aupload_files.await_args.args[0]]
    assert all(path.startswith("/managed/textbook-job/job-1/inputs/") for path in uploaded_paths)
    assert all("storage_key" not in body.decode() for _, body in mock_sandbox.aupload_files.await_args.args[0])

def test_rejects_output_missing_a_frozen_chapter_or_with_invalid_answer():
    with pytest.raises(TeachingPackageValidationError):
        validate_teaching_package(output, frozen_input)
```

**Step 2: 运行并确认失败**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_storage.py tests/unit/server/services/test_education_teaching_validation.py -q`

Expected: FAIL，因为 staging 与 schema 校验器尚不存在。

**Step 3: 实现 sandbox 数据搬运**

服务端通过 sandbox runtime 的 `upload_files()` 和 `download_file()` 传输字节，不把
MinIO URL、access key、secret、bucket 名或 storage key 写进 manifest。路径只允许：

```python
def managed_job_root(job_id: str) -> str:
    return f"/managed/textbook-job/{UUID(job_id)}"
```

`stage_teaching_inputs()` 从数据库中已经授权的 `markdown` 读取内容，计算哈希，写
`inputs/manifest.json` 和 `inputs/chapters/`。`download_teaching_output()` 只下载固定
`outputs/teaching-package.json`，拒绝目录枚举、通配符、符号链接和任何调用方提供的
路径。

**Step 4: 实现严格校验与原子归档**

`validate_teaching_package()` 必须要求输入章节一一覆盖、内容哈希匹配、UTF-8、字段
上限、至少一个知识点、题目位置唯一、2--6 个选项且答案在选项中、知识点关联有效。
不得让模型给出的对象键、文件名或 Markdown frontmatter 影响对象路径。

`write_teaching_package_bundle()` 仅在校验后写：

```text
education/<household>/<slug>/v<content-sequence>/teaching/v<package-sequence>/
  README.md
  manifest.json
  chapters/<position>-<slug>-material.md
  chapters/<position>-<slug>-questions.json
```

对象键由服务端构造；任何写失败使 package 保持 `validating`/`failed`，不更新 review
投影或 publication。

**Step 5: 运行测试**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_storage.py tests/unit/server/services/test_education_teaching_validation.py -q`

Expected: PASS。

**Step 6: 更新变更日志并原子提交**

```bash
git add src/server/services/education_teaching_storage.py src/server/services/education_teaching_validation.py src/server/services/education_textbook_storage.py tests/unit/server/services/test_education_teaching_storage.py tests/unit/server/services/test_education_teaching_validation.py CHANGELOG.md
git commit -m 'feat(education): stage and validate teaching package assets'
```

### Task 5: 启动并恢复隐藏的受管 PTC 根运行

**Files:**
- Create: `src/server/services/education_managed_ptc.py`
- Create: `src/server/services/education_teaching_jobs.py`
- Modify: `src/server/services/workspace_manager.py`
- Modify: `src/ptc_agent/agent/agent.py`
- Modify: `src/ptc_agent/agent/graph.py`
- Modify: `src/server/services/education_access.py`
- Test: `tests/unit/server/services/test_education_managed_ptc.py`
- Test: `tests/unit/server/services/test_education_teaching_jobs.py`
- Test: `tests/unit/ptc_agent/test_managed_textbook_execution_policy.py`

**Step 1: 写失败的受管运行测试**

```python
@pytest.mark.asyncio
async def test_launcher_creates_hidden_workspace_thread_then_stages_before_dispatch(monkeypatch):
    run = await launch_teaching_attempt(job_id="job-1")
    assert run["phase"] == "preparing"
    stage.assert_awaited_once_before(dispatch)
    assert dispatch.await_args.kwargs["skill_contexts"] == [
        {"name": "book-to-skill", "instruction": "--managed-textbook ..."},
        {"name": "the-knowledge-guy", "instruction": "--managed-textbook ..."},
    ]

@pytest.mark.asyncio
async def test_cancel_stamps_education_job_before_requesting_root_run_cancel(monkeypatch):
    await cancel_teaching_job(parent_user_id="parent-1", job_id="job-1")
    mark_cancel.assert_awaited_once()
    root_cancel.assert_awaited_once_with(thread_id="thread-1", run_id="run-1")

def test_managed_execution_policy_has_only_staged_files_and_two_builtin_skills():
    assert policy.allowed_skill_names == {"book-to-skill", "the-knowledge-guy"}
    assert not policy.enable_mcp and not policy.enable_web and not policy.enable_vault
```

**Step 2: 运行并确认失败**

Run: `uv run pytest tests/unit/server/services/test_education_managed_ptc.py tests/unit/server/services/test_education_teaching_jobs.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py -q`

Expected: FAIL，当前 PTC 只通过可见聊天运行，且 sandbox 同步所有用户资源。

**Step 3: 定义通用但最小的受管执行策略**

在 PTC graph/agent 边界增加显式 `ManagedExecutionPolicy`，不是教育专用的全局状态：

```python
@dataclass(frozen=True)
class ManagedExecutionPolicy:
    allowed_skill_names: frozenset[str]
    filesystem_root: str
    enable_mcp: bool = False
    enable_web: bool = False
    enable_vault: bool = False
    allow_subagents: bool = True
```

当该 policy 存在时，WorkspaceManager 只同步 allowlist Skill；PTCAgent 只创建
`book-to-skill`/`the-knowledge-guy` 所需的文件、Bash、Task 和 TaskOutput 工具，拒绝
MCP、Vault、web、preview、普通 workspace 持久化和 policy root 外路径。普通 PTC 和
Flash 调用的默认行为必须无变化。

**Step 4: 创建和隐藏受管 workspace/thread**

`education_managed_ptc.py` 使用现有 `WorkspaceManager` 创建父账户拥有的 PTC workspace，
但 config/metadata 必须标记：

```python
{"managed_execution": {"kind": "education_teaching", "job_id": str(job_id)}}
```

创建一个 `platform='education'` 的 PTC thread，metadata 同样关联 job。普通 workspace
列表、workspace 文件 API、thread 详情/消息/共享 API 必须拒绝这类 managed resource；
教育服务通过内部 Python 接口而非用户 HTTP 接口操作它。其他现有学生 Flash learning
thread 的访问保护不得回归。

**Step 5: 复用根运行生命周期，不复制聊天执行器**

抽取或封装当前 `astream_ptc_workflow()` 的内部受管启动入口，使它仍调用既有：

- 根运行 START/finalize 账本；
- `LocalRunExecutor`；
- checkpoint writer guard；
- Redis per-run SSE；
- 取消和 recovery scanner。

入口由 `education_teaching_jobs.launch_teaching_attempt()` 调用，固定 prompt、固定
`skill_contexts` 和 `ManagedExecutionPolicy`。它在根运行已持久化并可 reconnect 后才返回
`root_run_id`；每个运行/工具/Skill 阶段事件通过受控解析持久化到
`education_teaching_events`。不可把用户的 `ChatRequest`、thread ID、技能名称或 prompt
暴露为教育 API 参数。

**Step 6: 完成、失败、取消和恢复**

运行完成后由单一 finalize callback：下载 candidate 输出、校验、归档、写入包章节/题集，
再将 package 变为 `review`。失败保留 root run 失败码和脱敏消息；取消先持久化教育任务
状态，再调用既有根 run cancel。恢复必须创建新 attempt 和新的 root run，记录上一个
attempt，使用既有 checkpoint；若 sandbox 已不可用，则重建受管 sandbox、重新 stage 同一
冻结 input 后恢复到最后已验证章节。

**Step 7: 运行测试**

Run: `uv run pytest tests/unit/server/services/test_education_managed_ptc.py tests/unit/server/services/test_education_teaching_jobs.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py tests/unit/server/app/test_education_learning_thread_protection.py -q`

Expected: PASS。

**Step 8: 更新变更日志并原子提交**

```bash
git add src/server/services/education_managed_ptc.py src/server/services/education_teaching_jobs.py src/server/services/workspace_manager.py src/ptc_agent/agent/agent.py src/ptc_agent/agent/graph.py src/server/services/education_access.py tests/unit/server/services/test_education_managed_ptc.py tests/unit/server/services/test_education_teaching_jobs.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py CHANGELOG.md
git commit -m 'feat(education): run teaching generation in managed ptc'
```

### Task 6: 提供家长安全任务投影与控制 API

**Files:**
- Modify: `src/server/app/education/textbooks.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/services/education_textbooks.py`
- Modify: `src/server/services/education_teaching_jobs.py`
- Test: `tests/unit/server/app/education/test_textbooks.py`
- Test: `tests/unit/server/services/test_education_teaching_jobs.py`

**Step 1: 写失败的 API 测试**

```python
async def test_parent_creates_teaching_package_for_own_reviewed_content(client):
    response = await client.post("/api/v1/education/textbook-versions/<id>/teaching-packages")
    assert response.status_code == 202
    assert response.json()["status"] == "queued"

async def test_student_cannot_read_or_cancel_teaching_job(client):
    assert (await client.get("/api/v1/education/teaching-jobs/<id>")).status_code == 403
    assert (await client.post("/api/v1/education/teaching-jobs/<id>/cancel")).status_code == 403

async def test_safe_run_projection_excludes_paths_credentials_and_object_keys(client):
    response = await client.get("/api/v1/education/teaching-jobs/<id>")
    assert "storage_key" not in response.text
    assert "minio" not in response.text.lower()
    assert "/managed/" not in response.text
```

**Step 2: 运行并确认失败**

Run: `uv run pytest tests/unit/server/app/education/test_textbooks.py -q`

Expected: FAIL，因为教学包路由和安全投影尚不存在。

**Step 3: 添加路由和响应模型**

添加只允许家长调用的端点：

```text
POST /api/v1/education/textbook-versions/{content_version_id}/teaching-packages
GET  /api/v1/education/teaching-jobs/{job_id}
POST /api/v1/education/teaching-jobs/{job_id}/cancel
POST /api/v1/education/teaching-jobs/{job_id}/resume
```

详情响应只包含 package/job ID、产品状态、当前阶段、已完成/总章节数、最近心跳、
可执行 action、脱敏 events、attempt/run ID 和时间戳。实现一个白名单序列化器，
不得转发 PTC 原始 payload。`resume` 只允许 `failed`、`cancelled` 或确认 worker/sandbox
丢失的 attempt，不能覆盖 `review` 或已发布 package。

**Step 4: 扩展教材详情投影**

`GET /textbooks/{id}` 应返回内容版本和其教学包摘要；新内容版本的下一步为
`generate_teaching`，教学包为 review 时才显示发布。已发布历史版本继续通过迁移回填
的 legacy package 正常显示、分配与学生答题。

**Step 5: 运行测试**

Run: `uv run pytest tests/unit/server/app/education/test_textbooks.py tests/unit/server/services/test_education_teaching_jobs.py -q`

Expected: PASS。

**Step 6: 更新变更日志并原子提交**

```bash
git add src/server/app/education/textbooks.py src/server/app/education/models.py src/server/services/education_textbooks.py src/server/services/education_teaching_jobs.py tests/unit/server/app/education/test_textbooks.py tests/unit/server/services/test_education_teaching_jobs.py CHANGELOG.md
git commit -m 'feat(education): expose safe teaching job controls'
```

### Task 7: 在教材详情实现单一教学加工面板和运行抽屉

**Files:**
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/Education/TextbookDetailPage.tsx`
- Create: `web/src/pages/Education/TeachingRunDrawer.tsx`
- Test: `web/src/pages/Education/__tests__/TextbookDetailPage.test.tsx`
- Test: `web/src/pages/Education/__tests__/TeachingRunDrawer.test.tsx`

**Step 1: 写失败的组件测试**

```tsx
it('starts a teaching package only after content extraction is reviewable', async () => {
  render(<TextbookDetailPage />);
  await user.click(screen.getByRole('button', { name: '生成教学包' }));
  expect(startTeaching).toHaveBeenCalledWith('content-version-1');
});

it('projects a managed PTC attempt in the detail drawer without rendering a chat composer', async () => {
  render(<TeachingRunDrawer job={runningJob} />);
  expect(screen.getByText('生成教学材料')).toBeVisible();
  expect(screen.getByText('已完成 2 / 8 章')).toBeVisible();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});

it('does not expose server paths or storage keys in run details', () => {
  render(<TeachingRunDrawer job={unsafeFixture} />);
  expect(screen.queryByText(/storage_key|\/managed\/|minio/i)).not.toBeInTheDocument();
});
```

**Step 2: 运行并确认失败**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/TextbookDetailPage.test.tsx src/pages/Education/__tests__/TeachingRunDrawer.test.tsx`

Expected: FAIL，因为 API types、教学面板和抽屉均不存在。

**Step 3: 添加 API/query 层**

新增教学包创建、job 读取、取消、恢复函数和 React Query mutations。运行中的 job 使用
短轮询安全投影作为 reload/reconnect backstop；若后端提供该 job 对应的授权 SSE URL，
客户端附着 SSE 并在连接中断时回退到查询。不得基于 elapsed time 计算百分比。

**Step 4: 实现主面板和抽屉**

在同一个教材详情页显示以下有限状态：

- 内容版本 review 且没有活动/待审教学包：`生成教学包`；
- queued/preparing/building_skill/generating_teaching/validating：阶段、章节完成数、最近心跳、取消和运行详情；
- failed/cancelled：脱敏原因、继续运行/重新生成；
- package review：教学材料、题集审阅和发布；
- published：现有分配和记录界面。

抽屉使用既有 shadcn `Sheet`/`Dialog` 模式显示阶段时间线、章节进度和尝试链。不要引入
聊天 composer、文件浏览器、原始 PTC HTML artifact 或嵌套 card。

**Step 5: 运行前端测试与构建**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/TextbookDetailPage.test.tsx src/pages/Education/__tests__/TeachingRunDrawer.test.tsx && pnpm build`

Expected: PASS。

**Step 6: 更新变更日志并原子提交**

```bash
git add web/src/pages/Education/types.ts web/src/pages/Education/api.ts web/src/pages/Education/queries.ts web/src/pages/Education/TextbookDetailPage.tsx web/src/pages/Education/TeachingRunDrawer.tsx web/src/pages/Education/__tests__/TextbookDetailPage.test.tsx web/src/pages/Education/__tests__/TeachingRunDrawer.test.tsx CHANGELOG.md
git commit -m 'feat(education): show managed teaching generation progress'
```

### Task 8: 补充 mock E2E 和后端回归矩阵

**Files:**
- Modify: `web/e2e/education.spec.js`
- Modify: `tests/unit/server/app/education/test_textbooks.py`
- Modify: `tests/unit/server/services/test_education_textbooks.py`
- Modify: `tests/unit/server/services/test_education_learning_chat.py`

**Step 1: 写 mock 浏览器验收**

添加可控 mock API 流程：提取完成 -> 创建教学包 -> 阶段事件 -> review -> 发布/分配，断言：

- 页面从不出现聊天输入框或 storage key；
- 学生在教学包 review 前不能读取候选材料；
- 取消与恢复只显示允许操作；
- 抽屉显示运行事件但不显示 `/managed/` 路径。

**Step 2: 运行并确认失败**

Run: `cd web && pnpm playwright test e2e/education.spec.js --grep 'managed teaching package'`

Expected: FAIL，因为该路径尚未覆盖。

**Step 3: 完成 mock 路由与断言**

仅对 Playwright 使用路由 mock；测试标题与最终报告必须明确这是 mock 覆盖，不得当作
真实 PTC/MinIO 验收证据。

**Step 4: 扩展后端回归**

覆盖跨家庭 IDOR、学生拒绝、发布绑定教学包、legacy package 历史读取、取消先持久化、
输出校验失败不写 `education/`、受管 workspace/thread 常规 API 拒绝。

**Step 5: 运行聚焦矩阵**

Run:

```bash
uv run pytest tests/unit/server/app/education/test_textbooks.py tests/unit/server/services/test_education_textbooks.py tests/unit/server/services/test_education_teaching_jobs.py tests/unit/server/services/test_education_managed_ptc.py tests/unit/server/services/test_education_learning_chat.py -q
cd web && pnpm playwright test e2e/education.spec.js
```

Expected: PASS。

**Step 6: 更新变更日志并原子提交**

```bash
git add web/e2e/education.spec.js tests/unit/server/app/education/test_textbooks.py tests/unit/server/services/test_education_textbooks.py tests/unit/server/services/test_education_learning_chat.py CHANGELOG.md
git commit -m 'test(education): cover managed teaching package workflow'
```

### Task 9: 真实服务验收、构建和交付检查

**Files:**
- Modify only if a verified defect requires it: relevant implementation/test + `CHANGELOG.md`

**Step 1: 确认服务来源后启动当前 worktree 服务**

先记录 `5177`、`8000` 的监听 PID、命令、cwd、branch 和 HEAD。仅在不是当前 worktree
服务时启动：

```bash
uv run python server.py --reload --host 0.0.0.0 --port 8000
cd web && pnpm dev --host 0.0.0.0 --port 5177
```

确认 `lsof` 显示 `0.0.0.0:5177`，并从 LAN 地址请求 `200`。

**Step 2: 用真实家长会话验证完整新链路**

不设置 Playwright mock。记录真实浏览器 network、响应、控制台和条件渲染：

1. 创建唯一测试教材并真实上传小 PDF；
2. 运行本地 PDF 提取至内容 review；
3. 创建教学包，确认隐藏受管 PTC run 的真实状态、SSE/投影、inputs 不含对象键；
4. 等待 `book-to-skill` 与 `the-knowledge-guy` 真实执行完成，审阅返回的教学材料和题集；
5. 发布、分配安全测试学生；学生答一题，家长读取记录。

不得删除既有教材、对象或枚举无关 MinIO key。只通过应用边界确认新对象使用 `education/`
前缀；详情/API 响应中不得有 storage key 或 MinIO endpoint。

**Step 3: 运行全部相关自动检查**

```bash
uv run pytest tests/unit/server/app/education tests/unit/server/services/test_education_textbooks.py tests/unit/server/services/test_education_teaching_jobs.py tests/unit/server/services/test_education_managed_ptc.py tests/unit/server/services/test_education_learning_chat.py tests/unit/server/database/test_education_textbook_jobs.py tests/unit/server/database/test_education_teaching_packages.py -q
cd web && pnpm vitest run src/pages/Education/__tests__/TextbooksPage.test.tsx src/pages/Education/__tests__/TextbookDetailPage.test.tsx src/pages/Education/__tests__/TeachingRunDrawer.test.tsx src/pages/Education/__tests__/StudentLearningPage.test.tsx
cd web && pnpm playwright test e2e/education.spec.js
make lint
cd web && pnpm build
```

**Step 4: 使用 `superpowers:verification-before-completion`**

重新读取 diff、核对所有命令输出、检查真实服务证据、确认工作树没有未提交的意外文件。没有
真实 PTC 双 Skill 闭环、真实父端审阅以及安全边界证据时，最终报告必须明确未完成。

**Step 5: 原子提交任何验证中发现的实质修复**

每个已验证修复单独更新中文 `CHANGELOG.md` 并提交；不要将生成的运行日志、PDF、凭据、
临时 sandbox 文件或 MinIO 对象清单加入 Git。

**Step 6: 使用 `superpowers:finishing-a-development-branch`**

在所有验证通过后，读取该 skill 并按其分支交付流程给出集成/PR/保留 worktree 选择。最终报告
必须分开列出真实服务验收、单元测试、mock E2E、构建/lint 和正在运行的前后端进程来源。
