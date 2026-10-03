# Task 8 教材真实链路与恢复验收记录

日期：2026-10-02。分支：`feature/more-to-skills-textbook-refactor`。

## 当前结论（2026-10-03）

总 Task 8/语义 Task 6 按原 15 行矩阵完成，详见[最终收口](2026-10-03-more-to-skills-task8-closeout.md)。已补齐学生作业 UI/未来排程、真实讲义嵌图、刷新及列表历史返回；最终前端2623、后端7930、教材集成48、较宽浏览器35 passed。原矩阵允许自动化或真实行为证据，下面额外未测边界不再列为必验缺口；仍不声称所有故障均走真实模型或所有 Playwright spec 均已运行。

## 历史结论与范围

2026-10-03 后续增量：[家长 Cookie、传输故障与完成结果恢复补验](2026-10-03-more-to-skills-task8-incremental-results.md)已覆盖正常家长登录的完整添加/讲义提交、第二标签页源复用、真实 MinIO 中断/响应丢失、真实 PostgreSQL COMMIT 确认丢失，以及模型已完成结果的跨进程恢复提交。新版 action/工具子预算压力与普通 PTC/MCP/subagent/checkpoint 已补验；教材四套 `48 passed`。下文历史测试记录不冒充本次重跑，最新限制见增量记录，总 Task 8 暂不标记完成。

2026-10-03 增量交付：[业务动作时间线开发细则](2026-10-03-textbook-business-activity.md)已实施，包含可选 action、工具子预算、知识点终态历史、隐藏诊断、独立消费游标与 Skill 指引。新专用教材的数学无例题摘要/语言两原例讲义均真实提交，PG/SSE/browser 一致，聚焦后端 119、PG 45、前端 49、工作台 Chromium 11 passed。详细证据与未做配对性能/token 比较的限制见[新验收记录](2026-10-03-textbook-business-activity-results.md)。下述历史容量数据仍对应原 stage-only 与共享预算，不冒充新版本组合压力结果；总 Task 8 原未完成项不变。

Task 8 和语义进度计划 Task 6 仍在进行中，本记录不是完整验收通过声明。已完成真实模型结构提交、中间知识点首次讲义、真实语义阶段回放、批量默认跳过与真实取消、PostgreSQL 故障边界和浏览器恢复验证，以及专用学生普通 cookie 的学习与撤销链。本批补齐普通 runtime 的真实多进程故障、教材账本的 OS owner-loss 恢复，以及真实 PostgreSQL/Redis/浏览器组合容量与 Redis 断连回放。

继续沿用原分支 `.env` / `agent_config.yaml`，两份配置字节一致；S3 使用 `localhost:9000`。本轮没有重复迁移 082、清理旧教材、删除共享基础设施容器或改动持久 volumes。真实加工只操作新增的专用验收教材，家长账号由用户指定，服务解析其已有模型配置，未复制凭据或修改账号设置。

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

## 多进程故障与组合容量补验

本批未改产品代码或 more-to-skills。普通 runtime gate 复用 `scripts/multiworker_gate/gate.py` 的既有 cell，只将 Docker backend 控制替换为精确持有的本机进程句柄；临时 backend 使用 8841/8842，指定家长的已有模型配置仍由正常服务解析。请求使用 OSS 后台身份入口，不计为普通 cookie 登录证据。

- 首批 `5/5`：并发 START 返回 200/503 且只有一个 open run；另一 worker 取消及重复取消成功；同 request key 返回 409 与同一 run 身份；SIGSTOP 后 SIGKILL owner，另一 scanner 收为 `error`、`recovery=scanner`；SIGTERM owner 由自身收为 `cancelled`，无 scanner 来源且不是用户取消。
- 次批 `4/4`：Redis 在 START 前不可用时返回 503，request key 无 run 行；运行中断 Redis 后收为 `error`，持久化 `terminal_error_type=src.server.services.runs.stream_writer.TransportLostError`；另一 worker 活跃运行期间 compact/delete 均返回 409。首次验收脚本误查字面量 `transport_lost`，核对实际字段后修正脚本并重跑四项，未改生产异常协议。

容量与教材 owner-loss 使用 `langalpha_test`，未向开发库注入合成教材。Redis 使用本批创建的 127.0.0.1:6389 专用容器，`/data` 为 tmpfs、无持久卷、禁用持久化；从未停止或清空共享 6379。临时验收 backend/frontend 使用 8843/5188，5177/8000 保持运行。

- 全新夹具经真实 producer compact 过滤、活动 observer、PostgreSQL 写入及 Redis stream writer，逐条送入 `150001` 个约 8 KiB 原始 delta、2000 个工具开始、2000 个工具结果和一个受限阶段。输入为合成事件，不冒充真实模型生成或 1 GiB 网络传输。
- PostgreSQL 保留 1000 条明细，共 `293280` 字节，最大单条 `295` 字节、说明最长 `56` 字符；另有一条可更新省略摘要，`dropped_count=3001`。原始 delta 不计为公开活动，未发现私有正文 sentinel。
- Redis stream 与 producer accumulator 各保留一条 metadata，未缓冲全部原始流。脚本对 Redis 字段和值的计量为 `148` 字节，不等同 Redis 总内存占用。本次顺序处理耗时 `4.72` 秒，不作为吞吐量承诺。
- 实际浏览器回放后，活动 DOM 有界为 1000 行：终态前为 999 条工具明细加摘要，终态加入后为 997 条工具明细加三个里程碑。展开明细可读；375px 下 `scrollWidth == innerWidth == 375`，无私有正文 sentinel，私人桌面/移动截图已核对。合成源没有真实存储对象，空原文不计为读者内容验收。
- 实际 HTTP 教材 SSE 已订阅时停止专用 Redis，再经正常数据库失败接口提交终态。订阅收到两个页面，最终 `failed`、`has_more=false`，补齐两条终态事件，游标为 1004，耗时 `0.933` 秒；浏览器也更新为失败。证明 PostgreSQL 轮询能脱离 Redis wake 恢复事实，不代表 runtime 可以无 Redis 继续执行。
- 教材专属 owner 进程使用真实 `WriterGuard` 持有教材 thread 的 PG 写锁，创建并绑定正常 runtime 与 item 账本。另一 backend 的 scanner 存活时只续租，run/item/job 仍活跃，attempt=1；精确 SIGKILL owner 后，另一进程 scanner 收 run 为 `error`，教育 reconcile 收 item/job 为 `failed`。attempt token 和 execution ID 不变，只存在一个 run、两条终态活动，迟到失败回调被 fence 拒绝。此项是合成教材账本的真实 OS 退出证据，不是模型/沙箱生成中断后恢复提交或自动断点续跑。

验收脚本的 Redis 初始化/收尾接口已按真实客户端修正，容量结论来自之后的全新夹具。隔离库集成 suite 会重建 schema，首次与 owner-loss 并行运行清掉了验收夹具；该次不计为通过。随后停止临时 backend，集成 `42 passed`，再单独重建 owner 并完整复验成功。今后这两类验收必须串行执行，不可让后台队列扫描与隔离库重建争用。

最终临时 worker/frontend 和命名浏览器均已停止，8841/8842/8843/5188/6389 无监听。已删除本批专用 tmpfs Redis 容器及其一次性测试缓存，未删除任何持久卷或共享容器；普通 gate 的测试线程保留。隔离库容量夹具随集成 schema 重建清除，最后的 owner-loss 夹具仍留在隔离库。私人脚本、日志、身份和截图不提交。

## 验收矩阵

| 场景 | 已有证据 | 额外未覆盖边界（非必验缺口） |
|---|---|---|
| 图书馆一次添加 | 家长正常 Cookie 上传/AnyDoc 解析/首次添加，实际结构及讲义成功；PG 同源一个教材、一个初始任务；第二标签页重复添加复用 | 大文件冻结的异步响应优化不在本轮实现 |
| 结构-only | 真实模型提交 3 章/4 KP；严格解析器测试 | 大型、多类型教材 |
| 中间 KP 首次生成 | 真实第三 KP 成功，前两份无讲义；原文图片/脚注/邻近内容可用；最终专用真实讲义嵌图，授权HTTP/browser/375px通过 | 更多教材类型 |
| 已有讲义重做失败 | PG 四项替换批量第三项失败，旧材料保持可读 | 真实模型重做失败 |
| 批量第 3 项失败 | PG 前两项立即可读、第三项失败、第四项成功，retry 仅第三项 | 模型批量全链故障注入 |
| 取消与迟到回调 | 真实 UI/run 取消、后续 attempt=0；PG 当前 fence 拒绝迟到 token | 真实模型取消后迟到结果 |
| 双击/两标签页 | 真实创建复用及材料 409；PG 并发 idempotency；两个正常 Cookie 标签页顺序重复添加源复用 | 没有把顺序 UI 复用写为同时提交 |
| 上传/PG finalize 崩溃 | 真 PG 事务回滚；真实 MinIO body 中断及接受 PUT 后丢响应；真实 COMMIT CommandComplete 丢失；同 attempt 恢复、已提交不再生成、候选收尾保留对象 | 非本机云存储网络及长时间分区 |
| 关闭浏览器/换 worker | 浏览器重连/刷新；普通 runtime OS 故障；教材 owner-loss 收敛失败；真实模型完成后临时 worker 未提交即退出，原 8000 worker 从原沙箱提交同一 attempt，无第二次生成 | 默认租约等待时间未压测；本次精确加速专用 item 租约过期 |
| Redis/150001 delta | 旧版 PG/Redis/browser 组合与 Redis 断连终态补齐；新版 150001 delta/4000 工具/250 action，1000 明细/800 工具/200业务/298430字节、单摘要/3250省略、Redis及producer各1条；新版隔离 HTTP/browser 桌面/375px 默认203业务行、展开1000行，无横向溢出/raw泄漏 | 长期真实模型负载；合成事件和测试身份回放不作模型吞吐或普通Cookie证据 |
| 节点/长文/图片/深链 | 真实原文与讲义图像、中间KP；375px/长标题/512字符/相对链接E2E；真实刷新及列表历史返回，冷正文/图片独立视图恢复回归 | 更多真实教材/节点组合 |
| 学生与图书馆反查 | PG assignment/progress/note/chat-space/document-usage；真实学生 Cookie 进度/笔记/总结/模型追问及家长转录；家长正常 Cookie 图书馆添加 | 更多真实教材/节点的组合覆盖 |
| 撤销/跨家庭 | PG ACL；真实学生 cookie 原文/讲义/图片/笔记/chat-space 跨家庭拒绝，撤销后读取/写入/追问拒绝，旧 thread 无上下文复用拒绝；浏览器旧页不可用 | 授权撤销与在途模型提交同时竞态的 live 故障注入 |
| 旧路由/catalog | Task 7 切换清单、PG head catalog、退役路由单元回归 | 无新增清理；沿用 Task 7 证据 |
| 普通产品回归 | managed Docker、runtime gate9项；正常家长Cookie PTC/MCP/子代理/刷新续轮/checkpoint；学生Flash；专用g3学生作业UI、家长反馈、学生刷新/正常Cookie API、未来三日日历幂等；字典/Plugins缺口关闭；最终前端2623、后端7930、较宽四spec浏览器35 passed | 长期负载；字典历史缺失原因未确定但当前功能已恢复 |

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

- 本批普通 runtime 多进程真实模型 gate 分批 `5/5` 与 `4/4`；全新容量夹具及 live HTTP Redis 断连检查通过，教材真实写锁 owner-loss 在隔离库集成结束后独立复验通过。仅补验收证据，无产品代码修改。
- 本批重新执行教材三套 PostgreSQL 集成：`42 passed in 65.33s`。此前后端/前端全量记录保持原日期和原结果，不冒充本批重新运行；既有 Plugins 失败仍未消除。
- `.env` 与 `agent_config.yaml` 再次与原分支字节一致，5177/8000 本机及当前 LAN HTTP 200，共享 PostgreSQL/Redis/MinIO 均仍运行。

最新状态以[最终收口记录](2026-10-03-more-to-skills-task8-closeout.md)为准，总 Task 8/语义 Task 6 按原矩阵完成；上文历史失败保留日期语境。8000已加载用户LangSmith配置，但云端完整trace接收及指标分析不是本矩阵的完成证据，仍单独保留。
