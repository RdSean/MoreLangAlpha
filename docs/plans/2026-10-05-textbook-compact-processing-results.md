# 教材加工紧凑时间线验收记录

## 范围与实现

执行已批准的[设计](2026-10-05-textbook-compact-processing-design.md)及[实施计划](2026-10-05-textbook-compact-processing-implementation.md)，继续 `feature/more-to-skills-textbook-refactor` 和原 worktree。

- 需求 1–9：书名、真实原文信息、连线服务节点、当前动作 Shimmer、最新上报活动/折叠诊断、两行居中淡入淡出名句、终态计时与 Token、手动学习入口、紧凑侧栏动画及章节计数已实现。
- 结构任务与讲义任务分别投影当前时间线；材料加工不展示来源冻结节点。不堆叠尝试、历史业务动作、批量统计或诊断列表；仍保留当前项、完成数量、可靠服务时间和资源校验进度。
- 处理中返回阅读保留共享 SSE 与阅读位置；显式打开的紧凑面板不会因完成突然消失。终态“进入学习空间”和讲义阅读入口主动关闭面板，避免移动端覆盖阅读内容。不会自动跳转，首份已提交讲义可立即阅读。
- 需求 10 按用户指示跳过；原书目录继续打开既有 Markdown。需求 11 延后，讲义正文排版保持原状。旧格式不补转换，不推算缺失页数或用量。
- 未改 Skill、模型推理强度、结构切分策略、运行时主链路或 LangSmith 上传。

## 已通过

| 检查 | 结果与范围 |
| --- | --- |
| 前端相关单元 | 主代理最终 `pnpm test src/pages/Education src/locales/__tests__ src/styles/__tests__/tokenRefs.test.ts`：22 文件、182 passed |
| 后端聚焦单元 | 主代理最终用量、原文元数据、job、来源快照、计时：84 passed；B2 提交前更广相关矩阵 110 passed |
| 隔离 PostgreSQL | `TEST_DB_NAME=langalpha_test uv run pytest -m integration`，原文元数据、用量、job 数据库及计时四文件：41 passed；fixture 校验数据库名称后才重建测试 schema |
| 静态与构建 | 改动生产 TS 文件 ESLint 通过；`pnpm build` 内置类型检查通过，首屏 gzip 359.8kB，低于 450kB 门槛；B2 Ruff 通过 |
| 新旧浏览器矩阵 | 完成入口修复前新加工/紧凑测试 25 passed；修复后主代理最终合跑三个文件 40 passed（4.6 分钟） |
| 旧工作台回归 | 更新已变更的界面契约后完整 15 passed，保留安全与阅读行为检查 |
| 审查 | B2 规格/质量两阶段通过；B1/B3 规格与质量审查通过，两项 P2 修复后复审通过 |
| 开发服务 | 5177/8000 均监听所有地址且 cwd 属于本 worktree；前端本机及 LAN HTTP 200，后端 `/health` HTTP 200 |

浏览器测试使用独立的 5176 前端和 4100 HTTP/SSE mock，未复用或停止开发 5177。覆盖：

- 375/768/1440、亮暗主题、长书名、结构/单份/批量状态、400 项终态；正常竖屏一屏，375×420 极短窗口可安全滚动至入口，无横向溢出。
- 字体加载后计时位置稳定，终态停表；英语、减少动态效果、缺失/部分 Token 提示；两行名句的真实活动触发、单次池加载、五秒冷却。
- 加工页/紧凑面板/阅读共享一条活动流，阅读位置保留；取消、重试、断线、刷新、跨 attempt 恢复、权限丢失和错误教材任务 URL。
- 首份讲义可读及旧讲义保留；500 条活动的游标 `[0, 200, 200, 500]` 与重复回放去重，界面仅显示最新诊断；轮询更新、后台恢复和旧任务迟到响应。
- 目录抽屉、批量选择、讲义链接、延迟正文/图片后的滚动恢复；终态入口清理活动参数和覆盖面板。

## 实际已有数据与迁移

- 迁移前核对 head 086、0 活跃教材 job、0 in_progress run，以及唯一旧后端的 cwd/端口；仅停止确认属于本项目的旧进程，升级 087 后启动新版后端。最终只读复核 `087_book_token_usage`，仍为 0 活跃教材 job / 0 in_progress run。
- 用当前 worktree `.env`；MinIO 为用户指定的 `localhost:9000`。未打印/提交配置文件，未操作 Docker volumes、未知容器或无关存储对象。
- 只读核对真实来源候选：22 个候选均有原 PDF 页数；已有教材没有新字段则省略页数。087 前的已完成 job 用量为“未记录”，未回填、未冒充零消耗。
- 已登录 Chrome 打开此前真实验收批次，核对已完成 2/2、持久服务区间与总耗时 2 分 5 秒、Token 未记录、章节计数及已有讲义。点击修复后的学习入口，URL 清除 `activity`/`panel` 并保留 `kp`/`view`。检查后恢复原阅读教材 URL。
- 用户未提交的业务活动文档及 PDF 保留，不纳入提交。没有新增付费模型调用，没有删除已有教材或改写原文/解析产物。

## 失败记录与限制

- 新 25 项首次 19 passed / 6 failed：旧节点数量/文案断言与新契约不符，另有字体加载引起的 1px 计时位置差；修正期望并等待字体加载后 25 passed。
- 旧 15 项更新后首次 13 passed / 2 failed：严格文本断言包含 Loader 可访问性文字；保留实际阶段、状态、游标、轮询及单 SSE 检查后 15 passed。
- 诊断曾在 PTC 结束后附着于验收节点，已限制阶段并补红到绿回归；完成入口曾保留移动端覆盖面板，已补失败回归并修复，复审通过。
- Chromium Playwright 截图非空，已检查桌面/移动、亮暗与完成状态布局。原生 Chrome 截图工具只捕获浏览器外框及空白网页区域，尽管可访问性树和交互包含实际内容；因此不宣称该工具完成了真实页面像素验收。最后原教材 URL 已恢复，重新加载时曾捕获“加载中”状态，不能据此声称截图或正文加载验收通过。
- 本轮未追加真实付费模型验收，provider 到新增 PG Token 快照的完整真实付费链路未测试；已有付费工作流证据见[此前记录](2026-10-04-textbook-async-preparation-timeline-results.md)，不能替代本轮用量验收。进程退出或遥测写入失败仍可能留下“未记录”。
- 未重新运行全仓库全部测试、真实移动设备、屏幕阅读器或长期负载。构建保留既有 Browserslist 数据过期及大 chunk 警告，测试保留 React Router future flag / Node 弃用提示。

## 最终合跑

`pnpm exec playwright test e2e/education-textbook-processing.spec.js e2e/education-textbook-compact.spec.js e2e/education-textbook-workbench.spec.js --project=chromium --reporter=line`：40 passed（4.6 分钟），进程退出码 0。包含完成入口关闭面板的最终回归；无遗留测试失败。

开发与验证按文件显式提交；B0 `f4efabd9f`、B2 `9cd3b3af0`、B1/B3 `4a636509f`。无 merge、push 或分支切换。
