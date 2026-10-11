# Student Textbook Navigation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 暴露学生教材入口，支持阅读目录收放，并压缩学生作业页标题占用。

**Architecture:** 教材列表与学习 API 留在 Education 模块；共享导航按角色增加入口及排除路径。阅读页复用 BookNavigator.onCollapse，在同一阅读组件外调整网格。日历新增仅学生使用的有界视口布局。

**Tech Stack:** React 19、React Router、React Query、现有主题 tokens、Lucide、Vitest、Playwright。

---

### Task 1: 学生教材列表与入口

**Files:** `web/src/pages/Education/StudentTextbooksPage.tsx`、`web/src/components/nav/navItems.ts`、`useNavActive.ts`、`web/src/components/Main/Main.tsx`、`routeChunks.ts`、两个 locale 文件、`EducationPage.tsx`。

1. 添加导航可见性/高亮、教材列表状态测试，先运行确认失败。
2. 增加学生 `/education/learn` 静态路由和懒加载；`useLearningAssignments(member?.role === 'student')` 读取列表，家长进入该列表转向 `/textbooks`。
3. 学生导航显示「我的教材」，作业项排除学习路径；正确预加载列表、详情及总结路由。
4. 作业页替换内嵌列表为跳转链接，复用现有查询，不复制数据。
5. 运行上述测试、类型检查和入口 E2E。

### Task 2: 阅读目录收起

**Files:** `StudentTextbookLearningPage.tsx`、现有阅读 CSS、对应单元测试和 `education-textbook-learning.spec.js`。

1. 添加收起/展开和返回教材列表的失败测试。
2. 维护 `navigatorCollapsed`，接入 BookNavigator.onCollapse；宽屏隐藏目录并扩宽正文，工具栏提供 PanelLeftOpen 图标按钮。
3. 窄屏保持目录弹层和选择后关闭；书名返回链接改为 `/education/learn`。
4. E2E 确认目录收放不丢失问题草稿或正文，手机无溢出。

### Task 3: 学生作业页空间

**Files:** `EducationNotebook.tsx`、`EducationPage.tsx`、教育布局 CSS、`EducationPage.test.tsx`、`education-calendar.spec.js`。

1. 添加学生无标题和日历底部超出首屏、可滚动的失败断言。
2. 仅家长保留标题/学生选择区域；学生日历高度取视口高度和最小周行高度的较大值，不依赖事件数量。
3. 学生页面纵向滚动，桌面作业区保留自身滚动；家长维持既有有界分栏。
4. 复核六周月份、横向翻月及纵向滚动。

### Task 4: 验证与提交

1. `pnpm test` 运行导航/学生教材/作业聚焦单元测试。
2. 当前 Chromium 和实际 Chromium 90 运行教材、入口、日历 E2E；检查 375/820/1440px 的两个主题截图。
3. `pnpm build`、修改文件 ESLint、`git diff --check`；确认 LAN `192.168.3.240:5177` 返回 200。
4. 更新中文 `CHANGELOG.md`，只提交本次文件，保留用户已有文档/PDF。
