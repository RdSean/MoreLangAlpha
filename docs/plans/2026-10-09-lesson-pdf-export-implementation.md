# Lesson PDF Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 家长及学生在当前知识点讲义页直接下载浅色 A4 PDF，默认仅讲义，可选本人问答，排除过程数据。

**Architecture:** 浏览器复用现有 Markdown/KaTeX，教育专用接口校对授权正文并清理不可信排版 HTML，现有 Chromium 生命周期生成离线静态 PDF。图书馆/教材/加工账本及模型不变。

**Tech Stack:** React、Radix/Lucide、React Query、react-markdown/KaTeX、FastAPI/Pydantic、HTMLParser、Playwright、Vitest/pytest。

---

## Task 1：教育导出数据与 HTTP 契约

Files: `src/server/app/education/book_models.py`, `src/server/app/education/textbooks.py`, new `src/server/services/education_lesson_export.py`; tests in `tests/unit/server/services/test_education_lesson_export.py` and `tests/unit/server/app/education/test_textbooks.py`.

1. 写失败测试：仅授权讲义，包含问答时逐段校对公开文本；变化冲突、未知字段、错误角色和历史故障拒绝。
2. Run: `uv run pytest tests/unit/server/services/test_education_lesson_export.py tests/unit/server/app/education/test_textbooks.py -q`，确认新增用例失败。
3. 严格 DTO + 服务权限/正文校对；HTMLParser 白名单，图片仅通过当前教材资产 API 实现的服务读取。响应使用 attachment/private no-store。
4. 重跑上述用例，确认通过。

## Task 2：离线浅色 A4 Chromium

Files: `src/server/services/pdf_render.py`; tests `tests/unit/server/services/test_pdf_render.py`。

1. 写失败测试：不共享凭据、禁脚本/网络、A4、浅色、字体图片完整性、异常关闭上下文、总超时。
2. Run: `uv run pytest tests/unit/server/services/test_pdf_render.py -q`，确认新增用例失败。
3. 增加 `render_static_pdf`，复用已有浏览器和有界并发，不改变 workspace PDF 请求路径。
4. 重跑并检查现有 workspace PDF 回归。

## Task 3：讲义共用导出按钮与按需排版

Files: new `web/src/pages/Education/components/BookLessonExport.tsx`, new `web/src/pages/Education/lessonPdf.tsx`, existing `api.ts`, `components/BookReader.tsx`, `components/BookLessonReader.tsx`, `components/LessonConversation.tsx`; test `__tests__/BookLessonExport.test.tsx`, `__tests__/lessonPdf.test.tsx`, `__tests__/LessonConversation.test.tsx`。

1. 写失败用例：主按钮仅讲义、下拉本人问答、回答中禁用含问答、隐藏无讲义/原文入口、错误可重试、不采集过程事件。
2. Run in web: `pnpm exec vitest run src/pages/Education/__tests__/BookLessonExport.test.tsx src/pages/Education/__tests__/lessonPdf.test.tsx src/pages/Education/__tests__/LessonConversation.test.tsx`。
3. 动态加载静态排版模块，复用 Markdown（浅色代码块），按需嵌入 KaTeX 字体，调用教育 API；下载后释放 Blob URL，切换知识点/卸载取消前端请求。
4. Run targeted tests, `pnpm typecheck`, `pnpm build`；检查首屏预算和相关既有学生/家长测试。

## Task 4：真实 PDF/页面验证与收口

Files: new `web/e2e/education-lesson-export.spec.js`, `CHANGELOG.md`, this plan。

1. 真 Chromium 验证下载/浅色/公式/图片/长内容和两种账号 UI，核对后端实际生成字节、A4尺寸与页面 PNG。
2. 已有 5177/8000 服务先核对 PID/worktree，只使用正确服务；不停止其他会话的进程。必要时启动前端 `0.0.0.0:5177` 并检查 LAN。
3. 运行聚焦 pytest/Vitest/Playwright、Ruff/ESLint、typecheck/build、diff check。如权限/网络限制无法真实服务验证，明确记录，不伪称通过。
4. 中文 CHANGELOG；只提交本次文件。当前 .git 为只读，不能绕过限制，提交若受阻留存工作区并说明。

## 状态

- [x] Task 1：授权数据、严格请求、资源边界与 HTTP 失败映射已实现并通过单测。
- [x] Task 2：离线浅色 A4 渲染入口、资源完整性与异常清理已实现并通过单测；实际 Chromium 字节/版式验收归 Task 4。
- [x] Task 3：两种账号共享按钮、默认/问答模式、取消/错误/URL 回收已实现；教育回归、类型检查与生产构建通过。
- [ ] Task 4：真实浏览器/PDF/5177 LAN 验收与提交受环境限制，未宣称整体验收完成。

## 本轮验证与交接

开发位置：`/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha`，分支 `local-main`。用户已确认在此继续，后续由用户合并至原开发分支；未修改外部 worktree、数据库、MinIO、凭据或现有运行服务。

- 聚焦后端：`UV_CACHE_DIR=/private/tmp/langalpha-pdf-uv-cache uv run --no-sync pytest tests/unit/server/services/test_education_lesson_export.py tests/unit/server/services/test_education_book_study.py tests/unit/server/services/test_pdf_render.py tests/unit/server/app/education/test_textbooks.py tests/unit/server/test_import_layering.py -q`，95 passed。
- 前端教育回归：`cd web && pnpm exec vitest run src/pages/Education/__tests__`，25 文件、227 passed。覆盖父母/学生共享入口，以及新增下载适配层、过程字段过滤、Blob 错误、取消请求和 URL 回收。
- 变更文件 Ruff、ESLint 与 `git diff --check` 通过。已有 Browserslist/React Router 提示不属于此次功能，未改动依赖或路由框架。
- `cd web && pnpm build`（含 `tsc --noEmit`）通过，首屏关键路径 418.4kB gzip，低于现有 450kB 预算；Vite 仍提示部分已有大 chunk，未修改共享打包配置。
- 独立代码审查确认未发现新的权限、SSRF 或工具/推理泄漏缺陷；修复任务清单勾选状态丢失。有导出动作的页头改为自适应高度，并增加手机端按钮边界验收断言。
- `cd web && pnpm exec playwright test e2e/education-lesson-export.spec.js --list` 正常发现 5 个场景；实际执行在测试服务器启动时失败：`listen EPERM ... 0.0.0.0:5176`。此前直接启动 Chromium 也被系统拒绝，未绕过沙箱限制。
- 浏览器场景使用模拟 PDF 响应，仅验证 UI、公开内容收集、本地 KaTeX 字体打包与下载契约，不能替代真实后端生成 PDF 的版式验证。
- 当前 `.git` 为只读；不绕过权限写索引、提交或复制到不可写 worktree。

合并后待验证：

1. 在可监听端口和启动 Chromium 的环境运行上述 Playwright 脚本，确认桌面/375px 手机及亮暗主题的两种账号导出。
2. 启动正确分支前后端于 `0.0.0.0:5177` / `8000`，实际下载含中文、长公式、授权图片、跨页表格和长代码的讲义及问答；核对 A4 尺寸、文字完整性、页码并渲染 PDF 页面进行目视验收，检查 LAN 可达。
3. 服务端须安装 Playwright Chromium 和可用中文字体（建议 Noto Sans CJK SC）；目前只内嵌 KaTeX 字体，不能从单测证明 OS 中文字体可用。
4. 跨域 API 部署若未暴露 `Content-Disposition`，下载仍正常但文件名回退为“讲义.pdf”；同源部署可使用后端标题文件名。这是现有 CORS 配置的低风险兼容限制。
5. 真实验证通过后再勾选 Task 4，并创建仅包含本功能的原子提交。
