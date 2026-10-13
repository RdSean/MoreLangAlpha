# 教材整页阅读与讲义原书对照 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 家长、学生原书阅读整页自适应并支持键盘 / 滚轮，讲义可开启含 Chat 的左右原书对照。

**Architecture:** 复用 PdfViewer / BookOriginalReader / BookLessonReader，通过教育阅读入口显式开启整页尺寸及翻页事件。保持讲义会话的 React 树和独立滚动，右侧 PDF 只在对照开启时挂载，使用相同教材权限、冻结原文定位和 React Query 缓存。模式和对照页码由阅读页 URL 保存，切知识点后重新定位。

**Tech Stack:** React 19、TypeScript、react-pdf / PDF.js、ResizeObserver、现有主题 tokens、Vitest、Playwright。

## 交互约定

- 默认 100% 指整页适配可用宽高，移除教材阅读中的固定 612px 限制，真实 PDF 长宽比与视口变化后重新计算。
- 原书模式 Page Up / Down 默认翻页；输入框、编辑器和已打开对话框不拦截。对照模式仅右侧 PDF 获得焦点时处理，左侧 Chat 不受影响。
- PDF 区内普通滚轮翻页，一次滚动手势只翻一页；放大产生溢出时先滚动页内，抵达边界后才翻页。Ctrl+滚轮调整现有离散缩放级别并阻止浏览器整页缩放。
- 讲义标题栏新增方形 Columns2 图标开关与 tooltip。左边完整保留讲义和 Chat，右侧对应原书；两侧独立滚动。内容区域过窄时上下排列，PDF 保持独立有限高度。
- 对照开关不卸载 LessonConversation，草稿与会话不重置。切知识点时仍保留对照模式，清除旧 PDF 页码后按新知识点定位；原文件失败只影响 PDF 一侧，可重试或关闭。
- 沿用 Quiet / NASA 样式，不修改 Docker、后端、数据库或旧版 Chrome PDF 引擎兼容策略。

## Task 1: 原书尺寸与导航

**Files:** `web/src/pages/ChatAgent/components/viewers/PdfViewer.tsx`、`PdfViewer.css`、`web/src/pages/Education/components/BookOriginalReader.tsx`、`BookReader.tsx`、`TextbookWorkbenchPage.css`。

1. 新建 `PdfViewerInteraction.test.tsx`，覆盖实际宽高比例、ResizeObserver、键盘作用域、普通 / Ctrl 滚轮、惯性去重与放大页内滚动，运行并确认缺失行为导致失败。
2. 加入 opt-in 整页适配与输入导航，不改变已有文档 / 文件面板的默认行为；教育原书开启这些选项。
3. 修正原书阅读区域高度和装饰空间，将 PDF 内容限制在剩余高度内。
4. 运行原书与 PdfViewer 聚焦单元检查，修改文件 lint、类型检查。

## Task 2: 保留 Chat 的原书对照

**Files:** `web/src/pages/Education/components/BookLessonReader.tsx`、新增对照布局 CSS、`StudentTextbookLearningPage.tsx`、`TextbookWorkbenchPage.tsx`、两套语言文件。

1. 为共享讲义阅读器和家长 / 学生页面补回归，确认开关、草稿、对应页定位、刷新、切知识点及窄屏行为缺失时失败。
2. 在共享阅读器接入比较布局与标题图标按钮，保持左侧会话树稳定；按页面传入原书位置与受控比较状态，单独保存比较 PDF 页码。
3. 只在有讲义时开放对照，沿用原文件错误与重试状态。
4. 运行讲义会话、家长工作台、学生页和原书阅读器单元回归。

## Task 3: 浏览器验收与交付

1. 扩展 `web/e2e/education-textbook-original.spec.js`，实测 Page Up / Down、滚轮 / Ctrl 缩放、resize、实际 PDF canvas 和第一页 / 末页边界。
2. 验证家长、学生两套主题及手机 / 平板 / 桌面对照布局，确认 PDF 非空、适配宽高、独立滚动、Chat 草稿保留，无横向溢出。
3. 运行 `pnpm build`、修改文件 ESLint、主题 token 检查；通过现有 `0.0.0.0:5177` 确認 LAN 访问。
4. 更新中文 CHANGELOG 和本记录，创建只包含本次改动的原子提交；保留当前 worktree 和分支。

## 执行与验收结果

- Task 1 已完成：实际 PDF 比例及 ResizeObserver 整页适配、键盘作用域、滚轮手势去重、Ctrl 缩放和放大后的页内滚动均有聚焦回归；原书入口启用交互，其他共享阅读器默认行为保留。
- Task 2 已完成：共享讲义对照布局应用至家长和学生；模式与页码保存在 URL，切知识点清理旧页码；关闭、重开、刷新使用原文件缓存，Chat DOM 与草稿保持。
- Task 3 已完成：83 项单元检查及 27 项当前 Chromium 浏览器回归通过，覆盖 Quiet / NASA 和 375 / 768 / 1440px；PDF canvas 像素非空，整页适配宽高，长讲义与 PDF 独立滚动。截图检查后让对照模式的讲义标题独占一行，避免被操作按钮挤压。
- 修改文件 ESLint、TypeScript 与生产构建通过，关键路径 428.9 kB gz，预算 450 kB；现有目标 worktree 的 Vite 服务监听 `0.0.0.0:5177`，LAN `192.168.3.240:5177` 可访问。
- 本次无需后端 / 数据库 / Docker 修改，旧版 Chrome PDF 引擎问题仍按独立记录处理。
