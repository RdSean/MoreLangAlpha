# 教材近期活动与及时上报实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 改善长内容生成前的动作上报，在固定当前动作区域展示近期活动与古诗名句，不将诊断日志扩展为业务时间线。

**Architecture:** 复用教育活动账本、attempt fence、SSE 和折叠诊断。名句只作为前端静态资源，构建/启动前从根目录 `mingju.json` 校验、去重、分成最多 250 条的小包；页面按需加载一包并原位更新，不使用模型、Redis 或数据库。重要动作在长内容生成前以独立短轮上报；后端实际准备/验收步骤由服务报告。

**Tech Stack:** React/TypeScript、Vite/Node、Python、Vitest/pytest、Playwright。

---

## 已批准的边界

- 用户于本轮批准实施；沿用 feature/more-to-skills-textbook-refactor，不新建分支，不修改原分支配置与共享 Docker 数据。
- 工具事件只能证明近期执行活动，不是业务进度、模型视觉输入证明或持续健康心跳。无事件不自动宣称卡住。
- 当前动作固定在历史滚动区之外；名句不追加历史、不推动阅读位置、不进入 aria-live 播报。
- 每次连接以首包 high_water_seq 为补播边界，挂载时也保留快照历史边界。只响应当前 job/item、当前 attempt 开始之后、30 秒内的新诊断事件；历史回放、断线追赶和游标重置补播不轮换。
- 名句替换最少间隔 15 秒，无新事件不轮换。隐藏页面、断线、活动不可用、终态停止更新；迟到加载结果不能影响新执行项。
- 每面板只持有一包，静态资源加载失败静默降级为活动时间；不累计 React Query 名句缓存、不为每个工具调用请求资源。
- 上报提示不能保证所有自主模型都及时执行，不强制八项动作、不猜测 Bash/Edit 的业务含义、不补报已经完成的“正在”阶段。
- 不把本增量作为总 Task 8 完成。保留用户修改的原业务计划标题。

## Task 1：静态小包与固定活动区域

**Files:** `web/scripts/education-quotes.mjs`、`web/scripts/education-quotes.node-test.mjs`、`web/vite.config.js`、`deploy/Dockerfile.web`、`.gitignore`、`web/src/pages/Education/{quotePool.ts,components/BookLiveActivity.tsx,components/BookActivityPanel.tsx}`、对应 Vitest/Playwright。

1. Node 红测试：校验字段、去重、分片最多 250 条、版本化文件名、生成可复现；用临时目录验证，不动用户 JSON。
2. 生成器在 Vite 配置阶段运行，输出忽略的 `web/public/education-quotes/`。Docker 构建复制原始数据，两套开发 compose 精确只读挂载 JSON；名句不进入 JS 首屏导入图。
3. 前端红测试：初始回放不加载；新诊断加载一个包；15 秒冷却；无活动不轮换；不同 item/attempt/job 与旧事件不触发；断线/不可用/终态停止；加载失败及卸载安全。
4. 实现单包加载器与固定当前动作区，业务历史和诊断仍独立滚动。用普通文本展示名句与出处，稳定预留高度，主题 token 和移动端换行。
5. 运行 `node --test scripts/education-quotes.node-test.mjs`、聚焦 Vitest、`pnpm build`、改动文件 ESLint；与关联的宿主阶段提示改动一起记录中文 CHANGELOG 并原子提交本轮增量。

## Task 2：提前上报与宿主步骤

**Files:** `plugins/langalpha_local/skills/more-to-skills/SKILL.md`、`src/server/services/education_book_{jobs,activity}.py`、对应单元测试与 Skill 摘要断言。

1. Skill 提示应用基线：当前说明允许省略上报，或将 report_progress 和长 Write 放在同一轮。记录为模拟行为，不当作真实托管调用证据。
2. 红测试：托管提示要求长生成前独立短报告；宿主准备/验收事件走相同 fence/预算，详细投影失败不阻断加工且保持 unavailable。
3. 再核对真实 queued/running 任务为空，修改最小 Skill 约定及 managed_item_prompt；无工具/报告不可用时仍正常加工。
4. 同一观察器在创建沙箱前报告 preparing、Agent 完成后报告 finalizing；不报告假成功，提交事实仍由原事务写入。恢复路径沿用已有恢复逻辑，不另建运行状态。
5. 重跑三种提示应用情形；运行相关 pytest、Ruff。更新 Skill 目录真实摘要，schema 摘要不变。

## Task 3：验收与交付

1. 对比 baseline/更新后的提示批次，独立代码审查；修复发现后重跑对应测试。
2. Playwright 桌面及 375px 验证新事件/名句、历史不增长、无重叠、断线与终态；截图保存临时输出。
3. 保持 0.0.0.0:5177 / 8000，确认 LAN HTTP 可达。不得关闭用户新启动的加工。
4. 更新本计划结果、CHANGELOG 和原子提交；如没有真实模型新运行，明确不承诺已验证所有模型上报时机。

## 状态

- [x] 检查文件、真实任务与 Skill 基线。
- [x] Task 1：静态小包、固定区域与连接/加载边界。
- [x] Task 2：提前报告提示与真实宿主步骤。
- [x] Task 3：聚焦及浏览器验证、独立复审和交付记录。

## 本轮结果与限制

- `mingju.json` 原文件不改动：10,000 条输入去重为 8,819 条，生成 36 个最多 250 条的小包。首次新诊断只请求 manifest 和随机一包；后续换句在页面内完成，无 Redis、数据库或模型开销。生成产物、截图与日志不提交。
- 新动作提示要求长内容前独立短报告，不追补已经完成的“正在”。宿主 preparation/finalization 直接走现有 attempt fence、预算和公开投影；不可用仍不阻断教材工作，不改变可靠提交事务或 PTC 运行主干。
- 回归先复现再修复连接补播、中断加载无事件复启和终态页早于快照的窗口。连接首包固定历史边界，后续分页不抬高；中断后的新加载须有新的合格诊断。断线固定区域不塌缩，终态和 unavailable 停止显示/更新。
- Node 2 passed；后端 activity/jobs/structure/progress/skill-staging 92 passed；前端聚焦 63 passed；工作台 Chromium 13 passed，含 1440px/375px 真实静态名句、合成 SSE、冷却、补播、诊断折叠及终态。已查看截图，无横向溢出或文字重叠。
- typecheck/build/critical path 通过，首屏 356.4 kB gzip，上限 450 kB；改动文件 ESLint、Ruff 与格式检查通过。前端全量 2606 passed、1 failed，唯一失败仍为无关 `Plugins/connectReturn.test.ts` 的 storage-throws 基线问题，不宣称全量通过、不合并或推送。
- Skill 提示的 RED/GREEN 为独立 Agent 的应用情形模拟，不是实际模型时延测量。本轮未发起真实模型加工；提前报告不能保证所有自主模型均遵守，也未证明用户原教材加工变快。总 Task 8 仍未完成。
- 最终检查开发库 queued/running/cancelling 教材任务为 0，未取消用户任务、迁移或删除数据，也未重启共享中间层。原配置和用户原业务计划标题修改保留。5177/8000 均监听所有地址，LAN `192.168.1.252` HTTP 200，名句 manifest HTTP 200。
