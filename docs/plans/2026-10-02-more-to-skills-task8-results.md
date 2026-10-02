# Task 8 教材真实链路与恢复验收记录

日期：2026-10-02。分支：`feature/more-to-skills-textbook-refactor`。

## 结论与范围

Task 8 和语义进度计划 Task 6 仍在进行中，本记录不是完整验收通过声明。已完成真实模型结构提交、中间知识点首次讲义、真实语义阶段回放、批量默认跳过与真实取消、一组 PostgreSQL 故障边界和浏览器恢复验证，以及专用学生普通 cookie 的学习与撤销链。

继续沿用原分支 `.env` / `agent_config.yaml`，两份配置字节一致；S3 使用 `localhost:9000`。本轮没有重复迁移 082、清理旧教材、删除基础设施容器或改动 volumes。真实加工只操作新增的专用验收教材，家长账号由用户指定，服务解析其已有模型配置，未复制凭据或修改账号设置。

上一批家长浏览器与 HTTP 教材加工验收使用现有 OSS 可信后台身份入口，不是家长普通 cookie 登录的证据。本批学生使用正常登录端点与浏览器登录表单，不携带后台身份请求头；家长分配与撤销仍使用已获授权的 OSS 入口。账号状态、模型凭据、测试登录态、生成夹具和私人日志均不入库到 Git。

## 真实行为

三页合成算术教材经真实 Datalab 解析得到 69 行 Markdown、一张图、脚注、邻近练习及答案。原始内容和图书馆解析产物保留。

- 创建重复请求复用同一教材和初始结构任务。
- 首次模型结构已产出，但服务收尾遗漏可信来源 `line_offset` 而拒绝提交。修复后重试成功，结构有 3 章、4 个知识点，锚点来自冻结原文，讲义仍为 0/4。
- 不生成前两份讲义，直接对第三个知识点（分数、图像模型）执行真实模型任务，成功提交，工作台为 1/4。讲义引用脚注、前后章节、练习与答案，并描述面积模型及数轴。它未嵌入图片，所以不作为“讲义嵌图渲染”证据。
- 实际原文页显示图片，浏览器 `complete && naturalWidth > 0` 成立；375px 文档宽度为 375px，无横向溢出。桌面和移动页面、图片、活动面板均有私人截图核对。
- 真实结构活动依次观察到阅读、整理章节、切分知识点、校验；材料活动观察到阅读、组织、撰写、校验。阶段由 Agent 上报受限代码，中文由服务端映射，成功和计数来自数据库提交，而非模型阶段。
- 材料重复 POST 得到明确 409，无第二个 run；这是“明确冲突”证据，不是 API 幂等复用证据。
- 专用教材批量任务运行中，通过实际工作台点击取消。数据库确认当前 runtime 与 item 均取消，后续 item 的 attempt 为 0、无 runtime，先前成功讲义仍可读。另从 UI 选择全部 4 项且不勾选重做，只创建缺少讲义的 3 项；该任务也已真实取消。

## 本轮修复

1. PostgreSQL 活动事件 `job_id` 的 UUID 在公开投影处转字符串，消除真实 SSE DTO 500。实际 HTTP 已能回放公开事件。
2. 逐字节暂存原文的结构收尾显式提供 `line_offset=0`；保留严格 schema、来源覆盖和锚点校验。
3. 空候选对象的结构 attempt 清理直接返回，避免误报材料前缀无效；有候选的精确清理防护不变。
4. 375px 长标题的隐式网格宽度改为 `minmax(0, 1fr)`，消除目录、返回和操作按钮被推离视口。
5. 前台恢复立即同步 job，不依赖 SSE 首帧；即便 SSE 一直 503 也不等下一个五秒周期。
6. 关闭活动或查看历史 job 时，当前 job 的快照同步继续。job 身份、状态或提交成功数变化刷新教材 query prefix，让结构、讲义和工作台收敛；同一 job 不重复订阅，后台、卸载与终态清理 timer。
7. 首次打开已完成任务仍读取活动；终态分页只有 `has_more=false` 才停止，避免遗漏余下事件。

上述修复均先观察红测试再实现，通过独立代码审查。more-to-skills 目录与技能摘要没有改变。

## 学生 Cookie 链路补验

本批在指定家长家庭与原独立验收家庭各创建一名明确标记的专用验收学生，不使用或修改已有学生凭据。仅把专用算术教材分配给新增学生。

- HTTP `/auth/login` 与实际浏览器登录表单均取得正常学生身份。后续学生请求仅使用会话 cookie，无 `X-Dispatch` / `X-User-Id`。
- 普通 cookie 学生列表首次返回 500：PostgreSQL 的 `textbook_id` 为 UUID，响应模型要求字符串。教育服务改为公开投影字符串；新增路由测试调用真实服务与响应校验，修复前重现相同异常，修复后列表可读。
- 学生成功读取当前结构、已有讲义、69 行冻结原文及授权图片；写入并读取已学进度、批注、划重点、追问，修改批注后生成的节点总结包含对应内容。总结来自确定性学习素材汇总，不冒充模型分析。
- 同一 assignment 两次读取 chat-space 得到同一线程。真实 cookie Flash 追问返回模型正文，家长可读取该 assignment 转录。
- 核对真实 query metadata 发现裸字典教材 directive 被类型化序列化器跳过。教育模块改为返回标准 `DirectiveContext`，沿用普通聊天保存与解析机制。新增 request copy → metadata serializer → directive parser 红/绿回归；真实模型复验确认 PG 保存服务端讲义，丢弃浏览器 sentinel，上次任务账本为 completed。未修复前的追问不算完整持久化上下文证据。
- 跨家庭学生对结构、讲义、原文、图片、笔记与 chat-space 六类读取均得到 404；家长尝试分配外家庭学生也得到 404。未接受跨家庭授权。
- 撤销后教材从学生列表移除，上述六类读取、进度/笔记/总结三类写入及带 assignment 的追问均得到 404；移除教育上下文后复用原学习线程也得到 403，不能降级为普通 Flash 来绕过撤销。
- 临时重新授权后，用真实浏览器保存批注并生成包含该批注的总结；通过 HTTP 再次确认两者已落库。桌面与 375px 的原文图片 `complete && naturalWidth > 0`，移动学习页与总结页 `scrollWidth == innerWidth == 375`，私人截图已目视核对。
- 最终再次撤销专用验收授权，旧学习页和总结页刷新显示不可用。撤销按现有契约级联移除专用 assignment 的进度/笔记/总结和学习空间映射，保留测试聊天线程；未删除普通学生、工作区、聊天、图书馆源或基础设施数据。新增验收账号仍保留且无教材授权，私人凭据未提交。

本批两处产品修复的独立审查均无发现。以上是新增学生的实际链路证据，不替代家长 cookie 一键添加、完整普通产品 live 回归或故障压力矩阵。

## 验收矩阵

| 场景 | 已有证据 | 尚未覆盖的边界 |
|---|---|---|
| 图书馆一次添加 | 真实源冻结/重复创建复用；DB 原子性测试 | 正常 cookie 的完整添加页面流程 |
| 结构-only | 真实模型提交 3 章/4 KP；严格解析器测试 | 大型、多类型教材 |
| 中间 KP 首次生成 | 真实第三 KP 成功，前两份无讲义；原文图片/脚注/邻近内容可用 | 真实讲义嵌图 |
| 已有讲义重做失败 | PG 四项替换批量第三项失败，旧材料保持可读 | 真实模型重做失败 |
| 批量第 3 项失败 | PG 前两项立即可读、第三项失败、第四项成功，retry 仅第三项 | 模型批量全链故障注入 |
| 取消与迟到回调 | 真实 UI/run 取消、后续 attempt=0；PG 当前 fence 拒绝迟到 token | 真实模型取消后迟到结果 |
| 双击/两标签页 | 真实创建复用及材料 409；PG 并发 idempotency | 两个真实 cookie 标签页 |
| 上传/PG finalize 崩溃 | 真 PG 事务回滚及同 attempt 恢复，无重复 material/generation/终态事件；上传为 fake storage | 真实 MinIO 中断、COMMIT ACK 丢失 |
| 关闭浏览器/换 worker | 两个独立 PG 连接，过期 lease/live ledger 经另一 worker 身份 reconcile 不重领；浏览器重连 | OS 进程终止/真正跨进程接管 |
| Redis/150001 delta | PG 活动行数/字节预算与省略摘要；既有 compact projector 单元回归 | 实际 Redis 网络故障、150001 delta 的 PG/Redis/浏览器组合压力 |
| 节点/长文/图片/深链 | 真实原文图像与中间 KP；375px/长标题/512字符/读者滚动/相对链接 E2E | 更多真实节点及长文阅读位置回程 |
| 学生与图书馆反查 | PG assignment/progress/note/chat-space/document-usage；真实学生 cookie 进度/笔记/总结/模型追问及家长转录；浏览器保存笔记/总结 | 家长正常 cookie 的图书馆一键添加 |
| 撤销/跨家庭 | PG ACL；真实学生 cookie 原文/讲义/图片/笔记/chat-space 跨家庭拒绝，撤销后读取/写入/追问拒绝，旧 thread 无上下文复用拒绝；浏览器旧页不可用 | 授权撤销与在途模型提交同时竞态的 live 故障注入 |
| 旧路由/catalog | Task 7 切换清单、PG head catalog、退役路由单元回归 | 无新增清理；沿用 Task 7 证据 |
| 普通产品回归 | 全量后端 unit、前端 unit、真实 managed Docker capability smoke、普通文档 E2E | 普通 PTC/Flash/MCP/subagent/checkpoint/家庭作业完整 live 回归 |

## 验证结果

- 后端全量：`7916 passed, 8 deselected, 1 xfailed, 33 warnings`；新后端修复聚焦：`106 passed`。
- `TEST_DB_NAME=langalpha_test` 教材 books/jobs/activity 三套集成：`42 passed`；开发库未作为自动化隔离测试目标。
- 真实 managed Docker 能力 smoke：`1 passed`，只证明沙箱能力，不替代真实模型生成（模型证据见上文）。
- 前端活动/query/工作台聚焦：`38 passed`。前端全量：`2581 passed, 1 failed`；失败为既有 Plugins `connectReturn.test.ts:223` storage-throws，未改无关代码。
- 工作台 Chromium E2E：`9 passed`，包含 500 事件中途断线/重叠去重、健康但静默 SSE、unavailable、前台恢复、关闭面板后提交可读、迟到旧 job 响应、375px 长内容。Mock 使用真正保持打开的 HTTP SSE；取消按钮可操作的 mock 证据与真实 UI 取消分开记录。
- 较宽教材/文档 E2E 曾为 `17 passed, 1 failed`，文档移动端 body inspection 出现 `Network.getResponseBody` 无资源的间歇错误；聚焦重复两次为 `2 passed`，未改检查或宣称全套通过。
- `pnpm build`（包含 typecheck）及 critical path：通过，`356.4 kB gz`。改动前端 ESLint 0 error/0 warning；`make lint` 0 error/55 既有 warning。
- 改动后端文件 Ruff/format、`git diff --check` 通过。更宽的 `ruff check src tests` 有 56 条无关旧测试错误，format 全目录有 870 个既有待格式化文件，未扩大改动。
- 5177 与 8000 保持 `0.0.0.0` 监听，LAN 页面及 health HTTP 200；不关闭用户前后端服务。
- 学生链路两处修复后重新运行后端全量：`7918 passed, 8 deselected, 1 xpassed, 33 warnings`；本批学生/转录/thread 保护聚焦 `43 passed`。`xpassed` 按实际输出记录，不把它写为新的正常通过用例。
- 重新运行 `TEST_DB_NAME=langalpha_test` 教材三套 PostgreSQL 集成：`42 passed`。首次漏指定 `-m integration` 的命令仅 `13 deselected`，未计为通过；之后显式运行全部三套。
- 两处改动文件 Ruff/格式、独立审查与 `git diff --check` 通过；本批没有改前端代码，既有前端全量失败仍按上面的原始记录保留。配置字节一致，localhost/LAN 5177 与 8000 再次 HTTP 200。

下一批优先补真实多 worker/断流故障，再补组合容量测试和普通产品 live 回归。未完成矩阵行不得在总计划或语义计划标记完成。
