# 受管教材完整资产管线实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让家庭教材的受管 PTC 生成并安全审阅完整知识资产、章节工具包、覆盖审计、练习和中文教学包，而不是单一浅层 JSON。

**Architecture:** 教学任务保留一个家长可见的冻结 attempt 和持久 PTC 根运行。服务 stage 完整静态内置 Skill 目录、冻结输入与固定输出合同；PTC 自己按需读取/调度 `book-to-skill`、`the-knowledge-guy` 和受限内置子任务，服务不预设顺序，只在终态验证候选并私有写入 `education/`。数据库保存安全 manifest、根运行和安全进度，家长经授权 API 浏览白名单资产。

**Tech Stack:** Python 3.13+, FastAPI, async psycopg3, Alembic raw SQL, Pydantic, MinIO/S3-compatible private storage, React 19, TypeScript, React Query, Vitest, Playwright, agent-browser.

---

### Task 1: 定义 v2 完整资产候选与验证器

**Files:**
- Create: `src/server/services/education_teaching_assets.py`
- Create: `tests/unit/server/services/test_education_teaching_assets.py`
- Modify: `src/server/services/education_teaching_validation.py`
- Modify: `tests/unit/server/services/test_education_teaching_validation.py`

**Step 1: Write the failing test**

为两个冻结章节构造最小有效 fixture，断言 `validate_teaching_assets()` 接受恰好一份 concept index、coverage audit、每章 knowledge JSON、toolkit Markdown 和 practice JSON；遗漏、重复章节、未知概念引用、hash 不匹配、coverage 非通过、题目知识点不一致均应失败。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_assets.py -q`

Expected: FAIL，因为新验证器不存在。

**Step 3: Write minimal implementation**

实现纯函数 `expected_teaching_asset_paths()`、`validate_knowledge_assets()` 与 `validate_teaching_assets()`。每章要求冻结 ID/hash、概念、关系、证据、toolkit、practice；全书 index/audit 只能引用已验证章节和概念。复用既有 `validate_teaching_package()`，保留 v1/legacy 行为。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_assets.py tests/unit/server/services/test_education_teaching_validation.py -q`

Expected: PASS。

**Step 5: Commit**

```bash
git add src/server/services/education_teaching_assets.py src/server/services/education_teaching_validation.py tests/unit/server/services/test_education_teaching_assets.py tests/unit/server/services/test_education_teaching_validation.py CHANGELOG.md
git commit -m 'feat(education): validate complete teaching assets'
```

### Task 2: 固定 staging、下载和私有 bundle 归档

**Files:**
- Modify: `src/server/services/education_teaching_storage.py`
- Modify: `tests/unit/server/services/test_education_teaching_storage.py`
- Modify: `skills/book-to-skill/reference/managed-textbook-contract.md`
- Modify: `skills/the-knowledge-guy/reference/managed-textbook-contract.md`
- Modify: `src/ptc_agent/agent/managed_execution.py`
- Modify: `tests/unit/ptc_agent/test_managed_textbook_execution_policy.py`

**Step 1: Write the failing test**

断言服务从 frozen manifest 派生固定集合：`outputs/knowledge/concept-index.json`、`coverage-audit.json`、每章 knowledge/toolkit/practice 和 `teaching-package.json`。下载必须逐项请求已知 path，不得 listing；超大、非法、未知或不完整候选安全失败；归档 manifest 不含 storage key、URL 或 sandbox path。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_storage.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py -q`

Expected: FAIL，因为 v2 文件集和阶段写入限制不存在。

**Step 3: Write minimal implementation**

继续只 stage 冻结 Markdown/manifest，并预建固定 v2 output 目录；同时从当前 worktree stage 两个内置 Skill 的完整静态目录和所需引用资料。managed policy 对整个 root run 只开放 v2 白名单输出，维持 root、MCP、web、Vault 和普通 workspace 限制。服务自行下载、验证并向新的私有 `education/` prefix 写 artifact、README 和服务生成 manifest。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_storage.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py -q`

Expected: PASS。

**Step 5: Commit**

```bash
git add src/server/services/education_teaching_storage.py src/ptc_agent/agent/managed_execution.py skills/book-to-skill/reference/managed-textbook-contract.md skills/the-knowledge-guy/reference/managed-textbook-contract.md tests/unit/server/services/test_education_teaching_storage.py tests/unit/ptc_agent/test_managed_textbook_execution_policy.py CHANGELOG.md
git commit -m 'feat(education): stage full teaching asset bundles'
```

### Task 3: 持久化安全 manifest 与自主里程碑

**Files:**
- Create: `migrations/versions/033_add_education_teaching_asset_manifest.py`
- Modify: `src/server/database/education_textbooks.py`
- Modify: `tests/unit/server/database/test_education_teaching_packages.py`
- Modify: `tests/unit/server/database/test_education_teaching_jobs.py`

**Step 1: Write the failing test**

断言完成 v2 attempt 时 package 保存安全 asset manifest；同一 attempt 只绑定一个活跃 root；取消或新 attempt 后旧 root 不能推进或发布。断言 PTC 的 `planning`、`chapter_mapping`、`concept_linking`、`coverage_audit`、`practice_build`、`teaching_build`、`bundle_assembling`、`validating_bundle` 里程碑可投影，未知 phase、自由文本、路径和模型自报计数均被丢弃；parent detail 不返回 bundle prefix、object key、模型错误或 sandbox path。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_education_teaching_packages.py tests/unit/server/database/test_education_teaching_jobs.py -q`

Expected: FAIL，因为 schema 和 persistence API 不存在。

**Step 3: Write minimal implementation**

迁移为 `education_teaching_packages` 增加 `asset_manifest JSONB NOT NULL DEFAULT '{}'::jsonb`。复用现有 attempt/root run 行与事件表，只扩展白名单里程碑、asset kind 和安全摘要的持久化/投影；用既有 family join、transaction 和 row locks 保证取消或新 attempt 不能让旧 root 发布，保持 legacy package 兼容。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_education_teaching_packages.py tests/unit/server/database/test_education_teaching_jobs.py -q`

Expected: PASS。

**Step 5: Commit**

```bash
git add migrations/versions/033_add_education_teaching_asset_manifest.py src/server/database/education_textbooks.py tests/unit/server/database/test_education_teaching_packages.py tests/unit/server/database/test_education_teaching_jobs.py CHANGELOG.md
git commit -m 'feat(education): persist teaching asset manifest'
```

### Task 4: PTC 自主 Skill/子任务调度与恢复

**Files:**
- Modify: `src/server/services/education_teaching_jobs.py`
- Modify: `src/server/services/education_managed_ptc.py`
- Modify: `skills/book-to-skill/SKILL.md`
- Modify: `skills/the-knowledge-guy/SKILL.md`
- Modify: `tests/unit/server/services/test_education_teaching_jobs.py`
- Modify: `tests/unit/server/services/test_education_managed_ptc.py`
- Modify: `tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py`
- Modify: `config.yaml`
- Modify: `src/config/models.py`
- Modify: `src/config/settings.py`
- Modify: `src/server/services/runs/executor.py`
- Create: `tests/unit/server/services/runs/test_education_teaching_timeout.py`

**Step 1: Write the failing test**

断言 graph 只启动一个 root，且不向 `configurable.skill_contexts` 预注入 Skill 正文。断言 sandbox 中有两项完整内置 Skill，PTC 读取各自 `SKILL.md` 后由 middleware 标记实际加载；受管内置子任务继承同一 policy，而用户自定义子任务、MCP/web/Vault 仍不可用。断言模型安静等待期间 15 秒心跳持续发生，教材 root 使用独立的 24 小时 timeout 和无连接回收窗口，而普通聊天仍使用原 `workflow_timeout`。终态才下载/校验全部资产；取消或失败不得归档。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_jobs.py tests/unit/server/services/test_education_managed_ptc.py tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q`

Expected: FAIL，因为当前只 stage 两份 contract、图层强制关闭所有子任务，并把两个压缩模式内联进 prompt。

**Step 3: Write minimal implementation**

`build_managed_teaching_graph()` 保持单一 root，prompt 只陈述服务事实、输入、输出合同和安全边界。PTC mode 通过读取 staged `SKILL.md` 自动加载完整 Skill；不在启动时内联两份正文。调整 graph/agent 以尊重 `managed_policy.allow_subagents`，只允许服务定义的内置 worker 并把同一 filesystem/capability policy 传给它们。扩展 progress parser/DB projection，使用白名单 milestone 和服务推导的计数，而不是 PTC 指挥。新增 `education_teaching_workflow_timeout` 与 `education_teaching_abandoned_timeout`（均默认 86400 秒），并只对该 managed root 应用；普通聊天 timeout 不变。两个 managed mode 改为 v2 map/reduce/audit/practice 与中文教学构建，但由 PTC 决定调用顺序；恢复始终是新的冻结 attempt，不能复用旧 sandbox output。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_jobs.py tests/unit/server/services/test_education_managed_ptc.py tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q`

Expected: PASS。

**Step 5: Commit**

```bash
git add src/server/services/education_teaching_jobs.py src/server/services/education_managed_ptc.py skills/book-to-skill/SKILL.md skills/the-knowledge-guy/SKILL.md tests/unit/server/services/test_education_teaching_jobs.py tests/unit/server/services/test_education_managed_ptc.py tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py CHANGELOG.md
git commit -m 'feat(education): let PTC orchestrate textbook skills'
```

### Task 5: 家长安全资产审阅 API

**Files:**
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py`
- Modify: `src/server/services/education_textbooks.py`
- Modify: `src/server/database/education_textbooks.py`
- Create: `tests/unit/server/app/education/test_teaching_assets.py`
- Modify: `tests/unit/server/app/education/test_textbooks.py`

**Step 1: Write the failing test**

断言同家庭 parent 可取得 package 安全 manifest 摘要和指定 chapter 的 toolkit、knowledge、practice；学生、异家庭 parent 和未知 kind 返回 403/404。断言响应不含 `education/` path、storage key、URL、sandbox path、provider 或 raw model text；学生 API 仍只返回已发布材料和题。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/app/education/test_teaching_assets.py tests/unit/server/app/education/test_textbooks.py -q`

Expected: FAIL，因为 API 不存在。

**Step 3: Write minimal implementation**

增加 parent-only package asset summary 与 chapter asset endpoint。通过 package/household join 授权，使用数据库 safe manifest 构造内部相对路径并读取 private storage；`kind` 是 Literal。detail 只加计数、coverage 摘要和 package ID，不预载大文件，不改变 student contract。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/app/education/test_teaching_assets.py tests/unit/server/app/education/test_textbooks.py -q`

Expected: PASS。

**Step 5: Commit**

```bash
git add src/server/app/education/models.py src/server/app/education/textbooks.py src/server/services/education_textbooks.py src/server/database/education_textbooks.py tests/unit/server/app/education/test_teaching_assets.py tests/unit/server/app/education/test_textbooks.py CHANGELOG.md
git commit -m 'feat(education): expose safe teaching asset review'
```

### Task 6: 家长知识资产与阶段进度 UI

**Files:**
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/Education/TextbookDetailPage.tsx`
- Modify: `web/src/pages/Education/TeachingRunDrawer.tsx`
- Modify: `web/src/pages/Education/__tests__/TextbookDetailPage.test.tsx`
- Modify: `web/src/pages/Education/__tests__/TeachingRunDrawer.test.tsx`

**Step 1: Write the failing test**

断言 review package 显示“知识资产”标签、每章 coverage 和概念；点击 toolkit/practice 走 API hook 并展示安全内容。断言运行抽屉显示 PTC 自主里程碑、逐章已报告资产、开始后的耗时、最近心跳和“等待 Agent/模型响应”，并区分“Agent 已报告”与“已验证”；它没有 composer、storage key、sandbox path 或 provider 文本。

**Step 2: Run test to verify it fails**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/TextbookDetailPage.test.tsx src/pages/Education/__tests__/TeachingRunDrawer.test.tsx`

Expected: FAIL，因为 asset query、标签和阶段投影不存在。

**Step 3: Write minimal implementation**

增加 typed API/React Query key，不复制 server state。detail 增加紧凑“知识资产”标签，按需读单个 asset；运行抽屉扩展 PTC 自主里程碑、逐章资产、elapsed/heartbeat/安静等待和 retry。沿用 Dialog/Button/Quiet Workspace tokens，保持移动端换行和学生权限，不创建第二套 PTC/chat 界面。

**Step 4: Run test to verify it passes**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/TextbookDetailPage.test.tsx src/pages/Education/__tests__/TeachingRunDrawer.test.tsx && pnpm typecheck && pnpm build`

Expected: PASS，build exit 0。

**Step 5: Commit**

```bash
git add web/src/pages/Education/types.ts web/src/pages/Education/api.ts web/src/pages/Education/queries.ts web/src/pages/Education/TextbookDetailPage.tsx web/src/pages/Education/TeachingRunDrawer.tsx web/src/pages/Education/__tests__/TextbookDetailPage.test.tsx web/src/pages/Education/__tests__/TeachingRunDrawer.test.tsx CHANGELOG.md
git commit -m 'feat(education): review complete textbook knowledge assets'
```

### Task 7: Mock 回归和真实服务验收

**Files:**
- Modify: `web/e2e/education.spec.js`
- Modify: `CHANGELOG.md`（仅在发现并修复实质问题时）

**Step 1: Write the failing test**

新增 mock E2E：家长创建、选择来源、加工阶段一/二、查看知识资产、发布、分配；学生只能答冻结题；家长只读记录。mock 仅为回归，不得作为真实验收结论。

**Step 2: Run test to verify it fails, then passes**

Run: `cd web && pnpm playwright test e2e/education.spec.js --grep '完整知识资产'`

先观察新增测试失败，再补齐必要前端 contract/mock，复跑至 PASS。

**Step 3: Run complete automated verification**

```bash
uv run pytest tests/unit/server/services/test_education_teaching_assets.py tests/unit/server/services/test_education_teaching_validation.py tests/unit/server/services/test_education_teaching_storage.py tests/unit/server/services/test_education_teaching_jobs.py tests/unit/server/services/test_education_managed_ptc.py tests/unit/server/database/test_education_teaching_packages.py tests/unit/server/database/test_education_teaching_jobs.py tests/unit/server/app/education/test_teaching_assets.py tests/unit/server/app/education/test_textbooks.py -q
make lint
cd web && pnpm vitest run src/pages/Education/__tests__/TextbookDetailPage.test.tsx src/pages/Education/__tests__/TeachingRunDrawer.test.tsx && pnpm build && pnpm playwright test e2e/education.spec.js
```

**Step 4: Verify real services**

重启仅来自当前 worktree 的后端，确认 PID/cwd/branch/HEAD/health；确认 Vite 以 `0.0.0.0:5177` 可经 LAN 访问。用真实登录家长记录 auth、创建、上传/选择、两阶段 job、轮询、资产审阅、浏览器 console/network；使用已上传或新的安全 PDF 完成一次加工，且不枚举/删除无关 MinIO 对象。有安全学生时答一题并验家长只读记录；没有时报告缺口，不声称完成。

**Step 5: Finish branch**

使用 `superpowers:verification-before-completion` 对照 `2026-08-14-managed-textbook-full-asset-pipeline-design.md` 逐项审计，再使用 `superpowers:finishing-a-development-branch` 完成分支。最终报告分列真实服务、单元测试、mock E2E、构建/lint 和进程来源。
