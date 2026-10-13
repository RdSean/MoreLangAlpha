# 学生原始教材 PDF 阅读实施计划

目标分支：`feature/more-to-skills-textbook-refactor`，基准 `94a3c25dcc`。

## 目标与设计

学生阅读页复用家长端原始教材 PDF 阅读器。导航统一为知识点、原始教材（PDF）和文字目录（Markdown），沿用现有两套主题。原始教材切换后可以按章节定位、翻页和刷新恢复页码；知识点讲义及追问行为保持现有合同。

读取原文件与页码定位的现有接口扩展到已分配学生，复用与现有原文、封面读取一致的数据库 ACL。数据库同时返回上传者和 document ID；服务仍以原上传者身份通过内部 library 服务读取对应文件，不向学生开放 library、家长管理接口或其他原文件。

不需要数据库迁移，不涉及 Docker、PTC、Flash、MCP 或 sandbox 机制修改。

## 步骤

1. 为学生页补测试：原始教材 tab、章节定位、URL 刷新页码、Markdown 独立入口、切回知识点、旧 source 链接。
2. 为原文件服务补测试：家长/已分配学生读取、不可见教材阻止存储访问、定位使用冻结原文、缺失原文件。
3. 在数据库原文读取函数补内部 original 元数据，服务和路由使用调用者 user ID 进行权限校验。
4. 在学生页接入 BookOriginalReader 与 firstJsonPage，复用 BookNavigator 的三种导航模式。
5. 运行聚焦前后端测试、类型检查、修改文件 lint；条件允许时执行手机/平板/桌面 PDF canvas 浏览器回归。
6. 更新中文 CHANGELOG；目标 worktree 可写后应用并验证补丁，创建原子提交。

## 执行状态

最初会话仅允许主仓库写入，因此在 `/tmp` 准备基准副本和补丁。用户更新会话权限后，已将补丁应用至指定 worktree，重新验证；没有在 `local-main` 修改业务代码，也未覆盖目标 worktree 原有文档与数据文件。

## 验证记录

- 73 项后端单元检查通过：原文件服务、教材 API、原文 / 讲义读取。
- 69 项前端单元检查通过：学生阅读页、家长工作台、原文件阅读器和导航组件。
- TypeScript、修改文件 ESLint、Ruff 和新增 E2E 文件语法检查通过。
- 原文件权限的 PostgreSQL 集成检查通过，覆盖未分配、分配成功及撤销后的原文件读取。运行前确认连接目标为 `langalpha_test` 且无其他会话，未操作业务数据库。
- 当前 Chromium 下的 13 项 Quiet / NASA、375px / 768px / 1440px PDF 浏览器回归通过，覆盖 canvas 非空、翻页、刷新、Markdown / PDF / 知识点切换、问答恢复和横向溢出；截图检查显示 PDF 完整适配阅读区域。
- 生产构建和首屏预算通过（428.8 kB gz / 450 kB）；既有前端服务来自目标 worktree，以 `0.0.0.0:5177` 监听，LAN `192.168.3.240:5177` 返回 200，后端 reload 服务也来自同一 worktree。
- 实际 Chromium `90.0.4430.0` 的 PDF 检查失败：现有 PDF.js 使用 `Promise.withResolvers()`，旧内核缺失此 API。家长与学生的原书阅读共用该引擎，属于独立兼容问题，详见 `../debugging/2026-10-13-original-pdf-chrome90.md`；未实测用户 Android 设备。

## 后续兼容验收

共享 PDF 引擎的旧浏览器支持需单独实施，覆盖主线程和 worker 的语法 / API 兼容、实际 Chromium 90 PDF canvas 渲染，并在 Android 平板复核。本次学生 PDF 入口改动保留在指定分支，不自动合并回 `local-main`。
