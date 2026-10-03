# Task 8 最终收口

日期：2026-10-03。Worktree：`more-to-skills-textbook-refactor`，分支：`feature/more-to-skills-textbook-refactor`。

状态：总 Task 8 与语义进度 Task 6 按原验收矩阵完成，15 行均有自动化或真实行为证据，没有剩余必验缺口。额外未测边界见文末，不宣称每种故障都做了真实模型验收。

验收口径沿用总计划：每行需要自动化或真实行为证据，不要求每种故障再执行一遍真实模型。实际 UI、正常 Cookie API、后台可信测试入口、真实 PostgreSQL/MinIO 故障和合成事件压力分别记录，不相互冒充。

既有证据见 [Task 8 初始记录](2026-10-02-more-to-skills-task8-results.md)、[增量记录](2026-10-03-more-to-skills-task8-incremental-results.md)、[业务动作记录](2026-10-03-textbook-business-activity-results.md)；旧资源和 catalog 见 [Task 7 切换记录](2026-10-02-more-to-skills-cutover-results.md)。这些记录保留历史失败及当时未覆盖项，下表汇总当前状态。

## 本轮补验

### 学生作业 UI 与未来排程

- 正常家长 Cookie UI 给专用 `Task 8 Acceptance student`（g3）创建数学练习/校外作业/每日任务，说明标记 `Task 8 Final UI Acceptance 20261003`。首项 `8d3804c2-4300-44d9-91c1-1588d84fb23d`，截止 `2026-10-04T09:00:00Z`，家庭 Asia/Tokyo 当地 18:00。
- 独立 localhost 学生浏览器正常登录，通过“完成打卡”提交大小比较及十位说明。家长正常 UI 保存反馈，学生刷新实际看到已完成及同一反馈。独立正常学生 Cookie API 再核对一份提交和一条 review。
- 学生日历 API 连续读取 10 月 4–6 日，恰好三项，日期/当地截止时间正确，两次 task IDs 相同，无重复实例；其他学生作业未变。此部分是正常 Cookie API live，不冒充逐格日历 UI 操作。
- 仅停止本次规则 `fdf3e026-b0ef-4680-83a6-36519f954644`，10 月 7–8 日不再创建新实例，已有三项保留。规则收尾通过准确家长后台 API，不作为家长 Cookie UI 证据；两条未来待完成验收实例保留，未删除记录。
- 桌面及 375px 的完成/反馈截图已核对；375px `scrollWidth == innerWidth == 375`。用户家长登录和原标签页未切换。

### 真实讲义嵌图与阅读位置

- 只重做专用 `Task 8 Arithmetic Context` 的 `ch2-k01`，教材 `f44fac76-1eb8-4736-8085-51f277c2096e`，job `a72e7b25-a7aa-4b1d-974d-32cfdb1be5cb`。正常家长 UI 要求使用原 Figure 1，不生成新图/词表/额外练习；真实模型完成，业务任务 succeeded、成功项 1。
- 新讲义 SHA256 为 `94f73c95cb88beccaa81620c83b3021448e73aa454018dbbac68a4b36799ddc4`。嵌图路径为经过授权的教材 assets API，实际 HTTP 200/image，浏览器图片 complete、自然尺寸 1085×313；桌面及 375px 正常可见，移动文档宽度 375px，无横向溢出。
- 数据库时间：created `10:25:17.765714Z`、started `10:25:21.021593Z`、finished `10:26:40.362578Z`。受理到提交 82.597s，其中排队 3.256s、业务开始到提交 79.341s；后者包含运行和收尾，不是纯模型调用耗时，也不是 LangSmith 云端测量。
- 实测发现内存滚动记忆不能跨刷新；修复提交 `8d7101218`。阅读器按 KP/视图选择性保存最多 300 个会话偏移，200ms 合并写入，pagehide/卸载落盘，退出/切换账号清空；只存标识和偏移，不存正文/凭据。普通页面默认行为不变。
- 冷正文加载不覆盖旧位置，冷图片/异步 Markdown 高度不足时等待正文布局；用户鼠标、触摸、拖动或滚动键取消等待。存储损坏/禁用仍可读，明显变短的重做正文可能无法恢复旧像素偏移。
- 回归先失败：刷新 240px→0，延迟图片 580px→0；修复后聚焦两项通过。真实讲义刷新从约 459px 恢复到 455.5px，列表历史返回仍为 455.5px；字体/Markdown 布局允许 4px 容差，不将 1px 变化认作丢失位置。

### 较宽浏览器检查

- 初次四个 spec 为 29 passed/4 failed：文档 dataset 控件已改为选择弹窗，作业创建已改为按钮/分类/自动标题，补充提交已改为 completed + revisions。测试对齐当前 UI，并保留或增加分类、来源、截止时间、附件和幂等断言；之后 33 passed。
- 加入阅读回归后，文档敏感响应体检查偶发 `Network.getResponseBody` 资源失效。完整导航前等待相关 API/响应体检查，不忽略读 body 异常或取消敏感字段断言；不等待刻意保持的无关线程 SSE。桌面/移动聚焦 2 passed。
- 一轮为 34 passed/1 failed，阅读实际恢复到 239px，断言要求精确 240px；改为与恢复逻辑一致的 4px 容差，仍严格捕获回到顶部。最终完整套件结果见下节。
- 后续 mobile 仍偶发已结束 SSE 的 CDP body 不可读；对准确 job/events 用例从原 mock HTTP 读取真实字节并原样转发，再执行同一敏感字段检查。断言确实截获了 SSE，REST 仍用原 response.text 并让错误失败。两个 project 各重复三次，6 passed；这个有限终态转发不作为真实分块回放证据，分块/断流验收由独立工作台 suite 承担。

## 原矩阵核对

| 场景 | 当前行为证据 |
|---|---|
| 图书馆一键添加 | 正常家长 Cookie 上传/解析/添加/生成，PG 一个教材和初始任务，第二标签页同源复用 |
| 结构-only | 真实 3 章/4 KP、0 讲义；schema/来源/空 chapters 的自动化覆盖 |
| 中间 KP 首次生成 | 前两项无讲义时真实第三 KP 提交，原文图/脚注/邻近内容可用；本轮补真实讲义嵌图 |
| 已有讲义重做失败 | PostgreSQL 独立事务失败、旧材料仍可读、错误及重试准确 |
| 批量第 3 项失败 | PostgreSQL 前两项立即可读、第三失败、第四成功，计数来自提交，retry 只处理第三项 |
| 取消与迟到回调 | 真实 UI/runtime 取消、后续 attempt=0，PG fence 拒绝迟到 token |
| 双击/两个标签页 | 真实同源复用/材料 409；PG 并发幂等，不双跑 |
| 上传/PG finalise 崩溃 | 真 MinIO body 中断/成功响应丢失、真 COMMIT ACK 丢失、同 attempt 恢复、候选精确收尾 |
| 关闭浏览器/换 worker | 浏览器恢复/重连；真实模型完成结果由另进程从原沙箱提交同一 attempt，没有再次生成 |
| Redis 故障/150001 delta | 真实 PG/Redis/browser 有界组合与断连 PG 回放；新版动作/工具预算及单摘要 |
| 任意节点/长文/图片 | 源行/相对链接/深链自动化，真实图像，桌面/375px，独立视图、刷新及列表历史返回 |
| 学生与图书馆反查 | PG 新引用；正常学生 Cookie 进度/笔记/总结/模型追问，家长转录和图书馆反查 |
| 撤销/跨家庭 | PG ACL 及正常学生 Cookie 跨家庭/撤销后原文、讲义、图片、聊天和学习写入拒绝 |
| 旧路由/catalog | Task 7 升级/catalog/资源准确清理；旧路由单测和浏览器失效链接提示 |
| 普通产品回归 | 普通 PTC/Flash/MCP/子代理/checkpoint、runtime gate、Datalab；本轮补学生作业 UI/未来排程及较宽浏览器回归 |

## 最终验证

- 后端全量：7930 passed、8 deselected、1 xfailed、34 warnings，125.55s。
- 明确 `TEST_DB_NAME=langalpha_test`，教材 books/jobs/activity/storage faults 四套串行：48 passed，122.15s。只重建隔离测试 schema；开发库和共享卷不变。
- 前端全量：272 文件、2623 passed，53.08s；新增滚动单测 16 项。build（含 typecheck）/关键路径通过，357.8 kB gzip，450 kB 上限未改。
- 较宽 Chromium/documents-mobile 四个 spec：35 passed，3.0m。范围为 education、education-textbook-workbench、education-textbook-learning、documents，不声称仓库所有 Playwright spec 已运行。
- make lint：0 error/55 既有 warning；改动文件 ESLint 与 diff whitespace 检查通过。此前宽 Ruff 检查的 56 条旧测试错误及 870 个待格式化文件仍是已记录基线，不做无关修复。
- 独立复审没有剩余阻断；延迟图片风险已复现并修复，文档检查未屏蔽响应体失败。
- 5177/8000 均仍监听 `0.0.0.0`，PID 工作目录为本 worktree；localhost 与当前 LAN `192.168.1.251` 的页面/health HTTP 200。
- 本轮未删除业务数据、容器、对象或持久卷；专用验收规则已停止，四个验收标签页已关闭，用户原聊天、教材、LangSmith 标签页和家长登录保留。私人脚本、凭据、日志及截图不提交；用户已有业务计划修改不纳入提交。

## 额外边界

大型/多类型教材、长期真实负载、非本机云存储长分区、默认租约等待、真实模型批量失败/取消后迟到/撤销在途竞态没有逐一重跑。对应必须行为已有上述 DB/自动化或真实故障证据，这些是额外覆盖，不新增为 Task 8 必验门槛。

大文件“添加并分析”异步受理优化仍是独立需求；LangSmith 已加载启用，云端完整 trace 接收及耗时分析未在本验收中确认。一次真实运行不保证所有模型及时上报，也不证明全书加工提速；上述限制不写成已实现能力。
