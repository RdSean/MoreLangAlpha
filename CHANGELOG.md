# 变更日志

## 2026-10-03

### 完善：可选业务报告 Skill 指引与真实教材验收

- more-to-skills 仅增加通用可选报告约定及读取/组织/写作/校验局部提醒，内容范围优先，词表不是动作清单；无工具/不可用继续加工，不模拟报告、不重试循环。managed prompt 对齐契约，Skill manifest 锁定同步更新，schema/版本/模板/脚本不变；切换前在途教材任务为 0。
- 正常图书馆上传/解析及真实结构分析后，专用数学无例题摘要和语言两个原例讲义均成功，实际报告细动作，PG 与完整 HTTP SSE 逐条一致，桌面/375px 工作台可回放且默认不显示工具。未新增例题、练习、词汇站或图片，未重做用户教材或复制模型凭据。独立提示应用场景与代码复核完成，后端聚焦最终 119 passed。
- 更新总计划、语义计划/设计、业务细则与新增验收记录；如实保留全量前端既有失败、无法取得持久 token/同条件配对性能数据及旧组合压力未重跑限制。总 Task 8 仍未完成，5177/8000 与共享容器/持久数据保持原状。

### 完善：按知识点回放业务历史并默认隐藏诊断

- 工作台按可信 item 身份与快照知识点标题展示业务历史，终态和刷新后仍保留实际动作；当前加工对象独立于阅读选中项，相邻重复合并但回退/跨项保留。进度只用中性标记，可靠提交才显示成功，取消不显示成功勾。
- Bash/Edit 等工具明细默认不挂载到页面，键盘可展开诊断，切换任务恢复收起；有界客户端缓存优先保留业务事件，重连使用独立已消费游标，移动省略摘要只保留一份。401/403/404 清除缓存和游标并拒绝迟到回调。
- 前端聚焦 49 passed，工作台 Chromium 11 passed（含桌面/375px 终态标题回放、长标题纯文本、诊断键盘操作、断流/静默/旧响应）；typecheck/build/关键路径和改动文件 ESLint 通过。全量前端 2592 passed、1 failed，仍为无关 Plugins storage-throws；后端全量 7928 passed、8 deselected、1 xfailed，make lint 为 0 error/55 既有 warning。Skill 与真实模型验收继续收口，不宣称总 Task 8 完成。

### 开发：教材可选业务动作与工具预算保护

- `report_progress` 增加可选 action，材料任务下发八项跨学科动作及触发条件；教育 observer 校验任务类型/阶段/动作，映射受控文案并独立节流，保留旧 stage-only 调用。
- 活动账本在原 PostgreSQL 行锁与 attempt fence 下增加工具子预算（800 条/768 KiB），工具满额后仍可保存业务进度；省略摘要保持合并，终态沿用原事务保障。授权任务快照补充知识点标题，为前端分组提供确定来源。
- 新增行为先复现再实现，后端聚焦 93 passed，教材 PostgreSQL 集成 45 passed，涵盖并发容量、行数/字节上限、新 observer 和标题授权；独立静态审查未发现后端新问题。前端与 Skill 仍在本轮后续开发，完整时间线尚未交付。

### 计划补充：活动时间线的知识点标题与分组

- 明确标题来自服务端已入库教材结构，经授权任务快照返回；Agent 仍只报告阶段/动作，知识点标题不是新增动作或事件。
- 补齐按 item 身份和事件顺序分组、当前加工对象标注、同名知识点与标题缺失处理，以及刷新回放和 API/界面验收要求。仅更新计划，未修改产品代码或运行服务。

### 计划：教材业务动作时间线开发细则

- 补写八项跨学科可选动作及触发条件，明确“澄清概念与术语”“原文示例”不要求额外词表、例题或练习；规划扩展现有 `report_progress` 与 Skill 可选报告说明，完成状态和计数仍以服务提交为准。
- 细化终态业务历史、默认隐藏的工具诊断、工具预算子上限，以及显示缓存与重连消费游标分离；增加 Skill 摘要切换前的在途任务检查、聚焦测试和真实模型验收矩阵。
- 总计划、语义设计/实施计划与 Task 8 记录已关联此增量。此次仅文档，未修改产品代码、实际 Skill、数据库、配置或运行服务；新方案尚未实施，Task 8 仍未完成。

## 2026-10-02

### 验收：多进程恢复与教材活动组合压力

- 普通 runtime 使用真实模型补验多进程 START、重复 request key、跨 worker 取消、SIGSTOP/SIGKILL、SIGTERM、Redis 前置拒绝/运行中明确失败及活跃运行期间 compact/delete 保护，分批 5/5、4/4。教材专属真实 WriterGuard owner 被精确 SIGKILL 后，另一进程 scanner/reconcile 收敛 runtime 与业务失败，attempt/execution 不变，无第二个 run，迟到回调被拒绝；不冒充真实模型断点续跑。
- 全新隔离夹具的 150001 合成 delta 与 4000 工具事件经真实 PG/Redis/浏览器链保持有界：1000 明细/293280 字节、一个省略摘要/3001 次省略，Redis 与内存回放各一个 metadata。375px 展开明细无横向溢出或私有正文泄漏；停止专用 Redis 后，实际 HTTP SSE 在约 0.93 秒内由 PG 补齐终态。
- 教材 PostgreSQL 三套复跑 42 passed；隔离库 schema 重建与活 worker 验收改为串行，受夹具清理影响的首次 owner 检查不计为通过。临时 backend/frontend/浏览器已停止，专用 tmpfs Redis 及一次性缓存已删除，未删除持久卷、共享容器或开发数据；原配置字节一致，5177/8000 本机及 LAN HTTP 200。
- 本批仅更新验收记录、总计划与语义计划，不改产品代码或技能。Task 8/语义 Task 6 仍进行中，真实 MinIO/COMMIT ACK、模型已完成结果的跨进程提交恢复、家长 cookie 添加与普通产品完整 live 链尚待验收。

### 验收：学生 Cookie 学习与教材撤销链

- 新增两名专用验收学生，以正常登录 cookie 验证原文/授权图片/讲义、进度、批注/重点/追问、确定性节点总结、真实 Flash 追问与家长转录；浏览器登录、笔记和总结保存、桌面及 375px 图片/布局均已核对。
- 跨家庭六类读取与外家庭分配被拒绝；撤销后读取、学习写入、带教材上下文追问及旧教育 thread 的无上下文复用均被拒绝，旧学习页和总结页刷新不可用。最终撤销专用验收授权，只按契约清除其临时学习记录；保留测试聊天和账号，未修改原有学生数据。
- 真实链路中发现的列表 UUID 和 directive 保存问题已分别修复并提交；本批后端全量 `7918 passed, 8 deselected, 1 xpassed`，教材 PostgreSQL `42 passed`，学生聚焦 `43 passed`。配置与基础设施 volumes 不变，5177/8000 本机及 LAN 均 HTTP 200，私人凭据/登录态/截图不提交。
- 已更新总计划、语义计划及 Task 8 矩阵。Task 8 仍未完成，下一批继续真正多进程接管、Redis 网络故障及组合容量/普通产品 live 验收。

### 修复：教材学习上下文沿用聊天持久化契约

- 真实学生 Flash 追问返回成功后，数据库核对发现裸字典上下文可被运行时读取，却被现有类型化 metadata 序列化器跳过。教育模块改为返回标准 `DirectiveContext`，不修改聊天运行主干或持久化器，也不放宽学生授权。
- 新增先失败后通过的 request copy → 真实 metadata 序列化 → directive parser 回归，验证冻结讲义可保存且浏览器伪造上下文被丢弃。真实模型复验确认 query metadata 含服务端讲义、无客户端 sentinel，runtime ledger 为 completed。
- 验证：学生相关聚焦 `43 passed`；后端全量 `7918 passed, 8 deselected, 1 xpassed, 33 warnings`；隔离库教材三套集成 `42 passed`。改动文件 Ruff/格式、`git diff --check` 与独立代码审查通过，未改 more-to-skills 技能、模型凭据或基础设施 volumes。

### 修复：学生教材列表的 UUID 公开投影

- 普通学生 cookie 登录真实验收发现 `/education/learning` 将 PostgreSQL UUID 直接交给字符串 DTO，导致列表返回 500；在教育服务公开投影处转换教材 ID，不改变数据库类型、API 字段或家庭授权规则。
- 新增使用 PostgreSQL 形态 UUID、真实教育服务及 FastAPI 响应校验的失败复现测试；学生阅读、笔记、总结、追问与 thread 保护聚焦回归 `42 passed`，隔离库教材集成 `13 passed`，改动文件 Ruff/格式检查通过。普通 cookie 列表已恢复，Task 8 仍在进行中。

### 完善：教材真实链路与活动恢复验收

- 修复 375px 长标题撑开隐式网格；前台恢复立即同步 job，活动关闭或查看旧 job 时继续同步当前任务；提交状态/数量变化刷新教材结构、材料与工作台缓存，不让新讲义停留在不可读状态。
- 首次打开已完成任务仍回放活动，终态分页在 `has_more=false` 后才结束。新增真实保持打开的 mock SSE、500 事件中途断流/重叠去重、静默或 unavailable、迟到响应、关闭面板后提交可读及移动长内容验收。
- 新增真实 PostgreSQL 四项部分失败批量、双连接/另一 worker 身份 reconcile 与上传后事务回滚恢复用例；明确不代表 OS 进程接管、真实 MinIO 中断或 COMMIT ACK 丢失。
- 用户指定账号的现有模型实际完成结构与第三个知识点讲义，前两项无讲义仍成功，真实活动观察到 structure/material 各四类语义阶段。原文图片在桌面/375px 可读，讲义引用脚注、邻近章节与练习且描述图像，但未嵌图；未将此写为讲义图片渲染通过。
- 实际工作台批量默认只生成缺少讲义的 3 项；真实 UI 取消确认当前 runtime 取消、其余 attempt=0、已成功讲义仍可读。重复材料请求明确 409、无第二个 run，不误记为幂等复用。
- 验证：最终教材 PostgreSQL `42 passed`、后端全量 `7916 passed`；前端聚焦 `38 passed`、工作台 Chromium `9 passed`、build/typecheck/critical path（356.4 kB gz）与改动文件 ESLint 通过。前端全量 `2581 passed, 1 failed`，仍是无关 Plugins storage-throws 既有失败；更宽文档移动 E2E 的间歇 body inspection 失败和聚焦复验结果如实保留。
- 总 Task 8/语义 Task 6 仍在进行中；完整故障、学生 cookie 权限、多 worker 和组合容量边界见 `docs/plans/2026-10-02-more-to-skills-task8-results.md`。5177/8000 与 LAN HTTP 200 保留，配置和基础设施 volumes 未变，私人夹具/凭据/日志不提交。

### 修复：真实教材结构提交与活动回放契约

- 真实 PostgreSQL 活动页在公开投影处将事件 `job_id` 转为字符串，修复 SSE 严格 DTO 校验返回 500；保留 UUID 数据库类型、公开 DTO 和既有分页/游标协议。
- 教材原文逐字节暂存后，结构收尾明确提供 `source_lines` 的 `line_offset=0`，修复模型已完成但来源验收失败的问题；不放宽 schema、不转换锚点、不修改 more-to-skills 技能。
- 无候选对象的结构 attempt 清理直接返回，不再误报材料候选前缀无效，也不枚举或删除存储对象。
- 三处均先复现失败再修复；新增实际结构解析器收尾测试与真实 PostgreSQL 活动页 DTO 校验。聚焦后端 `106 passed`、活动集成 `10 passed`；最终全量后端 `7916 passed, 8 deselected, 1 xfailed`、教材 PostgreSQL 三套集成 `42 passed`、`make lint` 通过（前端 0 error/55 既有 warning），改动文件 Ruff/格式检查通过。
- 已使用用户指定家长账号的现有模型配置实际执行教材结构加工，公开回放观察到阅读、整理章节、切分知识点、校验四个语义阶段；未复制凭据或修改账号配置。真实结构重试和中间知识点讲义验收继续进行，不能据此宣称 Task 8 完成。

### 重构：教材旧链退役并完成开发库一次切换

- 删除旧教材 SQL 模块、20 个旧加工/审阅/进度/资产服务及其专用测试，移除版本、候选确认、讲义审批、发布 API/DTO、旧配置开关与 `book-to-skill` 分发注册。新教材继续使用单页工作台和当前授权，普通 PTC/Flash/MCP/subagent/checkpoint、家庭作业与图书馆源数据保留。
- 暂存技能不再依赖个人目录或旧教学资产适配器；`skill_sha256` 改为实际暂存目录的确定性路径/内容 manifest 摘要，工具脚本变化也会在上传前被拒绝，完整上传后只读封存。旧 JSONL helper 特例、version/position 快照目录和根路径 fallback 删除。
- 082 在破坏旧资源归属账本前拒绝活动旧任务/run、旧学习空间和旧 managed workspace；隔离 PostgreSQL 验证阻止升级后数据/revision 不变，并验证 081 升级与空库 head catalog 一致。对象清理脚本支持新教材准确 source/materials/supplementary 前缀，拒绝 household/textbooks 根范围。
- 已按用户授权与升级前私人清单，将开发库 081 升级至 082，删除 3 本旧教材、33 个精确旧托管 workspace/thread 及其运行消息/checkpoint、32 个无挂载旧 sandbox 容器、355 个教材派生对象（37,590,655 字节）和 17 个旧线程 Redis 回放缓存。旧对象未启用版本保存且未做内容备份，删除不可恢复；未使用 prune/FLUSHDB，基础设施容器及 volumes 保留，23 项图书馆/家庭作业/普通会话保护计数未变。详细范围与未完成验收见 `docs/plans/2026-10-02-more-to-skills-cutover-results.md`。
- 验证：最终后端 unit `7914 passed, 8 deselected, 1 xfailed`；教材 PostgreSQL 集成 `39 passed`；真实 managed Docker `1 passed`；前端 typecheck/build/关键路径检查通过（356.4 kB gz）。前端全量 unit 为 `2578 passed, 1 failed`，聚焦复查同一 Plugins `connectReturn` storage-throws 既有失败，教材及相关导航用例通过；未借本次清理修复无关插件行为。
- CI 教材浏览器 fixtures 已切换到当前工作台、学生讲义与授权契约；移除退役加工/教学包/审批/发布断言，保留家庭作业和普通文档测试。最终统一 Playwright 聚焦复验 `12 passed`（含桌面、375px 与 documents-mobile），三份改动 E2E 的 ESLint/语法检查通过；非教材解析方法选择、作业创建、附件重交三个浏览器基线失败未改，未宣称全量 E2E 通过。
- 5177/8000 继续由本 worktree 监听，LAN HTTP 均为 200；存储按用户确认沿用原 `.env` 的 `localhost:9000`。Task 8 的真实模型、故障注入、多 worker 与完整权限/浏览器链路验收仍未完成。

### 重构：图书馆教材使用查询切换到当前教材模型

- 文档教学使用反查改为直接连接 `documents` 与新 `education_textbooks` 冻结来源字段；结构状态来自当前结构和最近 structure job，讲义 N/M 来自当前 KP/material 记录，不再 JOIN version、旧 structure、publication 或多来源 position。
- 后端 DTO 与既有前端契约统一为解析任务、主产物、教材、冻结来源、结构状态、讲义计数和更新时间；移除 content version、publication、资产 manifest 及对象存储细节，链接继续直达教材工作台。
- PostgreSQL 行为测试覆盖排队教材、结构提交后的 ready 状态与 0/1 讲义计数，以及文档所有者和当前家长成员权限；Task 6 的学生授权、阅读/笔记/总结、Flash 上下文、家长转录和图书馆消费者至此完成接线，Task 7 旧代码与资源清理尚未开始。
- 验证：Task 6 相关后端单元测试 `48 passed`，`langalpha_test` 082 集成 `13 passed`，学生与文档前端测试 `32 passed`；`pnpm typecheck`、`pnpm build`、关键路径检查、Ruff、格式和 `git diff --check` 通过。5177/8000 均返回 200，未向开发数据库应用 `082`，未改动 Docker volume。

### 重构：学生 Flash 学习会话切换到当前教材授权

- 学习空间、学生 thread 识别和家长转录查询改接 082 的教材 assignment，不再经过 publication/version 表；同一 assignment 并发复用唯一的学生私有 Flash thread。
- Flash 每轮由服务端重新校验学生授权，读取当前成功讲义及当前结构中的知识点标题，并把当时内容冻结为本轮 directive；浏览器附带上下文会被丢弃，未生成讲义、猜测 KP 或撤销授权均不能注入学习材料。
- 撤销教材授权会在同一事务中移除学习空间映射后删除 assignment，但保留原 conversation thread；服务端创建时写入的教育标记继续阻止旧会话被普通 Flash 消息复用或由通用 thread API 删除。
- 验证：Flash 上下文、家长转录、thread 保护及相关教材门面单元回归 `41 passed`，`langalpha_test` PostgreSQL 教材集成 `12 passed`；5177/8000 均返回 200，未向开发数据库应用 `082`，未改动 Docker volume。

### 重构：学生笔记、进度与总结切换到新节点模型

- 学生学习页直接复用教材工作台的 Skill node/KP 导航、授权原文切片与阅读器；URL 保存 Skill KP ID 或 node ID，服务请求和进度写入使用当前结构映射出的数据库 KP UUID。移除版本号和“已发布”措辞，未生成讲义时直接展示原文。
- 学习进度与笔记 CRUD 改接 082 的 `textbook_id + knowledge_point_id` 和 `skill_node_id` 字段；新增、修改、删除同时校验学生、assignment、当前结构与教材归属，跨 assignment URL 不能修改 item。
- 个性化总结按递归 Skill 节点及其当前 KP 汇总，不再构造旧 Unit DTO；学生列表展示当前知识点完成数，旧 `/units/...` 与 `/knowledge/...` 学生阅读路由已移除。
- 验证：Education 前端回归 `84 passed`，学生相关后端回归 `56 passed`，`langalpha_test` 082 集成 `11 passed`；前端类型检查、聚焦 ESLint、生产构建与关键路径检查及后端 Ruff 通过。未向开发数据库应用 `082`，未改动 Docker volume。

### 重构：学生教材读取切换到当前结构与讲义

- 学生学习列表与稳定 assignment URL 改为读取 `education_textbook_assignments` 的教材授权；结构和讲义复用新教材门面的当前成功内容，不再通过 publication、version 或 revision 冻结链路。
- 新增严格的学生 assignment、结构和讲义响应 DTO；结构保留 Skill node/KP ID 与数据库 KP UUID 映射，讲义缺失时显式返回 `material_available=false`，响应不再暴露旧发布字段。
- 新数据库查询按 `assignment_id + student_user_id` 解析教材，并只统计当前结构的知识点与已读进度；跨学生 assignment 不可见，撤销授权后现有结构、原文、讲义和图片门面继续统一拒绝。
- 验证：聚焦学生 HTTP/facade 单元测试 `2 passed`，`langalpha_test` PostgreSQL assignment 集成测试 `1 passed`；未向开发数据库应用 `082`，未改动 Docker volume。

### 完善：教材工作台学生授权闭环

- “给学生使用”接入新教材 assignments 门面；弹窗只列出同家庭学生，打开时回显当前授权，保存时分别批量提交新增与移除的差集，不恢复 publication、revision 或逐讲义审批流程。
- 新增教材授权 TypeScript DTO、API、query key 和 React Query hooks；变更成功后同时刷新授权列表与工作台计数。提交期间锁定关闭和重复操作，失败保留当前选择并可原位重试，加载失败与无学生账户均有明确状态。
- 验证：API 与工作台聚焦回归 `19 passed`，`pnpm typecheck`、聚焦 ESLint、`pnpm build`、关键路径检查及 `git diff --check` 通过；5177/8000 继续由当前 worktree 进程监听。独立浏览器没有有效登录态，因此未把真实授权写入开发数据，也未宣称本轮真实页面验收通过。

### 重构：教材工作台切换到新后端门面

- 家长教材来源、创建、列表、工作台、结构、原文和讲义接口已改接 more-to-skills 新表；创建时冻结当前 Skill/schema 身份并同时排队初始结构任务，不再通过空教材、版本或 publication DTO。
- 新查询把家庭角色校验内聚到 PostgreSQL，跨家庭教材、结构、KP 和资源统一不可见；工作台状态与讲义 N/M 来自当前结构及已提交材料，`content_file` 仅由当前材料记录确定性投影。
- 原文和讲义只读取数据库授权的不可变对象指针，并校验前缀、大小和 SHA-256；图片只按教材 manifest 中的 `asset_id` 解析，由应用私有响应返回，Markdown 本地图片引用改写到授权接口，不暴露 MinIO key 或公开 URL。
- 工作台材料任务创建、取消和重试已接入现有 PostgreSQL 队列及真实 runtime cancel；创建冻结当前 Skill 身份，重试以源 job 为幂等范围，取消在任何运行信号前先验证家长 ACL，三者均回读同一公开 job 快照。
- 新增教材最小学生授权的查询、批量分配与批量撤销接口；分配在单一事务中完整校验同家庭学生，结构、原文、讲义和图片读取统一接受家庭家长或当前已分配学生，生成、活动和任务控制仍仅限家长。撤销后所有内容入口即时失效。
- 验证：教材 facade/路由/存储/DTO/job 单元回归 `91 passed`，`langalpha_test` PostgreSQL 新表集成 `11 passed`；前后端仍健康监听 `0.0.0.0:5177`/`0.0.0.0:8000`，未向开发数据库应用 `082`，未改动 Docker volume。

### 完善：教材工作台原文定位与阅读连续性

- 原文读取在知识点或目录锚点前后各保留最多 12 行上下文，并通过 Markdown AST 将正文块映射回绝对来源行；只高亮与真实锚点相交的块，阅读标题仍显示所选锚点而非扩展范围。
- 讲义与原文分别保存滚动位置，切换视图、知识点或组件重挂载后可恢复；受控的 `materials/<knowledge-point-uuid>.md` 相对链接在工作台内导航，目标尚无讲义时直接打开对应原文，不接受任意路径或对象存储 key。
- 通用 Markdown 允许调用方注入可信的清洗后 AST 转换，并为受控文件链接保留可访问 `href`；教材层继续只通过显式回调处理内部导航。授权图片映射仍留待 Task 6 后端 facade，不从存储路径推导 URL。
- 新增桌面与 375px Playwright 工作台验收，覆盖目录抽屉、原文高亮、讲义/原文切换、内部链接、批量设置、活动面板和横向溢出；补齐移动图标按钮的可访问名称，并让目录、活动及批量操作避开底部导航。
- 验证：教材工作台聚焦单元测试 `37 passed`，Playwright 场景 `4 passed`；`pnpm typecheck`、`pnpm build`、关键路径检查、聚焦 ESLint（0 error）与 `git diff --check` 通过。

### 完善：教材批量生成与失败恢复控制

- 批量生成改为先原位确认深度和补充要求，默认仅提交尚无讲义的知识点；界面明确列出所选数量及会被替换的已有讲义数量，只有显式勾选重做才把已有讲义加入任务。
- 活跃任务期间保留教材阅读并阻止并发生成，可直接取消本次任务；失败、部分成功或取消的最近任务可按原 job ID 重试，由服务端确定失败和未运行项，成功后自动打开新任务活动。
- 批量请求继续只使用当前结构映射出的数据库 KP UUID；提交成功后清理选择状态，重做失败时既有成功讲义仍由当前材料记录提供。
- 验证：工作台、导航与活动面板聚焦测试 `30 passed`，`pnpm typecheck`、`pnpm build`、关键路径检查、聚焦 ESLint 与 `git diff --check` 通过；前后端进程工作目录仍属于当前 worktree，未迁移开发数据库或改动 Docker volume。

### 重构：教材列表与单页工作台首轮切换

- 将家长端教材入口收敛为“教材列表 → 教材工作台”：工作台以 Skill KP ID/node ID/view 维护 URL，左侧可切知识点与递归原书目录，右侧原位阅读讲义/原文和提交生成参数，活动面板继续由 `activity=<job-id>` 控制。
- 新增显式批量选择基础交互、来源闭区间读取、数据库 KP UUID 转换及无讲义时原文优先；教材列表改为结构状态、已提交讲义 N/M 和当前活动入口，不再展示版本、候选审阅或发布状态。
- 旧处理、结构审阅、候选确认和讲义审批页面及其专用 stepper、轮询卡片、设置对话框、CSS、测试、lazy chunk、API hooks 与 query keys 已删除；旧深链只进入不请求旧 API 的静态重置页。
- 图书馆新增共享单选来源面板：同一文档默认选择最新成功解析产物，可修改教材名，“添加并分析”一次提交来源、教材与幂等键，成功后直达工作台初始活动；文档详情也提供相同入口。
- 图书馆 teaching-usage 前端 DTO 改为固定解析来源、结构状态和已提交讲义计数，链接直达工作台；移除 content version、publication、asset manifest 和知识包展示语义。
- 验证：教育、图书馆、通用路由及 query key 前端回归 `191 passed`，`pnpm typecheck`、`pnpm build`、关键路径检查、聚焦 ESLint 与 `git diff --check` 通过；前后端仍监听新 worktree 的 `0.0.0.0:5177`/`0.0.0.0:8000`。完整后端工作台、学生与图书馆门面继续归 Task 6，未向开发数据库应用迁移 `082`，未改动 Docker volume。

### 新增：教材工作台可恢复活动时间线

- 新增与托管教材 job/item/activity DTO 对齐的前端类型、任务查询键和可取消 SSE reader；活动页先完整校验并成功合并后才推进 `last_processed_seq`，空页和高水位不跳读，重放按 seq 去重，过期游标清空缓存后从 0 重建。
- 新增任务级活动订阅 hook，以 PostgreSQL job 快照作为状态和计数真值；业务通知按每秒一次合并并保留尾随刷新，可见活跃任务每 5 秒兜底，后台、卸载、任务切换及权限终止会清理 stream 与 timer。
- 新增分层活动面板：材料 N/M 仅统计成功 material item，supplementary 单列，当前项只取 running item；合法语义阶段显示在主线，Read/Bash 等工具事件收进折叠明细，断线重连和活动不可用不会被显示为任务失败。
- 活动面板由 `activity=<job-id>` URL 状态控制，展开运行明细不改变 URL 或正文滚动；控件使用稳定尺寸、可换行长文、减弱动画支持和 44px 关闭目标，为后续单页教材工作台接线保留窄屏布局边界。
- 验证：活动投影、URL、分页重连、游标和订阅生命周期聚焦测试 `19 passed`，连同既有教育查询回归共 `26 passed`；`pnpm typecheck`、`pnpm build`、关键路径检查及 `git diff --check` 通过。完整工作台与真实后端门面仍按后续任务接线，未迁移开发数据库或改动 Docker volume。

### 新增：可恢复的教材任务快照与活动流 API

- 新增家长授权的教材任务快照接口，以单条 PostgreSQL 语句读取同一时点的 job 与有序 items；公开投影包含 structure/material/supplementary 类型和业务状态，不暴露 attempt token、运行身份、候选对象或 Skill 摘要。
- 新增 PostgreSQL 权威活动 SSE 接口，复用既有 `BookActivityService.pages()` 完成补页与 Redis 唤醒；每帧经严格 DTO 验证并清除内部预算字段，未授权或跨家庭访问统一返回 404。
- SSE `id` 仅跟随该帧实际交付的最大事件序号，空页不推进；500 条活动按 200 条分页时可从 200 继续取得余下事件，过期游标、活动不可用、终态结束和断连清理均保持显式语义。
- 验证：DTO/路由单元测试 `28 passed`，activity service 回归 `18 passed`，`langalpha_test` PostgreSQL 集成 `10 passed`；未向开发数据库应用 `082`，未改动现有 Docker volume。

### 新增：教材语义阶段的严格活动投影

- `BookActivityObserver` 绑定 item kind，仅接受 artifact ID 与 payload stage 一致且属于该 item 白名单的阶段；公开文案和 running 状态均由服务端生成，模型自由文案、状态和跨 item 阶段被忽略。
- 隐藏 `report_progress` 自身的工具开始/结束活动，普通 Read/Bash 等工具摘要保持；工具关联记录在结果到达后释放并设置容量上限。
- 正常写入和预算耗尽后的省略摘要共用阶段节流与噪声过滤，非法阶段不消耗预算，合法阶段缺失、重复或写入失败不改变 job/item 状态。
- 验证：活动/job/SSE producer 单元回归 `60 passed`；`langalpha_test` PostgreSQL 活动流集成 `8 passed`，覆盖合法阶段持久化、跨 item 拒绝及 after_seq 回放；相关 Ruff 和 `git diff --check` 通过。

### 新增：教材托管任务语义阶段契约

- 教育服务定义 structure、material、supplementary 三类固定阶段及中文公开文案，并向每个 `task.json.progress` 写入当前 item 的工具名与允许阶段。
- managed prompt 要求 Agent 仅在进入真实阶段时调用 `report_progress`；上报可缺失、重试或回退，不替代产物和最终回复。既有任务身份、attempt、来源与输出契约保持不变。
- 验证：阶段与教材 job 服务聚焦单元测试 `42 passed`，相关 Ruff 和 `git diff --check` 通过。

### 新增：托管 PTC 受限语义进度工具

- 新增只接受短 stage 标识符的 `report_progress` 工具，将受控语义阶段写入 LangGraph custom stream；非法输入和 stream writer 故障返回固定继续说明，不中断 Agent。
- `ManagedExecutionPolicy` 新增默认关闭的进度能力，仅教材托管策略显式启用；普通 PTC、Flash 和其他 managed policy 的工具面保持不变。
- 验证：进度工具与教材策略聚焦单元测试 `28 passed`，相关 Ruff 和 `git diff --check` 通过。

### 文档：修正语义进度恢复协议与实施依赖

- 区分服务端活动高水位与客户端实际消费游标，明确分页断线、空页、缓存丢失及过期游标的回放规则，避免跳过尚未收到的活动。
- 补齐业务事件合并刷新与可见活跃任务的 5 秒快照兜底，覆盖无进度上报、下一项无事件启动、预算耗尽及活动不可用；完成数量和当前项持续来自数据库快照。
- 将独立计划 Task 1–4 限定为总 Task 4A，前端面板随总 Task 5、完整验收随总 Task 8；必要任务读取/SSE 接口不提前重写教材和学生完整门面。
- 明确新 progress 子对象保留既有 task.json 身份和产物契约，正常投影与省略统计共用阶段校验/节流/噪声过滤；Agent 阶段不作为验收状态机。
- 验证：四份设计/计划交叉复核，10 处本地 Markdown 链接有效、代码块配对完整，`git diff --check` 通过；本次仅修订文档，未运行业务测试或变更运行环境。

### 文档：明确托管教材语义进度与活动时间线边界

- 新增托管教材语义进度设计，明确教育服务掌握 structure/material/supplementary 任务边界，托管 PTC Agent 通过受限 `report_progress(stage)` 解释 item 内部阶段，最终状态和完成数量仍只由产物校验与数据库事务决定。
- 确定不修改 `more-to-skills` 核心 Skill、不解析 Bash/stdout 猜测阶段、不恢复旧 progress JSONL；阶段采用服务端白名单和中文映射，普通工具活动降为可展开明细。
- 将该契约回写总设计，补齐工作台 timeline 的权威层级、结构阶段无虚假完成率、材料计数口径以及 OCR/学生状态等非教材 Agent 阶段的边界。本次仅更新设计文档，未修改运行代码、数据库或 Docker 数据。
- 新增独立 TDD 实施计划并回写总实施顺序，将语义进度发送端列为 Task 4A、Task 5 工作台的前置任务；同时更正计划中的当前 worktree/分支，明确工具注入、阶段契约、活动投影、可恢复 API、前端时间线及全量验收的原子提交边界。

### 新增：有界教材活动与跨 worker 浏览器恢复

- 在通用 SSE producer 的可等待消费边界加入可选 observer；教材模块只投影工具开始/结束及显式 `report_progress`，原始模型 delta、思维内容、完整工具参数和结果仍在 compact replay 与持久化之前丢弃，普通聊天 full profile 不变。
- 新增 PostgreSQL 权威教材活动账本与 `after_seq` 快照分页；订阅 Redis 后再次读取 PG 以关闭 read-before-subscribe 竞态，Redis 只发布不含正文的紧凑唤醒提示，通知丢失或不可用时按 PG 轮询恢复。
- 普通活动限制为每任务 1000 条、完整公开事件 2 KiB、累计 1 MiB、说明 512 字符；同一进度和预算摘要至少合并 1 秒。预算耗尽后只更新有界摘要；明细写入失败会停止该 attempt 的详细投影，并以 `activity_status=unavailable` 持久暴露给快照和 SSE，而不是静默形成回放缺口。
- 结构、材料、附加材料、失败、未执行和取消均在业务事务内写 item 终态；job 终态独立记录且不受普通预算限制。取消先持久写入 `cancel_requested_at`，claim、三类成功 finalizer 与 recovery 共用该栅栏；即使回调先落为失败或部分成功，仍会补发真实 runtime 取消信号并最终收敛为 cancelled。取消与迟到回调竞态会移动并覆盖原终态序号，保持每个 item/job 只有当前终态，同时让旧游标收到更新。
- managed PTC 启动、终态回调、取消与恢复服务均接入活动 observer/唤醒提示；公开 DTO 只返回净化 metadata。验证覆盖 150001 条原始 delta、工具事件压力、长文本、预算写放大、未来游标、权限、Redis 不可用和跨 worker 重连；数据库集成继续仅使用 `langalpha_test`，未向开发库应用 `082`，未改动现有 Docker volume。
- 最终验证：全量单元测试 `8412 passed, 8 deselected, 1 xpassed`；Task 2/3/4 隔离数据库集成 `32 passed`；修改文件 Ruff、格式检查及 `git diff --check` 通过。独立终审未发现剩余 Critical/Important。

### 重构：教材处理接入逐项可恢复的正常 PTC 队列

- 将五套教材 managed purpose 与固定教材 subagent 收敛为唯一 `education_book` policy；结构与单知识点材料均走正常 `RunCoordinator`、graph、SSE、checkpoint 和 Docker sandbox，普通 PTC/subagent 能力不受影响。
- 新增 PostgreSQL 顺序任务队列和逐 item attempt fencing，持久化 workspace/thread/run/execution 身份、租约与结果；启动暂存期间持续续租，进程退出后按 runtime ledger 恢复，已完成回调可幂等补交。
- 结构提交持久化“一次添加并分析”的材料 follow-up；每个知识点独立提交，普通内容失败继续后项，运行、凭据、存储及 sandbox 基础设施失败停止余项，completed runtime 的恢复收尾沿用相同分类。取消先写 durable intent 和业务 fence，再停止实际 runtime；终态事务统一按 job、item/textbook 顺序加锁，重试保留结构后续意图、克隆全部未完成项并冻结当前 Skill 身份。
- 材料执行只暂存当前投影结构、指定知识点及相邻上下文；缺少上一讲义时回退原文锚点，不阻断当前项。附加材料使用显式单独 item 和固定三文件结果，不枚举对象存储。
- managed sandbox 禁用宿主开发 bind mount、平台 secrets、MCP 和 subagent，只暴露 `more-to-skills`；输入与 Skill 目录暂存后只读，Bash 与 ExecuteCode 仍可在隔离写区运行自编脚本。Docker ExecuteCode 临时文件改用容器 `/tmp`，避免只读 managed root 阻塞执行。
- 排队和执行分别校验 `more-to-skills` version、`SKILL.md` 与正式 schema 摘要；技能部署更新后旧任务明确失败，新 retry 使用当前身份，实际暂存字节不再与任务记录漂移。
- 来源暂存按解析服务的真实 manifest 契约读取 `artifacts/<relative_path>`，不再要求 manifest 自带 `artifacts/` 前缀；终态只清理 PostgreSQL 明确登记且属于当前 attempt 的候选对象，上传尚不可见时保留追踪供后续维护重试。
- 教材队列先向共享 executor 非阻塞预留容量，再 claim、续租和分配 runtime；普通请求不能占用已预留槽位，满载不会持有教材租约或 workspace。所有启动失败和终态路径继续清理候选对象、thread、sandbox 与 service-owned workspace，删除托管 workspace 时不重复持久化其临时文件。
- 验证：全量单元测试 `8392 passed, 8 deselected, 1 xfailed`，Task 3/runtime/storage 聚焦单元 `181 passed`，PostgreSQL 队列集成 `11 passed`；真实 Docker 能力 smoke 和实际 BYOK 模型读图各 `1 passed`，Ruff check、Ruff format check 与 diff check 通过。数据库集成仅使用 `langalpha_test`，未向当前开发数据库应用 `082`，未重建、删除或忽略现有 PostgreSQL、Redis、MinIO 挂载数据。

### 重构：建立 more-to-skills 教材数据与存储模型

- 新增不可逆的 `082_more_to_skills_textbooks` 完整切换迁移：重建单来源教材、学生授权与学习引用，建立结构、知识点、当前材料、任务、任务项和有界活动六张新表，并删除旧 version/package/candidate/publication/lesson/generation schema。
- 教材 UUID 在来源冻结前预留，数据库校验来源前缀与教材身份一致；教材与初始结构任务在同一事务创建，相同家庭与解析来源的网络重试返回原对象，冲突回读仍须通过家长授权。
- 结构及全部 KP 原子导入，数据库 KP UUID 与技能 KP ID 分离；结构和材料提交只读取 job 冻结的 skill、深度及要求，学生 assignment 与 KP 以复合外键约束为同一本教材。
- 新增任务 attempt fencing、材料 job 原子幂等创建与完整请求语义校验、候选对象预登记和当前 material CAS；item 保存稳定结果快照，重复或迟到 finalize 在后续重做覆盖当前材料后仍可幂等收尾，结构完成事件按活动高水位追加。
- 已有 `content_file` 讲义通过独立 materials job 走同一登记、上传、校验和提交路径；结构 API 的 `content_file` 只由当前 material 记录确定性投影，不写回不可变结构 JSON。
- 源快照使用按 `textbook_id` 的单来源目录与安全来源 DTO，移除新路径对 version/position 的依赖；组合服务先预检来源再冻结，竞态或失败只清理本次明确记录且未被数据库引用的教材对象键，提交结果不明时保留对象等待恢复确认。
- 验证：全量单元测试 `8407 passed, 8 deselected, 1 xpassed`；Task 2 聚焦单元/迁移测试 `36 passed`，真实 PostgreSQL 教材集成测试 `9 passed`，包含空库到 head、`081` 到 `082` catalog 等价、权限隔离、并发与语义幂等、跨教材拒绝、已有讲义归档、活动序号、迟到回调及 PG 故障保留旧材料。迁移仅在 `langalpha_test` 和一次性临时测试库执行，未应用到当前开发数据库，未改动 Docker 挂载数据。

### 新增：固定 more-to-skills 教材结构契约

- 将本机实际使用的 `more-to-skills` 2.1.0 以 MIT fork 署名固定到 `langalpha_local` 插件，规范 Skill frontmatter，并记录 Skill 与正式 schema 的内容摘要；运行不再依赖宿主机个人技能目录。
- 新增严格结构导入器：以服务端可信来源替换模型路径，拒绝重复 JSON 键、非有限数值、不支持的 schema major、非法引用、越界锚点、路径逃逸和缺失材料，同时保留递归结构与未知扩展字段。
- 冻结单来源建书、教材工作台、结构/KP 映射、原文闭区间切片、材料、任务活动及学生授权 DTO；数据库 KP UUID 与 `skill_kp_id` 明确分离。
- 只读复核真实 REX2 样例，正式 schema 精确报告 `$.nodes[6].children[0].children[4].title_source` 的 `null` 错误，未修改样例或放宽 schema。
- 验证：Skill 标准校验通过；结构、DTO、技能发现与插件组合聚焦回归 `42 passed`，Ruff 检查通过。本次未执行数据库迁移、未修改或删除 Docker 挂载数据。

## 2026-09-30

### 文档：补全教材重构清理范围与工作台交互

- 根据真实页面和代码依赖复核重写设计与实施计划，将家长加工收敛为教材列表与单一工作台，明确原文、讲义、活动、批量生成及失败重试的原位交互。
- 新增旧页面、服务、数据库表、PTC 专用配置及运行资源的清理清单，补齐图书馆使用查询、学生笔记/进度/追问和学习会话保护的接线范围。
- 明确逐知识点提交、单一材料指针、持久队列恢复和一次性切换要求；本次仅修改文档，未运行迁移、删除数据或改变服务。

### 文档：明确 more-to-skills 教材重构方案

- 根据确认后的技能契约整理结构入库、按知识点生成讲义、图书馆资产复用与精简 Timeline 的设计和实施计划。
- 明确清理旧教材派生数据及处理协议、不保留手动拆分和历史兼容，保留正常 PTC 编程能力与通用运行机制。
- 本次仅更新文档，尚未修改业务代码、执行数据库迁移或清理数据。

### 新增：图书馆 Datalab 高级解析选项

- 高级选项新增 Datalab STRUCTURE 与 CONTENT 参数：跨页合并、页眉/页脚保留、链接提取、新块类型、块 ID，以及已有的分页、图片提取和图片标题控制。
- 分页和输出页眉默认开启；页脚、跨页合并和新增内容特性保持关闭，只有用户主动调整的选项才写入前端请求。
- 后端将页眉/页脚映射到 `additional_config`，链接与新块类型合并进 `extras`，并兼容当前固定版本 SDK 缺少的 `merge_cross_page` 字段。
- 验证：Datalab provider 回归 `90 passed`，前端选项/API/本地化测试 `28 passed`，`pnpm typecheck` 与 `pnpm build` 通过。

## 2026-09-23

### 修复：课程生成 prompt 的跨知识点状态与冲突提示

- 结构审阅页切换知识点时会重置并重新加载该知识点自己的生成要求，避免把上一个知识点的 prompt 提交给下一个知识点。
- 前端统一从 Axios/FastAPI 的 `response.data.detail` 提取错误信息，真实 409 冲突现在会显示服务端说明而不是泛化的 HTTP 状态文本，且仍保留用户输入。
- structure generation job 响应现在把持久化的 `processing_brief` 投影为 `prompt`，API projection 与 lesson queue/status 保持一致。
- 验证：Education 定向 Vitest `34 passed`，后端结构/课程/review 回归 `129 passed`，Ruff 与 `pnpm typecheck` 通过。

### 新增：知识点课程生成要求输入与恢复

- 结构审阅页的“生成课程”入口和课程审阅页的“重新生成”入口新增“课程生成要求（可选）”textarea，最多输入 4000 字；首次生成和重新生成共用相同的规范化提交逻辑。
- 页面会从 lesson generation status 恢复活动或最近一次 job 的 prompt；用户开始编辑后，后台状态刷新不会覆盖当前输入，冲突或失败时也不会清空已填写内容。
- 后端 status 在活动 job 结束后仍返回最近一次 lesson job 的 prompt，保证离开页面再进入时仍能恢复生成要求。
- 验证：Education 定向 Vitest `31 passed`，后端请求、数据库、课程队列和 review 服务回归 `120 passed`，`pnpm typecheck` 通过。

### 新增：用户课程要求注入 managed lesson prompt

- 知识点课程生成会把 job 中的规范化用户要求追加到固定 managed contract 之后，并限制为最多 4000 字符。
- 用户要求只能影响课程语言和目标受众、结构与顺序、篇幅与深度、难度、表达风格、例子和练习形式；目标知识点、source refs、输出路径与格式、lesson/practice schema、sandbox 与安全边界明确保持最高优先级。
- 用户内容经过 HTML 转义后放入 `<lesson_generation_prompt>`，不能通过伪造结束标签改写 managed contract；空要求不追加任何 section。
- 验证：lesson prompt 聚焦 `7 passed`，完整 lesson jobs 回归与 Ruff 通过。

### 新增：知识点课程生成要求持久化与冲突保护

- 知识点课程首次生成和重新生成现在接受最多 4000 字的可选 `prompt`，并在服务边界去除首尾空白后持久化到现有 `education_generation_jobs.processing_brief`，无需数据库迁移。
- 同一知识点已有活动 job 时，只有 `auto_grading` 和规范化 prompt 都相同才复用；任一不同返回冲突且不改写正在运行的 job。
- 课程 job 与 lesson status API 现在返回持久化的 `prompt`，生成 profile hash 也纳入规范化 prompt，便于页面刷新后恢复原要求。
- 验证：请求、数据库、课程队列和 review 服务聚焦 `116 passed`，Ruff 通过。

### 修复：知识点候选接口因超长 quote 返回 500

- `StructureSourceRefResponse` 在响应序列化边界将 `source_refs[].quote` 截断到 500 字符；数据库和 package 仍保留完整 canonical quote，不再因单个长引用让整个候选列表返回 500。
- 真实 structure `75c7f0d8...` 已验证可构造完整候选响应：21 个 content nodes、24 个 pending candidates，返回 quote 最大 500 字符。

### 修复：教材 projection 格式与 asset manifest 过度校验

- importer 现在承认规范 projection 格式：`content_tree.json` 的 `langalpha-content-tree/v1`、`knowledge_points.json` 的 `langalpha-knowledge-points/v1`，以及既有 assets manifest 格式；这些文件的内容、引用、投影一致性、asset size/hash 仍继续校验。
- assets manifest 允许额外列出 `book_package.json` 等输出说明；package 中声明的每个 asset 仍必须在 manifest 中以完全相同的 path、node、kind、size 和 hash 出现，实际导入下载集合仍只来自 package 声明。
- 用失败任务 `9a8a1313...` 的真实 outputs 离线复核：修复前依次报 `content_nodes is invalid`、`assets manifest contradicts`；修复后成功校验 21 个 content nodes、24 个 knowledge points 和 30 个 declared asset files。

### 修复：教材列表和详情恢复 book pipeline 状态入口

- textbook library/detail projection 现在优先读取最新 `education_generation_jobs(scope='book_pipeline')`，不再只关联旧的 `education_processing_jobs`；因此离开加工页再进入教材时，失败、运行中、待审阅和已完成 job 的 ID、状态与错误信息不会丢失。
- 教材列表使用最新 pipeline job 状态显示“加工中 / 加工失败 / 待审阅 / 已取消”；教材详情显示“查看处理状态”，并携带 `?job=<generation_job_id>` 返回原有处理进度页。legacy processing job 继续保留兼容。
- progress API 现在返回 job 的 `error_code/error_message`；处理页将四个阶段完成与最终 job 失败分开显示，失败时明确显示“处理失败”及最终校验错误，不再用“处理任务已创建”掩盖终态失败。
- 验证：数据库/API 服务单元 `57 passed`，真实 PostgreSQL `test_book_pipeline_jobs_db.py` `12 passed`，Education Vitest `89 passed`，`pnpm typecheck` 通过。

### 修复：education jobs 使用 compact replay stream

- `RunSSEProducer` 新增 `replay_profile="full" | "education_compact"`；education compact 只保留 metadata、warning、error、interrupt、model retry/fallback，并在 sequence 分配和 accumulator 写入前过滤 message/tool delta、compaction、context window、provenance 与 steering 帧。
- compact wrapper 使用 `aclosing` 同步传播 generator close，保持 full profile 原有图流、compaction guard 与 tracing 的取消清理语义。
- structure、lesson、book asset、book pipeline 四个 managed education 调用点显式 opt in；普通 PTC 与 Flash 继续使用默认 full profile，原有 stream 形状不变。
- education 前端继续以 PostgreSQL progress API 为四阶段事实源，不依赖被过滤的 token/tool delta。
- 验证：producer 与 education dispatch 聚焦 `89 passed`；unified progress integration `3 passed`，其中 150,001 个 raw delta 的压力场景下 replay 与 stored events 均小于 1,000，并经真实 `stream_writer.buffer_event` 路径验证 quota 计数；semantic progress row 正常持久化。

### 文档：同步 managed textbook 工具与写区契约

- managed overlay 与 analyze/full/continuation prompt 明确列出 Read/Glob/Grep、Write/Edit、普通 sandbox Bash、ExecuteCode、Web、Preview/Widget 的可用范围；MCP/Vault 保持 disabled。
- 写入说明改为 `work/` 与 `outputs/` 区域边界，声明 package schema、精确文件名、extension 与 manifest membership 由导入/finalization 校验；禁止直接 Write/Edit progress stream。
- progress 文档补充稳定 event-key、`probe/diagnostic/test/debug` 禁止、`checkpoint_review` skip 及三个必选完成阶段。
- 真实 Docker smoke 验证普通 `ls`/`wc`/`head`/`grep`、嵌套 outputs、progress helper append、`inputs/` 只读和 managed root 内真实路径。
- 验证：文档/UAT 单测 `23 passed`，Docker provider 集成 `26 passed`，unified progress integration `2 passed`；Education Vitest `87 passed`，`pnpm typecheck` 与 `pnpm build`（critical path `355.9 kB gz`）通过。

### 修复：拒绝诊断进度并校验完整流水线完成阶段

- `event_key` 现在要求稳定分段格式，并拒绝 `probe:*`、`diagnostic:*`、`test:*`、`debug:*`；服务端 parser、staged helper 和四阶段 projection 使用同一规则，历史污染事件也不会进入时间线。
- `skipped` 只在 metadata reason 为 `checkpoint_review` 时允许，普通阶段不能被伪装成 skipped。
- 非 checkpoint 的完整 pipeline 在导入前必须存在当前 attempt 的 `chapter_analysis`、`content_processing`、`knowledge_point_generation` 三个 parser-accepted durable `completed` 事件；旧 attempt 或 `probe/diagnostic` 等已拒绝行不能满足门禁，缺失任一阶段都会 fail closed，不下载或导入半成品。continuation 模式只允许从 durable checkpoint attempt 继承 chapter completion，content 和 knowledge 仍需当前 attempt 完成。
- staged helper 与服务端共享 event-key 长度限制；continuation 通过 checkpoint prefix 识别具体 source attempt，不能从任意历史 attempt 借用 chapter completion。
- 验证：progress、projection、collector、teaching storage、pipeline jobs 与 managed policy 聚焦回归 `305 passed`，Ruff 通过。

### 重构：managed write gate 改为区域边界校验

- 删除写时对 `book_package.json` 等精确文件名、章节路径、JSON object shape 和知识点交叉引用的约束；agent 可在 `work/` 与 `outputs/` 下创建任意安全 scratch 或规范输出文件。
- 写校验继续强制 managed root containment、拒绝 `..`/反斜杠/C0 控制字符/根外绝对路径，只允许 `work/` 和 `outputs/`，并继续禁止 `inputs/`、`.agents/`、其他 `.langalpha/` 与直接写 progress stream。
- `Edit` 与 `Write` 共用同一 managed zone gate，并在路径 normalize 之前检查原始输入，避免编辑绕过 frozen/progress 路径约束或尾部控制字符被静默 strip。
- 保留 32 MiB 防御性大小上限和 `.json` UTF-8/严格 JSON 语法检查；package schema、候选归属、引用、asset manifest、大小和 hash 仍由导入/finalization 阶段验证。
- 验证：managed policy 与 book pipeline importer/回归 `104 passed`，Ruff 通过。

### 新增：managed textbook 使用完整 PTC 工具能力

- `ManagedExecutionPolicy` 新增 code execution、Bash、preview、widgets 能力开关；structure、lesson、book asset、book pipeline 和 teaching 五个 textbook policy 统一开启 web、ExecuteCode、普通 sandbox Bash、Preview、Widget、Read/Glob/Grep/Write/Edit，同时继续关闭 MCP 与 Vault。
- managed 工具构造改为按 policy 组装，textbook purpose 不再传 command-text whitelist；Bash 仍在固定 managed root 中运行，MCP/Vault secrets 与 interactive/household tools 继续隔离。
- textbook subagent 只继承 policy 实际启用的 code execution 与 Bash 工具集合；managed graph 显式不挂载 direct MCP。
- 验证：managed policy 与真实 agent 工具集合聚焦 `67 passed`，`tests/unit/ptc_agent` 全量 `816 passed, 1 xfailed`，Ruff 通过。

### 修复：managed textbook 预创建完整工作目录契约

- 新增统一的 managed textbook 目录契约，预创建 `work/`、`outputs/`、`outputs/book-skill/chapters/`、`outputs/content/`、`outputs/chapters/`、`outputs/knowledge/` 与 `.langalpha/`；`inputs/` 单独以只读权限创建，不进入可写目录列表。
- managed sandbox 初始化现在逐个验证可写目录属于 runtime 用户，并通过 provider upload 创建 helper 专用的空 `.langalpha/progress.jsonl`，不再依赖 staging 作为唯一的目录/文件创建机制。
- frozen inputs staging 完成后重新把 `inputs/` 收紧为 `0555`，同时 Docker tar 的 `ensure_directory()` 只给目标叶子目录应用指定 mode，祖先目录保持 `0755`。
- Docker managed sandbox 增加 `LINUX_IMMUTABLE` capability，由 runtime root 通道对 staged inputs 设置 immutable、对 `progress.jsonl` 设置 append-only；provider 不支持时回退到递归只读 mode，collector 同时校验已消费 progress prefix，阻止同长度重写。
- 验证：managed policy 与 storage 聚焦回归 `101 passed`，Docker tar 上传单测 `5 passed`，Ruff 通过。

### 修复：sandbox 上传目录统一归 runtime 用户所有

- Docker tar 上传现在只为本就不存在的父目录写入带 runtime uid/gid 的目录 entry，不再依赖 root 权限的 `mkdir` 或 Docker 隐式创建，也不会覆盖 `/tmp` 等既有祖先目录的 mode、sticky bit 或 ownership；普通 PTC、managed textbook 与批量上传共用同一归档构造。
- 新增 runtime 级 `ensure_directory()` 契约：Docker tar/bind、Daytona 和默认 shell runtime 都以 sandbox runtime 用户创建目录，`PTCSandbox` 的普通 workspace 与 managed job 初始化统一经该能力完成。
- 验证：聚焦 sandbox 单元 `152 passed`，managed setup 联合回归 `212 passed`；真实 Docker provider 集成 `24 passed`，包含嵌套上传父目录与文件的 uid/gid 校验；Ruff 通过。

### 修复：教材来源选择弹窗误触关闭

- “从图书馆选择来源”弹窗改为显式关闭模式，点击遮罩或按 Escape 不再关闭，只能使用弹窗内的关闭按钮退出，避免误以为已开始的教材准备任务被取消。
- 验证：`TextbookDetailPage` Vitest 8 项通过，`pnpm typecheck`、`pnpm build` 通过。

### 修复：用户资料请求失败时前端不再无限加载

- `useSetupGate()` 现在只在用户资料请求真实处于初始 loading 时保持加载状态；请求错误或返回空用户且已结束等待时，会返回 `profileUnavailable=true`，不再把应用永久锁在 `PageLoading`。
- 用户资料不可用时会显示明确的错误页，提供“重试”和“退出登录”操作；重试直接调用共享用户查询的 `refetch`，成功后恢复正常应用门禁。
- `/api/v1/users/me` 与 `/api/v1/auth/me` 分别设置 10 秒请求超时，避免受限网络下请求永久挂起并阻塞应用初始化；未设置 axios 全局超时。
- 验证：新增查询失败、正常 loading、用户资料超时和认证超时契约测试，聚焦 Vitest `11 passed`；Education Vitest `86 passed`；`pnpm typecheck`、`pnpm build`（critical path `355.8 kB gz`）通过。

### 新增：取消运行中的教材处理任务

- 新增 `POST /api/v1/education/book-pipeline-jobs/{job_id}/cancel`。终态任务幂等返回当前投影；`queued`、`preparing` 和 `awaiting_review` 在无 root run 时由 PostgreSQL 事务原子取消 job 和正在准备的 attempt；`running`、`validating` 统一委托既有 `cancel_workflow(thread_id, run_id)`，终态仍由原 finalizer 收口。
- 取消事务按 attempt-first 顺序加锁，并在事务内重新校验 parent membership、latest attempt 和 root run，避免与 launch、结算路径产生越权、锁顺序反转或前端重复提交。
- 教材处理页在活动任务上显示“取消处理”和确认弹窗；提交期间冻结按钮，成功后显示“正在取消”，任务进入终态后隐藏取消入口。
- 验证：service/API 聚焦 `73 passed`，真实 PostgreSQL 取消 ACL、queued、preparing、running delegation `11 passed`，Education Vitest、`pnpm typecheck`、`pnpm build`、Ruff 与 `git diff --check` 通过。

### 修复：managed 进度 helper 无法首次写入

- staging `book-to-skill` 时预创建空的 `.langalpha/progress.jsonl`。该文件按容器用户 uid/gid 落盘，后续 helper 可以直接 append，不再因 root-owned `.langalpha` 目录而触发 `PermissionError`。
- 保持 append-only 和现有最小目录权限，不修改 provider 全局目录权限。
- 验证：staging helper 聚焦单测按预期先失败、修复后通过；storage、progress、managed policy 聚焦回归通过。

### 修复：连接知识点候选审阅与课程制作

- 通用内容树候选审阅页的返回入口改为教材详情 `/textbooks/:textbookId`，不再进入只支持旧 Unit/Reading schema 的空结构页。
- 已接受候选现在直接显示带图标的“制作课程”链接，进入对应知识点课程页；待确认、已拒绝、已合并和已拆分候选不显示该入口。
- 验证：候选审阅页聚焦 Vitest `12 passed`，`pnpm typecheck`、`pnpm build` 与 `git diff --check` 通过。

### 验证：统一教材处理流水线完成 REX 3 端到端验收

- 使用真实 `datalab-output-REX 3e SB3 Page1-50.pdf.md` 构建通用内容树：Unit 为根节点，Reading A/B 是普通 `reading` 子节点；节点与知识点只提交确定性行范围，服务端从冻结 Markdown 派生并校验 canonical quote。标准结构、节点和候选最终通过 `validate_book_package()`，非对称节点资产或知识点覆盖仅产生 warning，不阻断合法教材。
- 真实 PostgreSQL 验收覆盖完整 package 导入结果：内容节点按父子拓扑持久化，知识点以 `origin='generated'`、`candidate_status='pending'` 绑定各自 content node，knowledge asset 一并写入。pending 候选调用课程接口会在创建 generation job 前失败；候选经人工接受后，同一知识点才能创建 `scope='lesson'` 的 queued job。
- 新增 live progress 端到端测试，实际驱动 `ManagedProgressCollector` 和 PostgreSQL 持久化协议。collector 在 managed run 仍未结束时写入首批事件，随后投影固定四阶段“教材章节解析、内容智能处理、知识点生成、课程制作”，并确认三个处理阶段的事件在运行中被观察到，lesson 阶段保持 queued。
- checkpoint 验收使用真实 collector 与数据库事件协议：`chapter_analysis/completed` 持久化后先停止 graph/consumer，再通过真实 pause service 写入 checkpoint prefix 和 `awaiting_review`，最后才允许 terminal finalization；带有 stop marker 的 finalization 明确拒绝导入部分 package。三个 managed prompt 的首句分别精确输出 `managed mode=analyze-pass`、`managed mode=full-pipeline` 和 `managed mode=full-pipeline-continuation`，不再包含 `mode=mode`；Task 11 只验证 continuation prompt contract 并声明从 Steps 4-9 继续，不把 prompt-only 断言冒充完整 resume 运行，真实 resume 状态转换仍由 Task 7 的 `test_resume_book_pipeline_requeues_only_waiting_checkpoint` 与 `test_pause_and_resume_enforce_household_acl` 覆盖。
- 本轮把整条特性边界串联验收：book-to-skill 统一 Steps 0-9、通用内容树、pending 候选人工确认、四阶段实时进度与重连、章节 checkpoint/resume、人工确认后的课程制作、processing brief 与 request_id/active-job 幂等，以及 migrations `076`-`081`。测试不启动真实模型、sandbox 或网络，模型端生成质量仍需独立运行验证。
- 验证：真实 REX 3 fixture 路径为必跑要求，本次验收确认文件存在且零 skipped。全量单元测试 `8305 passed, 8 deselected, 1 xpassed`；指定真实 Markdown/PostgreSQL integration `4 passed`；Education Vitest `80 passed`，`pnpm typecheck` 与 `pnpm build` 通过，critical path `355.5 kB gz`；Ruff 与 `git diff --check` 通过；迁移 head 为 `081_book_pipeline_checkpoint`。

## 2026-09-22

### 新增：仅从已确认且绑定内容资产的知识点生成课程

- 课程生成门禁同时支持 legacy Unit/Reading 和通用内容节点。查询继续按 structure/version -> textbook -> parent membership 校验归属；generated candidate 必须为 `candidate_status='accepted'`、具有 `content_node_id` 和已声明的 `knowledge` 内容资产。pending、rejected、merged、split、未绑定节点或缺少资产的请求在创建 generation job 前明确拒绝，不产生 job、attempt 或 run；旧手工 accepted 知识点保留原 Reading 兼容路径。
- generic lesson 不再猜测 Reading。运行时校验节点资产的私有 key、大小和 SHA-256 后读取该节点 knowledge 资产；source context 只解析节点自身声明的 frozen source ranges，范围不可用时回退到同一节点资产，绝不加载整本书。staging 使用 `inputs/content-nodes/<node_uuid>.md` 与 `inputs/chapters/<node_uuid>-knowledge.md`，manifest 使用无 Reading slot 的 v2 契约。显式空 refs 与缺少范围都按“无可解析范围”处理并回退节点资产，不会被误报为缺少必需输入。
- generic lesson revision 使用完整知识点 UUID + candidate key 的完整 SHA-256 作为节点内唯一身份，并以内容 SHA-256 作为最终不可覆盖对象名：`content-nodes/<node_uuid>/knowledge-points/<kp_uuid>-<key_sha256>/lessons/<content_sha256>/lesson.md`。不同内容永不复用对象 key，同内容重复写复用同一对象；并发手动保存由 lesson 行锁串行化 DB insert，相同内容返回既有 revision。超长且仅尾部不同的 candidate key 会生成不同对象 key。lesson get/review projection 返回 `content_node_id` 与 `candidate_key`，读取时校验 storage bytes 与 DB SHA-256/size，漂移 fail closed。
- 手动保存命中的内容 SHA 对应旧 revision 时，不再只返回旧行：事务内原子更新 `lesson.latest_revision_id` 指向该旧 revision、`status='review'`、`reviewed_at=NULL`，并返回更新后的 lesson projection。真实 PostgreSQL 覆盖“当前 v2、保存精确 v1 内容”后 latest 回指 v1 且读取内容一致。
- source reader 直接接受 `validate_book_package()` 持久化后的 canonical `start`/`end` 范围，同时兼容输入阶段 `char_start`/`char_end`。存在有效节点范围时不会静默回退到节点资产；只有无法解析范围或显式空 refs 时才使用该节点资产，且始终不会加载整本书。
- lesson queue 使用 per-knowledge-point transaction advisory lock，并发请求复用已有 `queued/preparing/running/validating` job，并返回 `reused_existing_job` 语义。Launch 另有 `queued->preparing` 单赢家 fence，在创建 workspace/thread/attempt 前完成；loser 不创建资源，attempt 前失败会把 preparing claim 收口为 failed，之后可再次创建 job。`preparing` stale lease 可恢复两类崩溃：无 attempt，或已有 attempt 但其 status IN (`preparing`,`worker_lost`)、root_run_id 为空且 job/attempt 均超过 5 分钟。reclaim 把仍在 preparing 的旧 attempt 原子标记 `worker_lost`、`error_code='launch_abandoned'`，已是 worker_lost 时不再重复报错，只刷新 job preparing/updated_at；即使第一次 reclaim 后又崩溃，二次 lease 过期仍可继续并创建 replacement attempt。未过期或已有 root_run 的活跃 attempt 不可抢占。同知识点 active job 的 `auto_grading` 不一致时返回 HTTP 409，不再静默复用。workspace 创建后但 attempt 前失败可能留下 orphan workspace，当前优先保证 job 状态可恢复。
- 有 latest attempt 的 stale reclaim 使用与 `mark_generation_attempt_running`/`settle_generation_job` 一致的 attempt-first 锁顺序：先无锁读取 latest_attempt_id，再锁 attempt，随后锁 job，并在事务内重新校验 latest identity、status、root_run 与 job/attempt lease。无 attempt 的恢复只锁 job。真实 PostgreSQL 并发 mark_running vs reclaim 在 10 秒内完成且恰好一个赢家，最终 job/attempt 状态一致，避免锁顺序反转和 TOCTOU。
- lesson scope 的 `claim_generation_job` 同样先无锁预读 job status/scope/latest_attempt_id，有旧 attempt 时先锁旧 attempt，再锁 job 并重新校验 expected status 与 latest_attempt_id 未变化；无 previous attempt 时只锁 job。replacement 只允许从已终结旧 attempt（如 `worker_lost`）继续，未解决的 preparing attempt 不会被错误串成 previous chain。真实 PostgreSQL 并发 replacement claim 与 stale reclaim 在超时窗口内完成，无 deadlock 且最终 chain 有效。
- managed lesson prompt 通过既有 staged helper 追加 `lesson_preparation` 语义进度，覆盖 `preparing`、`extracting_source`、`planning`、`generating_explanation`、`generating_practice`、`validating`、`completed`；非最终子阶段明确 running -> completed，event key 包含 generation job 和 attempt，仍由既有 collector 持久化，不暴露 reasoning、prompt、工具数据、凭据或完整 sandbox 路径。
- lesson-generation status 增加 `source_kind`、`candidate_status`、`content_node_title` 和 `content_asset_available` 安全投影。课程页对 pending generic candidate 或缺少节点资产的 accepted candidate 禁用生成按钮并显示明确原因；accepted generic candidate 不再要求整份 structure 先变为 accepted，legacy Reading 路径仍保留原结构门禁。刷新页面会从状态接口恢复活动 generation job；status query 报告 `generating` 或 lesson detail/status 正在加载时按钮保持冻结，状态、阻断原因和失败信息使用 `aria-live` 通知。
- managed `.langalpha/progress.jsonl` 现在只允许通过 staged Python helper 追加；managed policy 对所有教材用途统一拒绝普通 `Write`/`Edit` 直写，overlay 与 full-pipeline prompt 明确说明唯一允许的 append 路径。
- `education_lesson` managed runs 使用与 teaching/book pipeline 相同的 24 小时 abandoned/reconnect timeout，避免长课程任务被普通 6 小时窗口清理。
- 验证：Task 10 聚焦 unit/DB/timeout `115 passed`，structure API/DB 与 managed-policy 回归 `117 passed`，真实 PostgreSQL generic gate/并发去重/attemptless + preparing/worker_lost stale recovery/lock-order + replacement-chain race/revision repoint/asset/archive-projection integration `14 passed`，Education Vitest `80 passed`；`pnpm typecheck`、`pnpm build`（critical path `355.5 kB gz`）、Ruff 与 `git diff --check` 通过。迁移 head 保持 `081_book_pipeline_checkpoint`，本任务不新增 migration。

### 新增：生成知识点候选的人工确认与流转

- 新增 parent-only 候选审阅 API：按任意深度的通用内容树返回生成的 pending 候选，并支持 PATCH 描述字段、批量接受/拒绝、同节点合并和拆分。知识点查询严格经 structure -> version -> textbook -> membership 校验，只投影 `origin='generated'` 的行，旧的手工知识点继续保留且不会混入候选接口。
- 接受会把 `candidate_status` 与 legacy `status` 原子设为 `accepted`，拒绝设为 `rejected/blocked`；重复接受或拒绝按幂等成功处理，已接受后拒绝等非法终态迁移返回 409。合并会把非 target 来源设为 `merged/blocked`，按显式选项保留 target 为 pending/accepted，或新建同节点 pending 候选；拆分把原候选设为 `split/blocked`，并在同一事务中生成两个以上带唯一 candidate key 的 pending 候选。所有操作锁定确定顺序的候选行，任一失败整体回滚。
- 生产 generic structure schema 确认为 `langalpha-book-content-tree/v1`，同时兼容 forward-compatible `langalpha-managed-book-package/v1`。TextbookDetail 对 generic schema 只显示“确认知识点候选”，不再显示旧的“审阅结构与知识点”；legacy schema 仍保留旧入口。generic 的 `lesson_summary` 改为从未删除的 generated candidate 行按 `content_structure_id`/`content_node_id` 统计，pending+accepted 为 total，accepted/lesson-backed 为进度，不再经 Unit inner join 得到错误的 0/0。
- merge/split 在锁候选行前，按 node_id 顺序先用 `FOR UPDATE` 锁定所属 `education_content_nodes` 行。position 在节点锁之后分配，真实 PostgreSQL 双连接测试证明并发 merge/split 会等待节点锁，完成后 position 唯一且连续；不依赖 UUID 或 created_at 排序兜底。
- candidate PATCH/merge/split 的标题、类型和摘要统一在请求边界拒绝未允许 Unicode `Cc`；摘要允许契约中的换行/回车，NUL 等控制字符返回 422 且不会进入 DB。新增学生访问六个候选审阅端点的 403 覆盖。
- 拆分生成键使用“截断后的可读来源前缀 + 每项稳定 SHA-256 短后缀”，长度始终不超过数据库 `VARCHAR(255)`；255 字符合法来源键也已由真实 PostgreSQL 测试覆盖。无 target 的新合并候选必须保持 pending，`accept=true` 在请求模型层返回 422，service/DB 同样 fail closed；带 target 的显式接受语义保持不变。DB 失败注入测试确认拆分中途插入失败后，来源状态和已插入项都会回滚。
- 新增 `/textbooks/:textbookId/versions/:versionId/candidates` 懒加载审阅页，通用树按 `parent_node_id` 渲染节点和候选；页面提供选择、接受、拒绝、合并、拆分、标题/摘要/类型编辑，并显示加载、错误、空状态和状态统计。生成候选只会在用户明确操作后改变状态，不会因页面加载或其他动作自动接受。
- 审阅选择只允许 pending：非 pending 复选框禁用，批量操作始终使用当前 pending 交集，已选项在刷新后变为 accepted/rejected/merged/split 时会自动剔除。最多允许明确选择 100 个 pending 项；达到 100 后只禁用额外复选框并显示安全提示，已选 100 项的 bulk 操作仍可用且请求不会超过 100 个 ID。拆分对话框至少 2 项、最多 100 项，后端模型边界一致，支持增删拆分项且无法删除到 2 项以下。
- 当前候选 projection 保持完整审核语义：后端允许的校验上限为 5,000 个 content node 和 50,000 个 candidate，不静默截断；UI 未实现分页/虚拟化，计划将超过约 2,000 个可见行的场景列为 scalability follow-up，未来必须用 cursor/window + 显式 `truncated` 扩展。
- 验证：API 与结构路由单测 `35 passed`，数据库结构投影单测 `32 passed`，真实 PostgreSQL 候选迁移/更新/幂等/ACL/merge/split/255-key/rollback/concurrency 测试 `5 passed`，Education Vitest `73 passed`；`pnpm typecheck`、`pnpm build`、修改文件 Ruff 与 `git diff --check` 通过。迁移 head 保持 `081_book_pipeline_checkpoint`，本 Task 不新增迁移。

### 新增：统一教材处理四阶段实时进度接口与时间线

- 新增 parent-only 的 `GET /api/v1/education/jobs/{job_id}/progress` 与 `/progress/stream`。读取以 PostgreSQL 进度事件为准，固定返回“教材章节解析、内容智能处理、知识点生成、课程制作”四个阶段；未知 job 或其他 scope 返回 404。
- 进度查询连接 generation attempts 并保留 `attempt_started_at`，服务按 attempt 开始时间、attempt identity 和 sequence 确定性聚合。`last_sequence` 返回最后有序事件的 sequence，而不是跨 attempt 的数字最大值，因此旧 attempt 的 41 后接新 attempt 的 2 时 cursor 正确前进为 2。阶段状态按 attempt 分别处理：只有同一 attempt 的同一阶段已经出现终态后才抑制后续 fallback；新 attempt 的 running/queued 会覆盖旧 attempt 展示状态，若新 attempt 没有该阶段事件则保留旧状态。current/total 只取最新 attempt 的事件，每阶段只返回最近 8 条白名单字段，不返回 prompt、reasoning、工具参数/结果、凭据、sandbox 路径或原始 metadata。
- 没有事件但 job 已进入 `awaiting_review` 或 `completed` 时，只用 job 生命周期推导阶段状态：章节检查点只标记第一章完成；完整导入完成后前三阶段完成，课程制作保持等待人工确认。不会伪造事件或内容。
- SQL 查询使用最近 2,000 条事件加每阶段最新事件、最新终态事件和最新带计数事件构成有界窗口，避免普通 GET/SSE 全量读取历史；完整阶段和 current/total 上下文不会因窗口截断消失。current/total 只在最终用于该 stage 的 latest attempt 内反向查找计数字段；新 attempt 没有 count 事件时返回 null，绝不继承旧 attempt 的计数。响应通过 `truncated` 明确标记历史是否被省略。真实 PostgreSQL 测试覆盖多 attempt 排序、2000+ 事件截断、旧 completed 阶段保留、同 attempt running `10/12` 后无计数 completed 仍保留计数，以及新 attempt 无计数时不继承旧 attempt 计数。
- SSE 首帧发送当前快照，之后每 2 秒重新读取 PostgreSQL，并在 `awaiting_review/completed/failed/cancelled` 收口；当前不依赖 Redis wake-up。每帧携带语义唯一的 `id: <attempt_id>:<sequence>` compound cursor，但不改变 JSON snapshot contract，响应使用 `no-cache`、`X-Accel-Buffering: no` 与 SSE content type。
- 教材处理页新增四阶段时间线：展示已完成、运行中 Unit 数量、待处理 Unit 范围、知识点候选数和等待知识点确认状态；持久化事件 label/detail 只做文本展示。创建或复用 job 后把 job id 写入 `?job=...`，刷新会从 URL 恢复；React Query 仅在活动状态每 2 秒轮询，稳定状态停止。
- 验证：后端 Task 8 聚焦测试 `58 passed`，相邻进度/collector 回归 `206 passed`，真实 PostgreSQL progress integration `9 passed`，前端聚焦测试 `10 passed`，Education 前端回归 `62 passed`。跨 attempt completed→running、attempt-scoped counted fallback、DB 有界窗口与 order metadata、running→completed SSE fake-clock，以及 React Query fake-timer 2 秒轮询和终态停止均有测试覆盖；`pnpm typecheck`、`pnpm build`、修改文件 Ruff 与 `git diff --check` 通过。迁移 head 保持 `081_book_pipeline_checkpoint`。

### 新增：托管教材运行实时语义进度与章节继续检查点

- 新增 `ManagedProgressCollector`，在 managed workflow 运行期间独立轮询 sandbox 的 `.langalpha/progress.jsonl`，只在 typed `inserted` 或 payload 一致的 `already_exists` 返回后推进持久化字节 offset；临时数据库失败保留 pending line 并按有界退避重试，不会跳过事件。服务重启后重读相同字节会命中 `(attempt_id, sequence)` 幂等写入；同一 `event_key` 可通过后续 sequence 更新状态投影。
- collector 读取超过 16 MiB 的文件、超过单行上限、非法 JSON、路径/凭据类内容或数据库暂时不可用时只记录有界错误，不中断 managed workflow。最终 graph 收口前会再 flush 一次，且在模型或工具 SSE 长时间空闲时，仅根据已脱敏工具活动生成 `substage=executing`、`label=执行环境步骤` 的有界 fallback 投影，不覆盖已完成的语义阶段。
- structure、lesson 和 book pipeline 共用的 workflow wrapper 现在负责启动、记录活动并停止 collector；assets workflow 本轮不接入语义进度，捕获实际 sandbox 失败/关闭时仍不留下后台轮询任务。新增 service 层真实 PostgreSQL 写入测试，验证同 attempt/sequence 的同 payload 幂等、不同 payload 拒绝、同 event_key 状态更新、错误 run 与跨 job attempt 拒绝；只有 inserted 或内容一致的 already_exists 才能触发 checkpoint。
- 新增迁移 `081_book_pipeline_checkpoint`，在 generation job 上持久化不可变 `checkpoint_bundle_prefix`，数据库约束只接受 `education/` 下且不含 `..` 的私有对象前缀，并要求 `awaiting_review` 必须有非空 prefix；有 checkpoint 数据时 downgrade fail-closed。
- `pause_after_chapter_analysis=true` 不再由公开 API 强制返回 409。collector 持久化并观察到 `chapter_analysis/completed` 后先设置 stop signal；workflow wrapper 必须关闭 graph/consumer、确认没有 pending producer，完成 collector final flush 后，才归档完成章节所需的 `book_package.json`、`content_tree.json`（存在时也包含知识点与资产 manifest）并原子进入 `awaiting_review`。停止超时或归档失败不会产生不一致 checkpoint。
- checkpoint continuation bundle 的 manifest 绑定 generation job、content version、source attempt、固定 projection keys、大小和 SHA-256，并以 manifest 作为最后写入的提交点。恢复时重新校验 prefix ownership、manifest lineage、固定 key、大小和哈希后才 staging 到新 sandbox；跨 job、错 attempt、错 key 或损坏内容均转为 transition error。
- resume API 现在消费 `awaiting_review`，将同一 job 重新排队并立即创建 continuation attempt；恢复时只从私有 checkpoint bundle 还原固定 projection 到全新 sandbox，使用 `mode=full-pipeline-continuation` 从 Steps 4-9 继续，不重放 Steps 0-9、不重新分析章节。packaged managed overlay 同步声明 continuation 模式和权威 checkpoint 输入。
- 新增测试覆盖：collector 文件增长、半行缓冲、重启重放、行/文件上限、最终 flush、15 秒 fallback、checkpoint callback 单次触发、structure/lesson/book pipeline 实际 dispatch wiring、checkpoint bundle 归档/恢复、终止时不导入部分包、resume 启动 continuation，以及真实 PostgreSQL 的幂等 ownership、081 字段与前缀约束。

### 新增：统一教材处理语义进度协议

- 新增迁移 `080_education_job_progress`，为 attempts 增加 `(generation_job_id, attempt_id)` 唯一键，并创建 `education_generation_progress_events`，用 `attempt_id + sequence` 唯一约束形成 append-only 事件序。`event_key` 只表示逻辑身份，同一 key 可以在后续 sequence 重试追加，Task 7 的投影按 key 保留最新状态，不会把模型重试变成数据库唯一冲突。progress 同时引用 job 和 attempts 的复合 ownership pair，两个外键均级联删除，跨 job 使用其他 attempt 的写入会在 PostgreSQL 层拒绝。
- managed Bash 策略新增唯一窄授权：仅允许 `python .langalpha/progress.py` / `python3 .langalpha/progress.py` 使用 stdin 或一个 strict JSON object 参数；shell chaining、命令替换、重定向、绝对解释器和绝对 helper 路径仍拒绝。managed write 策略对 structure/assets/lesson/book_pipeline 统一允许 `.langalpha/progress.jsonl`，direct Write/Edit 逐行调用与服务端 parser、staged helper 相同的 `parse_progress_json_line`，完整执行 event_key、Unicode `Cf`、路径/凭据和输入上限校验；其他 `.langalpha` 文件继续拒绝。overlay 明确要求调用 staged helper，不允许直接重写 JSONL。
- 新增 `parse_progress_event`，固定 `chapter_analysis`、`content_processing`、`knowledge_point_generation`、`lesson_preparation` 四个用户可见阶段及 `queued/running/completed/failed/skipped` 五种状态；substage 归一为小写安全 token，label/detail 分别截断为 200/1000 字符。
- 脱敏与路径规则在服务端 parser 和 staged helper 间共享同一组正则。裸 `private_key`、`public_key`、`token`、`client_secret` 等普通领域词不再误报；API/ACCESS/SECRET KEY、PASSWORD/PASSWD/TOKEN 赋值、JSON-like 凭据字段、OPENAI/ANTHROPIC/GITHUB 凭据、`ghp_`/`github_pat_`/`sk-`/`AKIA...`/`ASIA...` 等真实凭据形态仍拒绝。路径只拒绝字符串起始绝对路径、敏感 root、多段 path、带扩展名路径、Windows drive path 和 UNC host/share；`TCP /IP`、`1 /3`、`Reading A /B`、`1 / 3`、`Reading A / B` 均正常通过。
- 每行原始 progress JSON 在解析前限制为 64 KiB，每个字符串字段在任何 regex 前限制为 8 KiB，staged helper 的 argv/stdin 使用同一限制并做有界读取；label/detail 继续截断到既有更小上限。普通文本允许，但零宽字符、bidi 控制和其他 Unicode `Cf` format controls 会拒绝。helper 与服务端共享 64-bit metadata integer 上限常量，避免漂移。
- 进度字段只保留 `event_key`、stage/status/substage、安全 label/detail、`node_key`、可选 `current_value/total_value`、带时区的原始 timestamp 和经过递归白名单清洗的 metadata；同时提供计数非负、整数上限、`current <= total` 与非有限浮点数校验。
- `stage_managed_teaching_skills()` 现在额外写入固定的 `<root>/.langalpha/progress.py`。该 helper 不接受 skill 代码注入，不访问网络或数据库，只接受 argv/stdin 中的 strict JSON 对象，拒绝重复 key，并仅以 append 模式逐行写入 `<root>/.langalpha/progress.jsonl`；测试实际执行 staged helper 验证续写、stdin、截断和非法事件不落盘。
- Task 6 只提供事件协议、持久表与 sandbox 写入助手；读取文件、增量持久化、checkpoint 触发和 continuation 仍由 Task 7 接入，当前不伪造任何用户可见进度。
- 验证：Task 6 聚焦测试 `164 passed`，managed policy/overlay `66 passed`，storage `28 passed`，migration 回归 `131 passed`，真实 PostgreSQL ownership/unique/index/cascade/downgrade integration `4 passed`，修改文件 Ruff 与 `git diff --check` 通过。

### 新增：通用教材包导入与统一流水线启动

- 新增迁移 `079_book_pipeline_package_import`：允许 legacy 知识点保留空 `unit_id`，为生成候选增加 `content_node_id`、`candidate_key`、开放 `point_type`、`origin` 与 `candidate_status`，并约束 generated candidate 必须绑定内容节点和候选键；唯一索引限制同一内容节点下的候选键重复。`book_pipeline` 完成后可回填 `structure_id`，长 `source_revision` 扩展为 255；存在通用包数据或已完成流水线绑定时 downgrade fail-closed。
- managed package 导入固定读取 `book_package.json`、`content_tree.json`、`knowledge_points.json` 和 `assets_manifest.json`，统一使用 strict UTF-8 JSON 解析并检查两份 projection 与权威 `book_package.json` 一致；只下载 manifest 明确声明的资产，校验路径、大小和 SHA-256，未声明输出不会枚举或导入。
- 已验证包在单个 PostgreSQL 事务中创建 `langalpha-book-content-tree/v1` 结构 revision，先根后子写入通用内容树，写入已归档资产和 `origin=generated`、`candidate_status=pending` 的知识点候选，最后原子完成 pipeline attempt/job 并绑定 structure；任一写入失败会回滚全部数据库行。
- 原始四个 JSON、manifest 明确资产和文件哈希归档到 `education/<household>/<textbook>/vN/book-packages/<job_id>/` 私有前缀，结构记录的 `bundle_prefix` 与 manifest hash 提供不可变包投影。
- 创建任务 API 在 durable queue 去重完成后通过既有 `WorkspaceManager`、`RunCoordinator`、`LocalRunExecutor`、`RunSSEProducer` 和 managed PTC graph 启动 full-pipeline；复用 running/awaiting 任务不会二次启动，并发启动仍由 attempt claim 单写者约束收口。运行成功进入 package import，失败、取消、无效包和归档错误分别完成失败结算。
- launch 前新增数据库原子 `queued -> preparing` claim fence；并发 queue-and-launch 只有一个请求创建 workspace/thread/attempt 并进入 executor，其余请求返回同一 job 且不创建孤儿资源。workspace、thread 或 attempt claim 任一失败时使用 `fail_claimed_book_pipeline_launch()` 原子收口 `preparing -> failed`；attempt 建立后的输入读取、manifest hydration、staging、graph 组装和 dispatch 使用同一失败边界，任何异常/取消都会结算当前 attempt/job，不会遗留 active preparing。
- package import 显式使用本次 launch 的 `attempt_id`，不再回退到 `latest_attempt_id`；retry/continuation 会完成当前 running attempt，旧 completed attempt 只保留历史状态。
- `pause_after_chapter_analysis` 的章节完成后 pause hook 已提供，但语义进度 collector 尚不存在；公开 queue/API 会在任何 parent 查询或数据库写入前用 `TextbookTransitionError`（HTTP 409）拒绝 checkpoint 请求，避免遗留无法推进的 queued job。Task 7 必须在持久 `chapter_analysis/completed` 事件可用后移除该 guard，并接入 continuation prompt；当前保证默认非 checkpoint full pipeline 可启动、导入并完成，不伪造章节暂停成功。
- `validate_book_package` 支持按 `source_id`/`content_chapter_id` 提供多份 frozen Markdown；每个字符或行范围、canonical quote 和知识点归属都针对实际来源校验。多来源缺少或未知 `source_id` 会 hard fail，只有一个来源时允许默认并产生 warning。legacy `markdown=` 只接受空 source ID 或固定兼容 ID，避免单 Markdown 接口接受伪造来源。managed prompt/overlay 同步明确该规则。
- `079` 为 generated candidate 增加 `content_structure_id` 与 `(content_structure_id, content_node_id)` 复合 FK，结构归属与节点所有权必须一致；跨 structure 绑定在 PostgreSQL 层拒绝。sequence 分配前锁定 content version 行，legacy structure 与 package import 并发时不会取得相同 sequence。
- `education_book_pipeline` managed kind 使用与 `education_teaching` 相同的 abandoned/reconnect timeout 窗口；新增等于 PostgreSQL INTEGER 上限通过、超过上限拒绝的 asset size 边界测试。
- 079 downgrade 同时覆盖有通用包数据时 fail-closed 和无相关数据时完整成功并可回滚事务的路径。
- 验证：Task 5 服务/API/DB/迁移聚焦测试 `172 passed`，server services 回归 `1508 passed`，database `375 passed`，Education/managed skill `111 passed`，migration `128 passed`，079 真 PostgreSQL package/queue-launch/checkpoint integration 合并运行 `21 passed`；覆盖多来源、单赢家 launch fence、workspace/thread/attempt 与读取/hydration 失败收口、当前 attempt、sequence 并发、跨 structure FK、downgrade 成功/失败、真实 dispatch runtime 与 bundle 归档，修改文件 Ruff 通过。

### 新增：教材处理补充要求与幂等启动

- 新增迁移 `078_book_pipeline_idempotency`，任务表持久化可选 `request_id` 和处理补充说明；补充说明限制为 4000 字符，同一内容版本下非空 `request_id` 唯一。
- 创建统一教材处理任务现在支持客户端请求 ID 幂等：同一版本重复提交同一 `request_id` 直接返回既有任务；不同请求命中已排队、准备、运行、校验或待审阅任务时也复用同一任务，并在响应中返回 `reused_existing_job`。
- 处理补充说明会去除首尾空白，明确允许内部制表符、换行和回车，并按 Unicode `Cc` 类别拒绝其余控制字符，包括 DEL 与 C1；它参与 processing profile hash，但暂停检查点开关仍不改变 profile 身份。
- `078` downgrade 在存在非空 `request_id` 或补充说明时 fail-closed，避免静默丢弃幂等与处理说明数据；无数据时仍可安全撤销字段和唯一索引。
- `managed_book_pipeline_prompt` 可在非空时追加独立的用户补充说明段；brief 中的 XML-like 字符会先转义再放入 delimiter，closing tag 后再次声明 managed contract、安全边界、输出路径和校验规则始终优先，任何覆盖尝试都必须忽略。
- 新增教材处理启动页 `/textbooks/:textbookId/versions/:versionId/processing`：开始前必须打开“补充要求（可选）”对话框，空说明可提交；提交期间启动和确认按钮冻结，本地提交锁与 mutation pending 状态共同阻止双击重复请求。
- 教材详情页的待加工版本改为进入统一处理启动页，既有结构与知识点课程入口在已有结构时继续保留。
- 计划中的后续进度 migration 先后顺延为 `079_education_job_progress`、再因 Task 5 引入 package import 迁移而顺延为 `080_education_job_progress`，并修正 Education API 与路由的真实文件路径。
- 验证：Task 4 后端聚焦测试、078 真实 PostgreSQL migration/并发 integration、相邻回归、前端启动页与教材详情测试、Ruff 与 TypeScript 类型检查结果按本次交付记录。

### 新增：统一教材处理任务台账与检查点 API

- 新增迁移 `077_book_pipeline_jobs`，扩展现有 `education_generation_jobs`：增加 `book_pipeline` scope、`awaiting_review` 状态和 `pause_after_chapter_analysis` 持久字段；`book_pipeline` 必须绑定 content version，且不允许提前绑定 structure 或知识点，现有 structure/assets/lesson 目标约束保持不变。
- 新增家长专属统一任务 API：创建/复用版本下的处理任务、读取任务投影、从章节检查点恢复；前端可轮询同一任务，后续增加 SSE 不需要改变这些持久契约。
- 创建任务在事务级 advisory lock 和内层 active job 查询中完成去重，同一 content version 在同一时间最多存在一个 queued/preparing/running/validating/awaiting_review 的 `book_pipeline` 行，重复点击返回既有任务而不是创建并行 sandbox run。
- `pause_after_chapter_analysis=true` 的契约由同一 job/attempt 台账实现：章节分析完成时收口当前 attempt 并进入 `awaiting_review`；resume 消费一次性 pause 标记，将同一 job 重新置为 `queued`，后续运行接入继续复用既有 attempt 链。
- checkpoint pause 现在必须同时匹配 parent、job version 所属教材家庭和 parent membership；错误家长、错误 scope、错误 attempt 或非 running 状态都不能完成 attempt 或修改 job。
- checkpoint resume 同样在数据库层校验 parent、version、textbook 与 household membership；错误家庭不能消费 pause 或改变 job ledger。
- checkpoint pause 与既有 settle 路径统一为 attempt-first 锁顺序：先锁定 attempt，再更新 attempt，最后锁定并更新 job；新增真实 PostgreSQL 两事务验证 attempt 锁竞争时 job 锁仍可用，避免与 settle 形成死锁。
- 077 新增状态约束，只有 `book_pipeline`、`pause_after_chapter_analysis=true` 的 job 才能进入 `awaiting_review`；downgrade 先恢复旧 status 约束，分别用 only-book_pipeline 和 only-awaiting_review 数据证明两类新状态都会 fail-closed。
- `book_pipeline` 的 processing profile hash 不再包含 checkpoint mode，pause/resume 不改变同一 job 的不可变 profile 身份。
- 旧通用 `create_generation_job()` 明确拒绝 `book_pipeline` 并指示调用统一 `queue_book_pipeline_job()`，避免绕过版本锁和 active job 去重产生并行任务。
- 077 downgrade 采用 fail-closed：存在 `book_pipeline` 或 `awaiting_review` 数据时恢复旧约束会失败并保留数据，不静默删除或转换；无相关数据时才允许撤销本 migration 的 scope/status/column。
- Task 3 仅建立持久任务与状态转换契约，不伪造 package 导入；实际 managed runtime 启动、暂停调用和产物导入按后续 Task 5/7 接入。
- 新增真实 PostgreSQL integration：两家庭 pause/resume ACL 与 attempt/job 状态迁移、attempt-first 锁顺序、实际 077 DDL 的合法/非法 scope、status、target、awaiting_review 组合约束、pause 字段默认值与 NOT NULL、两连接 advisory-lock 去重，以及有/无新数据时的 downgrade 行为。
- 验证：Task 3 focused 与 077 integration 通过，Education app/service、相邻 structure/asset/retry 和 migration 回归通过，Ruff 检查通过；本地 PostgreSQL 已实际升级并确认 head 为 `077_book_pipeline_jobs`。

### 新增：book-to-skill 完整 managed 流水线契约

- 新增 `managed_book_pipeline_prompt` 的 `mode=full-pipeline`，要求在 managed `book-to-skill` 的一次执行中完整运行 canonical Steps 0-9，并同时保留 canonical 教材 skill 资产与 `book_package.json`、`content_tree.json`、`knowledge_points.json`、`assets_manifest.json`、`progress.jsonl`。
- managed overlay 按调用方 prompt 分派模式；既有 `mode=analyze-pass` 明确保留 Steps 0-3、只写 `structure.json` 的 v2 结构分析契约，不被 full-pipeline 条款覆盖。
- analyze-pass overlay 恢复完整的 `units/readings` v2 schema 示例与边界规则，包含 Reading A/B、技能字段和 1-based 半开行号。
- 新增 `education_book_pipeline_policy`，以 `book_pipeline` purpose 沿用 managed root、Skills、MCP、web、Vault 和 subagent 边界；写策略仅允许四个 package JSON object、逐行 JSON object 的 progress、canonical book-skill 文件，以及首个路径段固定为 `outputs`、指向允许扩展名文件的内容资产。
- manifest 契约明确分为两层：managed write policy 只检查 root、路径/文件名/扩展名和 JSON/JSONL 格式，不检查 manifest 成员关系；导入阶段仅下载 `assets_manifest.json` 明确声明的路径，未声明文件永不下载或导入。
- package、canonical JSON 与 progress write gate 统一使用 strict JSON 解析，拒绝 NaN/Infinity/-Infinity、`1e999`/`-1e999` 等非有限浮点数和重复对象键；asset path 继续拒绝绝对路径、traversal、反斜杠、所有 C0 控制字符，以及非 `md/json/txt/csv/png/jpg/jpeg/webp/svg` 文件。
- progress write gate 要求每条非空事件包含 `event_key`、`stage`、`status`，stage/status 使用固定枚举，并拒绝 reasoning、prompt、tool、credential、secret、sandbox path 等明确禁止字段；Task 6 下游 parser 继续负责完整归一化、截断和持久化。
- managed overlay 改为通用内容树契约：节点和知识点类型开放，不强制 Unit → Reading A/B、不要求层级对称，缺少 Reading 或零知识点可以继续；知识点始终只生成待审核候选。
- `node_type` 与 `point_type` 现在只做 trim/lower、长度和控制字符安全归一，未知描述性类型保留原值并产生 warning，不再改写成 `other`。
- 来源引用只接受确定性的半开字符范围或 1-based 行范围，同一引用不能混用；`quote` 仅作可选描述，服务端忽略并从范围派生原文，无法确定范围时保留空引用而不是捏造。
- managed 模式明确禁止用户提问、网络、MCP、Vault、普通 workspace 和根目录外写入；progress 仅允许固定业务阶段与脱敏语义检查点，每条事件要求 `event_key`、`stage`、`status`，且 status 仅允许 `queued | running | completed | failed | skipped`。
- 验证：Task 2 与 managed overlay 聚焦测试 `17 passed`，managed execution policy `49 passed`，book package `65 passed`，migration 回归 `119 passed`，修改 Python 文件 Ruff 与格式检查通过。

### 新增：通用教材内容树与 book package 校验契约

- 新增迁移 `076_generic_content_tree`，创建 `education_content_nodes` 与 `education_content_assets`，支持任意父子层级、稳定节点键、来源引用和内容资产元数据；同级 position 使用 `NULLS NOT DISTINCT`，并通过复合外键阻止跨 structure 的 parent 与 asset 引用；structure 删除级联清理节点与资产，被引用 parent 删除保持受限。
- 新增 `validate_book_package`，仅对来源范围、父子引用、键唯一性、知识点归属、路径安全和 UTF-8/大小限制执行硬校验；未知类型与非标准教材结构转换为 warning，不阻断处理。
- 来源引用改为确定性 char/line range 契约：`char_start + char_end` 或 1-based `line_start + line_end` 必须完整落在冻结 Markdown 内；两种范围字段禁止混用。模型提供的 `quote` 仅作描述并被忽略，规范化输出始终从范围切片重新生成 quote；raw string、仅 quote、越界范围和不完整范围 hard fail。空、缺失或 null `source_refs` 保留 warning；行号索引只在确有 line refs 时构建，并且只保存请求行。知识点范围必须完整落入所属节点的至少一个范围。
- 缺失 position 会在同级未使用位置中确定性补齐；position 和 asset size 执行 PostgreSQL 可持久化范围校验；非法或越界 confidence 按现有结构校验模式 warning 后使用有限默认值或 clamp，绝不输出 NaN/Inf。
- 最终归一化 JSON 递归拒绝含 NUL 的键和值，避免 PostgreSQL TEXT/JSONB 持久化失败。
- 验证：迁移与 package 契约 `43 passed`，真实 PostgreSQL 约束、级联和 downgrade integration `4 passed`，迁移回归 `119 passed`，相邻结构/资产校验回归 `18 passed`，`TextbookStructurePage` Vitest `10 passed`，Ruff 与 TypeScript 类型检查通过。

## 2026-09-21

### 验证：canonical 教材流水线端到端契约

- 新增真实 REX 3 Markdown 集成测试：从实际 Unit / Reading 行号验证 scope 换算、Reading A/B 独立切片、知识资产输入和 lesson 原文上下文没有串读。
- 集成测试发现并修复 lesson 标题字段兼容问题：持久化 scope 使用 `title`，课程上下文现在同时兼容审核投影里的 `scope_title` 与数据库的 `title`。
- 本地数据库已升级到 `075_reset_textbook_pipeline`；旧教材根记录、结构、scope、课程和任务计数均为 0，旧教材对象已按 3 个精确前缀删除 329 个，未扫描其他教育对象。
- 验证：后端完整单测 `7886 passed, 1 xfailed`，真实 Markdown integration `1 passed`，Education 前端 `56 passed`，类型检查、生产构建和关键路径预算通过，修改文件 Ruff 通过。
- 已知仓库级验证噪音：直接执行 `uv run pytest -m integration` 会在收集 `libs/ptc-cli/tests` 时触发既有 `tests.conftest` 模块路径冲突；本变更使用独立 integration 文件验证，不涉及该库。

### 改进：重置旧教材流水线数据

- 新增迁移 `075`：通过 `TRUNCATE education_textbooks ... CASCADE` 清除所有旧版本、结构、Reading scope、知识点课程、发布、作业和学习进度，不再兼容旧结构数据。
- 重置不删除共享的 `education_assets`，也不会影响非教材对象；真实执行前仍保留独立脚本用于清点并删除明确的教材对象。
- 新增 `scripts/education_purge_prefix.py`：默认 dry-run，并要求显式传入每本教材的 `education/<household>/<textbook>/` 精确前缀；只匹配该前缀下的 `vN/...` 与 `source-bundles/`，不扫描或删除同命名空间中的普通教育附件。
- 存储层补充受控的前缀列举能力；清理脚本不会接受或删除前缀之外的对象。
- 验证：重置迁移与清理脚本聚焦测试 `4 passed`，修改文件 Ruff 通过。

### 改进：知识点课程绑定单一 Reading

- 新增迁移 `074`：知识点增加 `scope_slot`，只能关联 `reading_a` 或 `reading_b`，不再由课程任务默认取 Unit 的第一个范围。
- 结构审阅页为每个知识点提供 Reading 选择器；未关联、范围缺失或范围未验证时，课程生成按钮保持锁定。
- lesson prompt 现在同时读取该 Reading 的确定性原文切片和 canonical 生成的知识稿，课程生成前会校验知识点确实拥有对应 Reading。
- Reading 知识稿从已归档 manifest 按 `unit_id + slot` 读取，并校验对象路径、字节数和 SHA-256，找不到或内容损坏时停止生成。
- 验证：迁移、结构、lesson 与存储聚焦测试 `60 passed`，结构页 Vitest `10 passed`，`pnpm typecheck` 通过。

### 改进：按 Reading 生成教材知识资产

- 章节知识包生成改为 canonical `book-to-skill` generate pass：每个 Reading 使用服务端裁剪后的独立 Markdown 输入，不再把整本书作为无边界上下文交给模型。
- 新增 `langalpha-managed-reading-assets/v2` 输入/输出契约，为每个 Reading 固定生成 `knowledge.md`、`glossary.md` 和 `cheatsheet.md`，服务和模型之间不传递自由文件名。
- Reading 产物按 Unit 与 Reading slot 的稳定路径归档，manifest 记录文件路径、大小和 SHA-256；下载端只接受 manifest 明确列出的文件。
- 没有已验证 Reading scope 的结构不能启动知识包生成。
- 验证：教材知识包与 Reading 资产聚焦测试 `37 passed`，修改文件 Ruff 通过。

### 改进：结构审阅显示 Reading 范围验证状态

- 教材结构响应现在为每个 Unit 返回已持久化的 Reading A/B scope，包含标题、行号与字符区间以及 `verified` 状态。
- 结构审阅页新增“范围待确认”提示；Unit 没有有效 scope 或 scope 未通过验证时，知识点课程生成按钮会锁定，避免再次基于无依据范围生成课程。
- 人工编辑并保存结构时会保留匹配 Unit 的既有 Reading scope，不再因 Unit 重建而级联删除权威范围。
- 验证：结构数据库与审阅服务测试 `24 passed`，结构页 Vitest `9 passed`，`pnpm typecheck` 通过。

### 改进：教材结构审阅进度与原文依据

- 结构生成改为原子去重：内容版本行锁加事务级 advisory lock，同一版本存在 queued/running 任务时直接复用，重复点击不会再创建并行的 sandbox 任务。
- 结构 GET/详情响应补充 `latest_generation_job` 摘要（状态、尝试次数、`root_run_id`、开始时间、心跳时间），页面刷新后仍能恢复进行中的任务时间线。
- 教材结构页新增 Mentrix 式处理时间线：展示排队、准备输入、结构分析、校验归档、进入审阅五个阶段，以及耗时、心跳和失败原因；弹窗确认和重跑按钮在请求期间锁定。
- 新增 `GET /api/v1/education/knowledge-points/{id}/source-preview`：在结构仍为 review、课程尚未生成时，也能查看该知识点的原文引用和上下文 Markdown。
- 知识点工作区新增“课程 / 原文依据”双视图：无课程时默认展示原文依据，审阅时可以对照原文决定拆分或合并。
- 原文定位在精确 quote 失败后增加空白归一化回退，PDF Markdown 的换行和加粗不再导致摘录退回到文档开头。
- 知识点的 quote 上下文窗口扩展为定位点前后各 1200 字符，并按来源返回截断标记。
- 结构树补充删除 Unit 与删除知识点的审阅操作，删除后自动重排 1..N；点击 Unit 标题同时选择并展开/收起。
- 修复“删除 Unit 后找不到保存入口”：知识点工作区顶部也提供“保存结构 / 接受结构”，删除 Unit 的提示明确说明改动只存在于草稿，未保存时刷新会恢复。
- 结构保存与接受的标题、tooltip 和右侧栏分组标签明确其作用范围是整本教材的全部 Unit 与知识点，不是当前选中的 Unit。
- 修复课程审阅页在结构仍是 `review` 时仍显示“生成课程”按钮的问题：现在改为引导先返回接受结构，并说明生成请求会被服务端拒绝的原因。
- 新增教材结构加工的实时处理活动面板：从 run 的 SSE 事件投影出“读取冻结输入清单、扫描源文档、检索章节线索、派出并行子任务、收集结果、生成结构草稿”等安全的高层步骤，前端每 4 秒轮询并自动滚动到最新一条。
- 处理活动只暴露工具名、文件名和计数，剔除模型思维链、prompt、工具参数与结果正文；沙盒策略拦截的受限命令标记为“已跳过”而不是失败，重复步骤合并为 `×N`。
- 新增 `GET /api/v1/education/structure-generation-jobs/{id}/progress`，仅家长可读，返回去重后的活动事件、任务状态和截断标记。
- 修复知识点课程生成在来源引用没有解析出 `start/end` 时直接失败的问题：`build_lesson_source_context` 现在会先用 quote 做结构化定位、再做空白/换行归一化近似定位，最后退回来源文档前段，并把所用策略作为 warning 记录，不再让整节课中断。
- 课程来源摘录在定位片段过短时向两侧各扩展 1200 字符（至少 3000 字符窗口），保证 lesson prompt 有足够的原文材料。
- 课程准备阶段的真实异常现在会写入服务端日志，用户侧仍保持通用错误文案。
- 知识点工作区补上课程生成的进度卡片：此前只有课程页有进度展示，结构页的知识点视图只显示一个转圈按钮，现在生成期间会显示阶段时间线、实时处理步骤、心跳和耗时。
- 新增 `GET /api/v1/education/knowledge-points/{id}/lesson-generation`：返回该知识点当前进行中的课程任务（状态、尝试次数、started_at、heartbeat_at、root_run_id），刷新页面后也能恢复进度展示，而不是丢失任务关联。
- 进度卡片按 Mentrix 的呈现方式重做：顶部一行显示当前阶段、秒级实时计时、尝试次数和“阶段 N/5”，可展开查看五个阶段；处理活动嵌套在阶段下方并对齐缩进，重复步骤继续合并为 `×N`。
- 进度卡片抽成共享组件，结构与课程两种生成任务复用同一套展示。
- 原文依据预览不再按固定字符窗口截断：优先用 Markdown 标题定位知识点所在的**完整小节**，取到下一个同级或更高级标题为止；没有标题结构时才退回 PDF 页码分隔符推断。知识点来源引用没有 `start/end` 时也走同一套逻辑。
- 小节过长时仍保留 18000 字符上限，并且始终保证被引用的 quote 落在窗口内；截断标记改为相对小节边界判断，不再误报“后文已省略”。
- 课程生成的来源摘录复用同一套小节边界逻辑，lesson 拿到的原文材料从单句窗口变成完整小节。

## 2026-09-20

### 重构：清理旧教学包运行时与 schema 残留

- 修复知识点课程真实链路中的字段漂移：staging 现在使用 `generation_job_id` 和 `knowledge_point_source_refs`，课程归档在未预分配 revision 时使用作业 UUID 生成唯一不可变路径，避免并发覆盖或无效版本号。
- 修复 lesson 启动错误被误报为“知识点不存在”：只有排队阶段找不到 accepted 知识点才返回 404，sandbox/运行启动失败保留真实错误类型和日志。
- 删除旧教学包专用 service 模块、数据库函数和测试：`education_managed_ptc`、`education_teaching_jobs`、`education_teaching_assets`、`education_teaching_validation` 及其 attempt/archive/asset review 数据访问。
- 学生学习追问上下文收敛为已发布知识点课程，移除旧的章节级学习上下文和旧章节学习 API 字段。
- 清理教学存储模块中旧教学包归档、下载和 manifest writer，只保留结构、知识包和知识点课程实际使用的能力。
- 修复迁移 `071` 后的 schema 漂移：发布结构时不再写已删除的 `publication.teaching_package_id`；本地 PDF 内容落库时不再写已删除的 `teaching_material`、`teaching_material_key` 和 `education_chapter_questions`。
- 更新图书馆教材使用投影测试到 structure/book asset 字段，并移除已废弃的 frontend teaching-package 类型和 mock 数据。
- 验证：后端完整单测 `7863 passed`，结构/发布/内容处理聚焦测试通过，修改文件 Ruff 与 `pnpm typecheck` 通过。

### 改进：教材结构保留非阻断校验警告

- 新增 `education_textbook_structures.validation_warnings`，结构生成或人工编辑时产生的可恢复问题会随结构版本持久化，沙盒关闭后仍可查看。
- 教材结构页改为 Mentrix 式树状工作区：Unit 为一级节点，知识点为二级节点；点击知识点后在右侧内容区直接显示未生成引导或已生成 Markdown。
- 知识点树增加课程状态标记：未生成、待审阅、已通过；结构请求补充每个知识点的 `lesson_status` 和 `lesson_revision_id`，不修改课程数据。
- 树状目录进一步贴近 Mentrix：Unit 数量以内联括号显示，二级缩进收紧，长标题 hover 后横向滚动；课程状态改为左侧贴边 accent bar，已通过使用绿色。
- accent bar 改为复刻 `.sidebar-panel-item.active::before` 的独立 CSS class 实现，移除二级容器的 `border-l` 和按钮上的 box-shadow，避免内外弧形边。
- 收紧树状导航的 grid/flex 宽度链路，给 aside、nav、Unit 包裹层、子级列表和按钮统一增加 `min-width: 0` / `max-width: 100%` / `overflow-hidden`；超长标题只在自身容器内 hover 滚动，不再穿过中栏。
- 左侧知识点栏改为固定视口高度：顶部工具栏增加知识点 icon、全部展开/收起和栏位折叠按钮，目录主体独立滚动，底部增加“知识点学习 / 个性化总结”胶囊切换占位。
- 修复 accent bar 被按钮 `overflow-hidden` 裁掉的问题，并让删除知识点时自动重排剩余的 1..N 顺序号。
- 宽屏使用更宽主区域，树中长 Unit 标题强制截断并提供完整悬停标题，Unit 编辑区仍保留独立的来源面板。
- 知识点行改为“编号、标题、来源、操作”结构，四个操作按钮统一放入独立工具栏，并增加中文 tooltip：查看课程、拆分知识点、与上一个合并、删除知识点。
- “知识点”标题旁新增操作说明，“生成教材知识包”明确提示其作用于整本当前已接受结构，而不是当前 Unit。
- 结构生成、来源 quote 解析和编辑校验不再因为可选引用定位、缺失来源、类型推断或 slug 去重而直接丢弃已经可用的教材内容。
- 来源引用的 `start/end` 改为真正的可选诊断字段；无法定位 Markdown 偏移时仍返回 quote 和来源信息，审阅页只显示“未定位偏移”，不再因响应模型要求整数而 500。
- 教材结构审阅页新增紧凑警告条，按警告类型和出现次数展示自动处理结果；用户仍可继续编辑、接受结构和生成知识点课程。
- 新增迁移 `072`、数据库持久化回归和 API 响应契约测试。
- 真实 `REX 3e SB3.pdf` 数据完成结构分析：20 个 Unit、84 个知识点、7 条可恢复引用告警，成功归档到 `structures/v2` 并进入 review。
- 真实 Unit 1 知识点课程生成成功：`lesson.md` 17KB，包含学习目标、读前准备、分步讲解、词汇、易错点、复习和练习，并已审批为 `approved`；发布仍按既定规则等待其余 83 个 accepted 知识点也具备 approved lesson。
- 验证：迁移测试、结构数据库/任务/审阅测试通过；结构页前端测试、`pnpm typecheck` 和 Ruff 通过。

## 2026-09-18

### 重构：教材加工改用 book-to-skill 的容错处理链路

- 抽取共享 managed run 运行时，结构任务和知识点课程任务不再依赖旧教学包模块构建 PTC graph 与解析模型配置。
- 新增服务端来源 quote 解析器：优先精确匹配，其次空白归一化匹配；重复 quote 使用首个位置并告警；无法定位时保留 quote 并标记 unresolved，不阻断结构审阅。
- 将结构校验从格式裁判改为稳定化处理器：`position` 按数组顺序生成，`slug` 由服务端规范化或使用 `unit-01` / `kp-01` 兜底；旧 `start/end` 可在可恢复时回填 quote。
- 非教学 Unit 携带知识点时保留内容并提升为 teaching；缺失 source refs、confidence、summary 等可选字段产生 warning，而不是让整本教材失败。
- 只有无法解析、没有可用 Unit、路径越权或数据不安全时才硬失败。
- 结构编辑按 slug 复用 Unit 和知识点的 UUID，重命名和重排不再导致身份变化。
- 知识点课程生成改用 `book-to-skill` managed lesson mode；`the-knowledge-guy` 退出课程正文生成，保留为后续交互学习层。
- 新增结构失败重试：同一 structure job 重新入队，结构状态回到 `queued/running`，结构和内容版本保持不变；结构审阅空态提供“重新运行结构分析”。
- 新增 `book-to-skill` 章节资产模式：受管生成 `chapters/*.md`、`glossary.md`、`patterns.md`、`cheatsheet.md`、`nutshell.md` 和 `chapters_manifest.json`，并归档到结构版本的 `book-assets/` 前缀。
- 章节资产使用独立的 `assets` generation job，不修改 structure review 状态；结构审阅页已接受结构后可以启动生成或重新生成知识包。
- 图书馆“教材资产”改为读取教材结构、结构版本、知识包 manifest 和 publication，不再查询旧教学包表。
- 新增迁移 `071`：删除旧教学包、旧章节题目、旧章节学习进度/答案和 legacy textbook source 表；publication 现在只允许关联 structure，`teaching_package_id` 已移除。
- 恢复扫描器和教材学习入口同步退出旧教学包恢复/章节学习路由，避免已删除表被后台任务继续访问。
- 补充 `book-to-skill` 的 Mentrix 风格知识点课程 contract，明确 `lesson.md` 是单个知识点的完整静态学习页，不包含追问、笔记或个性化总结。
- 从公共教材 API 移除旧教学包、教学 job 和旧 version publish 路由，只保留结构审阅、知识点课程和 structure publication。
- 清理前端旧教学包 API、查询键、类型和 `TeachingRunDrawer`，教材加工前端只保留结构、知识点课程和发布链路。
- 验证：结构标准化、来源解析、结构任务、lesson 任务、共享运行时和 skill contract 聚焦测试通过，Ruff 通过。

### 重构：教材加工切换为独立入口与分阶段工作流

- 教材加工从 `/education/textbooks` 迁出为一级入口 `/textbooks`，父账号侧栏直接显示“教材加工”；学生导航不展示该入口。
- 教材详情页只保留新链路：内容准备、结构分析、知识点课程、发布四个阶段，旧教学包加工、旧知识资产标签和旧运行抽屉不再出现在用户主路径。
- 新增共享教材工作流步骤条，参考 `/setup/method` 的节点和连接线样式；步骤状态由内容版本、结构状态、知识点接受数、课程生成数和课程通过数实时计算。
- 结构 API 返回 `lesson_summary`，包含知识点总数、已接受数、已生成课程数和已通过课程数，供步骤条显示真实进度。
- 结构页增加相同的工作流步骤条；结构任务未产出任何 Unit 时显示明确空态，不再返回空白页。
- 新增一级导航和路由测试，覆盖父账号可见、学生不可见、`/textbooks` 路由、结构入口、课程进度和发布门槛。
- 已清空教材域历史数据：删除 3 本教材、旧教学包和新结构/课程数据，保留图书馆 17 份文档；同时移除 11 个旧“家庭教材加工”隐藏工作区。历史教材数据不再兼容，后续从图书馆重新建立内容版本。
- 验证：前端相关 56 项测试通过，`pnpm typecheck` 通过；后端结构、数据库和生成服务 20 项测试通过，Ruff 通过；`8000` 与 `5177` 健康检查通过，真实浏览器确认一级入口和空态页面正常显示。

### 新增：教材结构版本与分阶段生成任务

- 新增可审阅的教材结构版本、Unit、知识点及单元内知识点持久化模型，来源证据、置信度和审阅状态保存在结构层。
- 新增通用 `structure` / `lesson` generation job 与 attempt 账本，为后续逐知识点 Markdown 课程生成、失败隔离和独立重试提供持久化基础。
- 新增结构候选纯验证器：Unit 和知识点必须带有效来源范围，Unit 位置与 slug 唯一；教学 Unit 允许审阅前暂时没有知识点，非教学 Unit 禁止硬造知识点。
- 新增结构生成服务：复用受管 PTC 的 workspace、sandbox、run ledger、心跳与终态回调，但只加载 `book-to-skill`，只允许写 `outputs/structure.json`，通过验证后进入 `review`。
- 结构版本和原始结构 JSON 归档到私有 `education/.../structures/vN/`，沙盒关闭后仍可从数据库和 MinIO 查看。
- `book-to-skill` 增加独立的 managed structure mode，明确允许教学 Unit 暂时没有知识点，禁止非教学 Unit 编造知识点，并禁止在结构阶段生成课程或教学包。
- 新增家长结构审阅 API：创建结构任务、读取结构树、整树替换编辑，以及接受结构进入后续逐知识点课程生成；整树替换可承载重命名、合并、拆分、删除和新增知识点。
- 新增知识点 lesson 身份、不可变 Markdown revision、私有 revision 存储路径，以及发布快照到具体 revision 的冻结关系；重新生成课程只创建新 revision，不覆盖旧课程。
- 新增单知识点 Markdown 课程生成链路：每个任务只注入目标知识点的来源片段，只加载 `the-knowledge-guy`，主输出为 `lesson.md`；只有开启自动判题时才要求 `practice.json`。
- 删除 lesson 对 `vocabulary.json`、`evidence.json` 等固定 JSON 的依赖，英语词汇、数学公式和语文知识点都可在 Markdown 中按学科 Profile 自然表达。
- 新增 lesson 生成、读取、人工修订、审批 API，以及结构发布接口；发布必须为每个 accepted 知识点冻结一份 approved lesson revision。
- publication 现在明确支持 teaching package 或 structure 二选一，结构发布不再伪装成旧教学包。
- 新增家长端教材结构审阅页：章节树、Unit 与知识点编辑、来源定位、添加/删除/拆分/合并知识点、保存和接受结构。
- 新增家长端单知识点课程审阅页：Markdown 预览与人工修订、revision 历史、重新生成、逐课审批和结构发布。
- Markdown 统一通过 `EducationMarkdown` 适配层渲染，后续替换渲染样式不影响业务页面。
- 新增学生端发布快照投影：学生只能读取 assignment 对应 publication 冻结的 structure、知识点和 lesson revision，看不到未发布课程或家长数据。
- 新增 Unit 与知识点学习页：左侧章节树、Unit 概览、单知识点 Markdown 课程、已发布状态和移动端目录抽屉。
- 学生追问现在支持 `knowledge_point_id` 上下文，服务端只注入当前已发布知识点课程，浏览器无法替换或扩大学科上下文。
- 修复教材仍在解析或加工时提前显示“结构与知识点”入口的问题；只有内容进入 `review` 或 `published` 后才允许创建结构任务。
- 新增学生私有学习资产：知识点进度、追问、划重点、批注和 Unit 个性化总结；所有内容按 assignment 隔离，不修改正式 lesson revision。
- 新增 Processing Profile：可以按学科、学段、语言、深度、题型和补充要求冻结教材处理配置，并分别注入结构分析和单知识点课程 prompt。
- 单知识点课程校验失败时最多自动重排当前 generation job 3 次，其他知识点和 Unit 不受影响。
- 新增 `education_structure_lessons` 功能开关，并在本地部署中显式启用教材结构、知识点课程和学生学习链路。
- 新增 Chromium 与移动端 Playwright 验收：覆盖家长结构审阅、学生发布课程阅读、移动端目录与笔记本抽屉。
- 新结构模型不承担旧教学包双读、回填或迁移兼容；历史格式无法转换时直接重新加工。
- 验证：迁移在线降级/升级与离线 SQL 生成通过；使用真实 `bbb` 内容版本完成结构任务排队、读取和清理；后端结构、lesson、审阅、发布、学生学习投影、追问与 PTC 边界聚焦测试通过；前端家长审阅、学生学习页、既有教材详情和查询契约测试通过，`pnpm typecheck`、`pnpm build`、ESLint 和 Ruff 通过。

### 修复：图书馆“教材资产”接口遇到真实 UUID 返回 500

- **现象**：打开独立图书馆详情页的“教材资产”标签时，`GET /api/v1/documents/{id}/teaching-usage` 返回 500。
- **根因**：PostgreSQL 驱动返回 `textbook_id`、`content_version_id`、`teaching_package_id`、`publication_id` 为 UUID 对象，响应模型的这些字段却声明为 `str`；此前测试使用了伪造的字符串 ID，没有覆盖真实驱动类型。
- **修复**：service 投影在离开数据库层前把 UUID 字段统一转换为字符串，API 的 JSON 契约保持不变。
- **验证**：新增真实 UUID 行的 service 回归；文档 teaching-usage 与 API 聚焦测试 22 项通过，Ruff 通过。

### 修复：教材章节知识点超过 24 个时教学包被误判失败

- **现象**：RE3 教材任务运行约 18 小时后 root run 完成，生成 25 个知识点、完整 concept index、coverage audit、toolkit 和 practice，但最终提示“教材教学包校验或归档失败”。
- **根因**：`education_teaching_validation.py` 把所有字符串列表统一限制为最多 24 项；实际单章知识点达到 25 项时被拒绝，并非模型漏产出。
- **修复**：将通用列表上限提高到 64，仍保留数量、长度、重复项、章节覆盖、哈希和知识点关联校验。使用停止 sandbox 中保存的真实产物离线重跑 `validate_teaching_assets()`，结果为 `chapters=1 / concepts=25 / coverage=complete`。
- **验证**：教学包与完整资产聚焦测试 13 项通过，Ruff 通过。

### 修复：章节题目数量与知识点上限不一致

- **现象**：测试教材章节生成 25 个知识点和 25 道一一对应的知识检查题，最终因题目数量超过 24 被标记为 `managed_output_invalid`。
- **根因**：知识点列表上限已提高到 64，但题目仍使用独立的硬编码上限 24；25 个知识点各对应一道题是正常覆盖输出，并非模型异常膨胀。
- **修复**：题目上限改为复用统一的 `_MAX_LIST_ITEMS=64`，避免知识点与题目边界再次漂移，并新增 25 个知识点对应 25 道题的回归测试。
- **验证**：教学包校验聚焦测试 7 项通过，Ruff 通过。

## 2026-09-17

### 修复：普通对话页泄漏“家庭教材加工”工作区

- **现象**：侧栏和 `/chat` 工作区列表出现多个“家庭教材加工”；每个都点不开，并触发 workspace 文件/状态接口报错。
- **根因**：这些是 managed textbook PTC 运行使用的 service-owned workspace。详情、文件和消息接口已经按设计拒绝普通访问，但 `get_workspaces_for_user()` 的列表和 total 查询没有排除 `config.managed_execution`，因此内部执行行泄漏到了用户导航。
- **修复**：workspace 列表与计数 SQL 统一排除带 `managed_execution` 配置的行；共享 `useWorkspaces` hook 同时做前端过滤，确保侧栏和“工作区”画廊在现有缓存状态下也立即隐藏，不改变详情接口的 404 安全边界，也不影响后台按状态扫描和清理这些 workspace。
- **生命周期**：managed workspace 没有普通聊天活动时间，原 idle reaper 会因 `last_activity_at IS NULL` 永久跳过，导致 sandbox 可能持续 running。现在 managed row 使用 `updated_at` 作为活动时间；若没有活跃 workflow，超过 idle timeout 后由现有 `stop_workspace()` 停止并保留可恢复数据。
- **验证**：`test_workspace_db.py`、`test_workspaces.py` 与 workspace manager 聚焦测试通过；前端 workspace/navigation 测试 55 项、`pnpm typecheck` 和 `pnpm build` 通过；真实 `/chat` 页面仅剩 Flash 和用户工作区。

### 修复：教材加工环境无法启动

- **现象**：点击教材“继续运行”后，界面提示“教材教学加工环境无法启动”；后端日志显示 Docker sandbox 已成功创建，但随后立即被清理，任务没有产生 root run。
- **根因一**：managed textbook 沙箱初始化调用了已不接受 `sandbox_id` 参数的 `update_workspace_status()`，sandbox 就绪后触发 `TypeError` 并回滚。改为通过 `try_bind_workspace_sandbox()` 原子绑定 workspace 与 sandbox，保持平台密钥版本为 `0`，不再走普通状态更新接口。
- **根因二**：`build_ptc_graph_with_session()` 接到了 managed execution policy，却没有继续传给 `create_agent()`；受管 subagent 注册表因此没有生效，随后 root run 报 `textbook-chapter-worker` 未定义。
- **根因三**：当前 `LocalRunExecutor.start_run()` 已移除 `terminal_callback`，教材加工仍按旧接口传入该参数，导致 root run 在启动阶段报 `unexpected keyword argument`。执行器恢复可选终态回调，并在完成、失败和取消后调用；回调异常只记录日志，不会反向污染 run 的最终状态。
- **验证**：新增 managed graph policy 透传和 executor terminal callback 回归；`tests/unit/ptc_agent/test_managed_textbook_execution_policy.py`、`tests/unit/server/services/test_education_managed_ptc.py`、`test_education_teaching_jobs.py` 和 `test_executor.py` 聚焦测试通过。真实本地任务已从失败状态重新进入 PTC root run，sandbox 保持运行并开始读取 `/managed/textbook-job/<job>/`。

### 修复教材来源迁移的真实执行路径

- 迁移 `062`–`065` 共用同一个 DDL 执行 helper：在线模式走 `op.get_bind().exec_driver_sql(...)`，避免正则中的 `(?:` 等字符被 SQLAlchemy 当作 bind 参数；离线 `--sql` 模式走 `op.execute(DDL(...))`，避免 `MockConnection` 缺少 driver 执行接口。执行路径测试同时覆盖在线与离线分支，并校验约束 DDL 原样保留正则。
- 迁移 `063` 在记录首个超过 32 字符的 revision 前扩展 `alembic_version.version_num`，避免真实升级在 `063_textbook_artifact_source_prefix` 更新版本号时被 `VARCHAR(32)` 截断。
- 验证：`alembic upgrade 061_document_usage_records:head --sql` 成功生成完整 SQL；本地开发库反复完成降级到 `061` 与升级到 `065_textbook_source_asset_manifest (head)`。

### 教材正式资产集成最终审查修复

- 教材来源排队改为显式任务并通过 `await_settled` 等待数据库操作真正结束；调用方取消不再取消排队事务。任务结束后的已知 precommit `TextbookQueueValidationError` 或空结果只清理本次写入的精确快照键；未知异常或取消会保留快照，仅记录 `version_id` 与 `job_id`，不再执行短时 `EXISTS` 探针授权删除。
- 预览抽屉关闭后不再保留测量或拖动产生的内联宽高，抽屉根节点使用 React 19 `inert`，内部链接、按钮、标签和分隔条关闭时退出 Tab 顺序；新增关闭后布局清理和键盘 Tab 回归。
- 教材详情页的已完成解析资料查询新增独立错误态与重试按钮，不再把加载失败显示为空图书馆。
- 迁移 `063` 的升级与降级统一恢复显式安全快照前缀集合，保留 UUID 新格式和两种历史兼容格式，但不再接受宽泛的 `education/%`。
- 验证：后端来源/教材聚焦测试 90 项、前端抽屉/详情聚焦测试 22 项、迁移测试 61 项通过；`pnpm typecheck`、`pnpm build`、Ruff、ESLint 和 `git diff --check` 通过。

## 2026-09-16

### 修复：图书馆解析结果过多时“完成”按钮消失

- **现象**：PDF 解析产生大量图片或结构化产物后，结果步骤被内容持续撑高；“完成”按钮落到可视区域之外，用户无法直接结束向导。
- **修复**：把解析向导改为固定头部/步骤条 + 可滚动主体，限制产物列表自身的滚动高度，并让结果步骤的操作区固定在底部；大量产物仍可完整滚动查看和下载。
- **验证**：新增 Playwright 回归，在桌面 Chromium 与 `documents-mobile` 中用 80 个解析产物覆盖该场景，断言产物列表内部滚动且“完成”按钮始终落在视口内；两端均通过。

### 图书馆与教材正式资产 mock 回归与后端读取验收

- 新增 Playwright Chromium mock 回归，不代表真实服务 sandbox 验收：上传并完成模拟解析、在独立图书馆详情审阅 Markdown、以已完成解析任务创建教材、完成模拟教学包、审阅正式知识资产、发布并分配学生。
- mock 回归使用精确的教材、版本、教学包、章节、文档和学生标识；断言候选来源、文档教学用途、正式资产读取、发布请求和分配请求都命中预期 ID 与 payload，错误 ID 会因无匹配路由而失败。教学运行抽屉在桌面用 Escape、在 `documents-mobile` 用真实 TouchEvent 下拉手势关闭。
- 新增 API/服务读取回归：正式教学包摘要和章节资产在 managed PTC/运行服务不可用时仍通过 PostgreSQL 审阅投影与对象存储读取成功；测试断言只调用数据库和 MinIO 读取 seam，sandbox 启动、继续和取消路径均未调用。
- 浏览器回归检查所有相关文档、教学用途、正式资产和教育 API 的请求 URL、查询参数与请求体，并读取全部响应体和响应头，包括非 JSON、`Location`、`Content-Disposition` 等 URL 承载字段；检测字段名、对象 key、签名 URL、预签名参数和 URL 载体，同时以显式请求/响应计数防止监听器静默失效。
- 验证：指定 Playwright mock 回归在 Chromium 桌面与 `documents-mobile` 两个项目通过；正式资产 API/服务聚焦测试、相关 Vitest、`pnpm typecheck`、`pnpm build`、ESLint、Ruff 与 `git diff --check` 通过。

### 教材详情选择并审阅图书馆来源

- 新增 `GET /api/v1/education/textbook-parse-jobs/completed`，一次返回当前家长拥有的已完成 Markdown 解析任务候选；查询排除未完成、失败、非 Markdown 主产物和他人文档，并提供文件名、完成时间、解析器、原文件大小与 Artifact 数量，不返回存储键或对象 URL。
- 教材版本的 `sources` 现在优先投影冻结的 Artifact provenance：文档、解析任务、主 Artifact、解析器、完成时间、SHA-256 与 `document_deleted`；历史 `education_assets` 来源继续返回带 `legacy` 标记的兼容字段。详情查询通过 live Document 左连接判断文档是否仍存在，但文件名和解析元数据始终读取冻结来源，因此删除文档后仍可审阅。
- `开始加工`改为从图书馆一次加载已完成解析任务，可多选并提交 `source_parse_job_ids`；原 `source_asset_ids` 请求路径保留。版本标签调整为“概览 / 来源 / 教学 / 知识资产 / 学生”，“来源”展示真实文件、解析器、完成时间、SHA-256 前缀，并在文档仍存在时链接到 `/documents/:documentId`。
- 来源列表独立于教学包与 sandbox 运行状态；加工失败不会隐藏来源或图书馆链接，知识资产仍只在教学包进入 `review` 且正式资产清单可用后展示。前端不渲染快照前缀、存储键、对象 URL 或 sandbox 路径。
- 版本标签补齐完整键盘与读屏语义：稳定的 `id`/`aria-controls`、`tabpanel` 的 `aria-labelledby`、roving `tabIndex`，以及 `ArrowLeft`、`ArrowRight`、`Home`、`End` 的焦点与选中同步。
- 来源列表改为有名称的语义列表，并在移动端单列、桌面端双列结构中使用可换行元数据和 `min-w-0` 约束；新增移动/桌面视口回归，避免长文件名导致横向溢出。
- 已完成解析任务候选在 repository 边界再次按 `completed`、当前家长所有权和非空主 Artifact 过滤，并只投影安全字段；混合完成、失败、排队、他人和缺少主 Artifact 的任务均有行为测试覆盖。
- 恢复历史 `education_assets` 来源的“打开”操作：继续通过受控下载接口获取地址，保留打开中禁用状态和失败提示；图书馆文档来源新增观看者敏感的 `document_accessible`，仅文档存在且当前家长拥有时才显示链接，同一家庭其他家长会看到冻结元数据但不会得到死链接。
- 已完成解析任务候选查询键归入 `queryKeys.documents.completedParseJobs()`；解析任务完成刷新、文档更新/删除和创建新解析任务都会失效该查询。全部版本标签面板现在使用稳定 ID 和 `hidden` 同时挂载，确保每个 `aria-controls` 的 IDREF 均可解析。
- 新增 Playwright 浏览器级来源列表回归：在 390px 与 1280px 视口下渲染超长不可断 token，断言来源容器 `scrollWidth <= clientWidth`。
- 验证：后端数据库、服务与 API 聚焦测试 80 项、前端教材/查询/键/文档 hooks 聚焦测试 39 项、Playwright 浏览器溢出回归 1 项通过；`pnpm typecheck`、Ruff 和 `git diff --check` 通过。

### 图书馆文档详情发布状态与交互修正

- `GET /api/v1/documents/{document_id}/teaching-usage` 现在按内容版本与教学包关联正式发布记录，并返回安全的 `publication_id`、`is_published`；前端仅在发布记录存在时显示“已发布”，否则展示真实教学包生命周期状态，不再使用并不存在的 `published` 教学包状态。
- 文档详情的主标签支持 `ArrowLeft`、`ArrowRight`、`Home`、`End` 键盘导航，并在移动焦点时同步选择对应视图。
- 教材用途查询会在教学包处于 `queued`、`preparing`、`building_skill`、`generating_teaching`、`validating` 或 `running` 时轮询，终态停止；创建教学包、取消、继续、发布以及教学任务进入终态时会失效文档用途查询。
- 预览抽屉分隔条现在可聚焦并通过方向键调整宽度，提供 `aria-valuemin`、`aria-valuemax`、`aria-valuenow`，同时保留鼠标拖动期间禁用页面文本选择的行为。
- 修复键盘调整宽度从固定 680px 起步的问题：分隔条聚焦或首次键盘交互时会读取实际渲染宽度并应用与鼠标拖动一致的最小/最大宽度约束，`aria-valuenow` 在测量后同步显示真实宽度。
- 教材用途卡片补充安全的 `primary_artifact_id` 与 `producer_job_id` 来源信息，继续不展示快照前缀、存储键、sandbox 路径或对象 URL。
- 验证：文档用途服务/API 测试 21 项、相关前端聚焦测试 69 项通过；测量宽度修复后预览抽屉/详情页键盘回归 21 项再次通过，`pnpm typecheck`、Ruff、改动文件 ESLint 与 `git diff --check` 通过。

### 图书馆独立文档详情页

- 新增 `/documents/:documentId` 懒加载路由与独立详情页，保留 `/documents` 列表路由；页面提供“原文 / 解析结果 / 教材资产”三个视图，并继续使用 `/documents` 领域命名，用户可见产品名为“图书馆”。
- 原文与解析结果改用抽屉、详情页共享的只读预览组件，复用既有 PDF、Markdown 与 Artifact 图片解析逻辑；详情页不会再按来源复制一套查看器逻辑，也不依赖 sandbox。
- `教材资产`调用 `GET /api/v1/documents/{document_id}/teaching-usage` 的 typed API/hook，展示教材、内容版本、来源顺序和教学包状态；已审阅或已发布且存在正式资产清单时链接到对应教材详情，未打包、失败和取消状态如实展示且不提供资产入口。
- 教学用途视图保持只读，不渲染 MinIO key、快照前缀、sandbox 路径或对象 URL；快速预览抽屉新增可见的“查看详情”链接。
- 修复共享预览组件抽取后丢失抽屉拖拽状态的问题：拖动分隔条时 `PreviewViewer` 会继续收到 `isDragging`，非 PDF iframe 的遮罩和指针事件抑制会持续到鼠标释放；独立详情页没有分隔条，明确传入非拖拽状态。
- 验证：详情页、预览抽屉与列表聚焦测试 21 项、通用路由测试 11 项、Documents API 测试 10 项通过；拖拽回归修复后抽屉与详情页聚焦测试 19 项、`pnpm typecheck` 再次通过。

### 图书馆用户界面统一更名

- Web 中英文用户可见文案将“知识库 / Knowledge Library”统一改为“图书馆 / Library”，覆盖侧边导航、页面标题、视图标签、数据集删除提示和上传向导说明。
- `/documents` 路由、`Document` 领域命名、API 路径、类型和翻译键保持不变；新增导航回归断言，锁定 `/documents` 路由在两种语言下分别显示“图书馆”和“Library”。
- 验证：页面与导航聚焦测试 8 项、语言资源测试 5 项通过，`pnpm typecheck` 通过。

### 图书馆文档展示教材加工用途

- 新增只读接口 `GET /api/v1/documents/{document_id}/teaching-usage`：文档所有者可以看到该解析来源被哪些教材版本和教学包使用；缺失或不属于当前用户的文档仍返回 404。
- 用途查询只沿 `education_textbook_artifact_sources` 正式来源链路读取，不读取旧版 `education_textbook_sources`/`education_assets`；响应服务端白名单只投影文档、Artifact、教材、版本、教学包、状态、资产清单标记与创建时间，不暴露快照前缀、存储键、对象 URL、sandbox 路径或模型输出。
- 尚未生成教学包的内容版本仍会返回，教学包字段为空；`failed`/`cancelled` 教学包保持可见，`has_asset_manifest` 仅在正式教学资产清单存在时为真。
- 安全收紧：文档所有者失去教材家庭当前 `parent` membership 后，用途授权检查与结果查询都会拒绝该教材家庭的使用记录，接口按未授权文档返回 404，且不会返回任何用途行。
- 验证：新增服务与 API 回归测试覆盖所有者、外部用户、家长成员关系失效、旧资产来源排除、未打包版本、失败/取消状态、敏感字段过滤和路由权限；聚焦测试 20 项及相邻教材数据库/服务测试 92 项通过，Ruff 检查通过。

### 兼容旧版教材快照布局与编码图片引用

- 教材来源 object 读取现在优先尝试当前的 `{snapshot_prefix}artifacts/{relative_path}`，不存在时再回退旧的 `{snapshot_prefix}{relative_path}` 根布局；主 Markdown 与受管 staging 引用的图片都走同一套读取与 SHA-256 校验，选中旧路径时不会改写快照。
- 对 `asset_manifest` 为空的历史来源，队列与 staging 会在进入 `freeze_teaching_input()` 前读取根 `manifest.json` 并重建仅含安全字段的 manifest；重建结果不包含 storage key，仍按引用关系决定是否上传图片。
- Markdown 图片目标会先做 percent-decode，再检查绝对路径与 `..` 穿越，并继续支持精确相对路径和 basename 匹配；`http(s)`、`data:`、`blob:` 等外部引用仍被忽略。新增旧布局、空 manifest 回填、`%20`、混合编码和编码穿越测试。

### 补齐全来源图片资产的受管 PTC staging

- 新增迁移 `065_add_textbook_source_asset_manifest`，在 `education_textbook_artifact_sources` 上增加 `asset_manifest JSONB NOT NULL DEFAULT '[]'::jsonb`；历史来源行自动保持空 manifest，不需要回填。
- 快照冻结来源现在把安全 artifact 元数据（artifact ID、类型、格式、media type、源相对路径、SHA-256）写入 `asset_manifest`，队列写入不再暴露 storage key。claim 与教学输入读取会一并返回 `snapshot_prefix` 和 `asset_manifest`。
- 受管 staging 解析完整来源 Markdown 中的本地图片引用，支持精确相对路径、`./` 归一化和 basename 匹配；只读取被引用且摘要匹配的冻结图片，上传到 `inputs/assets/<position>/<relative_path>`，并在 `inputs/manifest.json` 中写入安全 `asset_paths`。缺失资产、摘要不匹配、外部 URL/data URI 和不相关资产分别按 fail-closed 或忽略处理。
- 两份 managed Skill contract 与 compact prompt 明确 `inputs/assets/` 和 `asset_paths`；新增迁移、快照 manifest、数据库 round-trip、staging 失败路径与安全投影测试。

### 教材加工消费冻结图书馆来源

- `process_textbook_job()` 现在识别 `education_textbook_artifact_sources` 来源：逐来源读取服务生成的 `manifest.json`，按 `primary_artifact_id` 定位主 Markdown，并校验路径、格式、大小、UTF-8 与 `primary_sha256`；该路径不会调用 `pypdf`、旧 PDF 打包或重新复制源文件，失败时直接进入既有失败状态。
- artifact-backed 版本按 `position` 把每份完整来源 Markdown 持久化为一个有序内容来源，标题使用来源文件名，slug 稳定且安全；`bundle_prefix` 固定指向版本的 `source-bundles/<version_id>` 命名空间。旧 `education_assets` 版本仍完整走 `build_local_pdf_package()` 与 `write_textbook_content_bundle()`。
- 受管 PTC 的读取模型对 artifact-backed 版本返回 `sources`，历史版本继续返回 `chapters`；staging manifest v2 只暴露有序来源 ID、相对路径和哈希，不暴露 storage key、URL 或 sandbox 路径。prompt 与两份 managed contract 明确输入可能是一份或多份完整文档，解析器不保证标准 Unit/TOC 边界，最终学习结构由 PTC 写入白名单输出。
- 新增服务、数据库与合同测试，覆盖跳过 PDF 链路、多来源顺序与完整 Markdown、manifest/主 artifact/大小/UTF-8/摘要失败关闭、旧链路兼容，以及 managed manifest 的安全投影。

### 设计：图书馆与教材正式资产打通

- 确定图书馆只负责高精度解析，教材库消费完整的 Markdown/图片 Artifact，不再维护第二套 PDF 上传与 `pypdf` 分章链路。
- 确定教材来源和教学资产都由 PostgreSQL 关系与私有 MinIO 内容承载，图书馆详情和教材详情读取同一份正式资产，不依赖 PTC sandbox 存活。
- 确定用户可见的“知识库”统一改名为“图书馆”；`/documents` 路由、Document 领域和 API 路径暂不重命名。
- 第一阶段不做 AI 结构分析、标准 TOC、Unit 识别、卷子与单元匹配或精确跨来源融合；多来源只作为完整来源集合交给 PTC 尝试加工并记录 provenance。
- 补充实现计划，按“解析产物来源绑定 -> 私有快照冻结 -> 多来源 PTC staging -> 图书馆/教材双视图 -> 无 sandbox 验收”拆分任务，并保留旧教材资产链路兼容。

### 教材来源绑定图书馆解析任务

- 新增 `education_textbook_artifact_sources`：教材内容版本现在可以绑定到已完成、且由当前家长拥有的主文档 Artifact；来源包含解析任务、文档、Artifact、顺序、SHA-256 与私有快照前缀。
- 新增 `queue_textbook_processing_from_artifacts()`：在同一事务内锁定并校验教材、创建 `processing` 版本、按顺序写入解析来源并投递一个加工任务；重复解析任务会直接拒绝。
- `claim_textbook_processing_job()` 优先返回新的 Artifact 来源；没有新来源的历史版本继续读取 `education_textbook_sources` 与 `education_assets`，旧数据不需要回填或迁移。
- queue 阶段校验教材家庭归属和已完成解析任务的所有权，同时保留旧来源表不变；新增单元测试覆盖来源顺序、跨家庭拒绝、重复任务拒绝和新旧 claim 分流。
- 修正冻结来源生命周期：不建立指向 live 文档、解析任务或 Artifact 的外键，而是在来源行中保存文件名、媒体类型、格式和解析器 provenance；删除图书馆文档后，claim 仍无需 join live 表即可读取。
- snapshot 前缀改由服务端根据 household、教材 slug、版本序号和来源位置统一派生，不再接受调用方传入；household 与 slug 会校验为单段安全路径，SHA-256 保持严格 64 位小写十六进制。

### 教材解析来源快照冻结

- 新增 `education_textbook_source_snapshots` 服务：家长选择已完成的图书馆解析任务后，服务会校验任务、文档和全部 Artifact 的所有权，要求恰好一个 Markdown 主文档，并把主文档、图片、结构化数据和 manifest 按原相对路径复制到私有 `education/` 快照。
- 快照前缀固定为 `education/{household_id}/{textbook_slug}/source-bundles/{version_id}/{position:02d}/`，其中 household、版本 UUID、教材 slug 和位置都会先校验；版本 ID 与加工任务 ID 在复制前生成，浏览器不能指定存储路径。
- 来源 Artifact 统一复制到 `artifacts/` 下，来源自带的 `manifest.json` 因此位于 `artifacts/manifest.json`，不会与根目录服务生成的 `manifest.json` 冲突。
- 每个快照对象写入后都由服务端立即读回并重新计算 SHA-256，只有与来源字节摘要一致才被接受；上传同时使用文档领域现有的 `max_upload_bytes` 上限。`primary_sha256` 只取冻结后的主 Markdown 字节，不信任客户端或解析任务中的旧值。主 Artifact 还必须同时满足 Markdown media type 和受支持的 Markdown format。
- 单个来源失败或取消时只删除该操作已写入的精确对象键；多来源冻结中任一后续来源失败、取消、已知队列校验失败或排队返回空结果时，服务会在 `asyncio.shield` 下清理全部先前快照，不会枚举或删除无关对象。未知数据库异常以及排队调用中的取消，都会对精确 `job_id`/`version_id` 执行最多 3 次、带短暂退避的 shielded 状态探针：确认行不存在才清理，行存在或探针耗尽后仍不确定则保留快照，并记录仅含这两个 ID 的结构化警告供后续孤儿对账。
- 每个快照对象上传都通过显式 referenced task 与仓库的 `await_settled` 等待 `to_thread` worker 真正结束；上传中发生取消或异常时，会先等待 worker settle，再删除该操作唯一的目标键后继续抛出，避免线程在清理完成后才写回孤儿对象。
- 新增迁移 `063_align_textbook_artifact_source_prefix`：安全删除 `062` 生成的命名快照前缀约束，并重新加入兼容历史前缀与 UUID 精确格式的命名约束，已在旧修订上创建过的来源行无需回填。
- 新增迁移 `064_strengthen_textbook_source_prefix_constraint`：移除 `063` 中过宽的任意 `education/%` 分支，最终约束只接受两种显式历史格式和可信的新 UUID 格式；降级恢复到同一安全兼容集合。
- 新增 API 字段 `source_parse_job_ids`，请求必须且只能选择 `source_asset_ids` 或 `source_parse_job_ids` 其中一种；新服务会先冻结全部来源，再以预生成的版本和任务 ID 落入数据库，避免任务在快照完成前被 claim，旧教材附件链路继续兼容。

## 2026-09-15

### 微信通道：不再让 Agent 停在只有 Web 能回答的提问上

- **现象**：Agent 用 `AskUserQuestion` 问"下个星期天具体指哪一天"，并在 Web 端渲染出选项控件；微信端只收到了那句问话，**选项在协议层没有文本表示**（通道适配器按设计只转发主 Agent 的纯文本，HITL 在设计文档里就是明确的范围之外）。用户在 Web 端选完后，那轮的答案也不会回到微信——通道只投递自己派发过的那一轮结果。
- **决定**（采纳最小方案）：**不让通道会话里出现需要点选的交互**，而不是给微信实现答题。
- **改动**：`LangAlphaFlashAdapter` 在每一轮注入了 `directive` 上下文——说明这是消息渠道、用户只有纯文本、打不开 Web 也无法点选；要求**不要调用 `AskUserQuestion`**，缺信息时选一个最合理的解释、用一句话说明假设（例如"按 9月20日 处理"）并继续；确需提问就用普通文本问，并把用户下一条消息当答案。图片附件上下文照旧排在它之后。`ask_user_guidelines.md.j2` 同步增加一条通用规则：界面无法渲染选项时不要用这个工具，并写明后果与替代做法。
- **验证**：channel 相关测试 **75 项通过**（新增 1 项断言每轮都带该 directive 且含关键约束；既有图片测试改为断言 directive 在前、image 在后）；用服务端自己的请求模型实测 `ChatRequest.model_validate([directive, image])` 通过（派发不会 422）；`tests/unit/ptc_agent` **765 项通过**（提示词模板仍可加载渲染）；`ruff check src/ migrations/` 干净。
- **未做（记录在案）**：真正的"在微信里答题"（解析 interrupt + 在 `channel_sessions` 存 pending interrupt + 把下一条消息作为 `hitl_response` 续跑），以及把 Web 端的回答镜像回微信；两者都按决定暂缓。

### 修复：长回合的通道消息被判失败（微信收不到回复，Web 端却有）

- **现象**：第一条微信消息（"嗨"）正常收发；之后的长回合（多步工具调用）微信收不到任何回复，而 Web 端明明能看到助手的完整回答。
- **证据**：`channel_inbound_messages` 里后续消息在 8 次尝试后 `dead`、`last_error_code=flashagenterror`；worker 日志是 `POST .../messages` 409（duplicate_request）与 `GET .../messages/stream` 200 反复交替；Web 端确实产出了回复，说明回合跑成功了，只是**通道侧判定失败**，于是没有生成 outbound。
- **根因（两层叠加）**：
  1. adapter 的 httpx 客户端用 `timeout=90s`，而该值**同时作用于 SSE 流式读取**——agent 思考、压缩上下文、跑工具期间不产生任何事件，读超时就把长回合判成 transport 失败并重试；
  2. inbound 的 claim 租约只有 `inbound_lease_seconds=120` 且**没有续约机制**，而一个真实回合可能跑数分钟：租约过期后同一 worker 的其它协程（`worker_concurrency=4`）可以再次领取同一条消息 → 重复派发 → 应用回 409 → 重试路径最终把消息判死。
  3. 附带问题：失败只记录异常**类名**（`flashagenterror`），adapter 的 `code` 被丢掉，所以完全看不出是超时、空回复还是 409——这也是这次排查慢的原因。
- **修复**：新增配置 `channels.agent_turn_timeout_seconds`（默认 900）作为**整回合**预算；流式请求 `read=None`（允许事件之间长时间静默），并用 `asyncio.timeout` 兜住整个回合，超时映射为 `FlashAgentError(code="turn_timeout")`；worker 构造 adapter 时传入该预算；claim 租约改为 `max(inbound_lease_seconds, agent_turn_timeout_seconds + 30)`；失败时把 `exc.code`（回退到类名）写进 `last_error_code` 并 `warning` 打印原因与尝试次数。
- 验证：channel 相关测试 **74 项通过**（新增 4 项：租约覆盖回合预算、失败记录 `code` 而非类名、流式读超时已关闭、整体预算超时会给出 `turn_timeout`）；`ruff check src/ migrations/` 干净。

### 修复：`education_create_homework` 执行成功但界面没有任何输出

- **现象**：工具调用成功，transcript 里只有"完成了 1 个步骤"，看不到它到底创建了什么。
- **根因**：这个工具（来自本地教育线）把 artifact 拼成了**裸 dict**，`type: "education_homework"` 因此**从未进入发布契约**——`web/src/contracts/artifact-types.json` 是 Pydantic 模型生成的，前端按 artifact 的 `type` 分发卡片，未发布的类型就没有卡片可注册。而工具返回值里的 content（JSON）本来就不在 transcript 里展示，于是消息停在"工具步骤"。合并时它绕过了本线的 artifact 契约，覆盖率测试也看不见它（那条测试只检查"已发布的类型是否都有卡片"）。
- **修复**：新增 `src/tools/education/schemas.py::EducationHomeworkArtifact`（Pydantic，`type` 用 `Literal`），工具改为用它构造 artifact；在 `scripts/contracts/export_schemas.py` 与 `web/scripts/generate-contracts.mjs` 注册，`make contracts` 生成 schema/zod 并把 `education_homework` 写进 `artifact-types.json`；新增前端卡片 `InlineEducationHomeworkCard`（布置给谁 / 作业标题 / 截止时间 / 文字作业标记）并在 `artifactRegistry.ts` 与工具名绑定；中英文案 `chat.homeworkCard.*`。
- **刻意保留的细节**：artifact 里的 `due_at` 是**家庭时区的 ISO 字符串**而不是 `datetime`——Pydantic 会把 tz-aware datetime 重新序列化成 UTC，悄悄挪走家长看到的截止时间（本地教育线此前专门修过这个 bug）。
- 测试：后端契约测试的 discriminator 清单更新为两项；工具新增"artifact 就是卡片要渲染的东西"（用完整 ToolCall 调用取 `.artifact`，断言判别式、任务内容与 +08:00 的截止时间）；前端新增契约测试与卡片测试（正常渲染、文字作业标记、坏 payload 显示提示而非崩溃、点击透传），fixture 取自**真实产物**（真实库行 + 稳定化 id）。
- 验证：后端 `tests/unit` **7702 通过**（租约续期那条计时用例在满载时偶发失败一次，单独重跑 3/3 通过，与本次无关）；`ruff check src/ migrations/ scripts/ops/ scripts/contracts/` 干净；前端 `tsc --noEmit` 通过，`charts/contracts` 5 文件 30 项通过。

### 修复：本地 MinIO 用户头像仍生成 AWS S3 地址

- **现象**：头像上传能写入本地 MinIO，但数据库和接口返回的 `avatar_url` 仍指向 `https://{bucket}.s3.{region}.amazonaws.com/avatars/...`。
- **根因**：上传客户端由 `STORAGE_ENDPOINT_URL` 指向 MinIO，公开 URL 却只读取 `STORAGE_PUBLIC_URL_BASE`；该变量未配置时，`get_public_url_base()` 无条件回退 AWS 域名。另外 MinIO 桶原本是 `private`，即使改对域名也会返回 403。
- **修复**：自定义 endpoint 未显式配置公开地址时，按 endpoint 与 addressing style 推导对象 URL；本地配置显式设置 `STORAGE_PUBLIC_URL_BASE`；MinIO 初始化脚本只为 `avatars/*` 增加匿名 `GetObject` 权限，教育附件和内部 blob 仍保持私有。
- **验证**：新增单元测试覆盖 MinIO path-style endpoint；本地对象 `http://127.0.0.1:9000/onemore-education/avatars/f8d3bcac-5ca2-4f54-9a27-c4e77e83de00.png` 返回 **200 + `image/png`**，`education/*` 匿名访问仍返回 **403**；已有用户头像记录已从 AWS 地址修正为 MinIO 地址。

### 修复：微信消息无回应的通道 worker 目标地址

- **现象**：微信 iLink 扫码绑定成功、消息也进来了，但发消息没有任何回应。
- **根因**：通道 worker 不直接跟微信通信，它把每条入站消息**派发到本应用的 HTTP 聊天接口**，地址来自 `GINLIXFLOW_BASE_URL`（名字是历史遗留）。`Makefile` 里写死了旧部署的 `http://127.0.0.1:8010`——那是**另一个部署前端代理的端口，不是 iLink 桥**。本机应用在 8000，于是 worker 每次派发都失败（worker 日志里是 8 次 `POST http://127.0.0.1:8010/api/v1/threads/messages` → `502 Bad Gateway`），重试耗尽后该入站消息被标记为 `dead`，不会再重试。
- **修复**：`Makefile` 改为 `GINLIXFLOW_BASE_URL=${GINLIXFLOW_BASE_URL:-http://127.0.0.1:8000}`（保留可用环境变量覆盖），`startup.sh` 默认跟随 `BACKEND_PORT`，README 的措辞一并改正（原来把该变量误写成"iLink 桥地址"）。
- **验证**：worker 重启后环境变量为 `http://127.0.0.1:8000`；对派发路径做非侵入探测 `POST /api/v1/threads/messages`（带 `X-Dispatch: background` + `X-User-Id`）返回 **400 业务校验错误**（提示 `workspace_id ... agent_mode='flash'`），说明**鉴权与路由都已通过**，只是探测体不完整——证明派发链路已通。已被判 `dead` 的那条旧消息不会自动重发，需重新发一条。

### 修复：迁移后语音输入按钮消失

- **现象**：对话框只剩文字发送按钮，语音（STT）按钮不见了。代码与 Volcengine ASR 配置都在（`.env` 里 `VOLCENGINE_ASR_APP_ID/ACCESS_TOKEN/CLUSTER/WS_URL` 齐全），不是功能被合并掉。
- **根因**：麦克风按钮的渲染条件是 `speechSupported && other_preference.voice_input_enabled`（浏览器能力 + **用户偏好**）。本机数据库换成本地库后，该用户的 `voice_input_enabled` 是 `false`；而且偏好在 Redis 里按 `user_prefs:{user_id}` 缓存，直接改库不会生效。
- **修复**：把该用户的 `user_preferences.other_preference.voice_input_enabled` 置为 `true` 并删除对应的 Redis 缓存键（等价于在「设置 → 用户信息」里打开该开关，UI 会自己失效缓存）。
- **验证**：`/api/v1/users/me/preferences` 返回 `voice_input_enabled = true`；真实浏览器里聊天输入框重新出现 `开启语音输入` 按钮。

### 本地一键启动脚本 `startup.sh`

- 仓库根目录新增 `startup.sh`：一条命令拉起**中间件（缺则起）+ 后端 8000 + 前端 5177 + WeChat channel worker**，另有 `status` 与 `stop [--docker]`。README 的 Quick start 与项目结构表同步更新。
- 每个进程通过 `setsid()` 放进独立会话，脚本退出后仍在跑；pid/日志写到 `${TMPDIR}/langalpha/`；**幂等**——端口已被占用就跳过而不是起第二份；启动后带**健康等待**（后端等 `/api/v1/auth/me`、前端等 5177 首页、中间件等 5432/6379/9000 端口）。
- 中间件走 `deploy/docker-compose-middleware.yml` + `deploy/.env`，端口从该 env 读取（默认 5432/6379/9000-9001），与应用 `.env` 保持一致。
- **踩坑记录（写进脚本注释）**：vite **必须在 `web/` 目录下启动**。vite 的 root 与 Tailwind 的配置都按 cwd 解析——从仓库根启动时 Tailwind 退回默认主题，`@apply border-border` 会让整页编译失败（表现为白屏 + PostCSS 报错）。脚本改为在子 shell 内 `cd web` 再拉起。
- 本次同时把 local-main 的运行环境补齐到合并后的状态：`uv sync`（venv 早于合并，`mcp` 旧版导致 `cannot import name 'Client'`）、`pnpm install`（缺 recharts）、`.env` 补 `STORAGE_ACCESS_KEY_ID/SECRET`、`STORAGE_ADDRESSING_STYLE`、`ENABLE_DATALAB_DOCUMENT_PARSER`、`DATALAB_API_KEY`、`DATALAB_PIPELINE_ID`。
- 验证：`./startup.sh` 起全栈后 `status` 六项全绿；`http://localhost:5177/` 返回 200；经 5177 代理 `/api/v1/auth/me` 200、`/api/v1/documents` 返回 **16 篇**；重复执行不重复起进程；`stop` 只停应用、`stop --docker` 连中间件一起停。

### 文档图片落盘（Datalab 提取的图片成为 artifact）

**背景**：D9 当初把图片提取默认关掉，唯一的理由是提取出来也**没有地址**——SDK 返回 base64，markdown 里写的是裸文件名，预览必然裂图。本次补齐那个后续项：图片落盘为独立 artifact，预览在渲染时解析引用。

**部署上限**：新增 `DOCUMENT_MAX_IMAGE_ARTIFACTS`（默认 200）与 `DOCUMENT_MAX_IMAGE_BYTES`（默认 32 MiB），`DocumentParsingConfig` 与 `get_document_parsing_config()` 透传，`.env.example` 的 Datalab 段落补上说明。图片从此有**自己的预算**：把图片字节算进 markdown 的字节上限，会让"文字很少、图片很多"的扫描件整体失败——正是 D9a 点名的风险。测试覆盖默认值、环境变量覆盖、非正整数（`0`/`lots`/`-1`/`32M`）报错；这几条是后补的，用变异验证代替"先失败"（默认值临时改成 64 MiB，断言立即失败）。

**provider 落盘**：`DatalabExtractor` 把响应里的图片写在 `document.md` **旁边**，文件名**就是 markdown 引用的那个名字**（`43012ae8…_img.jpg`），因此存下来的 markdown 与厂商产出逐字节一致，渲染时按 `relative_path` 精确匹配即可，不需要把绝对 URL 烧进文档（D9a 的红线）。类型**按魔数判定**而非扩展名——Datalab 一律命名 `*_img.jpg`，实际可能是 PNG，认不出才退回扩展名、最后默认 jpeg，否则浏览器不渲染。文件名当**不可信输入**处理：只取 basename（`../../etc/x.jpg` → `x.jpg`，不会写到 bundle 目录外）、空/`.`/`..` 丢弃、同名折叠保留第一个；无法 base64 解码的条目丢弃并记账，不因一张坏图让整份文档失败。超预算时**优先保留被 markdown 引用**的图片（按出现顺序），其余丢弃并写入 `images_kept` / `images_dropped` / `image_bytes` 与 `warning`：宁可少存并如实告知，也不要整单失败。测试 10 项，全部先写、确认 10 项失败后再实现。

**执行器分账**：`_validate_bundle` 原本把 bundle 内所有文件字节加总去比 `max_bundle_bytes`（默认 = 50 MiB 上传上限），图片会挤占文字预算。现在普通 artifact 计 `max_bundle_bytes`、`embedded_image` 计 `max_image_bytes`，超限报**不同的消息**，运维一眼能分辨是哪本账爆了。这道限制是**兜底**（provider 已自行裁剪），防的是别的 provider 或未来改动。

**预览解析**：新增纯函数 `resolveRelativeImageSources(markdown, artifacts, origin)`，把裸文件名引用改写成 `${origin}/api/v1/document-artifacts/{artifact_id}/download`，`DocumentPreviewDrawer` 渲染前调用（依赖 artifact 列表）。**必须带 origin**：共享 `Markdown` 组件把非外部 `src` 交给 `WorkspaceImage`，而后者读的是**工作区**文件接口——文档 artifact 不在工作区里，相对路径过去必然 404；绝对同源 URL 会被判为 external，由浏览器带 cookie 直取，正好走那个带 owner 校验的接口。规则：`relative_path` 精确匹配优先于 basename 匹配（两个 artifact 同名不同目录不会拿错图）；`./` 前缀与百分号编码可匹配；`https://`/`data:`/`blob:` 原样保留；**匹配不到的引用原样保留**——静默删除会让"缺图"这件事消失，alt 文字比空白有用。

**默认值翻转**：`disable_image_extraction` 默认由 `True` 改为 `False`（D9 关掉它的前提已消失），向导复选框默认勾选，中英提示文案改为"图片会另存为独立文件并在解析预览中显示"。为保住"只发送用户改过的字段"这一契约，只有**取消勾选**时才发送 `disable_image_extraction: true`。`disable_image_captions` 仍默认 `True`（不生成图片标题）——那是另一件事：模型写的标题会跟正文抢精度。翻转被既有断言抓住（`test_a_real_sdk_options_object_carries_the_defaults` 在翻转后立即失败，正是它该做的事），2026-09-14 设计文档的 D9 也补了"已被 2026-09-15 的 D7 取代"的注记。

**真实链路实测**：`RE3 Part.pdf`（2.98 MB / 5 页）走完整 API：上传 → 检测 → `datalab-online` → 解析 → 取 artifact。冷跑 247 秒（同文件第二次命中厂商缓存 16 秒），费用 2 分；产出 **7 张图片 artifact**（合计 754 497 B，`images_dropped=0`）+ `document.md`（14 994 字符、6 处图片引用）；对象键 `documents/<document_id>/artifacts/<job_id>/<32位hex>_img.jpg`，与 markdown 同目录；`/api/v1/document-artifacts/{id}/download` 返回 **200 + `Content-Type: image/jpeg`**；浏览器里 6 个 `<img>` 全部加载成功（naturalWidth/Height 非 0）。

两个与预期不符、已一并写进设计文档的事实：

- **同样选项，两次冷跑的图片数量不同**：同一文件、同样 `options`（提取开、标题关）分别得到 2 张/1 处引用与 7 张/6 处引用。"这一轮有几张图"不由我们决定，所以实现必须容忍任意子集——这正是预览不静默删除未匹配引用、provider 返回什么就存什么的原因。
- **`disable_image_captions` 影响的是 alt 文字，不是数量**：关标题时是 `![](<hex>_img.jpg)`（alt 为空），开标题时是 `![A photograph of a ski resort …](<hex>_img.jpg)`。我从一次运行得出的"关标题会连带丢图"结论，被第二次同配置冷跑直接推翻；这个错误结论也留在设计文档里，免得后来者照它优化。

**验证**：后端 `tests/unit` **7687 项通过 / 8 deselected / 1 xpassed**；前端 **257 文件 / 2485 项通过**；`pnpm lint` 0 error / 55 warning；`pnpm typecheck` 通过；`pnpm build` 关键路径 **353.6 kB gz**（上限 450）。提交：`5f3871b2` 配置上限、`65b60171` provider 落盘、`df29740b` 执行器分账、`5b7e392d` 预览解析、`b9829d05` 默认值与文案、`2b8c6d06` 实测与文档收尾。

### 文档解析：Datalab 高级选项面板重做（两行对齐 + 新增图片标题开关）

- **面板原来是"一列五行混排"**：三个复选框、一个下拉、一个文本框堆在一起，`documents-advanced-options` 这些类名**在 CSS 里根本不存在**，所以全靠浏览器默认样式渲染——提示文字跟在复选框后面同一行、控件高度各不相同。现在补上样式并重组为**按控件类型分行**：第一行是取值控件（解析模式 / 解析范围，标签在上、控件等宽对齐，范围提示下沉到控件下方），第二行是开关（2×2 等高等宽贴片，`grid-auto-rows: 1fr` 让两行高度一致）。行内 `repeat(2, minmax(0,1fr))` 而不是 `auto-fit`：按当前向导宽度，四个开关排成一行会把最后一个挤到第二行单独一个，正是这次要消掉的"参差感"。
- **顺手修掉一个会误导用户的极性 bug**：`提取图片` 复选框直接绑到了线上的**否定字段** `disable_image_extraction`（默认 true），于是**默认状态下显示为"已勾选"，而服务端其实在跳过所有图片**；单独勾选它还什么都不发送。现在复选框绑定 `disable_image_extraction === false`，勾上才发 `false`。
- **新增 `disable_image_captions` 开关**（默认关闭图片标题）：标签用否定式（`不生成图片标题`），与字段的否定语义一致、默认即勾选，避免再出现上面那类"标签与状态相反"的问题。旁边放了一个 info 图标 + Tooltip 说明原因：**图片标题由模型生成，可能反而干扰正文的识别精度**。Tooltip 按钮是 `<label>` 的**兄弟节点**而不是子节点——labelable 元素不能嵌在 `<label>` 里，且点它会顺带把复选框勾上。该字段后端模型（默认 `True`）与 `_convert_options` 透传本已存在，本次补齐前端入口与测试。
- 顺带补了两条后端测试，把这条链路钉住：`DatalabConversionOptions().disable_image_captions is True`，以及 `_convert_options` 真的把该字段送进 SDK 的 `ConvertOptions`（此前所有 provider 测试都把 `_convert_options` 替换掉了，字段名写错也不会有测试发现）。
- 新增前端测试 4 条：默认勾选且只在关闭时发送 `{"disable_image_captions":false}`、提示按钮的无障碍名称包含解释文案、面板确实分成"取值行 + 开关行"且互不混排、图片开关按"提取"语义而非线上标志位工作（先验证过：把极性改回去，该测试立即失败）。
- 验证：前端 `pnpm vitest run` **256 文件 / 2475 项通过**（上一步 2471）；`pnpm lint` 0 error / 55 warning；`pnpm typecheck` 通过；`pnpm build` 关键路径 **353.6 kB gz**（上限 450）。后端 `tests/unit/server/documents/providers` **77 项通过**，`ruff check` 干净。前端改动在真实浏览器中确认：四块贴片等高对齐（74.3px）、提示可用、默认态正确。

### 前端：关掉 i18next 自带的 locize.com 广告

- 前端控制台（以及用户浏览器控制台）每次加载都会打印一行 `🌐 i18next is made possible by ... locize.com`。这是 **i18next 包内硬编码的 `console.info`**（`node_modules/i18next/dist/cjs/i18next.js` 第 1781 行），触发条件是 `showSupportNotice !== false` 且未接入 locize 后端；**不涉及任何网络请求**（整个包里唯一的 `locize` URL 就是这条日志字符串）。
- 它**没有**限定只在开发环境出现，所以线上用户也会看到。我们的 `src/i18n.ts` 初始化里显式加 `showSupportNotice: false`，并写清原因：这不是我们要传递的第三方告示。
- 验证：`pnpm vitest run` **256 文件 / 2471 项通过**，日志中 `locize` 出现次数为 **0**（改动前每次运行都会打印）；`pnpm lint` 0 error / 55 warning、`pnpm typecheck` 通过、`pnpm build` 关键路径 **353.4 kB gz**（上限 450）。

### Datalab 在线解析器：真实链路验证，以及它暴露的失败路径缺陷

- **两条路径都在真实链路上跑通**（`scanned.pdf`，155 130 字节，1 页）：正确密钥 → `completed`（8.3 秒，取回 937 字符 markdown）；故意写错的密钥 → `failed`（4.2 秒，`parser_unavailable`，**0 产物、0 用量行**，不是卡住、也不是把空文档当成功发布）。
- **缺陷一：provider 写好的错误跨不出隔离边界。** `SpawnProcessRunner` 原本把子进程抛出的**任何**异常都压成 `IsolatedProcessError("The isolated process failed")`，于是 `DatalabExtractor` 精心构造的 `code` + `safe_message` 到不了用户，错密钥最终只显示一句"Document parsing failed"。现在 `DocumentDomainError` 以 `(code, safe_message)` 形式跨边界原样重建（类本身不参与反序列化——**稳定的是 code，不是类名**），其余异常改为回传一条**上限 400 字符**的摘要字符串，而不是被丢弃。
- **缺陷二：SDK 的失败从未被翻译。** SDK 把**连接失败**也包装成 `DatalabAPIError`（`Request failed: ...`，没有 status code），所以"密钥被吊销"和"网络不通"原本无法区分。现在：401/403 → `parser_unavailable` 并**点名** `DATALAB_API_KEY`；轮询耗尽（`DatalabTimeoutError`）→ `parse_timeout`；其余 → `invalid_parser_output`。原异常一律 `from` 串联，日志里保留 provider 的原话。
- 执行器补上**分级记账**：`DocumentDomainError` 属"已经能向调用方解释的结果"，记 info；其它异常说明是**没人解释过的失败**，记 warning 并带 traceback。两条路径都**不改**任务面向用户的消息——内部细节进日志，不进家长/学生的屏幕。
- 实测收益：验证过程中确实撞到一次瞬时的 `Cannot connect to host www.datalab.to:443`（同一分钟内重试两次都成功，属出站网络抖动）。这类原因现在会**落到服务端日志**，而不是留下一句无迹可寻的失败。
- 新增测试 7 项：`test_process_runner.py`（异常摘要被带上、摘要长度有界、**domain error 跨边界保持 code 与消息**）、`test_datalab.py::TestSdkFailures`（401 点名配置项、连接失败算转换失败、轮询耗尽算超时）、`test_executor.py`（不透明失败**记日志但不对用户展开**）。全部先写测试、确认失败后再实现。
- 设计文档补 `Measured against the real API (2026-09-15)` 一节，记录实测与文档预期的差异：免费额度下 `cost_breakdown` 只有 `{"final_cost_cents": 0}`、**没有 `list_cost_cents` 键**，`parse_quality_score` 为 `None`，`page_count=1`——用量页显示"1 页 / $0.00"是**准确的**，这也正是该页同时画页数的原因。
- 验证：后端 `tests/unit` **7666 项通过 / 8 deselected / 1 xfailed**；`ruff check src/ migrations/ scripts/ops/` 通过；前端 **256 文件 / 2471 项通过**，`pnpm lint` 0 error / 55 warning、`pnpm typecheck` 通过、`pnpm build` 关键路径 **353.4 kB gz（上限 450）**。

## 2026-09-14

### Datalab 在线解析器：第一步（部署配置）

- 新增 `DatalabConfig` 与 `get_datalab_config()`（`src/config/settings.py`），沿用 `get_volcengine_asr_config()` 的既有约定：**缺必要值即返回 `None`**，让 provider 的可用性如实上报，而不是在任务跑到一半时才报认证失败。`api_key` 用 `field(repr=False)`，避免密钥出现在日志里。
- 新增 env 常量（`src/config/env.py`）：`ENABLE_DATALAB_DOCUMENT_PARSER`、`DATALAB_API_KEY`、`DATALAB_CONVERSION_MODE`（默认 `balanced`，与原先 pipeline 一致）、`DATALAB_POLL_BUDGET_SECONDS`（默认 540）。布尔值按 `AUTH_COOKIE_SECURE` 的既有写法内联解析，没有引入新的 `_flag` 助手。
- **`DATALAB_PIPELINE_ID` 读入但不要求**——本集成走 `client.convert()`，不经过 pipeline；该变量留给将来的多步流水线（convert → extract/segment），注释里写明了。
- **超时次序被当作配置正确性来校验**：若 `DATALAB_POLL_BUDGET_SECONDS >= DOCUMENT_PARSE_TIMEOUT_SECONDS`，`get_datalab_config()` 记一条 warning 并返回 `None`（即视为未配置）。理由是设计文档 D3 那条——我们的子进程先被杀时，datalab 仍在继续执行**并继续计费**，而结果已无人收取。
- `.env.example` 的 Datalab 段落补齐了 API key、mode、轮询预算三项，每项一句说明；并注明 pipeline id 为预留。（该段落原有的 `DATALAB_API_KEY` 一行来自工作区中未提交的用户改动，随本次一并提交。）
- 测试 9 项（`tests/unit/config/test_datalab_config.py`）：全空 → None；开关关闭 → None；启用但无 key → None；**有 key 无 pipeline id → 仍然配置成功**；取值透传；默认 mode 为 balanced；轮询预算严格小于超时（按**性质**断言而非两个字面量，覆盖三组取值）；预算 ≥ 超时 → None；`repr` 不含密钥。先写测试后实现（初次运行 9 项全部失败）。
- 验证：`tests/unit/config` 共 **260 项通过**；`ruff check` 与 `ruff format --check` 通过。

### Datalab 在线解析器：第二步（SDK 依赖）

- 加入 `datalab-python-sdk`（解析后为 **0.5.0**），按仓库对同类 provider 的既有做法**钉死版本**，并挪到 `firecrawl-anydoc` 旁边（`uv add` 默认追加到依赖列表末尾，与文档解析相关依赖分开了）。
- 两条测试（`tests/unit/server/documents/providers/test_datalab_sdk_import.py`）断言的是**子解释器能否导入**，而不是当前进程能否导入——文档解析跑在 `SpawnProcessRunner` 的独立子进程里，只在父进程可导入的依赖会在生产炸、而测试完全看不见。第二条同时确认 `AsyncDatalabClient` / `ConvertOptions` 存在，顺带把"我们钉的是新一代 SDK、不是旧的 `datalab` 包"记录在案。
- 这两条测试是先加依赖后写的，所以首次运行即通过、没有"先失败"的过程。为确认断言并非空转，做了变异验证：把子进程里的导入改成不存在的模块后立即失败（`ModuleNotFoundError`，1 failed | 1 passed），恢复后 2 项通过。
- 验证：该文件 2 项通过。

### Datalab 在线解析器：第十二步（真实调用，以及它暴露的一个 bug）

- **真实链路跑通**：用 `tests/fixtures/documents/scanned.pdf`（扫描件）走完整 API——上传 → 解析检查（分类为 `scanned`，且 **推荐 `datalab-online`、`legacy-pdf-text` 不推荐**，正是本次实现的策略）→ 建立解析任务 → 完成 → 取回 markdown 产物（937 字符，内容是 OCR 出来的题目 "# SCANNED MATHEMATICS WORKSHEET / Exercise 01: Solve 3x + 0 = 9"）。**这正是本地解析器读不了、加托管解析器要解决的那类文档。**
- **真实调用抓到一个单测抓不到的 bug**：`claim_next_job` 的 claim 查询把 `documents.owner_user_id` 选进了 CTE，却**漏在 `RETURNING` 投影里**，于是执行器拿到空字符串，写用量时触发 `document_usage_records_owner_user_id_fkey` 外键违反（被 `_record_usage` 按设计吞掉并记 warning，所以**解析成功、只有记账丢了**）。修复为在 `RETURNING` 中补上 `candidate.owner_user_id`；复跑同一链路后用量行正确落库（`provider_id=datalab-online, pages=1`）。
- 同时**加强断言**：原来只断言 `"documents.owner_user_id" in sql`，命中的是 CTE 而不是返回值——和我之前在用量表那里犯过的 `RETURNING record_id` 属同一类"断言打偏"。现在同时断言 `candidate.owner_user_id`，即投影本身。
- 实测确认**这不是我的映射写错**：直接调 SDK 拿到原始响应为 `cost_breakdown = {"final_cost_cents": 0}`（**没有 `list_cost_cents` 键**），`parse_quality_score = None`，`page_count = 1`。也就是说该账号（免费额度）下这次转换服务端确实计 0 分，用量页面会显示"页数 > 0、金额 $0.00"，这是**准确**而非坏掉。免费额度耗尽后同一字段才会出现非零值。
- 次要观察：直连 SDK 的脚本偶发 `Cannot connect to host www.datalab.to:443`（同一次运行的前一次成功、后一次成功），看起来是出站网络的瞬时抖动，与代码无关；后端进程内的调用两次都成功。
- 验证：`tests/unit/server/database/test_document_jobs.py` + `tests/unit/server/documents` 共 146 项通过；`ruff check` 通过。

### Datalab 在线解析器：第十一步（Usage 页面）

- 新增 `UsageTab`（Settings 的第五个 tab，`!isStudent` 时显示，与 model tab 同样的做法）：两张指标卡（已解析页数 / 花费）与逐日柱状图，带 7d/14d/30d 切换。
- **页面不做合计**，直接用接口返回的 `totals`——否则"总花费"会有两份实现，早晚出现头部数字与图对不上（有测试专门钉这一点）。
- **空数据不是空图表**：没有活动时显示"这段时间内没有转换过文档"，而不是一个空坐标系——空图表框看起来像图表坏了，而它表达的其实是另一件事。
- 单位是**页数与金额**，不是 credits。页面注释里写明了原因：datalab 托管 API 没有余额/额度接口，on-prem 的 `/api/v1/usage` 需要 license；唯一诚实的数字只能来自我们自己真正跑过的记录。
- 金额在展示层用 `Intl.NumberFormat` 格式化（整数分 → 显示），全程不引入浮点。
- 测试 5 项（`UsageTab.test.tsx`）：显示服务端总计而非自行求和；有数据时渲染图表；**无数据时显示空态而不是空图表**；切换 range 会用新参数重新请求；选中态正确。测试里对 `ResponsiveContainer` 做了替换——jsdom 下容器宽度为 0，recharts 不渲染，图表本身的正确性是库的事，这里要测的是"什么时候渲染"和"数字对不对"。先写测试后实现。
- 验证：前端全量 **248 文件 / 2471 项通过**（上一步 2458）；`pnpm lint` 0 error / 55 warning（与基线一致）；`pnpm typecheck` 通过；`pnpm build` 通过，关键路径 **353.4 kB gz（上限 450）**——recharts 随 Settings 懒加载，没有进入关键路径，本次只增加 1.2 kB。

### Datalab 在线解析器：第十步（向导高级选项面板）

- 新增 `DatalabOptionsFields`（可展开的 `<details>`，默认折叠）：解析模式（fast/balanced/accurate）、解析范围、分页标记、为模型精简 markdown、图片提取。仅在选中的解析器是 `datalab-online` 时渲染——本地解析器没有参数，给它们显示空控件会暗示"可以调"。
- **只发送用户改过的字段**：某控件回到默认值时该键被删除（`balanced` → 不发送 `mode`；勾回"分页" → 不发送 `paginate`）。这样将来服务端默认值变了，不会被一个早先加载的向导悄悄覆盖回去。
- `types.ts` 新增 `DatalabOptions` 形状与 `toParserOptions()`：建 job 的请求体是 `Record<string, JsonValue>`，容不下 `undefined`，所以用一个显式的小函数把未设置的键滤掉，而不是在调用点硬转类型。
- 向导把 `options: {}` 换成 `options: toParserOptions(datalabOptions)`——这一处原本是写死的空对象。
- 组件里注明了它与服务端 Pydantic 模型（`providers/datalab_options.py`）是**手写对齐**的，两者可能漂移一两个版本；服务端对未知键宽容，所以不会互相弄坏。真正的"请求形状契约化"是之前 artifact 契约工作里指出的缺口，这里刻意留作后续，不半做。
- 文案 9 组中英双语新增（键为字面量，`keys.test.ts` 会强制两侧齐全）；其中图片提取一项的提示直说"图片暂不支持预览，保持关闭可避免 markdown 产生无法显示的引用"。
- 测试 8 项（`DatalabOptionsFields.test.tsx`）：初始不发送任何字段；改模式后只发 `{"mode":"accurate"}`；改回默认后该键消失；解析范围透传；`toParserOptions` 丢弃 `undefined` 而不是发 null；面板对 `datalab-online` 出现、对本地解析器不出现；默认折叠但内容仍可被辅助技术找到。
- 说明（事后记录）：本次提交顺带带入了工作区中一处**先前就存在的、属于使用者自己的未提交改动**——`HomeworkCalendarWidget.tsx` 的默认宽度由 4 改为 2（`defaultSize` / `minSize`）。该改动与本步无关，仅因提交时按目录 `git add web/src` 一并纳入；保留原样（是使用者有意的调整），在此更正归属记录。
- 验证：`src/pages/Documents` + `src/locales` 共 54 项通过；`pnpm typecheck` 通过；`pnpm lint` 0 error / 55 warning（与基线一致）。

### Datalab 在线解析器：第九步（usage 接口）

- 新增 `GET /api/v1/document-usage?range=7d|14d|30d`（`src/server/app/documents.py`）：返回逐日桶（`pages` / `cost_cents` / `conversions`）与服务端算好的总计。
- **总计在服务端算**：若让页面自己把桶加起来，就会存在两份"总花费"的实现，最终头部数字和图会对不上。
- 归属边界靠**查询层按 `owner_user_id` 收窄**，不是加角色门禁——调用者只看得到自己名下文档的花费，这才是真正的安全属性。学生账号因此得到的是**空序列而不是拒绝**（他名下没有文档），而 Settings 页面本身不会给学生显示该 tab（沿用 `activeTab === 'model' && !isStudent` 那套既有做法）。这一点与原计划里"拒绝学生"的写法不同，是我按仓库既有模式做的调整。
- 窗口由 `range` 决定（`7d`/`14d`/`30d`），未知取值返回 **422** 而不是猜一个；空序列返回 200 + 零总计，不是 404。
- 测试 6 项（`tests/unit/server/app/test_document_usage_api.py`，沿用该目录既有的 httpx + 依赖覆盖写法）：逐日桶与总计；**总计由服务端计算**；按调用者收窄；`range` 正确换算成窗口（含闭区间）；未知 range → 422；空序列 → 200 且零总计。先写测试后实现（初次 6 项全部 ERROR）。
- 验证：该文件 6 项通过；`tests/unit/server/app` 共 **737 项通过**；`ruff check` 与 `ruff format` 通过。

### Datalab 在线解析器：第八步（引入 recharts，并修好一条形同虚设的守卫）

- 加入 `recharts@3.10.1`，用于 Usage 页面的柱状图（此前设计里提过手写 SVG，改为按你的决定引入图表库）。
- **顺带发现并修复了一条失效的守卫**：`src/locales/__tests__/genericSurface.test.ts` 里那条"不得残留已退役金融依赖"的断言原本写成
  `expect(deps).not.toEqual(expect.arrayContaining(['lightweight-charts', 'recharts']))`——
  `arrayContaining` 要求**列出的包全部存在**才匹配，所以 `.not` 只在**两个都在**时才失败；只要缺一个（例如只装了 recharts），断言就通过。
  - 实证：装上 recharts、**在修订守卫之前**跑那条测试，结果是 **5 passed**（本该失败）。也就是说这条守卫从写下起就允许任意子集，我之前为 `react-grid-layout` 修订它时也没察觉。
  - 改为逐个包检查（`not.toContain('lightweight-charts')`），并保留 `lightweight-charts` 在禁用名单里——它只画过价格 K 线。`react-grid-layout` 与 `recharts` 明确允许，注释里写明各自用途且都不带行情数据。
- 「先看失败」验证：修订后的写法下，把 `recharts` 临时当作禁用包，测试立刻失败并指名（`expected [...] to not include 'recharts'`）；恢复后 5 项通过。
- 验证：该文件 5 项通过。

### Datalab 在线解析器：第七步（注册并退役 OCR 占位）

- `build_default_provider_registry()` 现在注册三个解析器：`anydoc-local`、`legacy-pdf-text`、`datalab-online`；**同时删掉了 `ocr-document` 占位**。理由是它一直以 `available=False` 挂在选择器里，而 datalab 正好提供了它所指的那项能力——留着一个永远不可用、且职责已被覆盖的条目，读起来像"坏了"而不是"没有"。
- 推荐策略改为：`text_based` 仍推荐 `anydoc-local`（免费且快，默认送付费 API 等于花钱省不到东西）；其余分类（scanned / image_based / mixed / unknown）**在 datalab 可用时推荐它**，这正是本地解析器读不了的场景。datalab 未配置时**回落到 legacy**，而不是让选择器没有默认值。
- 更新既有的 `test_recommendations.py`（它原先钉的是"scanned 推荐 legacy、列表里有 ocr-document"的旧组成）：矩阵期望改为新组成，并把"ocr-document 可见但不可用"那条改写成"占位已退役"。
- 新增 9 项测试（`test_registry.py`）：datalab 对**全部分类**都被列进可选；占位已消失；`text_based` 仍推荐本地；其余分类不再推荐 legacy；以及**直接对策略函数**驱动三组显式 descriptor 的确定性用例（本地优先、本地缺失时用 datalab、无 datalab 时回落到 legacy、scanned 下 datalab 优先于 legacy）。先写测试后实现（初次 3 条断言失败）。
- 过程中修正了一处**测试夹具失真**：我给 `anydoc-local` 声明了全部五种分类，导致"无 datalab 时回落"那条被它接管；而真实注册表是**先按分类过滤**再交给策略函数的。夹具已改为与真实声明一致（anydoc 只声明 `text_based`），并加注释说明为何必须一致。
- 验证：`tests/unit/server/documents` 共 **137 项通过**；`ruff check` 与 `ruff format` 通过。

### Datalab 在线解析器：第六步（执行器落库用量）

- **插入的一步**（原计划里没有）：设计上 provider 与执行器分工要清楚——provider 保持**纯函数**（只解析、只在元数据里声明用量），由**执行器**在产物发布成功后写库。这样"用量"这件事只有一种形状，也不需要往 `ParseRequest` 里塞 owner。
- 关键次序：**发布成功之后**才写用量。如果先写、而后 `_validate_bundle` 拒绝了产物，就会留下一条"这次转换花了钱"的记录，但文档其实什么都没产出——**把花费显示得比实际更高，比漏记更糟**。
- 失败处理有明确方向：写用量失败只记 warning 并继续。此时文档已经发布，为一笔记账把成功的解析变成失败任务是更坏的结果；宁可少报。
- 元数据里的 `usage` 必须在**所有产物**里被扫描到（不只看主产物），且缺 `provider_id` / `pages` / `final_cost_cents` 时**跳过而不抛异常**——形状不完整的声明等于"没有声明"。本地解析器不声明，因此不会产生任何记录（有测试）。
- `document_parse_jobs` 的 claim 查询新增 `documents.owner_user_id`，让用量可以归属到人而无需二次查询；对应的既有 claim 测试也加了断言。
- 测试：`test_executor.py` 新增 4 项（声明了用量则记录、字段与归属正确；本地解析器不记录；**记账失败不影响已发布的解析**；形状不完整的声明被跳过），`test_document_jobs.py` 新增一条列断言。执行器 `usage_recorder` 走依赖注入，与既有的 repository / object_store / process_runner 一致，测试不碰数据库。
- 验证：`tests/unit/server/documents/test_executor.py` 13 项通过、`tests/unit/server/database/test_document_jobs.py` 9 项通过；`ruff check`（针对改动文件）通过。全树 `ruff check src tests` 另有 13 项报错，全部位于本次未触及的既有文件（仓库既定的 lint 范围是 `src/ migrations/ scripts/ops/`）。

### Datalab 在线解析器：第五步（provider 本体）

- 新增 `DatalabExtractor`（`src/server/documents/providers/datalab.py`，`parser_id="datalab-online"`），实现既有的**同步** `DocumentParser` 协议，调用 `client.convert()`；可用性由 `get_datalab_config()` 决定，未配置时 descriptor 的 `reason` 直接写明要设置 `ENABLE_DATALAB_DOCUMENT_PARSER` 与 `DATALAB_API_KEY`，而不是让选择器只显示"不可用"。
- `datalab_sdk` **在函数内导入**（`_client` / `_convert_options`），因此没启用该解析器的部署仍然能构建 provider 注册表——与 `AnydocExtractor` 对待自身可选依赖的方式一致。
- **两个来自官方文档警告的行为各有独立测试**：请求"完成"但 `success=False` 时必须抛错且**不写出任何文件**（否则会把空文档当成功发布）；`metadata.failed_pages` 非空仍算成功，只产出 warning——因为一页读不出来就让整份任务失败，会丢掉已经成功解析的部分。
- 元数据里带一个**约定形状**的 `usage` 子对象（`provider_id` / `pages` / `list_cost_cents` / `final_cost_cents`），供执行器在产物发布后落库；用约定子对象而不是散落的 provider 私有字段，是为了让"用量"这件事只有一种形状。
- 轮询预算从配置透传到调用（`max_polls=540`）并**单测断言**——否则一次重构把预算写死在超时之上，会让计费工作变成孤儿而没有任何测试失败。
- 已存但非法的参数（旧版本向导写的）不会让任务失败，降级到默认值继续解析。
- 金额在 `_as_int` 里一次性转成整数分（SDK 可能给 int/float/Decimal），数据库层不再处理浮点。
- 测试 13 项。这批是先写实现后写测试，所以首次运行即通过；为确认断言非空转，做了变异验证：去掉 `if not result.success` 这条检查后，专门那一条立刻失败（1 failed | 12 passed），恢复后 13 项通过。
- 验证：`tests/unit/server/documents` 共 **125 项通过**；`ruff check` 与 `ruff format` 通过。

### Datalab 在线解析器：第四步（每次转换的参数模型）

- 新增 `DatalabConversionOptions`（`src/server/documents/providers/datalab_options.py`），字段覆盖 mode / paginate / page_range / max_pages / skip_cache / 图片提取与描述 / token 精简 markdown / extras，`output_format` 固定为字面量 `markdown`——用字面量而不是省略该字段，是为了让"只支持 markdown"这条约束出现在模型里，而不只藏在 provider 实现里。
- **默认值与原先的 pipeline 对齐**（`balanced` + `paginate=True`），这样从 pipeline 切到 `client.convert()` 不会悄悄改变解析产物。
- **`disable_image_extraction` 默认为 True**（与 datalab 自身的默认相反）：datalab 默认会提取图片并以 base64 返回，markdown 里会留下按 URL 寻址的查看器无法解析的引用；在图片作为独立产物发布、且预览能定位它们之前，关掉是唯一能产出"我们真的渲染得出来"的文档的默认值。
- 校验：未知 mode 拒绝；`page_range` 与 `max_pages` 互斥；`page_range` 必须是 `0-5,10,15-20` 形状；`max_pages` 必须为正。
- `from_stored()` 处理"可能是旧版本客户端写的"存储值：空值→默认；已知键应用；**未知键忽略**（新客户端不该弄坏旧服务端）；非法值**整体回退到默认**——刻意做成 all-or-nothing，因为"半应用"才是最危险的：`mode` 生效而 `page_range` 被丢弃会解析出与用户所要求**不同的页面范围**，且没有任何地方会提示。
- 测试 18 项，先写测试后实现（初次收集即失败）。
- 验证：18 项通过；`ruff check` 通过。

### Datalab 在线解析器：第三步（每次转换的用量落库）

- 新增迁移 `061_document_usage_records`（`down_revision = 060_restore_finance_schema`）与 `document_usage_records` 表：`job_id`（FK 到 `document_parse_jobs`）、`owner_user_id`（FK 到 `users`）、`provider_id`、`pages`、`list_cost_cents`、`final_cost_cents`、`created_at`。
- **`UNIQUE (job_id)` 是关键**：解析任务会重试（`document_parse_jobs.attempt_count` 就是为此存在的），按 job 去重 + 写入端 upsert，才能保证一条记录描述的是**任务**而不是某次尝试——否则同一次转换会在 Usage 页面上被计两次，把花费显示得比实际更高。`ON CONFLICT` 时不动 `created_at`，记录保留第一次产生花费的那一天。
- **按 `owner_user_id` 归属**：页面展示的是"**本账号**的文档花了多少"，而不是整个部署的支出——后者在多家庭共用的部署上会泄漏其他家庭的活动量。
- 金额全程整数分（cents），不经过浮点；`aggregate_usage` 按天聚合 `pages` / `cost_cents` / `conversions`，无活动的日期**不补零**（由页面自己画轴，稀疏序列才是诚实的输入）。读取窗口上限 `MAX_WINDOW_DAYS = 31`（页面上最长是 30 天），更宽或倒置的窗口直接 `ValueError`。
- `documents/ids.py` 增加 `usage` 前缀（`use-`），与既有的 `doc-`/`job-`/`art-` 等保持一致。
- 测试 8 项（`tests/unit/server/database/test_document_usage.py`），沿用本包既有的 mock 游标风格断言 SQL 与参数：插入带上报费用；**重试改写而非新增**（断言 `ON CONFLICT (job_id) DO UPDATE` 存在、且更新块不重新赋值 `record_id`）；读取按 owner 收窄；窗口边界参数；超长/倒置窗口被拒；按天分桶；空窗口返回空序列而非报错。先写测试后实现（初次收集即失败）。其中一条断言最初写错（`RETURNING record_id` 也含该名字），已改为针对赋值语句 `record_id =`，属于修正断言精度而不是放宽。
- **迁移已在本地调试库上实际执行并验证往返**：`upgrade head` → 确认列与索引（`document_usage_records_pkey` / `_job_id_key` / `idx_document_usage_owner_created`）→ `downgrade -1` → `upgrade head` → 表仍在。当前 alembic head 为 `061_document_usage_records`。
- **mock 测不出 SQL 语法错**，所以另外拿真实库跑了两条语句：`aggregate_usage` 正常执行（返回空）；`record_usage` 的 INSERT 能解析并按预期触发外键违反（`ForeignKeyViolation`）——这两件事一起证明了语句合法且约束真的生效。
- 验证：该文件 8 项通过；`ruff check` 通过。

## 2026-09-12

### 缺口 1/2/3 修复：artifact 注册收敛为一张表并被强制覆盖

- **缺口 1（注册手写两处）**：新增 `web/src/pages/ChatAgent/components/charts/artifactRegistry.ts` 作为唯一注册表（`artifactType` + 该 artifact 内联渲染所对应的工具名 + 组件），`INLINE_ARTIFACT_MAP` 与 `INLINE_ARTIFACT_TOOLS` 都由它派生，`InlineArtifactCards.tsx` 只做转出以保持既有引用不变。新增测试断言两条派生结果与表一致——这才是"加一张卡只改一处"的实质，而不是靠人记得改两个地方。
- **缺口 2（没有强制"能产出的 artifact 必须有渲染器"）**：导出器现在额外产出 `web/src/contracts/artifact-types.json`（扫描导出模型上 `type` 字段的 `Literal` 值），并纳入既有漂移守卫；前端新增 `artifactIdCoverage.test.ts`：后端能产出的每个 type 必须有渲染器，或在 `ARTIFACT_TYPES_WITHOUT_INLINE_CARD` 里带**理由**明确豁免；另有两条反向断言——豁免项若已获得卡片即为过期（必须删）、每条豁免必须写明理由。
- 「先看失败」验证：往 `artifact-types.json` 里塞一个新 type（模拟后端新增 artifact）后，覆盖测试立刻失败并指名：`homework_summary — add a card to artifactRegistry.ts, or record why it has none`（1 failed）；恢复后 21 项通过。
- **缺口 3（生成器手跑）**：新增 `make contracts`，一条命令跑完两跳，`.PHONY` 已登记；实测幂等（重复执行 `git diff` 为空）。
- 验证：后端全量 `tests/unit` **7591 passed / 8 deselected / 1 xfailed**（上一轮 7590，+1 为新增的 artifact index 用例）；前端全量 **248 文件 / 2458 项通过**（上一轮 2452，+6）；`pnpm typecheck` 通过；`pnpm lint` 0 error / **55** warning（比基线少 1，因为收敛后 `InlineArtifactCards.tsx` 不再需要直接引入 React）；`ruff check` 通过。
- 设计文档的缺口清单已更新：1、2、3、8 标记为已修复（3 为部分修复：有了一键命令，但不会自动触发——过期仍会让测试失败）；剩余 4（只覆盖响应不覆盖请求）、5（跨 artifact 联合类型）、6（locale 字符串手写）、7（过渡期新旧两套）属于**广度**而非机制，且都不阻塞"用这套方式新增一个工具"。

### 缺口 8 修复：`src/server/app` 不再在 import 时构造应用

- `src/server/app/__init__.py` 原先在模块顶层执行 `from src.server.app.setup import app`，于是 **import 该包下任何东西**——一个 Pydantic 模型、一个 router、一个 helper——都会构造整个 FastAPI 应用（340 条路由 + 全部中间件 + lifespan 资源）。两个实际后果：任何只需要数据模型的模块都被拖进整个 web 层（`src/tools/homework/schemas.py` 复用教育模型，而某个 router 又反向 import `ptc_agent.agent.agent`，于是模块级 import 构成硬循环）；以及不需要应用的测试和脚本也要为构造它付出代价。
- 改为 PEP 562 的惰性属性：`app` 在首次访问时解析，其余名字一律抛 `AttributeError`（这样 `from src.server.app import setup` 仍会正常回落到子模块导入）。`from src.server.app import app` 与 uvicorn 的 `src.server.app:app` 两种写法都保持不变。
- **顺手拆掉之前为绕过它而加的两处局部 import**（`build_domain_tools` 与 Flash 的 `_build_tools`），改回正常的模块级 import——这是"修复生效"的证据，而不是继续留着 workaround。
- 修复前后对照实测：修复前 `import src.server.app.education.models` 后 `src.server.app.setup` 已在 `sys.modules` 中；修复后为 **False**。同时验证四条路径：`from src.server.app import app`（FastAPI，340 routes）、`from src.server.app import setup`、`uvicorn.importer.import_from_string('src.server.app:app')`、以及实际重启 `server.py` 后 `Application startup complete` 且 `/api/v1/users/me` 返回 401（无 cookie 的预期结果），日志无 error/traceback。
- 验证：后端全量 `tests/unit` **7590 passed / 8 deselected**（其中 1 项 xpass 是既有非确定性用例 `test_delta_channel_ordering.py::test_fan_out_reconstruction_preserves_live_order` 自身 ~50/50 的翻转，其 xfail 说明里写明了，与本次改动无关）；`ruff check` 通过。

### Agent artifact 契约：第七步（端到端验证 + 配方落盘）

- **真实链路跑通**：重启后端（18000，接 15432/16379/19000）后，在 Flash 会话里问「最近我有哪些作业要做」，模型调用了 `get_homework_schedule`，卡片在会话里正常渲染——顶部区间、统计条（2 今日 / 8 本周 / 4 逾期 / 12 已完成，逾期标红）、按日期分组（今天 / 明天 / 9月14日周一 …）、科目双色图标、孩子姓名与截止时间齐全。
- **回放实测通过**：整页刷新后仍有 **3 张卡片、53 行任务**，即 artifact 确实随历史存储并在重开线程时重演——设计里那条「若不过就停下来」的假设，现在既有单元测试也有实测证据。
- 观察到一点（不是缺陷，供后续判断）：模型为了答"最近"自行按 2w / 上周 / 本周调了三次工具，于是出现三张卡片。工具本身正确；是否要在会话里把同一次回答的多张同类卡片折叠成一张，属于产品决策，不在本次范围。
- 把**配方**写进设计文档：新增工具时需要按序做 8 步（声明 Pydantic → 注册 OUTPUTS → 跑导出器 → 注册 CONTRACTS → 跑 zod 生成器 → `z.infer` 包装 → 工具返回 `(content, artifact)` → 渲染前校验并注册 artifact type），并注明每一步由哪个测试兜底；只有第 8 步（注册）目前没有结构性强制——那正是缺口清单第 1 项。同时明确写清这次**证明了什么**（新 artifact 的链路自洽、无需取数即可渲染、回放可重演）与**没证明什么**（能否扩展到大量 artifact 类型：一个带 `Literal` 的信封不等于联合类型，而注册仍要手写两处）。
- 验证：后端全量 `tests/unit` **7590 passed / 8 deselected / 1 xfailed**（基线 7547，本次 +43）；前端全量 **248 文件 / 2452 项通过**（基线 2419，本次 +33）；`ruff check` 通过；`pnpm typecheck` 通过；`pnpm lint` 0 error / 56 warning。
- 说明：验证过程中在用户的 Flash 工作区新建了一个会话（标题即那句提问），并临时签过一个本地开发会话（已删除）。后台服务已用新代码重启，仍在 18000 上监听。

### Agent artifact 契约：第六步（chat 卡片 + 注册 + 回放验证）

- 新增 `InlineHomeworkCard`（`web/src/pages/ChatAgent/components/charts/`）：按约定**复制**仪表盘 widget 的渲染，而不是抽公共组件——差异是结构性的：widget 是自取数、受 config 驱动的容器，而会话里的卡片必须渲染 payload，并在从存储事件回放时逐字重现。两者靠**契约**保持一致（同一份 Pydantic 生成的类型），而不是靠共享组件。
- 卡片作为叶子节点必须成立的两点：孩子姓名取自 payload 的 `student_names`（没有成员列表可拉）；分组按**日期**而不是 widget 的"今天/明天"相对桶——因为工具可以回答"上周的作业"，而"明天"对上周没有意义。今天/明天仍显示为中文相对标签，其余显示具体日期。
- 渲染前用生成的 zod 校验：**不通过就显示一行提示，而不是在会话里抛错**——这是"有契约"的实际收益。测试里专门做了变异验证：把校验分支短路掉后，两条用例立刻失败（2 failed），恢复后 11 项通过。
- 11 项卡片测试：渲染真实 artifact、按日期分组且升序、姓名来自 payload、**在没有任何 QueryClientProvider 的情况下也能渲染**（若有取数 hook 会抛错，这条隐式守住"叶子"性质）、逾期标记、未知科目回落到「书本」图标、契约不通过显示提示、完全不是作业 artifact 也显示提示、未知多余键忽略、空结果空态、点击透传给详情面板。
- 注册：`INLINE_ARTIFACT_TOOLS` 加 `get_homework_schedule`，`INLINE_ARTIFACT_MAP` 加 `homework_schedule`，并新增 4 项注册表测试（每个 artifact type 都有组件、认得作业工具、discriminator 映射到位、既有条目没被挤掉）。这套映射目前仍是纯字符串约定，所以这条断言是"便宜的那一半修复"。
- **回放 blocker 已验证通过**（这是设计里那条"若不过就停下来"的项）：新增 `tests/unit/server/services/history/test_tool_artifact_replay.py` 两项——带 artifact 的 `ToolMessage` 经 `messages_to_history_events` → `history_events_to_sse` 后，`tool_call_result` 事件里仍带着完整 artifact；而没有 artifact 的工具不会被凭空塞一个。顺带说明：projector 里那套 `_ARTIFACT_FROM_TOOL_MESSAGE` 派生的是**另一个**通道（widget/preview/chart 的 `artifact` SSE 事件），既有测试只覆盖了那一支，卡片读的这支此前没人钉过。
- 验证：前端 `src/pages/ChatAgent/components/charts` + `src/contracts` 共 33 项通过；`tests/unit/server/services/history` 168 项通过；`pnpm typecheck` 通过；`pnpm lint` 0 error / 56 warning；`ruff check` 通过。

### Agent artifact 契约：第五步（PTC 与 Flash 双端暴露）

- **PTC**：把原先内联在 `create_agent` 里的金融工具清单提成 `build_finance_tools(config)`，并新增 `build_domain_tools(config)` = 金融工具 + `get_homework_schedule`；managed 教学模式仍然只被**一处** `managed_policy is None` 挡住——这是故意的，一处守卫比两处更容易看住。managed 用例的排除集合已加上 `get_homework_schedule`。
- **Flash**：`_build_tools` 追加该工具，并在**同一个 commit** 里改掉文件头的自述——它原本写着 "external tools only"，加了读库工具后那句话就不成立了。新措辞说明真实规则：外部工具 + 第一方家庭数据读取，仍然没有 sandbox、没有 MCP。
- **一个必须记录的发现（也是这次真正的坑）**：`src/server/app/__init__.py` **在 import 时构造整个 FastAPI 应用**。而本工具的 schemas 要复用 `src/server/app/education/models.py` 里的日历模型——于是 import 一个数据模型会把全部 router 拖进 agent 的 import 图，其中某个 router 又反过来 import `ptc_agent.agent.agent`，形成硬循环。我一开始就在 `agent.py` 顶层 import 该工具，直接触发循环，managed 用例与工具导入双双报 `partially initialized module`。
  - 采用的处置：在 `build_domain_tools` / Flash 的 `_build_tools` 里**局部 import**，并在注释里写明原因与真正的修法（让 `app/__init__.py` 不再以副作用构造 app），和既有 `SECRETARY_TOOLS` 的写法一致。这是绕过，不是修复。
  - 这条已作为第 8 项记进设计文档的缺口清单：**共享数据模型不应该有能力构造一个 web server**，在更多工具依赖它之前值得修，但它属于平台改动、不属于本次契约试点。
- 守住子代理边界：`finance` 这个 tool set 名字被 `subagents/builtins.py` 按名引用、被 `compiler.py` 用来设置 `finance_enabled`，所以**不能**把作业工具塞进金融清单（否则会静默扩大 analyst 子代理的可达范围）。因此分成两个函数，并加了一条测试明确断言"金融集合里没有作业工具、顶层集合里有"。
- 测试：新增 `test_tool_exposure.py`（4 项：普通账户拿到作业工具、金融工具没被漏掉、market_watch 仍然按 feature 开关、金融集合未被扩宽）与 `test_flash_exposure.py`（2 项）。另外对 managed 守卫做了变异验证：把那一处 `managed_policy is None` 去掉，managed 用例立刻失败（1 failed | 10 passed），恢复后 11 项通过。
- 验证：`tests/unit/ptc_agent` 全集 **763 passed / 1 xpassed**（含本次改动的 `agent.py`）；homework 相关 40 项通过；`ruff check` 通过。

### Agent artifact 契约：第四步（工具本体）

- 新增 `get_homework_schedule`（`src/tools/homework/tools.py`），`response_format="content_and_artifact"`，返回「模型读的摘要」+「卡片渲染的 self-contained artifact」。
- **不含任何自有查询**：时段解析完就交给既有的 `get_task_calendar`——它已经负责解析调用者的家庭、并把学生收窄到本人。再写一份 scope 逻辑，正是两个界面开始对不上的起点。
- 时段解析：`today` / `tomorrow` / `this_week` / `next_week` / `last_week` 按 ISO 周（周一起始）计算，与日历 API 自己的"本周"统计口径一致；`2w` / `1m` 从今天向前 14 / 31 天；显式 `start_date`+`end_date` 优先。全部在**家庭时区**里算今天——测试里专门用 `2026-09-16T23:30Z` 验证：在东京已经是 17 号，用 UTC 会把"今天"算错一天。
- artifact 由 `HomeworkScheduleArtifact` 生成后 `model_dump(mode="json")` 输出，所以「工具校验的形状」就是「前端校验的形状」。孩子的姓名与家庭时区一并嵌入（卡片无法二次请求）。
- content 摘要上限 40 条（`MAX_CONTENT_TASKS`），超出写明 `(N more not listed; see the schedule card)`——**上限只加在文字上，artifact 仍然带全量**，因为那是卡片要渲染的东西。空结果明确写 "No homework is due in this period."。
- 工具签名同时暴露 `window` / `start_date` / `end_date`，让模型既能答"今天有什么作业"，也能答"上周/下周的"。
- 19 项工具测试：7 个 window 的精确日期（含跨周边界）、显式区间优先、时区影响"今天"、以调用者身份请求 service、缺 user_id 报错、`student_names` 只含学生、artifact 通过契约模型往返、content 含区间与计数与孩子姓名、40 条上限与余数、空结果文案。
- 「先看失败」验证：实现前该文件因 `ModuleNotFoundError: src.tools.homework.tools` 收集失败；实现后再做变异测试——把 `last_week` 改成 `+7 天`，对应用例立刻失败（1 failed | 31 passed），恢复后 32 项通过。
- 验证：`tests/unit/tools/homework` 32 项 + `tests/unit/contracts` 3 项全通过；`ruff check` 与 `ruff format --check` 通过。

### Agent artifact 契约：第三步（artifact 信封 + 工具入参）

- 新增 `src/tools/homework/schemas.py`：`HomeworkScheduleArgs`（工具入参）与 `HomeworkScheduleArtifact`（返回信封）。信封**复用** `EducationCalendarDayResponse` / `EducationCalendarStatsResponse` 而不是重新声明——这份复用正是让 chat 卡片与仪表盘 widget 描述同一个 payload 的原因，也让一份生成契约同时覆盖两者。
- 入参设计照顾你补的要求：`window` 覆盖常见问法（`today` / `tomorrow` / `this_week` / `next_week` / `last_week` / `2w` / `1m`，默认 `2w`），另有显式 `start_date` + `end_date` 覆盖任意时段；两者都给时**显式日期优先**（模型既然算出了日期就是有意的）。周语义按家庭时区、沿用后端既有 `isoweekday` 约定，避免工具与仪表盘对"一周从哪天开始"产生分歧。
- 校验：起止必须成对、`end >= start`、跨度 < 62 天（与日历 API 的上限一致，让模型拿到可读消息而不是下游 400）。
- 信封 `type` 是 `Literal["homework_schedule"]`，因此生成物里是 `const` 而不是自由字符串，前端据此分发。`student_names` 与 `timezone` 由工具解析后**嵌进 payload**——chat 产物无法二次请求，而仪表盘 widget 是另外调接口拿成员列表的；这就是两个组件必须是副本而非共享组件的原因。
- 契约扩展到两份：新增 `web/src/contracts/homework-schedule.schema.json` 与生成物 `homeworkSchedule.generated.ts`（2524 字节，**零 `z.any()`**，`student_names` 正确生成 `z.record(z.string(), z.string())`，`type` 生成 `z.literal(...)`）。
- 前端新增 `web/src/contracts/homeworkSchedule.ts` 与 8 项测试：真实 artifact 通过；缺少卡片必需字段（含 `timezone`/`stats`/`days`）失败；`student_names` 形状错误失败；未知多余键接受；**并且交叉验证两份契约对同一批嵌入模型一致**——用日历契约解析 artifact 里的 task、再用 artifact 契约解析日历里的 task，都通过。这条是"复用是真的、不是巧合"的证据。
- fixture 是从真实服务产出、用 `model_dump(mode="json")` 序列化后落盘；家庭/学生 UUID 与孩子姓名一并替换为稳定假值（`Student 1`），日期、时刻、标题、可空性保持原样。
- 验证：后端 `tests/unit/contracts` + `tests/unit/tools/homework` 共 16 项通过；前端 `src/contracts` 18 项通过；`pnpm typecheck` 通过；`pnpm lint` 0 error / 56 warning；`ruff check` 通过。

### Agent artifact 契约：第二步（前端校验器 + 生成器换型）

**这一轮推翻了设计里"不用第三方生成器"的结论，原因是被实测推翻的。** 三个候选在真实 schema 上的表现：

| 方案 | 校验 | TS 类型 |
|---|---|---|
| zod 自带 `z.fromJSONSchema` | 正确解析 `$ref`、校验正确 | **没有** |
| `json-schema-to-zod` 直接吃导出物 | **没有**（每个 `$ref` 静默降级成 `z.any()`） | 有 |
| **`json-schema-to-zod` + 先把 `$ref` 内联** | 正确 | 有 |

- `z.fromJSONSchema` 的声明是 `fromJSONSchema(schema: JSONSchema): ZodType`——**没有泛型**，所以 `z.infer` 得到 `unknown`、`.shape` 不存在。它只给运行时校验，不给类型，而 zod 自己的注释写着 "should be considered semi-experimental"。也就是说你的直觉（不用 v4 新特性）是对的，但理由比我们原先想的更硬。
- `json-schema-to-zod` 单独用更糟：它对 `days` 生成 `z.array(z.any())`、对 `stats` 生成 `z.any()`，**嵌套模型等于没校验**。那正是这套设计要消灭的"静默接受一切"。
- 因此最终链路改为：Pydantic → JSON Schema（提交、已守卫）→ **内联 `$ref`** → `json-schema-to-zod` → 生成的 zod 源码（提交、已守卫）→ 包装模块用 `z.infer` 导出真实类型。内联约 20 行，模型图是 DAG；`assertFullyResolved` 会在 `z.any()` 再次出现时让构建失败。
- 代价是一个 **devDependency**（`json-schema-to-zod@2.8.1`，仅代码生成期使用，不进 bundle）和第二个生成物。收益是契约两半齐了：真实运行时校验 **且** 真实 TS 类型——实测 `EducationCalendarTask` 报出 17 个必填字段，少字段/错类型都是编译错误。
- 新增 `web/scripts/generate-contracts.mjs`（生成器，含 `$ref` 内联与 `z.any()` 断言）与 `web/src/contracts/__tests__/generatedContracts.test.ts`（重新生成并逐字比对，防生成物过期）。
- 真实 wire fixture：从本地库经服务层取数，用 `model_dump(mode="json")` 序列化后落盘到 `web/src/contracts/__tests__/__fixtures__/education-calendar.wire.json`（12 项任务）。**家庭/任务 UUID 已替换为稳定假值**，日期、时刻、标题、可空性保持原样——那些才是契约关心的。
- 前端契约测试 8 项：真实 payload 通过；缺必填项失败；类型错误失败且 issue path 指向出问题的任务；未知多余键**接受**（边界校验而非严格闸门）；嵌套 task 类型可单独使用；**`+09:00` 偏移被接受**（这正是剥离 `format` 的理由）以及**故意不校验日期语义**（这条取舍也钉死了）。
- 「先看失败」验证：篡改生成的 `is_overdue` 为 `z.string()`，守卫立刻失败并指名文件；恢复后 10 项全通过。
- 验证：前端全量 **248 文件 / 2429 项通过**（上次 2419）；`pnpm typecheck` 通过；`pnpm lint` 回到基线 0 error / 56 warning；生成器重复执行 `git diff` 为空（幂等）。

### Agent artifact 契约：第一步（生成物 + 漂移守卫）

- 新增 `scripts/contracts/export_schemas.py`：以 Pydantic 为唯一来源，把 `EducationTaskCalendarResponse` 导出成 JSON Schema，写入并提交 `web/src/contracts/education-calendar.schema.json`（5507 字节，含 `$defs` 里三个嵌套模型）。
- 新增 `tests/unit/contracts/test_generated_schemas_are_current.py`（3 项）：重新生成并与提交物逐字比对；断言每个 `OUTPUTS` 条目都有对应文件；断言生成物里**没有任何 `format` 关键字**。
- **剥离 `format` 是刻意的**：zod 由 JSON Schema 生成的 `date-time` 校验器只接受 `Z` 后缀，`2026-09-13T19:00:00+09:00` 这种合法值会被拒。当前只是碰巧通过，因为 Pydantic v2 会把 tz-aware 时间归一化成 UTC 再输出 `Z`。所以契约只保留结构（类型、必填、数组、可空），日期语义交给前端，并用一条测试把这条决定钉住——将来有人想"恢复保真度"必须和失败的测试正面辩论。
- 输出使用 `sort_keys=True` 的确定性序列化：重复执行生成器后 `git diff` 为空（已验证），提交物只会因真实变化而变动。
- 「先看失败」验证：篡改提交物里 `today_count.type` 为 `string`，测试立即失败并指名文件（`... is stale — re-run ...`，1 failed | 2 passed）；恢复后 3 项通过。
- 本轮为**增量**试点：不动 `Education/types.ts` 与仪表盘 widget 的类型，新管线只服务新的工具与卡片。设计文档中另附「离成为标准流程还缺什么」的 7 条清单（其中注册仍手写两处、以及没有强制"产出 artifact 的工具必须有渲染器"这两条最关键）。

## 2026-09-11

### 作业日历：周期切换提到台面 + 月历视图

- **周期切换不再藏在设置弹窗里**。上一轮它只在「编辑布局」模式的齿轮里（照搬上游组件外框的约定），对一个高频操作来说太深。现在「1周 / 2周 / 1月」是控件头部的一段分段控件，点击即换窗口并写回 preferences；原有的设置弹窗保留「显示已完成」，并新增「默认视图」。
- **新增月历视图**。头部加「列表 / 月历」切换：
  - 月网格周一起始（与后端 `isoweekday` 推导的本周窗口一致），‹ › 翻月，不在本月时出现「回到本月」。
  - 每格：日号 + 当天作业的**科目色点**（同一科目只算一次，最多 3 个，超出显示 `+N`）；今天有描边，选中日为实心底，**当天含逾期未完成时该日号标红**。
  - 点某个日期 → 网格下方列出当天作业（复用同一行组件：科目图标 + 标题 + 孩子名 + 时间 + 逾期/已完成标记）；当天没有作业显示空态。默认选中今天，翻月后选中本月或该月 1 号。
- 数据：列表模式按窗口请求（今天起向前），月历模式请求当月整月（API 上限 62 天，够用）。统计条只在「当前周期 / 当前月」显示——它是当前状态摘要，套在历史窗口上会误导。
- 视图与周期都存进组件配置（`config.view` / `config.window`，schema 已加 `view`），刷新后保留；`offset`（列表回看）与选中的日期仍是组件内状态，刷新回到当前。因为 `useDashboardPrefs` 是乐观更新，切换是即时的，不用等写盘往返。
- `minSize` 高度由 15 提到 20：月网格约需六行格子再加当天列表。
- 测试：作业日历新增 15 项（周期控件换窗口并持久化、选中态、月网格天数与起止、整月请求、默认选中今天并列出当天、点日期换列表、空态、逾期日标记、色点去重与 `+N`、翻月与选中回落、统计条隐藏与「回到本月」、月历下同样过滤已完成）。测试夹具改成了「父组件持有 config 并把 patch 回灌」的有状态 harness，与真实画布一致——否则切换看起来是死的（这一版最初就是因此挂了两条）。
- 验证：真实浏览器 + 真实数据确认月网格渲染 30 格、20 天有色点、今天因逾期标红、默认选中今天并列出当天两条作业。`pnpm typecheck` 通过；全量 `pnpm vitest run` **248 文件 / 2419 项全部通过**；`pnpm lint` 0 error / 56 warning（与基线一致）。

### 教育双色图标接入

- 引入 `iconfont-172-教育类双色-svg` 这批 24 枚图标，落在 `web/src/components/icons/`：
  - `educationIcons.ts`：转换后的数据模块（110 条 path）。源文件是 1024×1024、path 上写死三种绿色（`#036B3C` / `#33A464` / `#B3E99E`）的同一色相三个深浅层次——这正是它们在小尺寸下呈现「双色」感的原因。直接内联这套绿色既会和主题冲突，也会让所有科目变成同一个颜色，所以转换只保留每条 path 的**深浅编号**（deep→1、mid→2、浅色变体→3），不保留字面色值。
  - `SubjectIcon.tsx`：把 tone 画成 `currentColor` 乘不同 alpha（1 / 0.68 / 0.3）。因此一个 `color` 参数就能得到原图那种双色观感，且在深色面上同样成立（写死的浅绿在深色面上会糊）。不传 `color` 时继承周围文字色——这正是它能在「选中态按钮」这种同色背景上用白色直接复用的原因。
  - `subjectIcons.ts`：`education_subjects.code` → 图标的映射。
- 接入两处：作业日历组件的行（原来是一个 2px 色点，现在是该科目的图标，用 `subject_color` 着色，20px）与 `/education/tasks/new` 的科目选择器（22px；选中态为科目色背景上的白色图标）。`ChoiceGroup` 原本的圆点只在科目这一组生效，因此直接替换，未引入额外分支。
- 尺寸与对比度是实测定的，不是拍脑袋：先生成对照组（三档 alpha × 16/18/22/26px）截图比对，结论是 1 / 0.68 / 0.3 这组对比度最优（更平的 alpha 会让浅色结构消失、图标退化成色块），而 16px 无论哪档都读不出形状——这批图是 1024 单位的细节，低于约 20px 就被深色剪影吞掉。所以选择器取 22px、组件行取 20px。
- 映射缺口已如实标注：这批图没有物理 / 历史 / 政治，分别借用「天文」（星球轨道）、「书本」、「目标」（靶心）；其余六个科目都是字面匹配。三者的替换点是 `subjectIcons.ts` 一处。未知或缺失的科目码回落到「书本」而不是不渲染。
- 测试：`SubjectIcon.test.tsx` 12 项（24 枚图标都有 path 且 tone 合法、每个字典科目都能解析到真实图标、未知科目回落、颜色覆盖与继承、无障碍语义、显式指定图标、尺寸）；作业日历新增 2 项（行内画出科目图标且用科目色着色、未知科目回落）。
- 验证：在真实浏览器里用真实数据看过两处界面（作业日历在画布中、`/education/tasks/new` 的科目选择器），图标可辨识、逾期红色与选中态均正常。`pnpm typecheck` 通过；全量 `pnpm vitest run` **248 文件 / 2406 项全部通过**；`pnpm lint` 0 error / 56 warning（与基线一致）；`pnpm build` 通过，关键路径 351.8 kB gz（上限 450，本次 +0.2 kB）。

### 画布落地：Dashboard 切换、组件画廊与保留组件

- `/dashboard` 现在是双模式：`classic` 是既有的 `WorkspaceOverview`（新增可选 `layoutToggle`，在页头渲染切换控件），`custom` 是新的组件画布 `DashboardCustom`。默认仍是 classic，只有用户主动切换或被种下预设后才进画布，因此本次改动不会打乱任何人已有的界面。
- `DashboardRouter` 沿用上游三条规则，每条都对应一个真实缺陷：移动端恒为 classic 且不显示切换；无 prefs / prefs 损坏时回落 classic；`isLoading` 期间拒绝写入，且切换时重读最新缓存再组装 payload。最后一条尤其重要——服务端整体替换 dashboard 键，用渲染期快照回放会把跨标签页的修改覆盖掉（本地 ModelTab 之前就栽在这类问题上）。
- 画布外壳 `DashboardCustom`：栅格 + 工具栏（添加组件 / 预设 / 编辑布局 / 重置）+ 组件设置弹窗 + 重置确认。**未**带来上游的市场 websocket provider、四个金融对话框与浮动聊天卡。
- 迁回组件画廊 `AddWidgetDialog`、预设面板 `PresetsDialog`、缩略图与设置原子组件（`EnumField` / `SettingsDoneButton`）。缩略图由上游 712 行（三十个金融 widget 的手绘图形）重写为约 240 行：只保留四种组件族的示意图形，缩略图的重点是布局形状而不是装饰。画廊的 `markets` / `intel` 分类与 TradingView 徽标随之删除。
- 自写 `presets.ts`：`family-desk`（默认，作业日历在右栏 + 工作台 + 近期对话 + 工作区 + 自动化）与 `homework-focus`（整宽作业日历）。沿用上游的 `PresetId` / `PresetMeta` / `PRESETS_META` / `getPreset` 形状，因此 prefs 层、画廊、缩略图无需改动；`useDashboardPrefs` 的首次切换与「重置」默认预设同步改为 `family-desk`。
- 迁回四个不依赖金融数据的组件：`automations.list`、`agent.conversation`、`workspace.picker`、`threads.recent`，以及 `ConversationWidget` 依赖的 `Dashboard/hooks/useChatInput.ts`。
- 本地适配：`AutomationsWidget` 删去 `trigger_type === 'price'` 分支（本分支 `Automation` 类型只有 `cron | once`），并移除 `automations.trigger.price` / `priceSymbol` 两条文案；`recentThreads.description` 去掉「研究」措辞。
- 上游 CSS/TSX 引用 `var(--color-focus-ring)`，本分支主题没有声明该 token（本地用 Tailwind `ring-ring`），会导致 `tokenRefs` 守卫失败，5 处改为已声明的 `--color-accent-primary`。
- 新增两条守卫：`widgets/__tests__/noFinanceWidgets.test.ts` 断言注册表里没有任何已弃金融组件、没有 `tv.*`、分类只剩 `personal | agent | workspace`；`presets.test.ts` 断言**每个预设引用的每个组件类型都已注册**（这正是本次迁移最容易踩的坑：预设引用了未注册的组件会渲染出一个空洞且不报错）、预设默认配置满足各自 schema、每个组件在每个断点都有布局位、单元格不越界、id 唯一。
- 「先看失败」验证：把预设里的 `threads.recent` 改成 `threads.recentt`，守卫立即失败并指名 `preset family-desk references unregistered threads.recentt`（1 failed | 5 passed），恢复后通过。
- 验证：`pnpm typecheck` 通过；前端全量 `pnpm vitest run` **247 文件 / 2392 项全部通过**（基线 237 / 2271）；`pnpm lint` 0 error / 56 warning（与基线一致）；`pnpm build` 通过，关键路径 351.6 kB gz（上限 450）。

### 作业日历组件

- 新增 `education.homeworkCalendar` 组件（`definitions/HomeworkCalendarWidget.tsx`），数据源是既有的 `GET /api/v1/education/tasks/calendar`：家长默认拿到全屋视角，学生由后端自动收窄到本人，因此前端不需要区分账户类型，只按 house 加载。
- 分桶为「更早 / 今天 / 明天 / 本周 / 下周 / 更晚」，桶内按 `due_at` 从近到远排序；逾期行红色标记，已完成行置灰划线并打勾；每行显示科目色点、标题、孩子姓名与截止时间，点击跳转 `/education`。
- 顶部统计条直接使用接口返回的 `stats`（今日 / 本周 / 逾期 / 已完成），逾期数大于 0 时标红。
- 周期范围可回看：窗口按 `today → today+len-1` 前向展开（默认 `2w`），‹ 按钮把同长度窗口整体前移一个周期，因此「看前一周」只需按一次；回看窗口时会隐藏统计条（那是「当前状态」摘要，套在历史窗口上会误导），并回退到 0 时恢复。offset 只是组件内 `useState`，不落库，刷新后总是回到当前周期。回看最多 8 个周期，避免长按把 query key 无限撑开。
- 日期一律用本地日期字符串（`toLocaleDateString('en-CA')`）而不是 `toISOString()`：后者按 UTC 切日，会让「今天到期」的作业掉进昨天或明天的桶。
- 复用框架能力：注册了上下文导出器，家长可以把整份清单或单条作业通过纸夹附加到对话；配置走 `HomeworkCalendarConfigSchema`（`window` / `showCompleted`）。
- 测试 14 项，先写测试后实现（初次运行因模块不存在失败）。其中三处最初失败源于测试夹具本身：`calendar()` 未把日期写回任务，导致所有任务都落进「今天」桶——夹具已改为以日期为准。
- 验证：`pnpm typecheck` 通过；`src/pages/Dashboard`、`src/locales`、`src/__tests__` 共 12 个文件 105 项测试通过；`pnpm lint` 0 error / 56 warning（与基线一致）。

### 迁回响应式栅格

- 迁回 `framework/DashboardGrid.tsx` 与其测试。栅格由 `react-grid-layout` 的 `ResponsiveGridLayout` 驱动，`lg`/`md` 两个断点各 12 列，行高 8px；它负责布局对账（`reconcileLayouts`）、自动补位、以及把每个单元格包在 `WidgetFrame` 里。
- 保留上游的 `WidgetErrorBoundary`：单个组件渲染报错时只显示该格子的错误提示，不会把整个画布带崩。
- 保留 fit-to-content 的高度锁：宽度拖拽时 RGL 会回报过期的 `onLayoutChange` 高度，栅格会沿用上一次内容测得的高度，避免组件内容被拉伸或截断。
- 测试适配：上游该用例把 fixture widget 注册为 `intel` 分类，本分支的 `WidgetCategory` 已收窄为 `personal | agent | workspace`，因此改为 `personal`。
- 验证：`pnpm typecheck` 通过；`src/pages/Dashboard`、`src/locales`、`src/__tests__` 共 11 个文件 91 项测试通过。

### 迁回组件外框、上下文快照与相关文案

- 迁回 `framework/contextSnapshot.ts`、`framework/WidgetFrame.tsx`（含 `.css`）、`components/RowAttachButton.tsx`（含 `.css`）及其 8 项测试。组件外框提供拖拽把手、设置菜单、复制、删除，以及把组件（或单行）作为上下文附加到对话的纸夹按钮。
- `contextSnapshot.ts` 原先在此文件里声明 `WidgetContextSnapshot`，本分支已把它移到 `@/types/widgetContext`（对话输入、ContextBus、消息载荷都从这里取）。因此改为从该处导入并 `export type` 再导出，保持上游路径的可用性。
- `WidgetFrame` 中 `definition.source === 'tradingview'` 的分支已删除：本分支不注册任何 TradingView widget，该判断没有可达输入。纸夹按钮现在只由「该组件是否注册了上下文导出器」决定。
- 文案：从中英 catalog 合并 `dashboard.widgets` 的框架级子树（`common` / `frame` / `addDialog` / `presetsDialog` / `settings` / `shell` 的自有子集），以及四个保留组件的子树；不含任何 TradingView 或证券类 key。
- 重写三条带有金融语义的文案：`conversation.placeholder`（中英）、`addDialog.category.personalLabel` / `personalBlurb`（中英），改为作业与文档语境的表述。
- 更新 `src/locales/__tests__/genericSurface.test.ts` 这条本地守卫：它原本断言 dashboard 命名空间只有 `overview`、且依赖里不能出现 `react-grid-layout`。现在改为「dashboard = overview + widgets」，并新增一条断言逐个点名 27 个金融组件的文案子树必须不存在；`react-grid-layout` 从禁用依赖列表中移除（纯布局库），`lightweight-charts` 与 `recharts` 仍在禁用之列。金融措辞检查保留并继续通过。
- 验证：`pnpm typecheck` 通过；`src/locales`、`src/pages/Dashboard`、`src/__tests__` 共 10 个文件 90 项测试通过。金融措辞断言在重写文案前确实失败（命中 watchlist / portfolio / 自选股 / 投资组合 / 持仓 / 财报），改后通过。

### 迁回 Dashboard 组件框架的纯逻辑层

- 从 `origin/main` 迁回 `web/src/pages/Dashboard/widgets/`：`types.ts`、`WidgetRegistry`、`ids`、`gridConstants`、`reconcile`、`configSchemas`、`snapshotSerializers`、`migrations`，以及 `reconcile` / `snapshotSerializers` / `migrations` 三套测试。63 项测试通过。
- 与上游的三处有意偏差，均因金融组件不在本分支：
  - `types.ts` 的 `initConfig` 由 `(ctx: DashboardDataContextValue) => C` 改为 `() => C`，并删去 `source?: 'tradingview'`；`WidgetCategory` 收窄为 `personal | agent | workspace`。上下文类型原本只被 `MiniChartGridWidget` / `TickerTapeWidget` 使用，两者都不迁回，保留空壳接缝反而增加无谓耦合。
  - 删除上游的 `framework/defaults.ts`（只有 `DEFAULT_BLUE_CHIPS = ['NVDA', ...]` 一个金融常量，唯一读者是上游的 `presets.ts`，本分支将自写预设）。
  - `configSchemas.ts` 只保留本分支实际注册的四个 schema（Automations / WorkspacePicker / RecentThreads / Conversation），并预先加入 `HomeworkCalendarConfigSchema`；上游另外 26 个 TradingView 与证券 schema 随之删除。
- 上游把 `sanitizeConfig` 的恢复行为（逐字段 `.catch()`、整配置回退、无 schema 透传、非法数组项丢弃而非复制出重复默认值）挂在 TradingView 的 schema 上测试。这些 widget 不迁回，因此改用测试内注册的 fixture widget 覆盖同样的行为，测试语义从「某个 widget 的 schema」回到「框架的恢复逻辑」。
- 已用「先看失败」验证测试有效：去掉 `fixture.bounded` 的 `maxSize` 后，`clamps stored w/h` 立即失败（1 failed | 10 passed），恢复后通过。
- 验证：`pnpm typecheck` 通过；`pnpm lint` 0 error / 56 warning（与基线一致）；`src/__tests__` 与 `src/locales` 共 16 项通过，金融依赖边界与 dashboard 边界守卫仍为绿。

### 恢复 Dashboard 布局系统所需的栅格依赖

- 新增 `react-grid-layout@2.2.3`（锁定版本）。它是纯布局库，peer 依赖只有 `react` / `react-dom`，与之前移除的金融图表依赖（`lightweight-charts`、`recharts`）无关，因此不与 `37fef0e9` 的裁剪冲突。
- 选择该版本是因为上游同一个 lockfile 就是 2.2.3，`ResponsiveGridLayout`、`useContainerWidth` 与 `css/styles.css` 的 API 面已被上游验证可用。
- 已验证：`package.json` 只增加这一条依赖；`pnpm build` 通过，关键路径 345.6 kB gz（上限 450 kB）。

### Dashboard 作业日历的演示数据

- 新增 `scripts/ops/seed_homework_demo.py`：为本地调试库的家庭插入一批真实的作业数据，让作业日历组件有内容可渲染。
- 脚本走服务层（`create_task` / `check_in_task`）而不是裸 SQL，因此科目/类型组合取自字典表、学生必须有年级、重复规则经正常路径物化；又因为日历是按查询窗口惰性物化的，把规则锚点放在两周前就足以让「上一周」也有数据。
- 幂等：`idempotency_key` 列为 `uuid` 类型，脚本用固定命名空间派生的 UUIDv5 作为种子键，重复执行不会产生重复行（已验证二次执行新增 0 行）。
- 数据分布：6 条规则（语文预习、数学练习、英语听读、数学订正、语文写作、英语背诵），覆盖前一周、本周与后两周；22 条已完成，保留 1 条逾期未完成用于验证红色逾期样式。
- 已知量与偏差：`--window-days` 默认 30 天，必须覆盖最早的规则锚点，否则窗口外的那条首次实例会被漏掉而多出一条「逾期」。

## 2026-09-09

### 平台 Bundle 配置组合与启动快照

- 补齐 `market_watch` feature catalog、market/news provider、OHLCV 与 Redis TTL 配置模型，同时保留本地教育、家庭和 WeChat channel 配置字段。
- 修正 Skills 匿名/登录态可选认证、MCP schema cache 导入边界，并在启动时冻结 bundled component ownership，确保磁盘 bundle 变化不会影响已运行实例的禁用策略。
- 增加 `fastmcp` 兼容依赖并适配本地 X MCP server，保留 MCP 2.x 后端与 sandbox MCP 1.x 兼容运行环境；补回 Skills slash-command alias 和 MCP 模型的本地兼容出口。
- 将用户/工作区 Skills 的 command alias 与有效 skill 集传入 PTC/Flash slash-command 解析和上下文元数据，避免已禁用或未授权的 Skill 被误触发。
- 在隔离测试容器中补齐 `quickjs-rs` 与 `wechatbot-sdk` 验证依赖；配置、Plugins、MCP、Egress 和 Skills delivery 共 93 项测试通过。
- `056_workspace_file_blobs` 继续延期；workspace 文件仍走 PostgreSQL 内联持久化，MinIO blob 读写与回填暂不接入。

### MCP 工具拒绝清单迁移

- 按本地迁移链追加 `055_tool_denylist`，保留旧 `tool_allowlist` 以支持滚动发布，并新增远程金融迁移未携带的 `policy_required` 兼容列。
- 升级时清理旧策略标记、重建允许旧/新策略并存的约束，并递增存在 OAuth 连接用户的工作区 MCP 配置版本，触发策略重新解析。
- 回滚时先将已有拒绝策略转换为空 allowlist 再删除 denylist，确保旧代码窗口保持 fail-closed；已完成聚焦测试及 PostgreSQL `054 → 055 → 054 → 055` 往返验证。

### 平台核心管理界面与后端能力迁回

- 迁回 Plugins、MCP OAuth、User Vault、egress relay、Skills/插件数据库与服务层，并接入用户级、工作区级管理路由；保留本地教育、家庭成员、WeChat iLink、文档库路由。
- 迁回 Plugins 管理页面、MCP/Skills/Vault 相关 hooks 与 API 类型，新增 `/plugins` 路由、旧 `/connectors` 重定向、导航入口及中英文基础文案。
- 前端 `tsc --noEmit` 与生产构建通过；远程 workspace blob 迁移暂缓，待本地文件持久化运行时具备对象存储读写后再单独迁移。

### PTC MCP 与 Skills runtime 对齐

- 对齐 MCP 工具生成、sandbox MCP setup/client runtime、Skills middleware/registry 与 Skills sandbox sync，使用户级 MCP/Skills 管理数据进入 PTC 运行链路。
- 扩展 `MCPServerConfig` 支持 `source="user"` 和 OAuth relay 的 `oauth_connection_id`，并保留本地 `is_user_server` 兼容调用。
- 静态编译通过；后端行为测试暂受 backend 镜像缺少 `argon2` Python 依赖阻断，待镜像依赖补齐后复跑。

## 2026-09-08

### 文档预览抽屉交互增强

- 将文档预览改为默认更宽的右侧可拖动分栏，复用 `chat-split-divider` 与文件面板图标、内容和条目语义样式。
- 预览面板与知识库列表改为真正的并排布局，切换同一数据集中的其他文件时保持面板打开并仅更新当前预览。
- 关闭预览仅收起面板，不再删除当前文档参数或触发页面导航；原始/解析 segmented control 改为按内容宽度展示，避免控件占满整行。
- 原始文件改用现有 `PreviewViewer` 呈现，支持连续滚动、单页翻页和全屏查看；解析文件继续保留 Markdown 预览及原始/解析切换。
- PDF 原始文件通过现有 PDF.js 查看器渲染并接入 `PreviewViewer` 外层，避免浏览器把带附件响应头的 PDF 误判为下载或拦截页面。
- 文件名右侧展示解析状态，新增中英文预览控制文案，并补充预览抽屉的交互回归测试。

### 文档预览与解析状态刷新

- 解析任务完成并加载产物后，主动刷新文档列表和详情缓存，列表状态会即时从“未解析”更新为最新状态。
- 点击知识库文件名改为打开右侧预览抽屉，默认使用同源接口加载原始 PDF 并交给现有 PDF.js 查看器；顶部 Tabs 可切换到最新成功任务的 Markdown 产物。
- 无解析产物时在内容区展示 `empty-state-for-file.svg` 并提供“开始解析”入口；结果页加入 `task-celebrating-confetti.svg` 的轻量完成提示。
- 新增 owner-safe `GET /api/v1/documents/{document_id}/source` 原始文件流式接口，浏览器不再跳转或暴露 MinIO 地址。

### 上传向导数据集选择

- 将上传向导中的数据集垂直勾选列表改为默认空选的 Multi-Select，并按已选择/其他数据集分组展示。
- 新增 SplitButton 数据集操作入口，可在向导内创建数据集；创建成功后立即加入当前选择，选择变化实时反映到上传草稿。
- Multi-Select 直接以标签展示每个已选数据集；解析结果页新增“完成”主操作，明确原文档与产物已保存并关闭向导。

## 2026-09-07

### 开发中间件数据目录迁移

- 将开发机 PostgreSQL、Redis、MinIO 的现有数据复制到 `deploy/volumes/`，并修正容器复制产生的重复目录层级。
- 根 Compose 与 middleware Compose 统一使用相对持久化目录；PostgreSQL 固定使用兼容现有数据的 15 版本。
- 清空本地 override 对 Downloads 路径的隐式覆盖，保留旧容器、Docker 卷及首次初始化目录作为回滚来源。

### 本地后端开发启动

- 支持通过 `uv run python server.py --host 0.0.0.0 --port 8000` 启动开发后端，健康检查地址为 `/health`。
- 当前迁移后的数据库已可连接；若尚未执行项目 migration，解析任务、运行恢复和自动化调度相关表会保持不可用，服务仍会启动并明确记录告警。

### PostgreSQL 数据挂载修正

- 修正 PostgreSQL Compose 挂载方式，直接将 `deploy/volumes/postgresql/data` 挂载到容器的 `PGDATA`，避免镜像的匿名子卷覆盖已迁移的数据。
- 重建开发容器后恢复原有用户和文档数据，并确认 migration 版本为 `045`；8000 后端继续从 worktree 根目录 `.env` 读取本地数据库、Redis 和对象存储配置。

## 2026-09-05

### Artifact 同源下载

- 文档解析产物下载不再 `307` 跳转到 MinIO/S3 预签名地址；LangAlpha 在完成用户所有权校验后，从私有对象存储分块读取并通过原 API 路由流式返回，浏览器不会暴露或访问对象存储域名。
- 下载响应沿用 Artifact 媒体类型和兼容 Unicode 的文件名，并在完成、读取异常或客户端断开时关闭对象流；公共路由保持不变，为后续切换 Nginx/X-Accel 交付保留兼容边界。

### 知识库端到端验证

- 新增桌面与移动端浏览器流程，覆盖 Dataset/全部文档切换、分区进入、组合筛选、分页、受控表格横向滚动及学生入口隔离。
- 覆盖上传检测后不自动解析、显式方法选择、OCR 占位禁用、SSE 断线续接、Markdown 预览、多格式 Artifact 下载和历史任务展示；扩展测试 SSE 服务的凭证 CORS 与顺序响应能力。

### 后端测试契约对齐

- 更新线程来源记录与自动化归属测试，适配包含受管执行标记的线程授权元数据；隔离手动压缩的用户模型解析依赖，并同步运行时安全元数据白名单断言。

### 教育页面验证修复

- 将家庭作业创建测试迁移到现有独立页面与分组选项交互，同时保留弹窗附件清理和提交中保护覆盖；修正教材学习页面遗留的未声明颜色变量，恢复前端全量 token 校验。

### 文档知识库集成验证

- 新增真实 PostgreSQL 与完整 HTTP 流程覆盖，验证 Dataset/标签归类、上传后检测门控、显式选择同步或异步 parser、重复解析、产物历史、组合筛选分页及用户/学生权限隔离。
- 新增按需运行的 MinIO 源文件与 Markdown、JSON、图片、manifest 往返测试，以及固定 SHA-256 的 Firecrawl 上游 PDF 兼容测试；对象清理仅处理本次生成的精确 `documents/test-*` 键。
- 新增可重复运行的知识库 smoke 客户端；未指定 parser 时停在检测建议，指定可用 parser 后才创建任务并轮询产物，输出仅包含 ID、分类、状态与产物名。

### 文档解析向导

- 新增知识库五阶段解析向导：用户上传 PDF 并选择 Dataset/标签后，先查看文件名、大小、页数、页面尺寸、检测分类与建议方法，只有显式选择可用 parser 后才创建解析任务。
- 解析进度支持 SSE 断线重连与自动轮询提示，并提供取消、失败后改选方法和重复解析；完成页预览 Markdown，同时列出图片、结构化 JSON、manifest 等通用产物及历史任务。
- 修正页面尺寸读取字段与后端检测契约不一致的问题，真实 PDF 的 point 尺寸现在可在检测概要中显示。

### 知识库集合浏览

- 新增 Dataset 卡片视图及创建、搜索、进入分区、重命名和删除操作；Dataset 只保存逻辑归类，删除后其中的原始文档仍保留在知识库。
- 新增 Dataset 内与全部文档共用的服务端分页表格，支持文件名防抖搜索、Dataset、多标签、格式、检测分类和解析状态组合筛选，并在 URL 中分别保存各视图状态。
- 文档表格展示文件名、Dataset、标签、格式、原文件大小、解析状态与更新时间，提供打开、重命名、删除操作；多标签查询固定使用 FastAPI 可识别的重复参数序列化。

### 知识库页面入口

- 新增懒加载的 `/documents` 一级页面与预加载映射，在桌面侧栏和移动底栏展示“知识库”；导航可见性统一由共享规则控制，学生账户不显示该入口。
- 新增 Dataset、全部文档双 Tab 壳层，切换时仅更新视图参数并保留两侧各自的搜索与分页 URL 状态；中英文文案、键盘焦点、窄屏安全间距和减弱动画均使用现有 Quiet Workspace 规范。

### 文档知识库前端数据层

- 新增格式中立的 Dataset、文档、检测、解析任务及多类型 Artifact 前端契约，并覆盖知识库全部 REST 操作、重复 Dataset/标签上传字段和同步/异步解析响应。
- 新增分层 React Query 缓存键与操作 hooks；解析进度按 PostgreSQL 状态版本续接 SSE，连续断流后自动降级轮询，Artifact 下载统一经过本站授权接口。

### PDF 上游兼容样本清单

- 记录 AnyDoc 与 pdf-inspector MIT 测试样本的来源、大小、Git blob、SHA-256、固定版本实测分类及 OCR/提取结果；真实兼容测试按需下载并先校验摘要，不把上游 PDF 大文件直接提交到仓库。

### 文档知识库 API

- 新增用户认证且学生禁用的 Dataset、标签、文档上传与筛选、检测、解析方法、重复解析任务、Artifact 下载 REST API；上传后只返回原文件信息，检测返回推荐方法，必须由用户显式选择 parser 才会创建任务。
- 新增 PostgreSQL 权威的任务 SSE、同步等待超时自动转异步与 MinIO 私有短期下载重定向；每个服务进程启动带 lease 的文档 worker，并在数据库及 Redis 关闭前停止，不把文档状态混入聊天 checkpoint。

### 文档任务进度通知

- 新增 PostgreSQL 权威的任务快照流：连接后先返回 owner-scoped 当前状态，订阅 Redis 后立即复读以封闭竞态，并在 hint 丢失、连接异常或 Redis 不可用时按节奏回查数据库。
- Redis 仅发布 `job_id` 与 `status_version` 唤醒提示，executor 在已提交的阶段与终态更新后 best-effort 通知；同步等待到期只返回当前非终态快照，不取消 durable job，客户端断开也不会改变任务。

### 文档解析任务执行器

- 新增带 lease/version fence 的文档任务 executor 与每进程 worker：按 preparing、parsing、storing 阶段推进，在隔离子进程中执行用户明确选择的 parser，并由 PostgreSQL claim 返回冻结的原文件与检测上下文。
- 严格校验 artifact 数量、总大小、相对路径、普通文件及 symlink，所有对象写入独立 job 前缀；上传或发布失败仅补偿本次已写 key，超时和内部错误落安全错误，取消或续租失败会终止受管执行且不能发布产物。

### 文档解析任务状态机

- 新增 PostgreSQL 持久化解析任务操作：支持同一文档重复创建任务、`FOR UPDATE SKIP LOCKED` 跨 worker 抢占、过期 lease 接管、续租、单调进度、owner-safe 取消及带 attempt/status-version fencing 的失败处理。
- Artifact 元数据发布与任务完成在同一事务内提交，原始 parser 信息保留在任务记录；真实双连接测试覆盖单任务互斥 claim 和过期任务递增 attempt 后恢复。

### 文档检测编排

- 新增用户私有的文档检测服务：每次重试创建独立检测记录，将已授权原文件下载到受限临时目录，完成后无条件清理，并分别持久化成功结果或不泄露内部路径的安全错误。
- 新增 pending 检测的 owner-safe 终态更新和最新成功检测查询；解析方法始终来自用户指定的检测记录，仅在未指定时读取该文档最新成功结果，检测过程不会自动创建解析任务。

### 文档解析 Provider 与推荐策略

- 新增 AnyDoc 本地数字版 PDF parser 与共享 legacy PDF parser：AnyDoc 固定拒绝 hosted OCR，并将需 OCR 或空 Markdown 结果转为可重新选择方法的 `parser_incompatible`；legacy 方法允许发布带质量提示的部分或空 Markdown。
- Provider registry 按检测分类返回简单解析选项：数字版推荐 AnyDoc，混合版、扫描版、纯图版和未知类型推荐 legacy；未来 `ocr-document` 仅作为不可用选项展示，不注册占位执行器。

### 共享 PDF 文本提取

- 将 Memo 与网页抓取器重复的 pdfplumber 优先、pypdf 回退逻辑收敛为同步共享工具，统一返回 Markdown、实际后端、成功页码和总页数，为知识库旧版 PDF parser 提供可复用基础。
- 保留 Memo 的 500 页、最少可读字符、1 MB 页边界截断、并发和超时规则，以及网页抓取器的原下载限制与空结果语义；新增真实数字版、扫描版、后端回退和页数上限回归。

### PDF 文档类型检测

- 新增按文件格式解析检测器的 provider 注册边界，并以独立 `spawn` 子进程调用 `pdf-inspector`；父进程使用容量受限的结果通道、硬超时和显式回收，原生崩溃与超时统一返回不含路径和堆栈的稳定失败信息。
- 将 PDF 分类、页数、页面尺寸、需 OCR 页码、置信度及受支持的版面诊断字段归一化为通用检测结果；增加可复现的数字版、扫描版、纯图版和混合版 fixture，并通过真实绑定验证四类结果。

### 文档上传与知识库服务

- 新增 PDF 有界流式上传：在单次写入私有临时文件时校验媒体类型、扩展名与 `%PDF-` 签名，并同步计算原文件大小和 SHA-256 后发布到 `documents/doc-.../source`。
- Dataset、标签和文档操作统一经用户所有权服务编排；数据库发布失败时只补偿新 source key，文档删除也只处理从 owned 元数据加载出的精确原文件与产物 key。

### 文档知识库数据访问

- 新增所有权强制绑定的 Dataset、标签、Document、检测、解析历史和产物查询；文档列表支持 Dataset、多标签、媒体类型、分类、解析状态及服务端分页组合筛选。
- Document 与 Dataset/标签关系在事务中校验并整体替换，空关系同样先锁定 owned Document，避免跨用户静默写入；多对多筛选使用相关子查询保持结果与总数不重复。

### 文档对象存储边界

- 为 S3-compatible/MinIO 增加有界文件上传、分块下载和私有短期下载链接，并在超限或失败时清理未完成的本地文件。
- 新增仅允许 `documents/doc-.../...` 安全键的异步文档存储适配器；上传使用文档专属 50 MB 配置，删除严格限制为已授权的单个精确对象键。

### 文档知识库持久化结构

- 新增用户私有的文档、Dataset、标签、检测、解析任务与多格式产物表；通过数据库约束隔离跨用户归类，并以租约、进度版本和可重复解析任务支撑后续异步 Pipeline。

### 文档领域基础契约

- 新增 Dataset、文档、检测、解析任务、产物和标签的三字母前缀短 ID 工厂，统一采用连字符与 12 位 Base62 随机后缀，并提供有界碰撞重试。
- 定义与文件格式无关的检测、解析请求、进度和 ArtifactBundle 契约；产物记录支持 Markdown、图片与结构化数据元信息，同时拒绝路径逃逸和任务进度回退。

### 文档解析依赖与运行限制

- 固定 `pdf-inspector==1.17.0` 与 `firecrawl-anydoc==0.2.4`，并验证其原生扩展可在当前 Python 3.14 环境安装和导入。
- 新增上传大小、同步等待和解析超时的环境配置，默认分别为 50 MB、30 秒和 600 秒；服务端统一通过冻结的类型化配置读取，并在启动时拒绝非法或非正整数。

### 通用文档知识库与解析 Pipeline 设计

- 明确新增用户私有的通用文档库：以扁平 Dataset 和多标签组织原始资产，通过 `/documents` 的 Dataset 卡片与全部文档表格两种视图访问，不依赖默认 Workspace 或教育家庭资产。
- 设计“上传检测、返回建议、用户选定方法、再创建解析任务”的显式流程；首版使用 `pdf-inspector` 分类 PDF，以 `anydoc` 处理数字版，并使用现有 pdfplumber/pypdf 对混合版、扫描版和纯图版进行可能为空或不完整的尽力提取。
- 定义 PostgreSQL 租约任务、同步等待转异步、跨 worker 进度恢复，以及支持 Markdown、图片、结构化 JSON 和 manifest 的 ArtifactBundle；同一原始文件允许保留多次解析任务与产物。
- 原文件和解析产物使用独立 `documents/` MinIO/S3-compatible 前缀，业务层通过通用对象存储接口访问；短实体 ID 统一采用三字母前缀、连字符和 12 位 Base62 后缀。

### 通用文档知识库实施计划

- 将知识库拆分为 20 个可独立验证和提交的 TDD 任务，覆盖依赖与配置、领域契约、`045` 数据库迁移、MinIO 流式存储、PDF 检测与解析 provider、持久化任务进度、REST/SSE API、双 Tab 文档界面、解析向导及真实 PostgreSQL/MinIO/LAN 验收。
- 固定首版路由：数字版推荐 AnyDoc；混合版、扫描版、纯图版暂用现有 pdfplumber/pypdf 尽力提取并展示质量提示；`ocr-document` 仅作为未来可见但不可执行的方法，不与输入分类混淆。

## 2026-09-01

### 精确 Token 词表资源与自修复

- 将官方 `cl100k_base.tiktoken` 作为经过 SHA-256 校验的代码资源提交，默认使用仓库相对目录 `var/cache/tiktoken`，不再依赖系统临时目录中的偶然缓存。
- 服务启动时优先校验固定缓存并从内置资源原子播种；本地资源不可用时才尝试固定官方地址下载。所有精确路径失败后继续使用近似 Token 计数，不阻断 Agent run。
- 近似编码器不再永久驻留进程，词表通过后续重试恢复后可自动切回精确计数，无需重启后端。
- 模型设置页新增中英文显著告警和“重新下载词表”操作，后端仅允许重试固定官方资源，不接受用户提供的下载地址。
- 后端与开发 Docker 镜像固定配置 `/app/var/cache/tiktoken`，构建时校验并预填充词表缓存，同时显式设置当前运行用户的目录所有权。

### Flash 离线 Token 计数兜底

- 修复 channel worker 调用 Flash 时首次加载 `cl100k_base` 依赖外网下载失败、导致微信入站反复重试后变成 `flashagenterror` 的问题。
- tiktoken BPE 文件可用时仍使用精确计数；加载失败时切换到进程内缓存的本地近似计数，不再阻断 Agent run。
- 新增离线加载失败回归测试。

### 微信 iLink 上下文消息预算与续发

- 微信适配器将连续的 Markdown 文本单元统一按 2000 字符上限贪心合并，保留自然换行和代码块围栏，避免标题、列表等短段各自占用一个聊天气泡。
- 通道基类增加可选的每个 provider context 消息数、续发命令和提示能力；iLink 每轮最多发送 10 条，超出时保留 1 条提示并将剩余内容持久化。
- 新增加密 `channel_continuations` 表及 epoch 校验。用户发送“继续”后使用新入站 `context_token` 恢复尾部，不调用 Agent；续发状态可跨 worker 重启并在 6 小时后过期。
- 将 iLink `ret=-2`/业务限流响应分类为上下文预算错误，停止无意义的指数重试；已发送和未发送的 outbox 尾部会转入续发状态，且不会误标记绑定为需要重新认证。
- 新增分块、预算、续发、业务错误和 migration 回归测试；聚焦通道测试 47 项通过。

## 2026-08-31

### 微信 iLink 最终消息分块与 Typing

- 在通用 `ChannelAdapter` 增加 binding 生命周期、typing 刷新和最终消息预处理钩子；`GatewayRunner`
  负责在 Agent turn 期间启动/取消 typing，并保证异常不会触发错误重试或泄漏 typing 状态。
- 微信适配器直接复用本地 `wechatbot-sdk` 的 `ILinkApi`，支持 `getconfig`/`sendtyping`、连接上线/下线通知，
  同时继续使用 PostgreSQL 加密 `context_token` 作为回复上下文。
- 微信最终回复移植 Hermes 的 Markdown 标题、表格、代码块和语义分片策略，按 iLink 长度限制写入有序
  delivery outbox；明确不实现逐 token 推送、`GENERATING` 更新或消息编辑。

### 微信最终内容分块与 Typing 设计

- 对照 Hermes `BasePlatformAdapter`、`stream_dispatch.py`、Weixin adapter 及本地
  `wechatbot` SDK，明确微信采用“生成期间 typing，完成后按 Markdown 语义块和长度
  顺序发送最终内容”的策略；不实现逐 token 推送、消息编辑或 `GENERATING` 更新。
- 新增微信 iLink 分块交付设计文档，记录通用 ChannelAdapter、PostgreSQL
  delivery outbox、context token、typing ticket、连接状态通知、错误恢复和测试边界。
- 将 Hermes 与 wechatbot 的有界参考源文件保存在 `docs/references/wechat-ilink/`，
  便于后续实现和评审时复用经过验证的协议逻辑。

### 助理设置界面

- 将设置页“通道”改名为“助理设置”，微信接入改为可纵向扩展的助理 group；配置按钮缩小并将扫码二维码内嵌到 group 展开区域，不再使用弹窗。
- 修复二维码轮询响应覆盖原图片的问题，确保二维码在有效期内持续展示；二维码过期后改为显示失效状态。

### 微信消息交付

- 微信只接收主 Agent 的最终普通文本；过滤 reasoning、技能/工具调用、工具结果、commentary
  及子 Agent 中间事件，内部运行历史和 Web 端 SSE 展示保持不变。
- 修复 Flash 主 Agent 在 SSE 中使用 `model:<uuid>` 命名空间时被误判为非主 Agent 的问题；
  现在在通道边界规范化为稳定的 `main` 身份，避免已完成的回复被 worker 重试 8 次后丢弃。

### 通道结构化事件与呈现抽象

- 新增 provider-neutral 的 `MessageChunk`、`MessageStop`、`Commentary`、工具调用和网关通知事件类；
  事件仅用于展示，不写入 Agent 历史。
- `ChannelAdapter` 现提供 Hermes 风格的平台能力默认值和消息/工具呈现钩子；
  `ChannelEventDispatcher` 负责把结构化事件路由到 channel-specific sink，适配器可返回 `None`
  吞掉不适合平台显示的工具 chrome。
- Flash 只把内部 SSE 转换为结构化事件；GatewayRunner 按适配器呈现结果写入原有 PostgreSQL
  delivery outbox，并兼容没有事件回调的旧 AgentAdapter。微信覆盖呈现策略，仅发送主 Agent 普通文本。

### 微信 iLink Bot 收发链路修复

- 修复入站纯文本消息写入 PostgreSQL 时可空媒体和回复上下文参数未标注类型、导致 worker 重试失败的问题。
- 修复 OSS 模式未配置 `INTERNAL_SERVICE_TOKEN` 时，独立 channel worker 无浏览器 session cookie 被消息接口拒绝的问题；保留配置服务 token 时的严格认证。

## 2026-08-30

### 微信 iLink Bot 通道网关

- 修复二维码无法显示的问题：iLink 的 `qrcode_img_content` 是待编码的 URL 内容，
  现在由 `qrcode` 生成 PNG Data URL 后交给前端；不要求 HTTPS，并兼容 provider 已返回的图片 Data URL。
- 修复二维码轮询在没有新的 provider poll state 时触发 PostgreSQL 未定类型 `NULL` 参数、
  导致接口返回 500 的问题；显式标注 SQL 参数类型并补充回归测试。
- 将原始 iLink 网关设计同步至已实现的通用 Adapter 契约、已绑定账号重配置、二维码
  超时恢复和自然边界文本分片，明确 token 与旧绑定状态均不暴露给浏览器。
- Gateway 的认证失效、图片解析、文本长度与来源平台信息改由通用 ChannelAdapter 契约提供；
  不再导入微信异常、探测微信私有方法或按通道名称分支。Flash 内部请求会保留实际 channel 类型，
  长文本按段落、换行和空格优先切分后才硬切，保持微信端回复可读性。
- 已连接的微信卡片现可重新配置。二维码请求会将现有加密 iLink token 临时传给 SDK；
  平台返回 `binded_redirect` 时原子复用当前 binding，不重置 cursor、会话或 epoch。二维码轮询本地
  超时会释放 attempt 并继续等待，重配期间 binding 已断开则安全终态为失败而非返回服务端错误。
- 新增基于通用 `ChannelAdapter -> GatewayRunner -> AgentAdapter` 的独立通道 worker；
  worker 通过 PostgreSQL 租约轮询、持久化收件、调用系统内部 Flash API，并从可靠发件箱投递回复。
- 新增 `LangAlphaFlashAdapter`：固定使用 Flash、携带所属用户的内部服务认证与稳定 request key，
  支持 SSE 文本汇总和重复请求后的既有 run 重连，不直接导入或运行 Flash graph。
- iLink 图片引用的 AES 元数据仅随加密入站 payload 保存；语音、文件和视频保持跳过。入站和
  出站均支持租约恢复、确定性 client id、按会话顺序处理，并始终使用所引用入站消息的 context token。
- 新增设置 API 回归、Flash adapter、GatewayRunner 和独立 worker 的聚焦测试；通道后端聚焦测试
  81 项、Settings 前端测试 45 项通过，后端通道 Ruff 通过，默认/开发/中间件/NAS 组合 Compose
  配置均可解析。
- 设置页新增所有登录成员可见的“通道”页签与微信绑定卡片，提供二维码轮询、一次性配对码、
  闲置会话时长、重新绑定和断开连接操作；前端 API 与 query key 均保持凭证不可见。
- 修复 gateway 收件与发件领取 SQL 的 CTE 分隔符，并以真实独立 worker 空跑验证；同步补齐
  家庭设置测试的查询 mock，使完整 Settings 测试覆盖恢复为通过。
- 新增 `043` 通道可靠性迁移：以 binding epoch 围栏隔离解绑、登录失效与重新扫码前的
  旧收件、旧媒体/回复上下文和旧发件箱；同一会话的发件改为全局单调序号，避免多条回复乱序。
- 收件游标、首次去重、6 小时 session 轮换改在同一事务完成；二维码尝试使用短租约并在新
  尝试、取消、过期或终态后拒绝旧轮询覆盖绑定。iLink 长轮询 binding 租约提升为 75 秒。
- 微信上传图片在解密前按响应长度与流式密文累计值限流；缺少逐消息 `context_token` 的事件
  记为拒绝；Flash 超长文本按 iLink 上限拆分后入发件箱；手工提交配对码成功会关闭弹窗并刷新状态。
- 收件的图片下载、Flash 调用和发件投递前都会再次确认 binding epoch；`043` 回滚到旧 schema
  时会移除已销毁轮询秘密的终态二维码尝试，避免旧版本读取无法解密的占位密文。
- epoch 确认改为 PostgreSQL 共享行锁，解绑或重绑会与已开始的 Flash/微信调用明确串行；二维码
  状态请求限制为 10 秒且小于 30 秒尝试租约。关闭会话仍可完成其已排队的历史收件确认；拒绝消息
  保留为独立审计状态，缺少 `context_token` 的遗留发件绝不再以微信用户 ID 冒充回复令牌。
- `043` 回滚同样会清理已销毁发件正文的终态发件箱记录，避免恢复旧版 `NOT NULL` 约束时失败。
- iLink 收件长轮询与发件会一致地将会话失效错误转换为重新认证状态；图片同时携带两种 AES
  key 时优先采用 `image_item.aeskey`，并将可配置的 iLink 文本上限严格限制在协议兼容的
  2000 字符以内。

## 2026-08-28

### 微信 iLink Bot 通道网关设计

- 记录微信 iLink Bot 的通用 `ChannelAdapter -> GatewayRunner -> AgentAdapter`
  设计、可靠收件箱/发件箱模型、6 小时通道会话轮换、二维码绑定流程和安全边界。
- 汇总 iLink 协议、wechatbot SDK、Hermes 平台抽象及 LangAlpha 现有 Flash、SSE、
  多模态和加密存储实现的参考地址与采用结论。
- 补充 iLink 扫码可能要求的短配对码流程：该码仅用于单次状态轮询，不持久化、不
  回显、不写日志；失败受阻后重新获取二维码。
- 新增可按 TDD 逐项实施的微信通道网关计划，覆盖数据库租约与收发箱、Flash SSE
  适配、独立 worker、设置页扫码流程、部署与最终验收命令。
- 为独立 worktree 的本地调试预留 backend `8010`、frontend `5187`，明确复用该
  worktree 的 `.env`，避免与另一开发会话的 `8000`、`5177` 服务发生串线。
- 明确第一期对所有用户开放：支持文本和图片入站、文本回复；视频、语音和文件
  附件跳过，Flash 原生图片输出暂不在本期解决。

### 出站 HTTPS 证书兼容性

- 移除后端对 `SSL_CERT_FILE` 和 `REQUESTS_CA_BUNDLE` 的全局 certifi 覆盖，恢复系统默认 CA 验证，避免本机代理环境下 Tavily 等出站请求在 TLS 握手阶段失败。

### 离线环境下的聊天 token 统计

- `tiktoken` 首次下载 `cl100k_base` 编码文件失败时，compaction 自动切换到本地近似估算，不再因网络 TLS 或代理问题导致 LM Studio 等 Endpoint 的聊天请求返回 500。

## 2026-08-27

### 聊天入口布置文字作业

- PTC 与 Flash 普通聊天均注册共享的家庭文字作业工具；托管教材 worker 不开放该能力，附件流程仍留在教育页面。
- 新增 `family-homework` 默认 Skill，指导模型识别布置意图、追问缺失字段并遵循文字-only 边界。
- 在 Skill 中固化中文科目、作业类型和校内/校外来源 code，避免自然语言入口依赖界面猜测字典值。

### 自然语言布置作业边界

- 新增按家庭只读列出学生账户与当前年级的数据库 helper，并固化自然语言布置文字作业工具的认证、家长权限、学生归属和姓名解析边界测试。

### 自然语言布置作业设计

- 确定第一阶段通过 PTC/Flash 共用的内置教育工具和默认 Skill，让家长在任意聊天窗口布置文字作业。
- 工具复用现有家庭作业服务和权限校验，暂不接入图片、PDF 或聊天附件；附件能力留待文字流程稳定后扩展。

## 2026-08-27

### 作业创建完成反馈

- 学科按钮选中时将颜色圆点切换为白色并增加浅色边框，保证圆点在彩色选中背景上仍清晰可见。
- 独立创建作业成功后自动返回家庭作业列表页。

### 每周作业与创建页细节修复

- 选择每周重复日期时，若首次截止日期不在所选日期内，会自动顺延到最近的已选日期，避免创建时出现无效的英文校验错误。
- 创建作业页面标题增加作业图标；科目选中态继续使用对应学科颜色填充，不被通用选中样式覆盖。

### 作业创建页面布局调整

- 创建作业改为独立页面，增加“家庭作业 / 创建作业”Breadcrumb，为后续扩展作业编辑与复用保留空间。
- 参照设置类页面采用居中内容列、分行字段和底部主操作区，取消简单弹窗承载完整创建流程。
- 按钮组改为无间距 segmented control，共享相邻边框并加深未选中边框与选中态；科目继续显示对应颜色。

### 家庭作业创建表单交互优化

- 创建作业弹窗移除标题输入，标题由科目和作业类型自动生成，详细要求统一填写在说明中。
- 学生、科目、作业类型、练习来源和重复方式改为按钮组，打开弹窗时自动选中常用默认项，减少重复操作。
- 科目按钮显示既有学科颜色，选中状态和键盘焦点保持清晰可见。

## 2026-08-26

### 家庭作业请求重试与附件回收

- 创建作业现要求客户端提供逻辑请求键；同一家庭家长以相同键重试时会返回首次已物化的任务，不会重复创建作业规则、任务实例或家长材料关联。
- 家长创建、学生首次打卡和补充提交会在上传前取得同一暂存键；网络中断或服务端异常后的重试复用既有附件 ID，不重复上传对象或新增附件记录。
- 附件暂存槽位按家庭、创建者和请求键唯一约束；并发上传相同槽位会采用已成功写入的附件，未被任务、提交或教材引用的附件可由创建者安全回收。
- 每周作业的首次截止日期改由后端按家庭时区判定，前端不再以浏览器本地时区阻止请求，并会直接展示服务端返回的校验错误。
- 附件回收改为先删除 MinIO 对象、成功后再删除数据库元数据；存储删除失败时保留元数据，用户再次关闭或替换失败的暂存尝试仍可重试回收。
- 家长创建、学生打卡或补充提交的失败暂存附件，会在更换提交内容或关闭对话框时尽力回收，不影响原始错误的展示。
- 作业字典接口现返回家庭 IANA 时区；创建作业的截止时间按该家庭墙上时间转换为 ISO 时间，并在表单中明确显示所用时区，不再受操作浏览器所在时区影响。
- 创建作业、学生打卡与补充提交正在请求时会保持对话框和暂存附件，拒绝 Escape、点击遮罩或关闭按钮触发的关闭；请求结束后才恢复原有关闭与回收行为。
- 暂存附件回收只有在所有删除请求成功后才会清除本地暂存 ID；存储暂不可用时，下一次关闭或替换提交内容会继续重试回收。
- 附件回收在数据库事务内锁定未引用的资源记录，直至 MinIO 对象和元数据均删除完成，避免任务或提交在检查与对象删除之间取得引用；任务列表的截止时间也统一按家庭时区显示。

### 家庭作业创建与前端数据契约

- 家长创建作业表单现支持一次、每天、工作日和每周指定日期；每周规则会要求至少选择一个星期，并与后端 ISO 星期规则保持一致。
- 创建作业与学生补充提交均支持一次选择多份图片或 PDF 附件；创建失败会在表单中显示明确错误，避免上传或创建异常被静默吞掉。
- 前端已补齐作业详情、提交反馈时间线与月度日历的类型、API 和 React Query 契约，为后续界面实现复用受家庭权限保护的后端接口。
- 打卡、补充提交、反馈和取消的客户端调用现返回对应服务端资源，保持状态更新与后续详情视图的一致性。
- 学生首次打卡改为确认弹窗：可直接确认完成，也可选填文字并上传多份附件；服务端失败和超量附件会在当前操作处显示具体错误，不再产生未处理的前端 rejection。
- 家长创建、学生打卡和学生补充提交均会在任何上传前拒绝超过 20 份附件；每周作业还会在本地校验首次截止时间必须属于已选星期，避免无效请求到达服务端。

### 家庭作业日历与进度

- 新增受家庭角色保护的作业日历接口：家长可查看家庭总览或筛选同一家庭子女，学生始终只能读取自己的任务；跨家庭子女查询按不存在处理。
- 日历要求明确起止日期并限制在 62 天内，且最多浏览家庭本地日期起 12 个月后的任务，避免异常远期请求物化大量重复实例；历史日历仍会补齐当前本地周的规则实例，保证今日、本周与逾期统计准确。
- 日历任务复用学科字典颜色，并分别返回完成与逾期标记；进度摘要提供今日、本周、逾期和所选范围内已完成任务数量，取消任务仅保留在历史中而不会进入日历。
- 日历物化仅生成请求日期段与当前统计周段，避免长期每日规则在浏览历史月份时回放数年的实例；`today_count` 仅表示今日待完成，`week_count` 仅表示本周已完成。

### 作业详情与附件时间线

- 新增受家庭角色保护的作业详情接口：同家庭家长可查看家庭任务，学生仅可查看分配给自己的任务；其他学生和跨家庭账户统一按任务不存在处理。
- 作业详情将家长布置原件与学生历次打卡/补充提交严格分段返回，每次提交保留多份附件及可追加的反馈历史，并按提交、附件和反馈的时间顺序稳定展示。
- 详情响应仅包含安全附件元数据和既有短期下载接口引用，不暴露 MinIO 对象 key；实际下载仍经原有家庭授权的签名 URL 接口完成。

### 作业工作流收敛修复

- 家长现可在“设置 > 家庭账户”中为每位子女查看和维护当前年级，年级选项复用家庭作业字典；创建作业会显示所选学生年级，未设置年级时明确引导并阻止创建。
- 家庭成员列表只会为学生返回年级字段；年级档案与作业字典并行加载时，会保留已有年级的受控选择状态并暂停编辑，不会误显示为未设置年级。
- 家长更新学生年级后，设置页会立即将接口返回的档案值写入查询缓存并继续后台刷新，等待查询期间不会短暂回退到旧年级。
- 每周指定日期的作业现要求首次截止日期本身属于所选星期，避免创建后第一条任务与排程不一致。
- 新增前向迁移 `040`：修复兼容期内“已有学生提交但仍为待完成”的遗留作业，按最早提交时间补齐完成时间并收敛为已完成；不会改写已应用的 `039` 迁移。
- 当前教育页面已接入作业字典：家长创建作业时选择科目和对应类型，练习时必须选择校内或校外来源；学生可直接空内容打卡，并在完成后补充提交；家长反馈仅使用反馈或请求修改，不再覆盖完成状态。
- `039` 升级现会先清理缺失、半成品或不匹配的分类快照，并同时清空关联年级，避免旧数据在添加学科-作业类型一致性约束时中断升级。
- 创建作业、学生打卡和修改提交遇到跨家庭附件时统一返回明确的 400 请求错误；任务状态冲突仍保持 409。

### 作业完成与批改解耦

- 作业创建现必须选择有效的学科和作业类型组合，自动保存受分配学生当前年级的快照；练习任务必须选择校内或校外来源，其他类型不能携带该来源。
- 重复作业支持一次、每日、工作日和每周指定 ISO 星期；每周规则要求非空且不重复的有效星期列表，后续实例会保留规则的分类快照。
- 学生首次打卡可以不填写文字或上传附件，并会在同一事务内将任务标记为已完成及记录完成时间；相同幂等键会返回原始打卡记录。
- 已完成任务允许学生持续追加修改提交，也允许家长追加反馈或建议修改；这些后续动作不再回退或改变任务的完成事实，已完成任务不能取消。
- 作业数据库状态已收敛为 `open`、`completed` 和 `cancelled`，评审决策收敛为 `feedback` 和 `revision_requested`；升级时会安全归并兼容期遗留状态并移除临时自动完成触发器。

### 学生年级与作业字典接口

- 家长现在可在家庭账户设置中读取或维护同一家庭子女的当前年级；学生本人和跨家庭账户均不能修改该档案。
- 新增受家庭成员权限保护的作业字典接口，按展示顺序返回学科颜色、各学科允许的作业类型、年级及练习来源，供家长和学生端统一使用。

### K12 作业迁移兼容修复

- 新增前向迁移修复已升级至初版作业工作流的数据库：恢复旧服务所需的任务状态、评审决策与提交类型默认值，并在每次学生提交时记录首次完成时间。
- 每周重复规则现拒绝空数组、JSON `null` 和非 ISO 星期值；已升级数据库无需降级或重建即可获得该校验。
- 每周重复规则进一步拒绝数组中的 JSON `null` 元素；036 的回退会先归并兼容期内写入的遗留状态，避免恢复旧严格约束时失败。
- 作业列表现兼容历史评审迁移后的 `feedback` 决策；升级会先检测既有每周规则，发现不合法元数据即明确停止，避免静默改变用户排程。
- 后续新服务完成切换后，严格状态与评审决策收敛迁移调整为 `039`，避免中途部署造成旧服务写入失败。

## 2026-08-25

### K12 作业工作流数据模型

- 新增学生档案，按家庭学生成员维护可为空的当前年级；既有学生成员已回填档案，不为历史数据臆测年级。
- 作业规则与任务实例新增学科、作业类型、练习来源和年级快照，并关联既有教育字典；旧作业保持空快照以兼容升级。
- 学生首次提交完成时间独立保存，提交记录区分首次打卡和后续修改；在服务切换前，迁移暂时保留既有任务状态和评审决策，避免运行中的旧写入失败。
- 家长反馈已允许追加；严格收敛任务状态和评审决策将与新服务在后续迁移一并启用，届时不再覆盖学生已完成事实。
- 重复规则数据库约束扩展为一次、每日、工作日和每周指定日期；每周规则要求非空且仅包含 ISO 星期值。

## 2026-08-24

### K12 作业字典

- 新增学科、作业类型、学科作业类型关联、年级和练习来源五组教育字典表，并写入小学至高中固定 seed 数据。
- 学科按语文、数学、英语、物理、化学、生物、历史、地理、政治维护展示色；练习来源统一为校内作业和校外作业。

## 2026-08-24

### 教育附件存储配置

- 统一使用 `STORAGE_BUCKET_NAME` 配置 MinIO 教育附件桶；Compose 初始化容器和应用运行时不再使用容易混淆的旧教育桶变量。
- MinIO 数据改为通过 Compose local/NAS override 挂载宿主机目录，便于迁移到 NAS 上的 Docker 部署。
- 新增 `deploy/docker-compose-middleware.yml`、`docker-compose-dev.yml`、`docker-compose-local.yml` 和 NAS 示例，分离基础设施、开发服务与宿主机路径配置。
- middleware 的 PostgreSQL、Redis 与 MinIO 现统一使用可覆盖的 bind mount；默认持久化到 `deploy/volumes/`，其启动参数和数据路径位于专用 `deploy/.env`，不再混入后端运行时 `.env`。

### 家庭作业创建

- 修复创建家庭作业在数据库已成功写入后，因 PostgreSQL UUID 与 HTTP 响应模型类型不一致而错误返回 500 的问题；作业、提交和批改的 UUID 现统一正确序列化为前端所需的字符串。

### 开发数据整理

- 重置本地开发数据库中的对话、工作区、运行账本、教材处理与学习记录、任务和 LangGraph checkpoint 状态；保留 Sean 与 Henry 的账户、家庭关系、本地登录凭据、模型配置及 LLM Endpoint 鉴权，移除诊断和验收测试账户。

## 2026-08-21

### 家庭对话持久化与历史回放

- 修复家庭模型共享改造后仍读取已删除 `conversation_usages.llm_endpoint_id` 列的问题；家长和学生的模型回复完成后，终态用量持久化与重新打开历史对话不再因此返回 500 或显示通用错误。
- 家庭用量继续保存家庭归属、凭据来源及不含凭据的模型快照，并以公开 `model_key` 标识实际使用模型。

### 家庭共享模型来源

- 家庭创建者现在记录为唯一共享模型管理员，学生模型偏好仅保存公开模型键，不再保存 Endpoint、Base URL 或凭据引用。
- 移除未应用迁移中的重复家庭 Endpoint/默认模型表，并保留家庭用量的非敏感归属与模型快照字段。
- 新增家庭模型 owner、成员上下文和学生偏好数据库 helper，并在家长账户创建时写入 owner。
- 家长继续在既有“模型”页维护唯一模型来源，移除重复的“家庭模型池”页面、Endpoint CRUD 和前端缓存键。
- 学生聊天按共享模型的 `model_key` 加载、显示和保存选择；学生设置页不再提供模型管理，后端也拒绝其写入任何个人模型、Provider 或自定义模型偏好。
- 测试数据重置脚本同步移除已经废弃的家庭 Endpoint 表检查和清理项。
- 迁移 033 兼容测试库中没有任何成员的孤立空家庭，清理该无主记录后再回填家庭模型 owner，避免模型可用性和历史回放因旧数据库未完成迁移而返回 500。

## 2026-08-20

### 后端语音识别

- 聊天输入支持通过受 Cookie 保护的后端 WebSocket 流式转发 16 kHz、16-bit、单声道 PCM 到火山引擎；访问凭据仅从服务端环境变量读取，后端不可用时仍会降级至浏览器语音识别。
- 录音中继续显示实时识别文本和既有动画，控制图标改为停止方块；单次录音最多 60 秒，停止时会发送不足 100 ms 的尾部音频后再结束识别。
- 静音且未识别到文本时会安静结束，不再错误地切换浏览器识别；新增协议、PCM 分包和语音输入边界回归测试。
- 未录音时，后端识别路径以音频线图标区分；实际降级到浏览器识别后保留麦克风图标。
- 增加可选的 Vite 本地 HTTPS 模式，为当前局域网 IPv4 生成忽略的开发证书，使同机通过局域网 IP 访问时也能使用浏览器麦克风权限。
- 对齐火山官方 WebSocket 协议与 token 鉴权示例，并禁用系统代理对上游连接的干扰；上游未授权资源会映射为安全的服务错误码。
- ASR 配置现仅保留官方 token 鉴权实际使用的 App ID、Access Token 和 Cluster ID；首个请求补齐官方 Demo 的中文语言和识别 workflow，浏览器仍按 16 kHz raw PCM 流式上传。

### 家庭模型池设置

- `/settings` 新增仅家长可见的“家庭模型池”二级页，可添加、编辑、启停或删除家庭 LLM Endpoint，并设置或清除默认模型；删除前会明确确认。
- 设置页仅展示 Provider、模型、Base URL 和掩码凭证；编辑时留空会保留原凭证，只有明确选择清除才会移除。每次管理操作都会刷新家长模型池及学生可用模型状态。

### 学生家庭模型选择

- 学生 Flash 会话只展示家长家庭模型池中可用的模型，可切换并保存个人选择；首次进入使用服务端给出的家庭默认，不再把内部模型标识或 Sonnet 5 当作显示模型。
- 家庭模型池为空、加载失败或尚未选定模型时，聊天输入仍可编辑，但发送会被阻止并提供刷新入口；学生不会看到 Endpoint、凭证、Provider 或个人模型管理操作。

### 学生个人模型隔离

- 学生账户现在由后端统一拒绝读取、修改、删除或试用个人 BYOK 配置，也不能使用遗留个人 Endpoint 进行动态模型发现；家长与非家庭账户保持原有能力。
- 新增测试数据重置脚本，必须提供精确目标与明确确认短语，并先核对迁移版本和项目表完整性；任一前提不满足即停止。

### 家庭模型池准入与用量快照

- 学生通过“新建对话”入口时会先解析同家庭可用模型；模型池为空不会创建 Flash 工作区、线程、标题任务或 START 运行记录，已存在的非 Flash 工作区也会先按学生权限拒绝。
- 家庭凭证（包括无 API Key 的本地 Endpoint）沿用非平台额度路径，但用量记录额外保存家庭、Endpoint、凭证来源和 Provider/模型/显示名快照；快照不携带 API Key 或 Endpoint URL，Endpoint 后续改名或删除也不影响历史记录。
- Flash/PTC 运行、终态元数据、账单写入和历史重放统一使用白名单模型来源字段，旧用量行继续兼容空值。

### 家庭模型池运行时解析

- 学生聊天现在只会解析同家庭、已启用的家庭模型 Endpoint：无请求模型时按学生偏好和家庭默认顺序选择；不会读取学生个人模型偏好、BYOK、OAuth 或平台模型。
- 学生未选中可用模型时在创建模型客户端和运行前返回安全的 `no_model_available` 错误；跨家庭或失效的显式家庭模型标识返回不可枚举的拒绝结果。
- 家庭 Endpoint 的解密凭证仅用于创建当次客户端，不进入配置序列化、SSE 或持久化元数据；运行元数据只保留家庭、Endpoint、Provider、模型和显示名快照。Flash/PTC 的辅助角色复用同一家庭客户端，避免回退到个人模型。

### 家庭模型池入口保护

- 学生的家庭模型现在会先于个人 Provider 准入门禁解析，避免已继承家庭 Endpoint 的学生被错误拒绝为“未配置 Provider”；无可用家庭模型时继续返回安全的 `no_model_available`。
- Flash、PTC 独立调用和自动化任务会在创建 workspace、thread 或 START 运行记录前解析模型配置，空家庭模型池不会留下无效运行记录。

### 家庭模型池实施计划

- 确认家庭级 LLM Endpoint 模型池的实施路径：家长统一维护加密凭证，学生仅查看、切换并保存模型偏好；无可用模型时不创建空模型请求。
- 规划家庭默认、学生偏好、失效回退、家长/学生权限、账单归属和历史模型快照的数据库、API、解析器与前端测试边界。

## 2026-08-19

### 学生模型显示与新会话入口

- 保存并展示每轮实际解析到的 LLM 模型，区分逻辑请求模型与平台托管模型，避免学生未配置独立模型时错误显示 Sonnet 5。
- 学生在已有 Flash 工作区内点击侧边栏“新对话”时直接进入空白线程，避免重复等待工作区初始化。

### 聊天会话时间展示

- 聊天顶部现显示会话开始时间，并在用户与 Agent 消息处显示本地化发送时间；复用现有线程详情和消息时间数据，不新增专用 API 或数据库字段。
- 消息时间现同时显示日期和时间，并移动到各自消息内容的顶部，用户消息右对齐、Agent 消息左对齐。

### 学生 Flash 聊天入口

- 修复学生首次进入 `/chat` 创建确定性私有 Flash 空间后仍停留在加载页的问题；根路由完成跳转后会正常渲染既有聊天界面，工作区和线程深链接不会重复创建空间，服务端的资源归属校验保持不变。

### 家庭账户兼容与只读边界

- 修复已有学生成员没有本地登录名时，家庭账户列表因响应校验失败而无法加载的问题；该类成员现显示为“未设置登录名”，不会阻断家长查看整个家庭账户页。
- 家长只读回放现在只返回学生输入和助手正式文本，明确过滤系统消息、推理内容、工具调用与其它内部事件。
- 家庭账户读取在列出空间、查看空间或浏览对话前，会再次核对确定性 Flash 工作区归属学生且处于 `flash` 状态；异常或遗留工作区安全拒绝访问。
- 学生通过深链接打开家庭账户详情时，只显示无权限提示，不发起家长专用的空间或对话读取请求。

### 家庭账户授权边界

- 家长读取子女 Flash 空间和对话前，服务层现在再次核对家长与学生的家庭标识；跨家庭学生不会触发空间创建或历史读取。

### 家庭账户登录信息

- 家庭账户列表现在仅向已授权家长返回子女用户名，便于家长将登录信息交给子女；不会返回密码或其它凭据。

### 设置页家庭账户管理

- `/settings` 新增家长专用“家庭账户”二级页，可创建子女账户、查看私有 Flash 空间状态，并通过深链接打开只读对话记录；页面不提供改名、换绑、删除或发送操作。

## 2026-08-18

### 家庭账户管理设计

- 确认在 `/settings` 下增加家长专用家庭账户页：创建学生账号、查看其确定性 Flash 空间状态，并以只读方式浏览对话记录。
- 明确授权只在后端校验家长与学生是否同属一个家庭，不增加答题、二次密码或其它界面验证；不允许家长改空间名称、换绑空间或写入学生对话。
- 新增家长专用家庭账户读模型：可列出同家庭学生、幂等确保其私有 Flash 空间，并分页查看线程；只读回放仅投影学生和助手文本事件。

## 2026-08-15

### 受管教材 PTC 长程执行

- 修复真实受管教材 PTC 已把候选暂存到 PostgreSQL、但空闲恢复扫描器先于终态归档回调将任务误标为普通中断的问题：暂存记录现在持久保留六分钟归档租约，扫描和最终结算都会让新鲜租约优先；过期暂存统一投影为“等待私有归档”。家长继续运行会续租并只重新校验/归档同一候选；兼容已被旧扫描器一致标记为 `managed_terminal_unprojected` 的暂存，不启动新 root run 或重复消耗模型额度。家庭授权、`education/` 前缀和不暴露暂存字节、对象键、URL、sandbox、模型或凭据的边界不变。
- 修复真实受管教材 PTC 已允许内置章节 worker、却在图构建时丢失 root `WriterGuard`，使子任务不能取得 `task:<id>` checkpoint 写入租约而被拒绝的问题。受管运行现在只在策略明确允许内置 worker 时传递服务端 guard；家长身份、记忆、Vault、MCP、网页、普通工作区和用户自定义 worker 仍不会进入教材加工。
- 修复真实 MinIO 路由中断超过短退避窗口后，已完成的受管教材 PTC 被迫从头重跑并重复消耗模型额度的问题：服务现将通过最终校验的固定候选 bundle 暂存为 attempt 绑定、大小受限的内部 PostgreSQL 传输副本；归档耗尽后家长点击“继续运行”只重新校验并写入同一私有 `education/` 前缀，不启动新 root run 或 PTC。暂存不进入 API、SSE、对象 manifest 或浏览器，不包含对象键、URL、sandbox、模型/provider 信息或凭据；成功归档后删除。
- 修复真实受管教材 PTC 已生成各章概念、却在全书概念索引中重命名、合并或额外生成概念而于最终校验失败的问题：`book-to-skill` 与 `the-knowledge-guy` 现共同提供概念索引的严格 JSON 形状，要求逐字复制每章知识资产的概念 ID、名称和源章节，且禁止重命名、合并、替换或新增概念；服务端仍严格校验、家庭授权与私有 `education/` 归档边界不变。
- 修复受管练习合同只描述“题目”而没有规定 JSON 顶层字段、使 PTC 写出 `exercises` 并在最终候选校验被拒绝的问题：`book-to-skill` 与 `the-knowledge-guy` 现共同规定每章练习必须使用非空 `questions` 数组，包含冻结章节标识、题目位置、同章概念和知识点，并明确禁止 `exercises`、`items` 等替代字段；服务端严格校验、家庭授权与私有 `education/` 归档边界不变。
- 受管教材候选归档因文件缺失而失败时，服务端日志现在仅记录由服务固定合同派生的相对输出文件名，用于区分合同路径不匹配和 sandbox 传输失败；家长 API 仍只返回原有的脱敏可重试错误，绝不返回 sandbox 根路径、对象键、URL、模型内容或凭据。

## 2026-08-14

### 受管教材 PTC 长程执行

- 修复真实受管教材完整资产已生成、但 MinIO 短暂出现路由中断时私有归档单次失败便使整轮 Agent 加工失败的问题：同一服务生成的 `education/` 候选对象写入现在以 5、10、20、40、60 秒有界退避重试，给临时网络恢复约 135 秒窗口；成功后继续同一归档，耗尽后仍安全保留可恢复失败。它不列举、删除、公开或跨家庭写入对象，也不放宽最终校验、发布与权限门槛。
- 修复受管教材 PTC 覆盖审计合同只描述“每章一项”、却未规定 JSON 顶层字段而使 Agent 写出 `coverage`、最终被服务端拒绝的问题：`book-to-skill` 与 `the-knowledge-guy` 现共享明确的 `coverage-audit.json` 模板，强制使用 `chapters`、冻结 ID/哈希与完整 `asset_kinds`，并禁止 `coverage`、`items` 等替代字段。服务端的严格校验、家庭授权与私有 `education/` 归档边界不变。
- 修复受管 PTC 已投影“正在汇总教材资产”后将包推进为 `validating`、但终态回调只接受较早阶段而放弃候选归档的状态机断层：同一活跃 root run 现在可从 `validating` 正常领取最终校验，取消和新 attempt 仍优先阻止归档。
- 修复真实 PostgreSQL 中受管教材进度事件序号查询对 `MAX(sequence)` 使用 `FOR UPDATE` 而被拒绝的问题：事务仍先锁定活跃 attempt/job/package，再无聚合行锁地计算并插入下一个序号；PTC 写入的固定候选路径现在可投影为家长可见的安全里程碑，不存储模型原文、路径或凭据。
- 修复受管 PTC 教材候选中的知识关系字段合同歧义：两份 staged Skill 合同现明确规定章节和全书关系对象必须使用 `from_concept_id` / `to_concept_id`，禁止含糊的 `from` / `to`。服务端继续严格拒绝未知概念引用，失败候选不会归档、发布或暴露给学生。
- 修复受管教材 PTC 在持续输出模型或工具流片段时只在“流静默”分支刷新心跳、使家长运行详情误显示旧心跳的问题：现在同一 root run 即使始终有流量也按 15 秒持久更新 attempt 心跳；取消、恢复、家庭授权、私有 `education/` 资产和脱敏进度边界不变。
- 修复真实 PTC 已写出受管候选资产、但模型没有额外输出 `EDUCATION_PROGRESS` 时家长只能看到“准备中”的问题：服务现从已成功写入的固定 v2 候选路径派生章节知识表示、工具包、练习、概念索引、覆盖审计与汇总里程碑。它不读取候选正文、不接受任意路径、不规定 PTC 的处理顺序；重复和未知写入不会生成事件。异步自主事件也按单调阶段秩序更新教学包，后写的覆盖审计不会将已到达教学生成的状态倒退。
- 教材教学包运行详情现在显示 PTC 自主上报的当前细粒度里程碑、运行时长、最近持久心跳和“正在等待 Agent/模型响应”状态；浏览器置于后台仍会每 5 秒刷新运行投影。已完成任务只标记服务已验证的事件，未完成任务保持“Agent 已报告”，避免把模型自述当作完成事实。
- 家长审阅状态下新增“知识资产”标签：可查看服务校验后的覆盖审计、概念计数、各章知识表示、工具包和练习内容。界面只使用安全摘要和按需内容接口，不渲染对象键、`education/` 路径、sandbox 路径、模型或 Provider 信息。
- Mock 浏览器回归现覆盖教学包进入审阅后的知识资产读取与工具包查看，再继续发布、分配、学生答题和家长只读记录查看；该覆盖仅验证前端 API 契约，真实 MinIO 与 FastAPI 流程仍单独验收。

- 家长现可在同家庭授权下读取已进入审阅状态的 v2 教学资产摘要，并按章节查看知识表示、工具包或练习内容。服务根据数据库中的安全 manifest 与冻结章节派生固定私有对象路径，读取时再次核对字节数和 SHA-256；API 不返回 `education/` 路径、对象键、URL、sandbox、Provider 或模型原文。教学任务事件同时保留白名单 `asset_kind`，供单一运行详情展示逐章资产进度。
- 受管教材加工现在由一个可持续 24 小时的 PTC 根运行自主读取 staged 的 `book-to-skill` 与 `the-knowledge-guy`，并仅允许继承相同受限策略的内置章节 worker；服务不再注入或编排两项 Skill 的执行顺序。阶段事件可安全投影规划、章节映射、概念关联、覆盖审计、练习、教学、汇总和校验，以及对应章节/资产种类；浏览器断开后的无连接回收同样使用教材专属的 24 小时窗口。两份 staged contract 现共享严格 JSON 字段、转义和冻结标识逐字匹配要求，避免长程任务在最终校验才因候选格式失败。
- 教学包持久化新增 v2 `asset_manifest` 安全摘要和资产种类字段；完成的同一根运行才可将摘要与候选包原子绑定。受管进度事件扩展为 PTC 自主的规划、章节映射、概念关联、覆盖审计、练习、教学、汇总与校验里程碑，服务以本地中文模板投影，丢弃模型自由文本、路径和自报统计。
- 受管教材任务现在会 stage `book-to-skill` 与 `the-knowledge-guy` 的完整静态 Skill 资料，而非仅两份短契约；执行仍禁止脚本、网络、MCP、Vault 与普通工作区写入。候选写入收紧为完整资产合同的固定 v2 路径，服务逐项直接回收并以服务生成的 `education/` 路径归档，归档 manifest 不复制 sandbox 路径、对象键或 URL。
- 新增受管教材完整知识资产的 v2 服务端校验合同：全书概念索引、覆盖审计、每章知识表示、工具包、练习与教学包均必须由冻结章节标识和 SHA-256 对齐，缺项、未知路径、未完成覆盖、概念或知识点错配会在归档前拒绝；校验结果仅保留大小、散列、概念数和章节关联等安全摘要，不包含对象键、存储路径、URL 或 sandbox 路径。
- 明确下一阶段教材加工将从单一教学包 JSON 升级为受管的完整知识资产管线：在保留本地 PDF 提取、家庭授权、长程 PTC 账本和私有 `education/` 归档边界下，增加章节知识表示、工具包、覆盖审计、概念索引、练习集与面向中国学生的教学材料；同时建立可执行评审规范，禁止向浏览器暴露对象键、sandbox 路径、模型原文或凭据。
- 新增完整资产管线的逐步 TDD 实施计划：按候选校验、固定私有归档、PTC 自主 Skill/子任务调度、家长审阅 API、界面和真实服务验收分解；服务只约束 sandbox、检查点、进度投影和最终校验，不把教材处理重新固化为两阶段任务编排。
- 教材长程任务将把 PTC 自主声明的章节/资产里程碑投影为细粒度、安全进度，并展示最近持久心跳与等待状态；受管教材默认允许运行至 24 小时且可取消、恢复，浏览器断开不会被视为任务失败。
- 修复家长停留在教学页时，受管教学任务已完成却仍显示旧“正在加工”缓存的问题：教学任务轮询首次进入完成、失败或取消终态后会失效教育查询并刷新当前教材详情；以终态转换守卫避免轮询重复触发刷新。家长随即可看到已生成的教学材料、题集和发布入口，家庭授权、私有 `education/` 资产及浏览器不暴露 storage key 的边界不变。
- 修复真实教学包候选的题目知识点与本章知识点列表不一致、在最终归档才失败的问题：两份受管教材契约及受管模式提示现要求题目逐字复用本章 `knowledge_points` 值，固定候选文件的 `Write` 也在 JSON 解析后前置拒绝不匹配引用，给 Agent 在同一根运行中修正；最终服务端的完整关系校验继续保留，未放宽审阅发布门槛。
- 修复真实教材教学包已完成 PTC 生成却在最终校验中错误使用未含派生哈希的数据库章节投影、从而一律报“冻结内容哈希无效”的问题：最终化现复用 staging 的 `freeze_teaching_input()` 从不可变 Markdown 重建哈希后再验证候选；不新增可变数据库哈希、不放宽章节覆盖校验，也不改写现有教材或 `education/` 对象。
- 修复真实教材教学包因中文正文内未转义双引号写出非法 JSON、直到最终归档才失败的问题：受管 `Write` 现在仅在固定候选文件路径先解析严格 JSON 对象，拒绝内容不会写入 sandbox；`the-knowledge-guy` 受管契约同时明确要求转义内嵌双引号并在收到 JSON 错误后原地修正。服务端最终的章节覆盖、哈希和题目校验及 `education/` 私有归档边界不变。
- 修复 Docker 受管任务根目录由服务创建后、受限 Bash 无权新建 `work/knowledge-skill` 而导致 Agent 重试的问题：冻结输入现在仅通过既有 sandbox 字节上传 API 预建固定知识中间目录和固定输出目录的空标记；模型仍不能指定其他目录、枚举 sandbox 或访问 MinIO，正式资产仍只由服务端校验后写入 `education/`。
- 受管教材根运行不再被原先面向短聊天的 48 步图递归上限截断，而是遵从部署的 PTC 递归预算；运行仍使用同一持久化根账本、心跳、取消与恢复机制。受管模式现明确指出 sandbox 内两份 staged contract 的实际路径，并仅允许在固定 job 根目录运行 `sha256sum inputs/manifest.json`，使 `book-to-skill` 能生成契约要求的输入清单校验值，而不会尝试绝对路径、Python 辅助程序或普通 shell 能力。
- 修复部分 OpenAI 兼容模型将累计或异常 usage 回报为百万级上下文 token、使 PTC 压缩中间件反复总结而教材加工停在“准备中”的问题：压缩预算现在每轮与本地 token 估算交叉校验，异常回报会安全退回本地值；正常范围的 provider usage 仍用于精确控制。该保护同时覆盖同步与异步模型调用路径，不改变模型凭据、家庭权限或 `education/` 私有资产边界。
- 修复受管教材教学包任务把两份完整的交互式 Skill 文档同时注入 PTC 上下文、并复制到 sandbox，导致模型反复读取普通转换/问答流程且频繁触发上下文压缩的问题：运行时仍从当前 worktree 的 `book-to-skill` 与 `the-knowledge-guy` 提取各自唯一的 `Managed textbook mode` 段落并按顺序执行，但 sandbox 仅保留两份固定 managed contract，不再暴露完整交互文档。
- 受管根运行现在在等待模型或 SSE 输出期间每 15 秒刷新同一 attempt/root run 的持久化心跳；更新受最新 attempt、运行状态和根运行标识共同约束，取消或新 attempt 不会被旧 worker 重新标为存活。家长运行详情可据此区分仍在执行的长程加工与失联尝试，且不会接收原始模型文本、对象键、sandbox 路径或凭据。

### 平台统一模型额度

- 新增部署级平台模型档案解析器：仅由非秘密的来源账号与模型环境变量启用，运行时通过既有加密 BYOK 与自定义模型解析器构造客户端；缺少配置、来源账号、启用凭据或模型时均安全失败，不读取其他用户凭据，也不将 Key、Base URL 或来源账号写入日志。
- 自定义模型的凭据解析日志不再记录 Base URL，避免平台档案或普通 BYOK 使用时把私有服务端点带入应用日志。
- 系统目录模型在个人 OAuth 与 BYOK 均不可用时，现优先使用已启用的平台档案；该档案会让无 reasoning effort 的受管教材任务也在启动前获得可预检的模型客户端，未配置档案时仍保留原有环境变量回退和惰性行为。
- `.env.example` 现记录平台档案的两个非秘密变量；当前本地服务配置为已批准的 `silicon / deepseek-ai/DeepSeek-V4-Flash`，真实数据库解析和最小模型请求均已验证，但运行时配置文件和任何凭据均不进入版本控制。
- 更正开发环境 MinIO 指引：`192.168.3.164:9000` 是 S3 API，`9001` 仅为控制台；家庭教材真实上传必须使用 API 端口，并继续限制在私有 `education/` 前缀。
- 修复平台档案只解析主模型、却让 compaction/fetch 等角色回退到 `agent_config.yaml` 默认供应商的问题：当且仅当部署档案已启用时，缺少独立角色凭据的角色使用主档案 client 的隔离副本；传统平台回退仍保持原有按名称解析行为。

## 2026-08-13

### 受管教材 PTC 加工与恢复

- 修复真实受管教学加工在 sandbox 已启动后调用不存在的批量上传接口而中断的问题：冻结章节和两份内置 Skill 契约现在逐项通过 PTC sandbox 的受限字节上传 API 写入固定教材任务根目录；任一写入被拒绝会安全失败，不调度根运行，也不暴露存储键或 sandbox 路径。
- 修复受管教材根运行向 UUID 类型的持久化 `request_key` 写入合成文本而无法入账的问题：每次 service-owned attempt 以新根运行 UUID 作为去重键，服务任务类别仍仅保留在内部 metadata，家长接口继续只显示脱敏阶段投影。
- 修复受管教材根运行使用未纳入既有数据库约束的自定义查询类型而无法持久化的问题：服务托管任务现使用既有 `system` 类型，教材加工类别和任务标识仍只保留在内部 metadata，不改变家长可见数据边界。
- 修复受管教材加工错误地绕开家长模型凭据解析、直接依赖全局平台密钥的问题：启动前仅在服务进程内解析并预检家长的模型 client，图执行仍不携带家长身份、Vault、记忆或普通工作区能力；无可用模型时任务以可重试的安全失败投影返回，避免恢复接口返回未处理 500。
- 受管教材教学包在家长未连接 OAuth、未配置 BYOK 且服务端没有默认模型时，现在将模型预检失败与 sandbox 故障区分为安全的可重试状态；运行详情提供“配置模型服务”入口，不泄露 provider、密钥、对象存储或 sandbox 诊断。

- Mock 浏览器回归现在覆盖教学包的受管长程加工投影、自动打开的只读运行详情、审阅后发布、学生答题与家长记录查看；测试路由限定为 mock API 源站，避免页面重载被错误替换为 JSON。

- 教材详情现以单一阶段面板呈现“资料 → 内容提取 → 教学包 → 审阅 → 发布 → 分配”：内容审阅完成后家长可启动教学包；运行中显示真实安全投影的阶段和章节数，失败或取消时可继续运行。运行详情使用只读弹窗显示阶段事件和尝试次数，不提供聊天输入、文件浏览或 PTC 原始输出。

- 家长教材 API 现提供受管教学包的创建、状态读取、取消和恢复控制；创建时会在启动 PTC 根运行前固定内容 manifest、两份内置 Skill 正文和固定服务指令的 SHA-256。浏览器只能获取阶段、章节进度、脱敏事件、尝试/root run 标识与允许操作，不能获取对象键、MinIO 地址、sandbox 路径、原始 SSE 或模型文本。
- 教材详情的教学包摘要新增安全的任务标识和状态，刷新后仍可继续查看运行详情；待审教学包的教学材料和题集从独立教学包快照读取，内容提取版本与教学资产保持分层，历史 `legacy-local-v1` 包仍兼容发布与学生学习。

- 教学包任务现以服务拥有的隐藏 PTC 根运行执行 `book-to-skill` 与 `the-knowledge-guy`：根运行先进入既有 RunCoordinator 账本，再由 LocalRunExecutor、检查点和 Redis SSE 驱动；不再借用聊天 HTTP 入口或伪造子 Agent 任务。
- 受管 sandbox 仅创建本次教材任务根目录，注入两份内置 Skill 契约与冻结 Markdown；禁止 MCP、Vault、网页、预览、用户记忆、普通工作区同步、用户 Skill 和子代理。Skill 正文只从当前服务端工作树的受控内置目录加载，sandbox 内副本仅供受管运行使用。
- 教学包、任务与 attempt 的状态现按 `queued → preparing → building_skill / generating_teaching → validating → review` 原子投影；候选输出只在验证阶段从固定路径回收、校验、归档到私有 `education/` 前缀后才写入审阅数据。取消会先持久化产品状态，阻止晚到完成回调发布候选包。
- 失败、取消、sandbox 初始化失败和 worker 丢失均保留脱敏错误并允许使用同一冻结输入创建新的 attempt/root run。恢复扫描器会投影失联根运行，并在空闲扫描时对账已终态但尚未投影的任务，不读取死 sandbox 或对象存储。
- 服务拥有的教材加工 workspace/thread 已从普通工作区、线程列表、生命周期订阅、详情、消息和共享入口隐藏；家长只能经教材 API 查看安全的阶段投影，不能获取 sandbox 路径、对象键或凭据。

### 家庭教材教学包持久化

- 新增冻结内容版本之下可重试的教学包、任务、受管 PTC 根运行尝试、脱敏阶段事件、教学章节和题集关系模型；每次尝试保留根运行标识与线性重试链，不伪造子 Agent 任务。
- 已有教材章节、教学材料、题集和发布记录在迁移时回填为兼容的 `legacy-local-v1` 教学包，发布快照新增教学包引用而不删除既有教材或学习记录。
- 教材详情只返回同一内容版本下的教学包状态和章节/题目计数，不返回对象存储键；纯内容版本已可在后续加工阶段省略旧教学字段。

### 家庭教材内容与教学包分层

- 本地 PDF 提取器现只生成冻结来源、页码映射和章节 Markdown，并以内容 bundle 写入 `education/`；不再在提取阶段生成教学材料、默认题集或教学对象路径。
- 发布接口要求家长选择同一内容版本且已审阅、完整覆盖章节与题集的教学包；发布快照同时冻结内容版本与教学包，学生学习、知识检查、学习对话上下文和家长记录均从该教学包读取。
- 兼容迁移保留历史题目 UUID，并将学习答案外键安全转接至教学包题集，因此不会删除或改写现有学生答题证据。

### 受管教材技能契约

- `book-to-skill` 与 `the-knowledge-guy` 新增服务端触发的 `--managed-textbook` 非交互模式：只读取冻结的章节 Markdown 与 manifest，在固定 job 根目录生成知识中间表示和单一候选教学包。
- 该模式不读取原始二进制资料、MinIO、普通工作区、用户记忆或其他路径，不启动自由问答、课程或 HTML artifact；逐章仅输出可投影为持久化事件的 `EDUCATION_PROGRESS`。
- 两项 Skill 共享教学包 schema，要求保留内容章节标识与哈希、中文教学材料和可自动判定题集；正式资产仍须由服务端校验并写入私有 `education/` 前缀。

### 教学包受控资产边界

- 教育服务新增受管 sandbox 输入注入：只上传冻结章节 Markdown 和不含对象键、URL、凭据的 manifest 到固定任务目录；候选输出只能从固定 `teaching-package.json` 路径回收，不枚举 sandbox 文件。
- 服务端严格校验 Agent 候选的章节覆盖、内容哈希、文本边界、知识点关系、题目位置、选项数量和正确答案，再生成私有 `education/` 教学包归档路径；模型不能影响对象名或写入其他资料。

### 家庭教材 PTC 教学加工设计

- 明确将 PDF 内容提取与面向中国学生的教学加工拆为可独立版本化的阶段：本地提取器保留为当前默认实现并可在未来替换为 Datalab；冻结内容版本可被重复用于教学包生成而无需重新提取。
- 批准以受管 PTC 长程任务运行 `book-to-skill` 与 `the-knowledge-guy` 的双阶段教学加工。教材详情将以单一阶段面板和运行详情抽屉投影 PTC 账本、检查点、SSE、取消和恢复链，不新增可自由追问的教材聊天界面。
- 受管教材尝试复用隐藏 PTC thread 的根运行账本，而不是人为嵌套一个无业务价值的子 Agent `task_run`；继续保留现有的跨 worker 检查点、SSE、取消和恢复语义。
- 正式教材资产继续只由服务端写入私有 `education/` 前缀；受管 sandbox 只接收本次任务冻结内容的临时工作副本并回传候选输出，不取得 MinIO 凭据、storage key 或其他家庭资料。

### 家庭教材真实流程修复

- 家长新建教材后现在会直接进入该教材详情；无版本草稿首屏明确显示上传或选择资料、创建加工任务，以及后续执行加工、审阅、发布和分配的连续流程，避免真实服务中只看见教材名称而无法继续操作。
- 修复仅调整前端路由与草稿状态渲染，继续使用既有的受限上传、家庭授权、加工和 `education/` 私有存储边界，不向客户端暴露对象存储键。
- 修复已发布教材详情读取已删除账户表导致的服务端 500：分配摘要改从同一家庭的学生成员关系读取显示名，保留学生角色和家庭范围约束，使家长能在发布后继续分配并查看学习记录。

### 家庭教材学习闭环计划

- 以已批准的家庭教材讨论记录重新审计首期垂直切片，明确候选来源选择、家长内容审阅、移动端章节学习面板、失败反馈和双角色端到端验收仍需收敛；实施计划按测试先行和原子提交推进，未扩展至 OCR、Datalab、富编辑、开放题判分、打印或学习计划等延期能力。
- 家长现在可读取本家庭已上传教材资料的安全候选列表，用于后续显式组合加工；列表不暴露对象存储键或签名地址，学生访问会被服务端拒绝。
- 家长教材详情现在使用严格的版本审阅响应，只返回冻结来源的安全元数据、章节页码映射、提取正文、教学材料、题集与分配摘要；对象存储键无法通过详情 API 泄露。
- 教材详情页现在可多选本家庭已上传资料，并可在同一加工任务中补充上传新文件；提交会显式去重来源标识，失败时保留选择并提供错误提示。家长可按概览、内容、教学和学生分栏审阅冻结来源、页码范围、提取正文、教学材料、题目及学习记录，来源文件仅经受控临时下载链接打开。
- 学生教材阅读器在移动端以正文为中心，目录与知识检查通过独立的可访问面板按需打开；宽屏继续使用目录、正文、知识检查三栏布局，学习进度和冻结答题行为不变。
- 新增家长创建教材、选择候选来源、加工、发布和分配，学生在移动端完成知识检查，再由家长只读查看学习记录的浏览器闭环验收；覆盖两种角色均不显示越权写操作。

### 家庭教材创建与工作流响应修复

- 将教材创建、加工、发布、分配、学习进度和答题接口的持久化 UUID 标识建模为 UUID，令 FastAPI 稳定序列化为前端既有的 JSON 字符串，修复记录已写入但响应校验返回 500、界面看似未创建的问题。
- 增加真实数据库 UUID 返回值的 API 回归覆盖，并将旧测试夹具统一为有效 UUID，防止教材后续工作流重复出现同类响应错误。
- 中文或同名教材的内部存储 slug 现在附带唯一后缀，避免它们被规整成同一个 `textbook` 后触发家庭范围的唯一约束冲突。

## 2026-08-12

### 家庭教材学习架构与实施计划

- 将家庭教材讨论记录提升为已批准的架构决策，明确家庭复用教材库、可恢复对象包、版本冻结发布、学生分配、学习证据及家长只读边界。
- 新增可执行的分阶段实施计划，限定首期本地加工、确定性章节材料和自动判定客观题；Datalab、开放题判分、Markdown 编辑、学习计划和受控学习对话保留为后续适配能力。

### 家庭教材版本与本地加工

- 新增家庭教材、候选版本、冻结来源、可租约领取的加工任务、章节/题集、发布快照、学生分配和学习证据的关系模型；已发布快照与学生记录均不被后续版本覆盖。
- 首期本地加工器会显式领取家长启动的任务，生成可审阅的确定性章节、学习材料和自动判定题，并在 `education/` 前缀写入含 `README.md`、`manifest.json`、来源副本及章节材料的可恢复对象包。
- 加工失败会保留任务尝试与错误并将候选版本标记为失败，供后续 PTC/Datalab 适配器按相同的持久化契约重试；上传资料不会隐式加入已冻结任务。

### 家庭教材管理与学习 API

- 新增家长教材目录、候选版本审阅、显式执行/发布本地加工、发布快照分配和学生学习记录只读接口；所有教材发布与分配均由服务端再次校验家庭家长身份。
- 学生接口仅返回本人被分配的已发布章节和冻结题集，并只允许写入自己的阅读进度与答案；客观题在服务端按发布题集自动判定，重复作答保留首个不可变证据。
- 家长无法通过学生学习接口写入进度、答案或对话，学生也不能查看候选版本、来源、加工错误或其它成员记录。

### 家庭教材阅读器与受控学习问答

- 新增家长教材库、版本详情和学生 DeepWiki 式稳定章节阅读器；家长可上传、显式执行或重试本地加工、审阅发布并分配学生，学生仅可浏览自己的已发布快照、完成确定性知识检查和章节问答。
- 文本层 PDF 现在由本地 `pypdf` 适配器按稳定页段生成候选章节；扫描件或不受支持来源保留为确定性导读。可恢复对象包在 README 与 manifest 中记录 `book-to-skill`、`the-knowledge-guy` 作为未来 PTC 教学增强基础，当前不额外启动教育运行时或 PTC worker。
- 每个学生 assignment 懒创建并持久绑定唯一私有 Flash learning space。聊天请求必须携带该 assignment 和当前已发布章节，服务端注入冻结材料并拒绝将普通消息发送到该学习 thread。
- 家长记录视图新增 assignment 范围的学生/学习助手原文对话只读投影；没有家长发送、编辑、删除或以家长身份重放学生聊天的接口。
- 本地教材加工领取增加 15 分钟持久化租约。失败任务或租约过期的处理中任务均可由本家庭家长显式重新入队，继续复用既有冻结来源与重试审计。
## 2026-08-09

### PTC 重连流恢复

- PTC 的 Redis 事件流在浏览器读取连接中断后，重连路径现在会保留原运行标识与游标，并复用既有的最多五次退避重连；重试内部的再次断开会回到同一受限重试循环，不再直接向用户显示“Reconnection stream disconnected”。
- 增加前端回归测试，覆盖已存活运行的首个重连读取失败后继续附着同一运行并渲染后续事件，保留家长/学生权限、Flash、PTC、自动化与 Skills 的既有边界。

### 本地 Sandbox 镜像构建

- Docker Desktop 的 HTTP 代理到 `ports.ubuntu.com` 的上游连接不稳定时，sandbox 镜像构建改用已验证可达的 USTC Ubuntu Ports 镜像，仍使用签名仓库元数据，并保留强制重新获取索引、关闭 HTTP 请求管线与 10 次 APT 重试，避免 `fonts-noto-cjk` 等依赖下载失败导致首次工作区预置失败。

### 工作区创建存活保护

- 本地 sandbox 镜像首次构建等慢速预置尚未生成 sandbox 标识时，周期性回收会识别同一进程中的创建所有者，不再把仍在执行的 `creating` 工作区提前回收为 `stopped`；跨进程或已中断的无 sandbox 创建仍按原条件回收。

### 工作区创建取消清理

- 首次 sandbox 预置若因客户端断开或服务优雅关闭而被取消，会在保留取消语义的同时清理部分会话，并以条件更新将尚无 sandbox 标识的 `creating` 记录转为可重试的 `stopped`。
- 条件更新不会降级已经写入 sandbox 标识的工作区；新增数据库和生命周期回归测试，防止创建过程再次永久卡在 `creating`。

### 工作区创建状态恢复

- 对因进程中断而停留在 `creating` 且尚未写入 sandbox 标识的工作区，新增基于数据库条件更新的过期回收；存活创建流程不会被并发请求抢占。
- 工作区启动、会话获取和周期性清理均会将已回收记录送入既有启动流程，并为无 sandbox 的记录重新创建运行环境，避免教育测试工作区长期卡在创建状态。
- 新增 API、生命周期管理器和数据库层回归测试，覆盖过期创建回收、无 sandbox 重建及周期性自愈。

### 原生图书学习 Skills 集成

- 集成 `book-to-skill` 与 `the-knowledge-guy` 为项目原生 PTC Skills；宿主源码保留在项目 `skills/`，PTC sandbox 中生成的图书知识写入 `.agents/skills/` 并可被运行时发现。
- `/api/v1/skills?mode=ptc` 与移动端斜杠菜单均可使用这两个命令；`mode=flash` 明确不返回它们，学生 Flash 会话不会获得文件系统、sandbox 或子 Agent 依赖的能力。
- PDF/EPUB 提取依赖仍只在技能的按需隔离环境中安装，未加入平台运行时依赖。

### 通用自动化保护

- 金融清理明确保留通用自动化的 `cron` 与 `once` 调度、执行、持久化、API 和前端入口；仅退役金融价格触发变体。
- 新增路由和调度合约回归测试，防止后续金融残留清理移除创建、暂停、恢复、手动触发或执行历史能力。

### 金融配置与回归残留清理

- 移除 EDGAR、`exchange-calendars` 依赖、FMP/Alpha Vantage 环境变量、金融日志项、工作流市场字段以及通用搜索中遗留的金融分类；默认运行时、示例和外部检索能力保持领域无关。
- 删除废弃行情回归测试包，并将平台密钥、Daytona 探针、MCP 和前端聊天测试夹具改为中性命名；Daytona 实测仅在显式配置通用 HTTPS 探针时运行，不再依赖金融服务。
- 补充通用 Agent 边界测试，覆盖退役配置、工作流合约、依赖锁、金融测试源码和工具提供方分类，避免金融能力重新进入默认产品面。

### 教育移动端 HTTP 提交兼容性

- 学生作业提交复用聊天已验证的 UUID v4 请求键回退，在 HTTP + FRPC 等不提供 `crypto.randomUUID()` 的浏览器中仍可提交，并在失败重试时保留同一幂等键。

### 学生权限回归修复

- 学生 Flash workspace 校验仅在确认学生角色后读取工作区，恢复家长热会话的无数据库查询快路径；单元测试的默认身份显式为非家庭成员，生产环境继续在成员查询异常时拒绝越权请求。
- 移除用户 API 中金融能力清理后遗留的未使用导入，恢复完整 Ruff 检查通过。

### 教育附件与 MinIO 私有存储

- 新增教育附件元数据、私有上传和按家庭成员范围签发的短时下载链接；上传响应不暴露存储键或持久化下载地址。
- 附件只接受受限的 PDF、JPEG、PNG、WebP 格式与大小，并使用不可控的 `education/<household>/<asset>` 对象键；元数据写入失败时仅回滚本次新上传对象。
- 增加可选的本地 MinIO Compose Profile 与幂等初始化脚本，只在桶缺失时创建专用教育桶；默认不访问远端 MinIO，也不枚举或改动其它对象。

### 家庭作业工作流

- 新增家庭作业规则、按家庭时区物化的任务实例、任务材料、不可变的学生提交序列和纯文本家长反馈记录。
- 家长可创建、取消任务或停止后续重复规则；学生只能提交分配给自己的任务，重复请求通过每任务幂等键复用同一提交。
- 状态机限定为 `open -> submitted -> revision_requested -> submitted -> completed`，历史任务、提交和反馈在规则停止后保留。

### 家庭教育界面

- 新增响应式“学习”入口，家长可从家庭学生列表创建或取消作业并给出纯文本反馈；学生可提交、根据反馈重新提交并添加受限附件。
- 前端通过 React Query 访问 FastAPI 教育 API，复用现有 Button、Dialog、Input、Textarea、Tooltip 和 Quiet Workspace 设计令牌，不引入 Supabase 或旧家庭学习组件。
- 提交附件控件补充可访问标签，完成状态改用已声明的语义颜色令牌；新增家长创建/反馈与学生附件重交的 Vitest、Playwright 双角色回归覆盖。

### 学生 Agent 权限与平台收口

- 学生账户按需获得私有 Flash workspace；服务端拒绝其创建或进入 PTC sandbox，以及 Vault、MCP、自定义 sandbox 配置和自动化 API。家长与学生线程仍按 workspace 所有者隔离。
- 前端学生会话自动解析到 Flash workspace，隐藏自动化和设置入口，并跳过通用 PTC 配置引导；后端限制仍为最终授权依据。
- 清理遗留的 MarketView 监控、`data_client` 刷新标记、金融缓存示例、集成测试清理钩子和 Supabase 运行说明，文档改为本地 Cookie 认证与家庭教育模块表述。

### 本地账户与家庭成员认证

- 新增基于 PostgreSQL 的本地家长注册、家长创建学生账户和家庭成员关系，使用 Argon2id 保存密码哈希。
- 以仅保存摘要的随机 HttpOnly 会话 Cookie 替换浏览器端 Supabase/JWT 会话，支持会话轮换、注销和未登录接口拒绝。
- 保留 `users.user_id` 作为长期身份，并将认证与家庭时区校验纳入 FastAPI 请求边界。

## 2026-08-08

### 公网 HTTP 聊天兼容性

- Flash 首条消息的幂等请求键在浏览器未提供 `crypto.randomUUID()` 时改用 UUID v4 回退生成，修复通过 HTTP + FRPC 访问时线程已创建但聊天请求未发出的卡死问题。

### 金融运行时残留与开发环境收口

- 删除孤立的市场洞察数据库/模型、市场交易时间工具、用户模型中的价格提醒、观察列表与持仓合约，以及旧 Ginlix sandbox 凭证通道；通用用户偏好、Vault、workspace、PTC、Flash 与 MCP 机制继续保留。
- sandbox 默认依赖、Daytona/Docker 镜像和锁文件不再安装或提及 `yfinance`、Polymarket、`mplfinance`、`peewee` 等金融专属组件；相应的 SEC、行情回归测试与数据夹具一并退役。
- 将 README、配置向导、默认提示词、来源溯源说明及中日文公开说明改为通用 Agent 平台表述；溯源哈希稳定性测试改用 WebFetch/WebSearch 与教育研究示例，继续覆盖去重、超大正文和密钥脱敏。
- 删除 E2E 会话回放中遗留的大型证券研究夹具，替换为最小化的中性教育研究 SSE 序列，保留主 Agent 与子 Agent 转向事件不会产生空消息的回归覆盖。
- 前端默认开发服务器统一为 `0.0.0.0:5177` 且启用严格端口，Docker Compose 同步映射 `5177`；移除 Vite 中已删除的 `lightweight-charts` 分包引用，避免与其它 LangAlpha 实例冲突并支持局域网访问。

### 金融数据服务与协议移除

- 删除 `data_client`、`market_protocol`、金融 MCP Server、SEC 与行情工具，以及其单元和集成测试；默认安装、sandbox 同步和 MCP 配置不再包含 FMP、Yahoo Finance、期权或实时行情依赖。
- 删除服务端的行情、新闻、SEC、投资组合、观察列表、图表标注、财经洞察及行情 WebSocket 路由与缓存实现，保留通用搜索、抓取、工作区、SSE、自动化和 MCP 扩展能力。
- PTC 与 Flash 请求链不再注入图表选择上下文；通用 Skills、工作流案例、电子表格规范和 X 内容研究说明全部改为领域无关表达。
- 将特性开关和 Skills 注册测试从已退役的市场观察、`ui-design` 能力迁移到仍受支持的通用能力，并增加保留 Skills 不得重新引入金融语义的边界测试。

### Agent 运行时金融资料与 Skills 清理

- 移除 PTC 的数据库虚拟用户资料文件系统，不再向 sandbox 暴露投资组合、观察列表和风险偏好 JSON；对应的文件 API、原子差异写入、行情观察中间件及其测试一并删除。
- Agent 图构建和动态提示仅保留昵称、时区、区域及通用 Agent 偏好，不再查询投资组合或观察列表计数，也不再在记忆、Flash 协作、计划模式和数据准备提示中引导金融分析。
- 删除金融专属的内置 Skills、图表标注、用户画像、金融引导和行情观察工具；保留 Skills 框架、通用报告和内联组件能力，并将后两者改为领域无关的简洁指导。

### 通用用户偏好边界

- 用户偏好 API、Pydantic 合约和数据库读写统一为 `agent_preference`、`other_preference` 两个通用 JSONB 字段，与初始 schema 保持一致。
- 移除风险偏好和投资偏好字段；请求携带已退役的金融偏好字段将返回校验错误，避免后续调用重新引入无效列查询。
- 修复 `/api/v1/users/me` 在新建数据库上因查询不存在的金融偏好列而返回 500 的问题。

### 通用工作区前端发布收尾

- 清理中英文翻译目录中仅属于行情、观察列表、投资组合、证券文件、价格提醒和金融自动化的残留文案；自动化模板统一为工作区日常任务。
- 删除不再被代码调用的 `lightweight-charts`、`react-grid-layout`、`recharts` 依赖，以及 E2E 中对应的市场行情、新闻、投资组合、观察列表和财报日历 mock。
- 移除旧图表库的全局 CSS、修正前端开发说明与目录文档中遗留的 MarketView 描述，并为依赖和 E2E mock 加入防回归边界测试。
- 新增通用工作区 Playwright 用例，验证桌面和移动视口不再出现市场、投资组合或观察列表入口，且可分别进入对话和自动化页面。

### 金融前端图表与展示清理

- 删除行情中心、K 线与报价库、TradingView 小部件、证券文件查看器、金融 Dashboard 小部件、行情监控和图表标注等前端实现及其测试。
- 聊天会话保留通用 Agent 产物、文件附件、自动化、Skills、MCP、工作区和 SSE 能力，移除只服务于金融行情、投资组合和用户投资偏好的状态、类型及展示分支。
- 登录页、加载页、法律与隐私文案改为通用工作区表达，移除指数走势图、财经行情背景及第三方金融数据声明。
- 自动化模板替换为工作区每日摘要、每周复盘和一次性任务；移除价格触发配置与界面。
- 新增前端金融表面和依赖边界测试，并修复 Node 25 测试环境中未注入 `localStorage` 导致的跨套件失败。

## 2026-08-07

### 通用工作区仪表盘

- `/dashboard` 改为通用工作区概览，提供对话、自动化和工作区文件三个可用入口，并展示近期会话与工作区状态。
- 工作区文件入口会直接打开对应 Agent 工作区的文件面板；不再依赖金融 Dashboard 的经典/自定义布局和偏好设置。
- 将仍被聊天、设置和引导流程使用的确认对话框、上下文预览、OAuth 和用户 API 迁移至通用路径，避免后续删除金融 Dashboard 时破坏应用壳层。

### 金融前端公开入口移除

- 主导航移除行情中心，公开路由不再加载 `/market` 与 `/news/:id`；旧地址统一回落至通用工作区仪表盘。
- 删除对应的侧栏中英文文案，并为 Dashboard、Chat、Automations 与 Settings 的通用路由建立回归测试。

### 金融运行时与自动化移除

- 服务端不再注册市场数据、K 线、SEC、财经新闻、经济日历、投资组合、观察列表、财经洞察、图表标注和行情 WebSocket 路由。
- 启动与关闭生命周期移除市场数据订阅、价格监控、财经洞察和财经新闻刷新服务，保留通用自动化调度、Vault、MCP、SSE 与工作区服务。
- 初始 PostgreSQL schema 删除 watchlist、portfolio、market insights、图表标注相关表和投资偏好字段；相关历史 migration 改为保持 revision 连续性的空迁移。
- 自动化仅支持 `cron` 与 `once`，移除价格触发的请求模型、Agent 工具参数、执行分支、数据库查询与监控服务。
- 使用隔离 PostgreSQL 实际验证 migration `upgrade head`、约束内容和 `downgrade base`，随后已清理该临时容器与卷。

### 通用 Agent 工具边界

- PTC 与 Flash 默认工具集移除 SEC、行情、期权、股票筛选和价格监控能力，保留代码执行、文件系统、搜索抓取、Skills、MCP、工作区与子 Agent 机制。
- 默认 MCP 配置移除 FMP、Yahoo Finance、Alpha Vantage 等金融服务；用户仍可通过工作区自定义 MCP 接入通用外部能力。
- sandbox 不再同步 `data_client` 与 `market_protocol` 两套金融内部包。
- 内置子 Agent 改为通用角色，`equity-analyst` 更名为 `analyst`，并同步更新默认提示词与配置。
- 删除默认提示词中的金融工具和市场监控引导，防止模型调用已移除能力。
## 迁移调试（2026-09-09）

- 在隔离的 Postgres/Redis/MinIO 栈中完成本地数据库迁移链 `001–045` 基线验证。
- 将远程 MCP connector 基础 schema 按本地迁移链移植为 `046_mcp_platform_core`，并通过升级、降级再升级验证。
- 按本地迁移链追加 `047_user_skills`，完成用户/工作区 Skills 表、归档约束、作用域唯一索引和继承禁用表的升级与回滚验证。
- 按本地迁移链追加 `048_builtin_mcp_disables`，完成账户级内置 MCP 禁用表并验证升级、降级兼容性。
- 按本地迁移链追加 `049_agent_plugins`，完成插件实体、MCP/Skills 归属字段及 RESTRICT 外键，并验证升级与回滚。
- 按本地迁移链追加 `050_plugin_owned_secrets`，完成 Vault Secret 的插件归属、SET NULL 外键和查询索引，并验证升级与回滚。
- 按本地迁移链追加 `051_account_disable_kind`，扩展内置 MCP/Bundle 账户级禁用范围，兼容回填旧 server 行并验证同名不同 kind 共存。
- 按本地迁移链追加 `052_in_flight_credits`，为主运行与子代理运行增加未结算额度字段、非负约束和部分索引，并验证升级回滚。
- 按本地迁移链追加 `053_model_preference`，将模型相关偏好迁入独立 JSONB 列并保留非模型偏好，验证数据搬迁及升级回滚。
- 按本地迁移链追加 `054_jsonb_deep_merge`，提供递归 JSONB 合并函数并验证嵌套合并、null 删除及升级回滚。
## 2026-09-09

### 平台运行时绑定迁移

- sandbox manifest 支持用户/工作区 Skills 视图、禁用内置 Skills 与可选的作用域 token，并把对应内容变化纳入增量同步；本地教育托管会话保持原有隔离路径。
- PTC 请求将当前 Skill delivery signature 传入 WorkspaceManager，用户 Skill 上传、删除或禁用后会绕过 warm cooldown 及时收敛。
- MCP resolve 接入 connector binding plan、OAuth egress grant/JWT 同步，以及 direct-call 与 sandbox wrapper 的统一 schema 分流；无 OAuth 的旧会话继续使用原有兼容路径。
- sandbox 增加 relay 凭据原子发布和 token manifest 上传能力；`056_workspace_file_blobs` 仍延期，未接入数据库文件存储主链。
- 验证：sandbox MCP sync、WorkspaceManager MCP、Skills command、chat request preparation 共 `171 passed`。
## 2026-09-10

### 能力切片补齐与 MCP 2.x 运行时兼容

- 补回 bundled 插件运行所需的共享实现：`mcp_servers` 下的浏览器/信封/抽取/schema/yfinance 辅助模块、`src/data_client`、`src/market_protocol`，以及 `brokerage_tool_overlays`；此前只迁入 `plugins/` 时这些服务器无法启动。
- `mcp_servers/_bootstrap.py` 重新导出 `MCPServer`（mcp 2.x 优先、1.x FastMCP 回退），使内置 MCP server 文件同时可在新镜像与旧 sandbox 中运行。
- `MCPRegistry` 工具发现改为读取 mcp 2.x 的 `input_schema` 并保留 `inputSchema` 回退，修复工具 schema 全部丢失的问题。
- 本地 `scrapling` stdio server 因 `scrapling==0.4.7` 仍依赖已被 mcp 2.0 移除的 `mcp.server.fastmcp` 而关闭；同等的抓取能力由 bundled `alternative_data/scrape` 服务器经 `mcp_servers/_browser.py` 提供。
- 宿主开发模式启动说明与端口/连接参数写入迁移 runbook；后端 `18000`、前端 `15177`，基础设施复用隔离 Compose 栈的 `15432/16379/19000`。
- 验证：宿主栈启动后注册 10 个 MCP server、61 个工具且无连接失败；`/health` 与前端均返回 200；数据库位于 `055_tool_denylist (head)`；相关聚焦测试 `54 passed`。
## 2026-09-10

### 平台 MCP 管理面补齐

- 补回远端 MCP catalog 路由（catalog CRUD、批量导入、binding 设置、内置服务器列表与开关、券商注册表与图标、工具列表）；此前本地仅保留了最小旧版，导致 Plugins 页连接器列表整页报错。
- 补回远端 workspace MCP 路由，并保留本地教育账号守卫（学生 household 成员仍被拒绝访问工作区 MCP 能力）。
- 修正 `get_db_connection` 缺少可复用连接参数的问题：迁移过来的数据库模块均以 `get_db_connection(conn)` 复用调用方事务，本地旧签名会让所有 catalog 接口直接 500。
- 迁移链新增 `056_mcp_tool_binding`（工具绑定映射/预设/审批列）与 `057_brokerage_capabilities`（连接级能力同意列及回填），均在隔离库完成升级验证。
- 接入远端 `tool_binding`、`egress_grants`、`relay_jwt`、工具错误格式化实现，并补入 direct MCP 运行时模块（middleware、direct_tools、flash_binding、grant_resync）；这些模块已就位但尚未接到图形与 Flash 构建入口。
- 前端合并远端 `plugins`、`mcp`、`vault` 三个文案命名空间，Plugins/连接器页面不再出现未翻译 key；本地金融用语守卫改为排除刻意保留的券商能力分组文案。
- 验证：MCP catalog/workspace/model 三组测试由 58 个失败变为 `264 passed`；前端 Plugins、hooks 与 locales 共 `359 passed`（1 个失败源自本地 `TestStorage` 测试替身）；后端单测收集 `7195/7203`，无导入错误；实跑接口 `/api/v1/mcp/servers`、`/builtin-servers`、`/brokerages`、`/api/v1/plugins`、`/api/v1/skills` 均返回 200，启动仍注册 10 个 MCP server / 61 个工具。
## 2026-09-10

### 修复对话一发送即报错、会话重开为空

- `serialize_context_metadata` 补齐 `extra_commands` / `allowed_skills` 参数并透传给 `detect_slash_commands`。PTC 与 Flash 两条请求链都会传入这两个参数，旧签名会让每一轮在落库前就抛 `TypeError`，界面显示错误、会话重开后看不到任何内容。
- 该函数在 START 事务之前执行，所以失败的那一轮既没有写入 `conversation_queries` 也没有 `conversation_responses`；线程行与前缀标题已写，因此表现成“标题在、内容空”。修复后新对话正常落库并可回放。
- 增加回归测试覆盖别名与有效技能集的透传；同时修正 workspace status 测试桩缺少 `skills_signature` 参数的问题。
- 验证：以真实配置调用 PTC/Flash 两条 `serialize_context_metadata` 路径均通过；用 API 实跑一轮 Flash 对话产生 `message_chunk`/`run_end` 且无错误，`conversation_queries` 与 `conversation_responses` 均写入，`GET /threads/{id}`、`/messages/replay`、`/turns` 均返回该轮内容；`tests/unit/server/handlers` 677 项全部通过。
## 2026-09-10

### Skills 来源与平台模型对齐

- 自有 Skills（`book-to-skill`、`the-knowledge-guy`）迁入新 bundle `plugins/langalpha_local/`，随镜像发布且不会遮蔽厂商 bundle；同时删除仓库根 `skills/` 目录与过期的 `skills-lock.json`，随包 Skills 一律来自 bundle。
- `host_skill_dirs`、`SkillsConfig` 与配置加载器改为平台形态（bundle + `user_skills_dir`，不再依赖工作目录）；Dockerfile 与 compose 改为复制/挂载 `plugins/`。
- 两个教育服务改为通过 `host_skill_dirs` 定位受管 Skill，不再硬编码仓库路径；技能注册表补回这两个 Skill 的条目（对齐平台版本时丢失）。
- 补齐平台缺失模块 `ptc_agent/core/mcp_schema.py`，`MCPToolInfo` 改由它提供并在 registry 重导出，工具文档恢复 enum/默认值/可空类型等 schema 事实。
- 退役与当前策略冲突的“彻底无金融”守卫测试（工具边界、启动服务、迁移链、路由注册的源码断言），它们守的是本地已主动放弃的状态；未来按依赖顺序移除金融时再从历史恢复。
- 验证：各单测分组全部通过（config 245、core/observability/ci 552、llms/tools/utils 1240、middleware 484、ptc_agent 707、server/services 1208、server/app+handlers 1413、server/database+models+utils 765、其余根级 125）。
## 2026-09-10

### 平台核心合并后的教育线回补

- 回补托管教材（家庭教育）在平台类上的全部扩展点：`PTCSandbox.setup_managed_textbook_job`、`Session.initialize_managed_textbook`、`build_ptc_graph_with_session(managed_policy=...)` 及其身份/存储清空分支、`PTCAgent.create_agent` 的 `managed_policy` 参数与受限工具装配。
- 托管 Bash 恢复 `command_validator` 与 `fixed_working_dir`（命令必须落在冻结的作业根内）；文件 Write 工具恢复写前校验钩子；托管子代理恢复固定注册表 `textbook-chapter-worker`。
- 托管模式不再携带环境工具：`AskUserQuestion`、`RunWorkflow`、金融工具、Web/Site-crawl 一律按 `managed_policy` 关闭；技能注册表按 `allowed_skill_names` 过滤。
- 退役与当前策略冲突的本地测试 `test_generic_sandbox_packages.py`（断言跳过退役金融包，而本分支保留金融）。
- 验证：`tests/unit/ptc_agent` 763 passed、1 xfailed/xpassed；相关文件 ruff 通过。
## 2026-09-10

### 家庭模型解析与平台模型档迁回远端 LLM 分层

- 采用远端拆分后的 `llm/{availability,clients,config}` 三件套，移除合并时保留的旧单体 `config.py`；家庭（household）解析移入新模块 `llm/household.py`，`resolve_llm_config` 在 BYOK 自解析后立刻尝试 `resolve_student_household_config`，学生账号命中即早返回，不进入任何个人偏好分支。
- 平台模型档（`PLATFORM_LLM_SOURCE_EMAIL` + `PLATFORM_LLM_MODEL`）改接在远端 `resolve_model_client` 的 SYSTEM 平台回退口：配置存在时优先使用服务账号客户端；角色客户端物化闸门增加 `PLATFORM + 已配置档` 例外，使压缩/抓取/子代理角色复用主客户端。
- `AgentConfig` 补回 `resolved_model` 与 `llm_runtime_metadata` 两个本地运行时字段（远端已无），并在 PTC/Flash 落库元数据与 SSE 首帧 metadata 里重新发出 `resolved_llm_model`，前端“实际运行模型”显示恢复。
- 单测基座补齐：`tests/unit/conftest.py` 增加远端 `_empty_user_skill_bundle` 桩并把 household 成员查询纳入默认匿名桩（`resolve_llm_config` 每轮都会查家庭层级）；补回远端新增但合并时遗漏的 `tests/unit/server/services/conftest.py`。
- 测试目标重新指向拆分后的模块归属（`llm.clients` / `llm.user_models` / `llm.household`）；`tests/unit/server/handlers/test_resolve_llm_config.py` 与 `chat/test_resolve_llm_config_credential.py` 以远端版本为基座，仅叠加本地 household 与平台模型档用例。
- 顺带修正合并残留：`src/server/models/user.py` 重复的 `normalize_instrument_type` 定义，以及 `education_teaching_storage.py` / `workspace_manager.py` 的未使用导入。
- 验证：`tests/unit/server`（排除两个 workspace_manager 收集文件）由 164 failed/3450 passed 变为 99 failed/3520 passed；`tests/unit/llms` 553 passed，`tests/unit/server/handlers/chat` 296 passed，`tests/unit/config` + `tests/unit/core` 817 passed，`tests/unit/utils` + `tests/unit/ptc_agent` 883 passed；`ruff check src/` 通过。
## 2026-09-10

### 手工合并剩余平台文件，全量单测转绿

- 13 个“双方都改过”的文件改用三方合并（fork 点 `4f56db64` 作 base）后逐个裁决：`app/setup.py`、`app/users.py`、`app/api_keys.py`、`app/vault.py`、`app/workspaces.py`、`app/mcp_servers.py`、`app/workspace_sandbox.py`、`app/threads/{create,messaging}.py`、`database/user.py`、`handlers/chat/{request_prep,error_handling}.py`、`services/persistence/usage.py`、`services/runs/recovery.py`、`services/user_data_io.py`、`config/{env,settings}.py`；`utils/api.py` 与本地一致（首方会话鉴权本地为准），不取远端。
- 远端新增能力随之上线：`users` 的 auth sync 与模型 tuning 校验、`database/user` 的 `migrate_user_id`/`create_user_from_auth` 与 JSONB 深合并子句、`api_keys` 的 `byok_eligible` 默认值与 `prompt_guidance` 默认档、`settings` 的市场/新闻/OHLCV 配置访问器、`setup` 的 WorkspaceFileGC 与 credit-gate 接线。
- 本地产品面按上游形态回补：`ChatRequest` 补回 `education_assignment_id` / `education_chapter_id`；`s3_compatible` 回补 `download_to_file` / `open_download_stream` / `create_presigned_download_url`；`run executor` 回补托管教学断连窗口 `_abandoned_timeout_for_metadata`；`coordinator` 回补 `llm_runtime_metadata` 透传；`skills registry` 回补 `book-to-skill`、`the-knowledge-guy`；`threads_read.get_thread_auth_meta` 回补 `managed_execution` 列，配套 `utils/api`、provenance、automation 归属校验。
- 学生/家庭守卫统一走 `education_access.is_student_account`（`users` 偏好写、`api_keys` 个人模型配置），避免每轮打一次 household JOIN，也让单测默认匿名桩覆盖到全部入口；`tests/unit/conftest.py` 增加技能 bundle 与 household 成员默认桩。
- 退役两个与“先整体迁回金融、后续再定点移除”冲突的本地守卫测试：`server/database/test_generic_user_preferences.py`（断言偏好表不得出现 risk/investment 列）；`test_generic_router_registration.py` 的 trigger_type 断言放宽为“通用触发器必须在”。
- 修正单测污染：`test_preferences_validation.py` 改为 patch `LLM.get_model_config()` 而不是 `ModelConfig`（后者会把 MagicMock 写进类级单例，污染同进程后续用例）；`test_llm_constructor_boundary.py` 为 `llm/household.py` 的 `create_llm_from_custom` 补白名单说明。
- 验证：`uv run pytest tests/unit -q -p no:randomly` 全绿 **7486 passed, 1 xfailed**；`ruff check src/` 通过。
## 2026-09-10

### 迁移链补齐工作区文件 Blob 与 Direct-Tools 表结构

- 本地迁移链独占 `035`–`045`，远端的后续迁移按顺序落到链尾：新增 `058_workspace_file_blobs`（对应远端 `039`）与 `059_direct_tools`（对应远端 `040`），`down_revision` 依次接 `057_brokerage_capabilities` → `058` → `059`。
- `058` 建 `workspace_file_blobs` 内容寻址登记表，给 `workspace_files` 加 `blob_sha256`/`kind`/`symlink_target`/`pack_sha256`/`pack_offset`，给 `workspaces` 加 `files_restore_incomplete_at`，并建 condemn/live 两个部分索引；热表只取一次 ACCESS EXCLUSIVE，VALIDATE 与 CREATE INDEX CONCURRENTLY 放到 autocommit 块；降级在仍有 blob 指针或未完成恢复的库上直接拒绝。
- `059` 给 `sandbox_egress_grants` 加 `tool_direct_only`，并递增有连接的 workspace 的 `mcp_config_version` 触发重新解析。
- 迁移后运行时才真正可用：合并进来的 `persistence/{_rows,backup,blobs,resolve,restore}` 会写 `blob_sha256` 指针，`WorkspaceFileGCService` 负责回收；一并迁回 `scripts/ops/_db.py`、`backfill_workspace_file_blobs.py`（正反向回填）与 `report_orphan_blobs.py`，并把脚本里对旧编号 `039` 的引用改为 `058`。
- 远端 `037_free_webull_name` 有意跳过：它依赖本链从未执行过的远端 `030`/`032`，且只是把存量用户 MCP 行从 `webull` 改名的一次性数据修复；本地无此类数据，将来需要时再作为 `060` 补。
- 新增 `tests/unit/migrations/test_workspace_file_blobs_migration.py`、`test_direct_tools_migration.py`；在隔离库（15432）完成 `057 → 058 → 059` 与 `059 → 057 → 059` 往返验证，并确认新列与新索引落库。
- 验证：`uv run pytest tests/unit -q -p no:randomly` → **7491 passed, 1 xfailed**；`ruff check src/ scripts/ops/` 通过。
## 2026-09-10

### 回补金融偏好与自选/持仓/洞察表，PTC + Docker 沙盒端到端跑通

- 端到端实测暴露本地基线 `001_initial_schema` 曾删除的金融 schema：`user_preferences.risk_preference` / `investment_preference` 两列，以及 `watchlists`、`watchlist_items`、`user_portfolios`、`market_insights` 四张表。合并进来的 `database/user.py` 每轮都会 SELECT 那两列，`/api/v1/watchlist`、持仓路由与洞察服务读那四张表，因此新增 `060_restore_finance_schema` 按远端 `001` 重建，并把本地已成为空壳的 `005`（generating 唯一索引）与 `007`（user_id UUID→VARCHAR）的效果折进来；降级在仍有数据时拒绝执行。
- `agent_config.yaml` 修正启用子代理名 `analyst` → `equity-analyst`（远端重命名后，旧名字会让 PTC Agent 初始化直接失败），并按上游形态补回 `price_data` MCP 条目与上游新注释。
- 端到端验证（宿主后端 18000 + 隔离栈 15432/16379/19000 + Docker 沙盒）：启动无告警，注册 12 个 MCP server / 61 个工具，checkpointer 健康；创建 PTC 工作区拉起容器 `langalpha-sandbox-docker-9d2ebd6f5759`；两轮对话均 `completed`——第一轮直答 `pong` 并上报 17494 input tokens，第二轮在沙盒内写读文件并产出 `Write work/sandbox_check/hello.txt`（content `step-ok`）artifact。
- 停止工作区触发沙盒落库：`workspace_files` 写入 `kind`、`pack_sha256` 且内联列为空，`workspace_file_blobs` 登记 1 条 4.8MB pack 记录，证明“打包 → 上传 → 登记”整条 blob 链路可用（这也是 `058` 属于必需而非可选的原因）。
- 尚未完成：用户级（非内置）MCP 连接器的真实端到端；`workspace_mcp_tool_schemas` 在未添加用户服务器前保持为空。
- 验证：新增 `tests/unit/migrations/test_restore_finance_schema_migration.py`；隔离库完成 `059 → 060 → 059 → 060` 往返；前端 15177 与后端 18000 均 200。
## 2026-09-10

### 补回被本地移除的金融/行情路由

- 合并后的 `setup.py` 曾沿用了本地“已删金融面”的路由清单，导致 `market_data`、`bars`、`watchlist`、`portfolio`、`news`、`calendar`、`sec_proxy`、`insights`、`chart_annotations` 与 ginlix-data 的 `market_data_ws`（未配置时退化为 `/ws/v1/market-data/status` 返回 200 的状态桩）全部未注册；按“先整体迁回、后续再定点移除”的策略恢复注册，路由数由 250 增至 258。
- `test_generic_router_registration.py` 中的本地守卫 `test_default_api_has_no_finance_or_market_routes` 改为 `test_finance_routes_are_registered`：当前断言这些路由**必须**在册，移除金融时再翻转回原来的断言（与源码包守卫同一处理方式）。
- 实跑验证（宿主后端 18000）：`/api/v1/users/me/watchlists`、`/api/v1/users/me/portfolio`、`/api/v1/market-data/market-status`、`/api/v1/news`、`/api/v1/insights/today`、`/api/v1/calendar/earnings` 均返回 200；`/api/v1/sec-proxy/document` 返回 502（上游 SEC 代理按预期转发失败）。
- 验证：`uv run pytest tests/unit -q -p no:randomly` → **7494 passed, 1 xfailed**；`ruff check src/` 通过。
## 2026-09-11

### 前端迁回上游模型调参（账号默认 + 逐模型覆盖）

- 新增上游的调参基础层：`web/src/lib/modelTuning.ts`（`resolveTuning`/`resolveEffort`/`TUNE` 词汇表，与服务端 `resolve_turn_tuning` 同一条优先级）、`web/src/lib/modelPreferences.ts`（`modelPrefs`/`modelProfile`/`MODEL_PREF_KEYS`/`splitPreferenceWrite`，决定每个 key 写进 `model_preference` 还是 `other_preference`）、`web/src/hooks/useModelProfile.ts`（`writeProfile`/`clearProfile`/`writeAccountDefault` + `useEffectiveTuning`）。
- 新增调参界面组件：`components/model/{AccountTuningDefaults,PerModelMatrix,CompactionProfilePicker,FallbackModelsPicker}.tsx`；`Settings/panels/ModelTab.tsx` 换成上游版本（simple/advanced 两档、`Defaults` 与 `per-model` 两个区块、每个控件各自 patch 并按列路由写回），并保留本地独有的 `TokenizerStatusAlert`。`ModelTierConfig.tsx` 与 `Setup/steps/DefaultsStep.tsx`、`ModelPickStep.tsx` 回到上游形态（fallback/compaction 选择器从 tier config 抽出，安装向导的下拉折叠区改用它）。
- 关键修正：本地 Model tab 过去把所有模型 key 写进 `other_preference`，而合并后的后端只在写入方向把它们改道到 `model_preference`（读回不镜像），所以**存过一次、切走再回来会显示默认值**。现在读写都按 `MODEL_PREF_KEYS` 分列，`starred_models` / `search_provider` / `search_depth` 仍留在 `other_preference`。
- `useUpdatePreferences` 换成上游版本（乐观合并预测 + `PREFERENCE_MUTATION_KEY` 保存态），只把 `updatePreferences` 的导入指向本地的 `@/api/user`；`useAllModels` / `useFilteredModels` 回到上游（`ModelMetadataEntry` 补回 `reasoning_efforts`/`reasoning_effort_default`/`prompt_guidance`/`compaction_profile`，`systemDefaults.prompt_guidance` 恢复）。
- 补齐契约与文案：迁回 `tests/fixtures/tuning_precedence.json`（前后端共用优先级表）与 `tests/fixtures/reasoning_clamp.json`，以及后端 `tests/unit/llms/test_tuning_precedence.py`、`test_reasoning_efforts_manifest.py`；`settings.modelTuning` 32 个 key 与 `settings.fallbackModels*`/`removeModel` 补进 en-US/zh-CN。
- 顺带修掉三处先前遗留的前端红灯：`--color-identity-0..7-*` 与 `--color-bg-card-hover` 令牌未声明（MCP 的 IdentityTile/McpPrimitives 从早前阶段就已在用）；导航测试未同步 `/plugins` 入口；退役与“先迁回金融、后定点移除”冲突的 `financeSurfaceBoundary.test.ts`。
- 验证：`pnpm typecheck` 通过；`pnpm vitest run` **230 files / 2227 tests 全绿**（基线为 3 failed/2173 passed）；`pnpm lint` 0 error；后端 `uv run pytest tests/unit -q -p no:randomly` → **7547 passed, 1 xfailed**。
- 尚未迁移：composer（`chat-input.tsx` 与其 modelMenu/parts/toolbar 一簇）。它仍是本地版：effort/fast_mode 存 localStorage 且按请求级发送，所以未在 composer 里显式选择时，后端会应用新持久化的账号/模型档；选定后仍以请求级覆盖。这一簇本地另有家庭模型菜单逻辑，需要单独一次 3-way 合并。
## 2026-09-11

### composer 调参接线迁回上游

- `components/ui/chat-input.tsx` 一簇改按上游形态：effort / fast_mode 不再存 localStorage 并按请求发送，而是 `useEffectiveTuning(selectedModel)` 解析（请求 > 模型 profile > 账号默认），发送时带上 `resolvedEffort` / `resolvedFastMode`；模型菜单改用 `useModelProfileWriter`，在下拉里改档位就是写 `model_preference.profiles[<model>]`。上游的一次性迁移 shim 保留：本机 `localStorage` 里已有的 `reasoning_effort:<model>` / `fast_mode:<model>` 会写入对应模型 profile 后清掉。
- 同簇一起对齐：`chat-input.modelMenu.tsx`（`TriggerBody` 兼收上游的 `effortLabel` 与本地的 `modelLabels`/`emptyLabel`）、`chat-input.useSlashCommands.ts`（`workspaceId` 作用域）、`chat-input.useVoiceInput.ts`、`chat-input.css`、`dropdown-menu.tsx`（`variant="setting"` 行样式）、以及缺失的 `lib/inputModality.ts`（下拉按指针/键盘区分）。
- 本地产品面照旧保留：家庭（household）模型菜单与 `handleModelSelection`、`displayModel` 只读标识、`TokenizerStatusAlert`、以及本地刻意移除的图表捕获 props；市场观察（market watch）开关没有恢复，因为本分支的 composer 与发送链路里都没有它的落点。
- 配套：`chat.modelSelector` 补 `effortHint`/`defaultBadge`/`speed*` 6 个 key；本地 `chat-input.familyModel.test.tsx` 的 `useAllModels` 桩补上 `metadata`/`systemDefaults`（`useEffectiveTuning` 要读），否则渲染即崩。
- 验证：`pnpm typecheck` 通过；`pnpm vitest run` **230 files / 2227 tests 全绿**；`pnpm lint` 0 error；`pnpm build` + critical-path 检查通过。
## 2026-09-11

### Plugins 模块前端补齐到远端一致

- 审查结论：Plugins 面本来就有 ~92% 与远端逐字节相同（`pages/Plugins` 81 个文件里 71 个一致、本地无任何独有文件；i18n 的 `plugins`/`mcp`/`vault` 三个命名空间与远端完全相同），所以不做整体替换，只补 delta。
- 取远端（11 个）：`pages/Plugins` 下 `BrokerageDetailParts`/`BrokerageRow`/`McpCatalogRow`/`ScopeControl`/`ServerDetail`/`hooks/useWorkspaceOptions`，配套的 `hooks/useMcpServers`、`ChatAgent/components/mcp/McpTab`、`ChatAgent/components/vault/WorkspaceSecretsTab`、`ChatAgent/utils/api/{mcp,vault}`。逐行核对确认这些文件相对远端**没有本地产品逻辑**，唯一两处本地差异是 `McpTab`/`WorkspaceSecretsTab` 里为旧版未定型 `api/vault.ts` 加的类型注解——取上游的 `WorkspaceVaultSecret[]` 之后两处注解已不再需要。
- 补齐远端独有（10 个）：`pages/Plugins/components/ToolAccess.tsx`、`pages/Plugins/hooks/useFlashWorkspace.ts` 与两个测试；`ChatAgent/components/mcp/{ArgsTable,DirectToolDetail,DirectToolMark,JsonTree,useDirectToolVendor}`、`ChatAgent/utils/directTools.ts`；以及 plugins 面三个上游测试 `useBuiltinMcpServerTools`/`useVaultInvalidation`/`chatInputModelMenu`。
- 由此恢复的界面能力：**Flash 作为作用域目标**（只对 `has_direct_tools` 的行出现，Flash 无沙盒、只能装直连工具）、**逐工具调用路径开关**（`ToolAccess` + `useSetMcpServerBinding` + `setMcpCatalogServerBinding`，按工具定位 422 文案）、**直连工具详情视图**。这些能力对应的后端（`has_direct_tools`、`059_direct_tools`）合并不久前已经就位，此前是前端用不出来。
- `chat.modelSelector` 文案对齐远端：`reasoningEffort` "Reasoning"→"Effort"、`effortXhigh` "X-High"→"Extra High"，补 `effortNone`/`effortMinimal`/`effortMax`，删除已被远端 `speed*` 取代且本地无引用的 `fastMode*` 四个 key。
- `components/ui/segmented-control.tsx` 取自远端后发现本仓库无任何引用（它只服务于上游的 `UserInfoTab`，属产品前端，不在本次范围），未纳入。
- 验证：plugins 面与远端达**完全一致**（`pages/Plugins` 81/81 逐字节相同，配套面 46/46，无缺失文件）；`pnpm typecheck` 通过；`pnpm vitest run` **235 files / 2263 tests 全绿**；`pnpm lint` 0 error；`pnpm build` + critical-path 检查通过。
## 2026-09-11

### 密钥页补充面向用户的用法说明（中英 i18n）

- 界面层（简约）：`plugins.secrets.scopeHint` 改成一句话的白话说明——集中存放服务器与助手要用的密钥密码、所有工作区都能取用、工作区内存了同名值就在该工作区优先。
- 详细文案（tips）：新增 `SecretsUsageTips`（`components/vault/SecretsUsageTips.tsx`），在列表头放一个带 ⓘ 的「使用提示 / Tips」按钮，点开是 Radix `Popover`,分四段讲清楚:这些密钥干什么用(不会直接交给模型,只在需要时读取)、三种会用到它的场景(装插件时向导索要 / 配连接时不粘明文只按名字引用 / 助手执行任务时运行时读取)、放账号层还是工作区(含同名覆盖规则)、以及几条说明(打码与显示值、卸载插件不删除密钥、家庭学生账号看不到)。
- 文案刻意不出现技术词:不提 MCP、不提 `${vault:NAME}`、不提 pgcrypto,只讲"密钥/密码、连接、助手、工作区"。`plugins.secrets.tips.*` 共 18 个 key,en-US / zh-CN 同步补齐;场景用显式字面 key 而非模板拼接,保证仓库的 locale 一致性检查能覆盖到。
- `SecretsManager` 新增可选 `tips` 插槽(渲染在列表头的操作区),Plugins → Secrets 传入;工作区「密钥库」页保持不变(它本来就有自己的用法/安全卡片)。
- 新增 `__tests__/SecretsUsageTips.test.tsx`,钉住"默认收起、点击后三个场景与两段说明都在",避免 key 改名后静默渲染成空白面板。
- 验证：`pnpm typecheck` 通过；`pnpm vitest run` **236 files / 2265 tests 全绿**（含 locale 键位一致性）；`pnpm lint` 0 error；`pnpm build` + critical-path 检查通过。
## 2026-09-11

### 斜杠菜单:教育 Skill 置顶 + 取消截断改为滚动

- 起因:用户在工作区对话里打 `/` 找不到 `book-to-skill` / `the-knowledge-guy`。排查确认后端没问题(两个工作区、`mode=ptc` 都返回这两个,`mode=flash` 按设计不返回),问题在菜单:裸 `/` 时列表是"3 个系统命令 + 前 7 个 skill",而这两个 skill 排在注册表末尾,永远进不了 `.slice(0, 10)` 的截断。
- 置顶:`chat-input.helpers.tsx` 新增模块私有的 `FEATURED_SLASH_COMMANDS`(两个教育 skill),`slashRank` 排序改为"先看匹配质量(前缀 > 子串),再看档位(置顶 > 系统命令 > 其余 skill)"。这样裸 `/` 以这两个开头,而 `/d` 仍然把 `/dcf-model`(前缀)排在仅含字母 d 的置顶命令之前——匹配质量优先这一点没有被破坏。
- 取消截断:去掉 `.slice(0, 10)`,所有匹配都渲染;菜单高度由 `.mention-autocomplete` 自己限制(从固定 `240px` 改为 `min(340px, 45vh)`,保留 `overflow-y: auto` 并加 `overscroll-behavior: contain`),键盘上下选中的项仍会自动滚入视野。
- 新增两条测试:裸 `/` 时置顶命令排在任何系统命令之前;列表尾部的 skill 依然在(不再被截断)。原有排序断言(系统命令优先于 skill、前缀优先于子串)全部保留通过。
- 验证：`pnpm typecheck` 通过；`pnpm vitest run` **236 files / 2267 tests 全绿**；`pnpm lint` 0 error 且告警数未增加(56,与改动前一致)；`pnpm build` + critical-path 检查通过。
## 2026-09-11

### 修复文档预览切回「原始文件」时整页空白

- 根因（有依赖源码作证，不是猜的）：pdf.js 把文档字节**当 transferable 交给 worker**——`pdf.mjs:14158` 的 `sendWithPromise("GetDocRequest", docParams, data ? [data.buffer] : null)`，`react-pdf` 的 `Document.js:128` 只是原样转发调用方的 `Uint8Array`。而 `PdfViewer` 里 `new Uint8Array(data)` **只是同一块 buffer 的视图**，于是抽屉 state 持有的 `source` 在首次渲染后就被 detach。切到「解析文件」会卸载 viewer,切回「原始文件」重新挂载时把这块已 detach 的 buffer 再交给 pdf.js → 加载失败 → `onLoadError` → `setError` → 渲染期 `throw error`;而 `DocumentErrorBoundary` 此前**只包在 ChatAgent 的 FilePanel**，文档抽屉没有,异常直冲根节点 → 整个页面被卸载成空白。
- 修一（根因）：`PdfViewer` 交给 pdf.js 的永远是**副本**（`ArrayBuffer` 走 `data.slice(0)`，`Uint8Array` 走 `new Uint8Array(data)`），调用方持有的那块 buffer 不再被拿走，重挂载即可正常工作。这条对 FilePanel 的 PDF 预览同样有效。
- 修二（兜底）：`DocumentPreviewDrawer` 用 `DocumentErrorBoundary` 包住 viewer（与 FilePanel 一致的既有做法），viewer 抛错时降级为「原始文件无法加载」的提示，而不是把整个应用拖白。
- 回归测试两条，且都验证过"没有修复时会失败"：`viewers/__tests__/PdfViewer.test.tsx`（用真实的 transfer 语义 detach 掉传进去的 buffer，断言调用方的 buffer 未受损、重挂载后仍可用）与 `DocumentPreviewDrawer.test.tsx` 的新用例（viewer 抛错时抽屉仍挂载并显示提示）。
- 验证：`pnpm typecheck` 通过；`pnpm vitest run` **237 files / 2270 tests 全绿**；`pnpm lint` 0 error（告警数 56 未变）；`pnpm build` + critical-path 通过。
## 2026-09-11

### 文档预览「原始文件 / 解析文件」切换加滑动动画

- 用仓库既有的动画方案:framer-motion 的 `layoutId` 共享布局(与 `components/ui/animated-tabs.tsx` 同一个手法,Automations 表单、SourcesPanel、RightPanel 都在用这类滑动药丸),全站已由 `App.tsx` 的 `<MotionConfig reducedMotion="user">` 统一处理"减少动态效果"偏好,无需另行判断。
- 保留原有语义与外观:两个按钮仍是 `role="tab"` + `aria-selected`(测试与无障碍契约不变),选中态的底色不再由按钮自己画,改由唯一的 `motion.span` 药丸承载,切换时它在两个位置之间**滑过去**;`.documents-preview-mode-switch`(连续/单页)共用那条 CSS 规则,保持不变。
- 药丸只在"标签真的变了"时走 spring:抽屉本身也会移动(拖拽改宽、进全屏),否则会被读成药丸自己在滑。这一点沿用 `AnimatedTabs` 里同样的 `valueChanged` 判断。
- 新增用例:任意时刻只有一个药丸,且它属于当前选中的那个标签。
- 验证：`pnpm typecheck` 通过；`pnpm vitest run` **237 files / 2271 tests 全绿**；`pnpm lint` 0 error（56 告警未变）；`pnpm build` + critical-path 通过。
