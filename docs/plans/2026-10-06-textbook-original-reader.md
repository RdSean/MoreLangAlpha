# 教材原文件阅读与起始页定位实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 原书目录打开原PDF，有已有页码则定位起始页，无定位信息仍可阅读；文字目录保留Markdown定位。

**Architecture:** 沿用教材家长权限及图书馆原文件存储，通过教材专属只读接口提供原文件与可选起始页。定位优先用冻结Markdown中的确定性分页标记，其次用已有目录JSON起始页；不重新加工、不写模型结果、不迁移。前端复用受控PdfViewer及React Query，文件缓存与定位请求分离。

**Tech Stack:** FastAPI、async psycopg、React、React Query、react-pdf、Vitest、pytest、Playwright。

## O1：受权限保护的原文件与分页定位

- 修改`src/server/database/education_books.py`，只读查询带出原文件owner与解析器身份，不扩大教材权限。
- 新增`src/server/services/education_book_original.py`：家长教材归属校验先于图书馆读取；流式原文件与关闭回调复用现有DocumentLibraryService。冻结Markdown读取失败/无标记返回未知页，不阻止原文件读取。
- 在`src/server/app/education/textbooks.py`增加`original`与`original-location`只读接口；定位参数为正整数，页序统一为阅读器1-based，Datalab标记0-based加1，legacy标记已1-based。
- 新增服务与HTTP回归，先失败再实现，覆盖权限、缺失文件、未知定位、跨页、空白/重复标记与流关闭；同步cutover白名单。
- 验证`uv run pytest`聚焦单元与Ruff；中文CHANGELOG、显式文件原子提交。

## O2：三种导航与原文件阅读

- 修改`web/src/pages/Education/components/BookNavigator.tsx`，增加文字目录，三tab键盘及动画沿用现有样式；原书/文字树点击使用不同回调，URL保留选择及tab。
- 修改教材API、queries、queryKeys及类型，分别缓存原文件bytes和起始行定位；新增`BookOriginalReader.tsx`复用lazy PdfViewer，页码越界回首页，未知页不自动定位，缺失原文件显示错误及重试。
- 修改`TextbookWorkbenchPage.tsx`：`view=original`渲染PDF，旧`view=source`仍为Markdown；知识点原文入口可打开PDF，讲义及加工阅读位置不变。中英文文案同步。
- 补导航、页码选择、阅读器及工作台回归，先失败再实现；`pnpm test`聚焦、相关ESLint、build预算及diff检查。

## O3：浏览器与交付

- 使用隔离HTTP/SSE fixture及真实小PDF验证canvas非空、已知页跳转/未知首页、刷新/切tab、亮暗/移动端、原有加工阅读回归，不调用模型或操作用户教材。
- 检查5177/8000进程归属与本机/LAN；必要重启仅限本worktree服务，不混跑新旧worker，不触碰Docker与存储。
- 记录通过/未测及mock边界，更新中文CHANGELOG并原子提交；保留用户业务文档与PDF，不merge/push。

## 状态

- O1：已实施，相关单元/HTTP60 passed、Ruff通过；真实读取待O3。
- O2：已实施，相关前端285 passed、相关ESLint及build通过；新PDF浏览器七项通过，联合回归待O3。JSON回退收紧为明确PDF页序标签，学生共享组件保留原有两tab。
- O3：待实施。
