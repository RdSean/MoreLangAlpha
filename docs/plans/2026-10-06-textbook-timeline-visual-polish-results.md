# 教材时间线视觉微调与验收记录

日期：2026-10-06。按用户直接授权的九项前端优化，在现有
`feature/more-to-skills-textbook-refactor` 分支及worktree实施。

## 完成范围

1. 整页时间线使用Quiet Workspace工具背景、统一边框与圆角；标题、加工操作、服务阶段及完成入口之间使用中性分割线。
2. 取消按钮位于加工标题右侧；紧凑活动面板同样在标题旁提供取消。活动加载中、快照失败、跨教材或访问丢失时保留页头回退入口，避免当前任务无法取消。
3. 结构尚未ready或结构正在加工时隐藏学生分配按钮。
4. 完成服务节点使用注释级主题色实心圆，勾为反差色，未执行节点保持空心状态。
5. 书名右侧显示完成标签，并保留失败、取消和部分完成的不同终态。
6. 阶段名称、状态、耗时采用独立列，后两列右对齐，不与名称紧贴。
7. 可见时间统一为可靠服务耗时。Agent业务动作和诊断没有可靠独立耗时，只在悬停提示保留明确标为上报时间的时刻；缺失服务计时仍为“未记录”，不推算动作耗时。
8. 时间线偏顶部居中；加工中的名句位于下方，沿用两行、淡入淡出、真实活动触发与冷却。
9. 返回阅读保留箭头图标，新增随语言切换的后台继续执行提示；阅读位置、共享订阅及手动完成跳转沿用原行为。

本次未调整讲义正文排版、Skill、模型、切分策略、后端或迁移。

## 验证证据

- 相关单元：`pnpm test src/pages/Education src/locales/__tests__ src/styles/__tests__/tokenRefs.test.ts`，22文件191 passed。
- 浏览器三个文件：`education-textbook-processing.spec.js`、`education-textbook-compact.spec.js`、`education-textbook-workbench.spec.js`，Chromium最终完整40 passed（4.7分钟）。覆盖桌面/移动、亮暗、长标题、滚动、计时稳定、共享SSE、取消/重试和完成入口。
- 完整浏览器初轮38 passed/2 failed：375px亮暗视口内容619px超过605px。收紧底部名句留白后重跑完整三个文件通过，未删减按钮或内容。
- 最后取消回退修复后，聚焦`activity snapshot fails|processing stays readable|cancel and retry`，8 passed（59.7秒），含六组亮暗视口和503取消回退。该轮与完整40项存在重叠；没有一次完整41项的最终运行，不相加宣称48个不同用例通过。
- 改动四个生产TSX的ESLint通过；最终`pnpm build`通过（包含类型检查和首屏预算），359.9kB gzip低于450kB上限；`git diff --check`通过。
- 质量审查发现取消入口回退问题，新增加载失败、加载中、跨教材和权限丢失四项回归先失败再通过，修复后复审未发现剩余问题。
- 已检查移动端加工/完成和桌面暗色截图，确认分区、状态列、完成圆标与操作区无重叠。
- 最终确认前端PID1294属于此worktree/web并监听`*:5177`，后端PID86408属于此worktree并监听`*:8000`；本机5177、LAN `192.168.1.252:5177`及后端`/health`均HTTP200，保持服务运行。

## 验收边界

浏览器HTTP/SSE为隔离fixture，本次不称真实模型工作流通过；未调用付费模型，未新跑后端或数据库集成测试，未操作存储、Docker或已有教材。保留既有Browserslist陈旧数据、大chunk和测试工具警告，未运行全仓库lint/测试或原生Chrome交互。

用户已修改的`2026-10-03-textbook-business-activity.md`及未跟踪PDF不纳入本次提交；不merge/push，不改变当前分支。
