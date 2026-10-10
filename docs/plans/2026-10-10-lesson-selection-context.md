# Lesson Selection Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在教材讲义与回答正文中选中文字，加入可移除的提问上下文，随当前知识点的问题发送。

**Architecture:** 保留教材的连续会话输入框和现有教育权限、消息 API、SSE。复用 Flash 的 details 引用格式；选区检测只接受同一讲义/回答 Markdown 容器内的文本。待发送选段属于当前 LessonSession，发送后作为消息内容进入现有历史，切换知识点销毁草稿。

**Tech Stack:** React 19, DOM Selection API, CSS theme tokens, Vitest, Playwright.

## 已确认交互

- 讲义或回答正文选中文字后显示“加入上下文”按钮，支持鼠标、键盘与手机 selectionchange。
- 输入框上方显示选段摘要和来源，可追加多段、按来源及原文去重、单独移除。
- 点击加入后聚焦文字输入，问题与完整选段一次发送；发送后清空本轮草稿。失败由现有消息重试路径恢复已发送内容。
- 仅引用当前阅读区正文，排除输入框、目录、用户气泡、工具和跨容器选择；选区取消、滚动、切换知识点时关闭浮层。
- Quiet / NASA 复用既有语义 token，44px 移动操作，正文和输入安全区保持可用。无需新数据库、后端、Docker 或持久批注功能。

## Task 1: 先验证发送与选择契约

**Files:** `web/src/pages/Education/__tests__/LessonConversation.test.tsx`, `web/src/lib/__tests__/quotedContext.test.ts`

1. 新增 DOM Range 选择测试：讲义与回答选段、上下文去重/移除、发送内容及切换知识点清空。
2. 新增引用格式测试：完整保留多行代码和特殊字符，使用不会被选段内部反引号截断的 fence。
3. 运行 focused Vitest，确认缺少选中按钮或 formatter 导致失败。

## Task 2: 实现正文选择与引用发送

**Files:** `web/src/lib/quotedContext.ts`, `web/src/components/ui/chat-input.tsx`, `web/src/pages/Education/hooks/useLessonSelectionContext.ts`, `web/src/pages/Education/components/LessonConversation.tsx`, `web/src/pages/Education/components/LessonConversation.css`

1. 提取 Flash 的 details 序列化为共享函数；原有标签及消息结构保持兼容。
2. 新增教育选区 hook，验证 DOM 归属，收集完整文本，使用可见选区位置放置浮层；注册并清理 selectionchange / pointerup / keyup / scroll / resize 监听。
3. LessonSession 增加可移除引用卡和浮层按钮，将引用与问题一起传给现有 handleSendMessage；发送、widget prompt、pending HITL 和跨知识点隔离均保留原有边界。
4. 运行 focused Vitest、教育测试与 Flash 输入引用测试，修复任何回归。

## Task 3: 浏览器验收和提交

**Files:** `web/e2e/education-textbook-conversation.spec.js`, `CHANGELOG.md`

1. Chromium 实测 375px / 1440px、Quiet / NASA，验证选择操作、浮层范围、上下文预览与实际请求正文。
2. 验证学生请求仍带 assignment / knowledge point 范围；验证重试保留引用，后一轮不会隐式附上旧选段。
3. 运行 `pnpm typecheck`、相关 ESLint、`pnpm build` 和 `git diff --check`。
4. 核对 `0.0.0.0:5177` 及 LAN HTTP 200；更新中文 CHANGELOG，原子提交本功能。保留用户原有业务计划和教材 PDF。
