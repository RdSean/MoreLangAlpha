# Remove Finance Runtime Residue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 删除核心金融数据栈以外仍可被加载、安装或展示的金融运行时残留，使 LangAlpha 保持通用 Agent 平台定位。

**Architecture:** 保留 PTC、Flash、sandbox、工作区、通用 MCP 和通用自动化。删除没有路由或调用方的金融模型、数据库模块、市场时间工具和专属 sandbox 凭证；同时让镜像依赖、提示词和 README 不再宣传或安装金融能力。

**Tech Stack:** Python 3.13+、FastAPI、Pydantic、Daytona/Docker sandbox、pytest、Markdown。

---

### Task 1: 建立运行时残留边界

**Files:**
- Modify: `tests/unit/ptc_agent/agent/test_generic_tool_boundary.py`
- Test: `tests/unit/ptc_agent/agent/test_generic_tool_boundary.py`

**Step 1: Write the failing test**

增加断言，要求孤立的市场洞察、市场交易时间、观察列表和持仓模型、Ginlix 专用 token 路径均不再存在于通用运行时。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ptc_agent/agent/test_generic_tool_boundary.py -q`

Expected: FAIL，因为遗留模块和依赖仍在。

**Step 3: Write minimal implementation**

删除无调用方的模块和相关测试，收缩用户模型与 sandbox 初始化流程。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/ptc_agent/agent/test_generic_tool_boundary.py -q`

Expected: PASS。

### Task 2: 去除金融 sandbox 依赖和凭证

**Files:**
- Modify: `src/config/env.py`
- Modify: `src/config/settings.py`
- Modify: `src/ptc_agent/core/sandbox/_defaults.py`
- Modify: `src/ptc_agent/core/sandbox/ptc_sandbox.py`
- Modify: `src/ptc_agent/core/sandbox/assets.py`
- Modify: `src/ptc_agent/core/sandbox/providers/daytona.py`
- Modify: `src/server/services/workspace_manager.py`
- Modify: `Dockerfile.sandbox`
- Test: affected sandbox and workspace-manager tests

**Step 1: Write the failing test**

用 Task 1 的边界断言固定：默认依赖、环境变量出口和 snapshot 命令不再含 `yfinance`、Ginlix 或 Polymarket。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ptc_agent/agent/test_generic_tool_boundary.py -q`

Expected: FAIL，因为默认 sandbox 仍安装金融依赖。

**Step 3: Write minimal implementation**

移除内部金融 token 文件、token 铸发链和金融 CLI/Python 依赖；保留 Vault、OAuth、通用自定义 MCP 和 workspace 初始化。

**Step 4: Run focused tests**

Run: `uv run pytest tests/unit/core/sandbox tests/unit/server/services/test_workspace_manager.py -q`

Expected: PASS。

### Task 3: 清理提示词、示例和公开说明

**Files:**
- Modify: `README.md`
- Modify: `src/ptc_agent/agent/prompts/templates/components/workspace_context.md.j2`
- Modify: finance-only comments and test fixture wording discovered by `rg`

**Step 1: Write the failing test**

扩展通用边界测试，扫描公开 README 与默认提示词，禁止证券、行情、交易和金融数据栈术语。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ptc_agent/agent/test_generic_tool_boundary.py -q`

Expected: FAIL，因为 README 和提示词仍是金融产品叙述。

**Step 3: Write minimal implementation**

把 README 收缩为面向通用 Agent 平台的架构与快速启动文档，保留 Agent 模式、Skills、sandbox、工作区、MCP、SSE 与 Docker 说明。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/ptc_agent/agent/test_generic_tool_boundary.py -q`

Expected: PASS。

### Task 4: 全量验证和提交

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Run the complete unit suite**

Run: `uv run pytest tests/unit -q`

Expected: 退出码为 0。

**Step 2: Record the change**

在 `CHANGELOG.md` 添加中文条目，说明运行时残留、镜像依赖和公开金融描述已清理。

**Step 3: Commit**

Run: `git add -A && git commit -m "refactor(core): remove finance runtime residue"`
