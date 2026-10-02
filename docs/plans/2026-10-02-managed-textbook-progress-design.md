# 托管教材语义进度与活动时间线设计

## 1. 目标

在不修改 `more-to-skills` 核心能力、不让 Skill 接触数据库的前提下，为托管教材 PTC 运行补充少量、可公开的语义进度，使工作台能稳定展示“正在整理章节层级”“正在组织讲义内容”等说明。

这套能力必须同时满足：

- 教育服务创建并掌握 `structure`、`material`、`supplementary` 任务边界；
- 托管 PTC Agent 只报告它在一次 item 内部正在做什么；
- 只有服务端验证并提交的产物才能改变业务状态和完成计数；
- 过程说明缺失、重复、乱序或写入失败都不能改变任务结果；
- 普通聊天、其他 Skill、父级 workspace、MCP、Vault 和 subagent 能力不受影响。

## 2. 当前事实与问题

教育服务会为每个任务创建持久 job/item。一个结构任务对应一个 `structure` item；材料任务按知识点创建 `material` item，并在明确要求时追加一个 `supplementary` item。服务端知道当前 item 的类型、目标、位置、attempt、run 和最终提交结果。

托管 PTC root Agent 读取 `task.json` 和冻结的 `more-to-skills/SKILL.md`，再自主调用 Read、Bash、ExecuteCode、Write 等能力。通用运行流能观察工具开始和结束，却无法仅凭 `Read` 或 `Bash` 判断 Agent 正在做结构归一化、知识点切分还是最终校验。

Task 4 已实现 `artifact_type=report_progress` 的接收、节流、持久化与重连，但生产路径还没有发送端。因此当前活动可以可靠展示工具摘要和服务验收终态，不能稳定展示 Skill 内部的业务语义阶段。

## 3. 方案比较

### 方案 A：只展示服务端 job/item 生命周期

教育服务根据 item 类型展示“结构分析中”“讲义生成中”，完成数来自数据库。

优点是完全确定、无需模型配合。缺点是长时间运行期间信息过粗，用户只能看到一个持续很久的“处理中”。

### 方案 B：解析 Bash、文件路径或工具结果推断阶段

根据命令中是否出现 `scan_outline.py`、`validate_structure.py` 或输出文件名推断当前阶段。

这个方案不采用。模型可以改变命令、合并脚本、重试或直接使用 ExecuteCode；工具参数和结果还可能包含私有路径及教材内容。字符串推断既脆弱又扩大公开数据面。

### 方案 C：托管 PTC 注入受限进度工具

平台向教材托管 Agent 注入一个 `report_progress(stage)` 工具，managed task contract 规定允许的 stage 和调用边界。工具只向 LangGraph custom stream 写一个小型 artifact；教育 observer 校验并翻译 stage，随后使用 Task 4 的有界活动账本持久化。

采用方案 C，并以方案 A 作为始终存在的权威骨架。即使 Agent 一次进度都没有报告，用户仍能看到正确的任务状态和完成数量。

## 4. 谁是上报 Agent

“Agent”指每个教材 item 启动的托管 PTC root Agent。它由教育 worker 通过 `build_managed_education_graph()` 创建，读取服务端 prompt、`inputs/task.json` 和冻结 Skill，然后在隔离 sandbox 中执行。

`more-to-skills` 是 Agent 遵循的工作方法和脚本集合，不是常驻进程，也不拥有数据库连接。教育服务不会根据“进入 Skill”自动得知内部步骤；只有 Agent 显式调用进度工具时，服务端才能得到内部语义阶段。

## 5. 三层活动权威

活动面板同时展示三类来源，但它们的权威不同：

| 层级 | 来源 | 示例 | 是否能改变业务状态 |
|---|---|---|---|
| 服务端里程碑 | job/item 创建、claim、产物校验与事务提交 | 结构任务已开始；讲义已提交；完成 3/10 | 是 |
| Agent 语义进度 | `report_progress(stage)` | 正在整理章节层级；正在组织讲义内容 | 否 |
| 通用工具摘要 | PTC `tool_calls` / `tool_call_result` | Running Read；Finished Bash | 否 |

前端不得从进度或工具活动推导成功、失败、完成数量或百分比。业务状态只能读取 job/item 快照；终态事件只是该事务结果的活动投影。

阶段白名单只保证公开表达受控，不能证明 Agent 实际执行了对应步骤。阶段允许缺失、重试和回退，不构成必须逐项完成的状态机，也不能成为产物验收或提交的前置条件。

## 6. 工具契约

第一版工具只接受一个 `stage` 标识符，不接受自由文案、业务 ID、文件路径、计数或教材正文。通用工具校验其格式和长度；教育 observer 按 item 类型校验固定阶段白名单，工具模块不导入教育词表：

```python
report_progress(stage="structure_organizing")
```

工具写入的 custom event 为：

```json
{
  "artifact_type": "report_progress",
  "artifact_id": "structure_organizing",
  "status": "running",
  "payload": {
    "stage": "structure_organizing"
  }
}
```

`job_id`、`item_id` 和 `attempt_token` 不由模型提供。`BookActivityObserver` 在创建时已经绑定这些身份，并继续使用现有 attempt fence。未知 stage 被忽略并记录诊断，不写入公开活动。

工具返回固定短结果，例如 `Progress reported.`。发送失败不能使 Agent 运行失败；事件是否持久化仍由 observer 的 `activity_status` 语义处理。

## 7. 第一版阶段词表

阶段数量保持少而稳定，不复刻 `SKILL.md` 的每一个步骤。

### 结构 item

| stage | 公开文案 | 调用边界 |
|---|---|---|
| `structure_reading` | 正在阅读教材结构线索 | 开始读取来源与已有解析产物 |
| `structure_organizing` | 正在整理章节层级 | 开始结构语义归一化 |
| `structure_splitting` | 正在切分知识点 | 开始生成 `knowledge_points` |
| `structure_validating` | 正在校验教材结构 | 开始最终结构校验与修正 |

### 单知识点材料 item

| stage | 公开文案 | 调用边界 |
|---|---|---|
| `material_reading` | 正在阅读知识点原文 | 开始读取当前 KP、图片及相邻上下文 |
| `material_organizing` | 正在组织讲义内容 | 开始确定模板与讲解顺序 |
| `material_writing` | 正在撰写讲义 | 开始写入目标 Markdown |
| `material_validating` | 正在校验讲义产物 | 提交前检查范围、格式和引用约束 |

### 附加材料 item

| stage | 公开文案 | 调用边界 |
|---|---|---|
| `supplementary_reading` | 正在汇总全书讲义 | 开始读取已成功材料 |
| `supplementary_organizing` | 正在整理全书附加材料 | 开始归纳术语、方法和速查内容 |
| `supplementary_validating` | 正在校验附加材料 | 提交三个固定文件前 |

不为 `glossary.md`、`patterns.md`、`cheatsheet.md` 分别声明实时阶段，因为同一个 Agent 可能交错生成三个文件。服务端只在三个文件全部验收后确认附加材料成功。

## 8. 注入和提示契约

`report_progress` 是通用、无业务身份的 PTC stream 工具，但默认不进入普通 Agent 工具面。`ManagedExecutionPolicy` 增加显式开关，只有教材托管 policy 启用。

教育模块在 `task.json` 中写入本 item 允许的阶段列表，并在 managed prompt 中要求：

- 只在真正进入该阶段时调用一次；
- 重试同一阶段可以再次调用，由 observer 合并；
- 不得用进度调用代替产物写入或最终回复；
- 没有适用阶段时继续工作，不得为了填满 timeline 伪造步骤。

新增内容仅位于 `task.json.progress`，包含工具名和允许阶段。已有顶层 `job_id`、`item_id`、`execution_id`、`attempt_token`、`attempt`、来源与输出契约保持原样；“不接收业务身份”约束的是进度工具参数和新增 progress 子对象。observer 始终使用服务端绑定的身份，不从模型上报中取身份。

阶段及提示属于 LangAlpha 教材托管适配层，不写入 `more-to-skills` 核心 Skill。这样 Skill 仍能在 CLI 或其他 Agent 环境中独立使用，也不会依赖 LangGraph 或数据库。

## 9. 持久化、失败与恢复

现有 `BookActivityObserver` 继续负责：

- 在 compact 过滤前接收 artifact；
- 依据 item 类型校验 stage；
- 使用服务端文案映射生成公开 message；
- 按 `artifact_id/stage` 对同阶段至少节流 1 秒；
- 使用绑定的 attempt token 拒绝旧运行迟到事件；
- 受 1000 条、1 MiB、单条 2 KiB 和 message 512 字符预算约束；
- 写入失败后标记 `activity_status=unavailable`，但不改变任务运行。

正常写入与预算耗尽后的省略统计使用相同的阶段白名单、节流和工具噪声过滤规则。合法且通过节流的 stage 在预算耗尽后只增加有界省略摘要；非法 stage、旧自由文案和 `report_progress` 自身的通用开始/结束事件均不进入明细或省略计数。工具调用关联状态及时清理并保持有界。

服务端里程碑和终态不依赖 `report_progress`。材料完成数在产物提交事务中从 item 表重新统计；结构分析期间在结构真正导入前不显示知识点完成率。

活动页中的 `high_water_seq` 是本次查询所见的服务器最高序号；浏览器另存 `last_processed_seq`，仅在整页事件成功解析并合并后推进到该页最大事件 seq。SSE `id` 使用该帧已交付事件的最大 seq，空页不推进；重连使用 `after_seq=last_processed_seq`，不能直接使用服务器高水位。序号允许存在间隔，不要求逐号连续。例如高水位 500、第一页收到 1–200 后断线，必须从 200 重连。

初次打开或本地事件缓存丢失时先读 job/item 快照，活动从 `after_seq=0` 回放服务端有界账本；不能用新快照的高水位跳过历史活动。保留本地缓存的重连使用原消费游标。`cursor_expired` 时取消旧订阅、刷新业务快照、清空活动缓存并从 0 重建回放；当前协议没有额外保留窗口令牌，不能虚构“新游标”。后台恢复重新获取快照并按同样规则恢复活动。

活动页只包含 job 状态、活动可用性、事件和分页信息，不等于完整 job/items 快照。前端收到 item/job 业务事件或 job 状态变化时，按每任务最多每秒一次合并刷新 job 快照及相关工作台查询；同一任务不重叠请求，合并窗口内的新通知须有尾随刷新。收到首帧、重连成功和终态时也需同步业务快照。活跃任务在页面可见期间保留每 5 秒一次的任务级兜底刷新，即使 SSE 正常也覆盖下一项已启动但尚无事件的情况；后台暂停，恢复前台立即刷新，网络错误有限退避。确认终态后最后刷新工作台以发现后续任务，再停止该 job 的定时器；403/404、卸载和任务切换也清理订阅与定时器。旧请求不能覆盖新任务或较新的快照。

若 Agent 漏报阶段，界面回退到 item 类型对应的“结构分析中”或“讲义生成中”；若活动不可用，明确显示活动不可用并使用通用任务说明。历史阶段不能继续冒充当前进度。完成数量和当前项始终取刷新后的业务快照。

## 10. 工作台呈现

活动面板以服务端里程碑为主线，每个运行中 item 最多突出一个当前语义阶段。重复 Read/Bash 等工具事件放在可展开的“运行明细”中，不在主时间线堆叠。

材料批量任务的头部来自数据库快照，例如：

```text
正在生成讲义 3/12
当前：《Sweet Love 2》
正在组织讲义内容
```

这里的 `3/12` 只统计已提交的知识点材料，不把正在运行、失败、附加材料或 Agent 自报完成计入。结构任务只显示耗时和当前阶段，直到结构事务提交后再显示真实知识点数量。

图书馆 OCR/解析属于文档服务。教材工作台可以把已完成的来源准备显示为历史里程碑，但不能把它伪装成当前 `more-to-skills` 阶段。没有实际学生状态分析时，也不展示“正在分析你的学习状态”。

## 11. 安全与非目标

- 不修改 `more-to-skills` 的转换逻辑或脚本输出。
- 不恢复旧 `.langalpha/progress.jsonl`、progress helper 或旧教育进度表。
- 不解析 Bash 命令、stdout、文件正文或 reasoning 来猜阶段。
- 不允许模型提供 job/item/attempt 身份或完成计数。
- 不承诺百分比、token 进度或剩余时间。
- 第一版不把进度协议开放给普通聊天或用户自定义 Skill。

## 12. 验收标准

- 普通 PTC Agent 看不到 `report_progress`；教材托管 Agent 可以调用。
- 未知阶段、跨 item 阶段和模型自由文案不能进入公开活动。
- 结构、材料、附加材料只接受各自阶段词表。
- Agent 完全不调用进度工具时，任务仍可正常成功并显示正确终态。
- 进度工具调用失败、重复、乱序或迟到不改变 job/item 状态。
- “完成 N/M”只随成功提交事务变化，刷新和跨 worker 重连后保持一致。
- timeline 主视图不泄露工具参数、结果、路径、教材正文或思维内容。
- 活动不可用与任务失败在 UI 上保持不同语义。
- 分页中途断线不跳过未消费事件，空页不推进消费游标，缓存丢失可从有界账本恢复。
- 没有语义事件、活动预算耗尽或明细不可用时，当前 item 与材料计数仍可通过任务级快照刷新收敛。
- 新增 progress 子对象不删除或改写已有 task.json 身份与产物契约。

## 13. 与总计划的实施边界

独立实施计划的 Task 1–4 对应总计划 Task 4A：发送工具、阶段契约、活动投影，以及必要的任务快照读取和 SSE 接口。Task 4A 复用已完成的 Task 4，不提前重写完整教材门面、学生 API 或工作台。

独立 Task 5 随总 Task 5 实施；独立 Task 6 随总 Task 8 汇总验收。完整教材门面及消费者接线仍归总 Task 5/6，一次迁移切换仍归总 Task 7。Task 4A 的完成条件仅为其后端聚焦验证通过，不以尚未开发的工作台或全链浏览器验收为前置条件。
