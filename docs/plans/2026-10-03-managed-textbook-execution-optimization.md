# 托管教材执行契约与耗时优化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 消除托管教材任务中已确认的交付冗余和提示冲突，通过同条件小样本确认行为与质量，再进入 REX 3e SB3 大教材实测。

**Architecture:** 继续复用 PTC、sandbox、Skills、SSE、checkpoint 和现有教材提交机制。通用运行层仅增加明确的托管提示选择能力，教材产物与提交职责留在教育模块；宿主契约与 more-to-skills 的托管运行例外同步修订，独立使用 Skill 的流程保持可用。

**Tech Stack:** Python、Jinja2、现有 PTC/LangGraph、PostgreSQL、MinIO、LangSmith、pytest。

---

## 状态与边界

- 2026-10-03：待用户审阅，尚未实施。当前只编写计划，没有启动模型、负载测试或修改运行配置。
- 沿用 worktree `more-to-skills-textbook-refactor`、分支 `feature/more-to-skills-textbook-refactor`，不另开分支。
- 本计划是原重构完成后的独立改进。原 Task 8 与语义进度 Task 6 的完成状态见 [最终收口记录](2026-10-03-more-to-skills-task8-closeout.md)，不倒改已有验收结果。
- 用户已说明大教材测试启动时会另行告知：本计划获准开发，不自动等于获准启动 SB3 或持续负载测试。
- 本轮不加入 Redis 消息队列，不改调度、并发、数据库结构、模型默认值、前端 timeline 或名句冷却；大文件冻结与资产搬运先测量再决定是否另立优化项。
- 保留用户修改的 `docs/plans/2026-10-03-textbook-business-activity.md`，不纳入本计划提交。

## 一、依据与可证明范围

用户提供的 LangSmith trace：`f55f5ae6-6c76-465b-a702-c3c47c3da0e8`，项目 `9127bad0-a474-4e71-a477-5d91947d8d98`。本计划沿用用户提供的计时分析，没有再次独立核算全部 span。

| 证据 | 结论与边界 |
|---|---|
| `ch1-k02`，约 4 行有效原文、无图片、成品约 3,441 字符；graph 79.71 秒 | 是短知识点讲义基线，不代表整本教材结构分析 |
| 14 次模型调用合计 71.17 秒，约 89.3% | 优先检查模型承担的额外工作；不重复累加 model 与内部 LLM span |
| 两轮分别 20.63/21.99 秒，TTFT 0.33/0.37 秒 | 该两轮主要耗在持续输出，不能泛化成所有运行都没有服务端等待 |
| 累计 586.9K tokens | 是多轮累计统计，包含重复上下文及缓存读取，不是一次读入这么大的教材 |
| 代码：所有任务声明 `output.structure`，单篇讲义 finalizer 只读取 Markdown | 已确认交付契约冗余 |
| Skill Step 7 要求回填 `content_file` 并重跑结构校验 | Agent 有依据执行冗余工作，后端与 Skill 必须一起修订 |
| 系统模板包含金融身份、`work/` 目录、TodoWrite 和 `agent.md` 工作流 | 已确认与托管任务不匹配；无法从单条 trace 量化每条提示造成的延迟 |

不承诺提速百分比，不把 3.16 秒结构复制和 2.02 秒结构校验直接等同于可节省的完整时长；模型推演、缓存和调度均会变化。

## 二、设计决策

### 1. 按任务类型明确交付与职责

| 托管任务 | Agent 必交付物 | 保留的输入与检查 | 宿主负责 |
|---|---|---|---|
| structure | `outputs/<slug>/book-structure.json` | 来源锚点、结构与知识点分析、现有结构校验 | 严格导入、事务提交、业务状态 |
| material / 单知识点 | `outputs/<slug>/chapters/<kp-id>.md` | 输入结构、目标 KP 原文、必要相邻上下文、图片/脚注、来源与讲义自检 | 材料存储、材料关联、结构投影中的 `content_file`、成功计数 |
| material / supplementary | 已声明的 glossary/patterns/cheatsheet 三个文件 | 现有结构与材料上下文、对应内容自检 | 附加材料存储与状态，不计入讲义完成数 |

`output.root` 是路径基准，不表示整个目录都是必交付物。只移除材料任务的结构输出要求，不移除结构输入；不能为减少 token 静默丢掉来源图片、脚注或必要上下文。

建议为 `task.json` 增加明确字段：

```json
"delivery": {
  "structure_owner": "host",
  "content_file_owner": "host",
  "completion_owner": "host"
}
```

以上示例用于材料任务；structure 的 `structure_owner` 为 `agent`，另外两项仍为 `host`。契约 schema 版本从 v1 升至 v2，并同步所有消费者、fixtures 和 trace 元数据。字段只表达交付职责，不授权 Agent 修改数据库，也不是新的执行状态机。

Skill 在 Mode 3、Step 7 及交付简报处明确：只有宿主提供该契约时使用托管例外；读取输入结构，但不复制输出结构、不回填指针、不因缺少其他 KP 的材料而补做或修复全书。无该契约的独立模式继续原有回填与校验流程。structure-only 保留现有严格校验。

### 2. 托管系统提示与教材说明分层

- `ManagedExecutionPolicy` 仍是可信服务端入口。系统提示选择根据该入口确定，不从用户文本、书中内容、文件路径或 task.json 任意选择模板。
- 新增通用 `managed_system.md.j2`：中性执行身份、实际托管工作根、只读输入/Skill、可写区域、受限能力、产物与成功确认边界。复用适用的安全规则和真实可用工具说明。
- 托管模板不包含投资研究身份、通用 `work/<name>` 流程、更新 `agent.md`、个人记忆、未启用的子代理/MCP 使用指令。不要通过字符串替换裁剪完整系统提示。
- 教材模式、文件职责、来源要求和进度约定继续由 `education_book_jobs.py` 的任务与提示提供；不在通用 PTC 模板写入教材业务 ID、数据库操作或中文动作字典。
- 保持普通 PTC/Flash/子代理的提示与能力不变。托管模板按现有 lean/detailed 规则组织必要事实与可选指导，不额外复制两套模板。
- 检查最终装配后的消息与 middleware，避免其他注入层再次带入相同冲突。模板文件变短不等于运行时消息已经正确。
- 静态系统提示不加入 execution ID、时间或动态用户信息；实际根目录和当次身份继续走现有配置/运行上下文，保留可复用前缀。不把动态业务字段提前到缓存断点之前。

### 3. 精简工作而不强制固定步骤

材料任务明确目标 KP、深度、必交付路径和完成边界，允许 Agent 根据原文选择必要动作。鼓励直接形成最终文件，避免额外创建完整草稿副本和长篇交付复述；不承诺能够禁止模型内部重复推理。

保留来源核对、图片阅读能力、材料自检与失败修正。重要长工作开始前仍用独立短轮调用 `report_progress`，之后才生成长正文或脚本；不能为了少一轮而与长 Write 参数合并。动作不是必须遍历的清单；不倒填上报，不把进度当成功。诊断心跳、动作预算、失败降级、5 秒名句冷却保持原契约。

## 三、实施任务

以下步骤均在审阅通过后执行。每个代码任务按“先确认当前行为 → 增加有意义的失败用例 → 最小实现 → 聚焦验证 → 中文 CHANGELOG 与原子提交”推进。只有所有提交都完成，才发布对应的新托管契约。

### Task P0：固定基线与发布边界

**文件：** 新建 `docs/plans/2026-10-03-managed-textbook-execution-optimization-results.md`；检查 `src/server/services/education_book_structure.py` 与 `src/server/services/education_book_recovery.py`。

1. 记录基线 trace ID、代码 commit、任务/KP、来源 hash、Skill hash、schema、模型、推理强度、prompt guidance、深度、额外要求、产物长度与质量检查项。取不到的字段标为未知，不能猜测。
2. 同时记录已有业务时间戳与 trace 覆盖范围。旧 trace 无外层耗时的部分标为缺失，不通过相减虚构明细。
3. 检查 queued/running/recovering 任务及冻结 Skill 身份：改 Skill 后尚未 staging 的旧任务可能因 hash 不符被拒绝，不能只看 running 数量。
4. 切换选择无未结束教材任务的窗口；不取消用户任务，不重写旧任务冻结 hash，不禁用身份校验。若有积压，等待排空并保留现有版本服务；不能热加载一半改动。
5. 若需要隔离旧/新服务做配对基线，使用准确 checkout 和独立启动方式；不对用户当前分支做 reset，不让两个 worker 同时争抢同一开发库任务。

**完成条件：** 基线出处与缺失项清楚，安全切换办法确定。此步骤不要求先跑 SB3。

### Task P1：统一材料交付契约与 Skill 托管例外

**修改：** `src/server/services/education_book_jobs.py`、`plugins/langalpha_local/skills/more-to-skills/SKILL.md`。

**测试：** `tests/unit/server/services/test_education_book_jobs.py`、`tests/unit/server/services/test_education_book_skill_staging.py`、`tests/unit/middleware/skills/test_native_book_learning_skills.py`。

1. 增加行为用例：structure 有结构输出；单篇与 supplementary 无结构输出；单篇输入结构/上下文保持；交付职责和 schema v2 一致。核心断言示例：
   ```python
   assert "structure" not in task["output"]
   assert task["delivery"]["content_file_owner"] == "host"
   assert task["output"]["material"].endswith("/chapters/ch1-k02.md")
   ```
   使用现有 item fixture 派生样本，不把以上片段当成完整测试。
2. 运行相应新用例确认旧实现失败；按上表调整构建函数和 managed prompt。
3. 同步修改 Skill 的 Mode 3、Step 7、交付说明，避免仍有无条件回填要求。保持独立 Skill、structure-only 和可选进度的语义。
4. 检查仓库实际存在的 Skill 校验/锁定记录并按已有方式更新；冻结 identity 由现有函数从文件计算，不手填绕过。覆盖旧 hash 被拒绝、新 hash 可 staging 的行为。
5. 验证仅提供讲义文件即可 finalise；不存在输出结构也成功，空/非法讲义仍失败。supplementary 必须三份各自合格，不能因精简契约放松验收。

**命令：**

```bash
uv run pytest tests/unit/server/services/test_education_book_jobs.py tests/unit/server/services/test_education_book_skill_staging.py tests/unit/middleware/skills/test_native_book_learning_skills.py -q
```

**预期：** 全部通过；原文/上下文可用、材料存储和幂等收尾契约不变。单独提交本任务，尚不将中间版本部署给在途任务。

### Task P2：装配受限托管系统提示

**修改：** `src/ptc_agent/agent/agent.py`、`src/ptc_agent/agent/prompts/loader.py`。

**新增：** `src/ptc_agent/agent/prompts/templates/managed_system.md.j2`、`tests/unit/ptc_agent/agent/prompts/test_managed_system_prompt.py`。

**检查/必要时修改：** `src/ptc_agent/agent/managed_execution.py`、`src/server/services/education_managed_runs.py`。

**回归：** `tests/unit/ptc_agent/test_managed_textbook_execution_policy.py`。

1. 先读模板目录 `AGENTS.md`；增加实际渲染与装配测试，覆盖普通/托管及 lean/detailed。测试同时检查安全、路径、可用工具规则保留，避免仅断言删掉若干单词。
2. 用明确的 managed policy 分支选择模板；默认调用仍选择 `system.md.j2`。保留现有模型解析与 capability gate，不新增另一套 Agent 引擎。
3. 依据真实启用能力渲染工具指引，覆盖 Bash/ExecuteCode、图片、可选 progress；禁止模板鼓励调用不可用工具。
4. 核对 middleware 拼出的最终输入、目录信息和缓存前缀：普通运行无变化；托管运行无金融身份和 agent.md 工作要求，真实路径仍可获知。
5. 核对提示变更未赋予额外权限；输入/Skill 只读、路径隔离和受限工具测试继续通过。

**命令：**

```bash
uv run pytest tests/unit/ptc_agent/agent/prompts tests/unit/ptc_agent/test_managed_textbook_execution_policy.py tests/unit/server/services/test_education_book_jobs.py -q
```

**预期：** 渲染和装配均通过；普通提示与能力不发生回归。中文 CHANGELOG 与独立提交。

### Task P3：覆盖进度、提交和可观测性边界

**检查：** `src/server/services/education_book_jobs.py`、`src/server/services/education_managed_runs.py`、`src/server/services/education_book_activity.py`、`src/server/services/education_book_recovery.py`。

**测试：** 现有 book jobs/progress/activity 单测与四套教材集成测试；缺失的计时行为用例补入 `tests/unit/server/services/test_education_book_jobs.py`。

1. 复核阶段上报前置、失败时继续内容工作、业务成功由宿主提交三个边界。不得通过增加虚假报告来满足“首次进度更快”。
2. 先检查现有 trace 和业务记录能否分开以下区间：请求与冻结、等待调度、sandbox 准备、输入/Skill staging、graph、结果校验与存储提交。
3. 仅在有缺口时，给教育服务现有调用边界补最小结构化计时。记录 operation/item/execution/attempt/run 的关联及耗时，不记录正文、密钥或完整工具参数；跟踪失败不影响业务。跨进程恢复记录独立区间，不能伪造连续单进程计时。
4. graph 已有 LangSmith 根 trace，新增外层计时与它关联即可，不为同一模型调用重复建统计层。同进程时长用 monotonic；跨服务时间戳注明来源，嵌套阶段不相加冒充总耗时。
5. 如新增计时，以 mock 时钟验证阶段结束、异常结束与跟踪不可用；不对墙钟性能写易抖动单测。没有缺口则只记证据，不新增指标基础设施。

**命令：**

```bash
uv run pytest tests/unit/server/services/test_education_book_jobs.py tests/unit/server/services/test_education_book_progress.py tests/unit/server/services/test_education_book_activity.py tests/unit/ptc_agent/agent/tools/test_report_progress.py -q
uv run pytest tests/integration/test_education_books_db.py tests/integration/test_education_book_jobs_db.py tests/integration/test_education_book_activity_stream.py tests/integration/test_education_book_storage_faults.py -q
```

**环境约束：** 集成测试按原 Task 8 文档加载隔离库/存储及 opt-in 配置，串行执行；先核实连接目标，不能对开发库套用测试 schema 重建。skip 不算该项通过。沿用 localhost:9000，保留共享容器、挂载目录与无关对象。

### Task P4：同条件小样本对照与质量验收

**记录：** `docs/plans/2026-10-03-managed-textbook-execution-optimization-results.md`。

1. 开发通过后，执行已获用户授权范围内的小样本；真实模型运行使用原家长配置，不复制凭据，使用专用验收教材。新增费用性运行的批次范围在启动前说明。
2. 样本包含原短 KP、一个较长 KP、一个包含相关图片/脚注的 KP。短 KP 建议旧版与新版各 3 次；长/图片各 1 次用于质量与边界，不据此计算稳定 P95。若旧版重跑不可安全获得，则明确只有历史单次基线，降低性能结论强度。
3. 相同来源、模型与推理强度、guidance、讲义深度和要求；记录冷启动/缓存/外部错误。用隔离且内容一致的验收副本，避免重做状态、已有材料或并发干扰对照。旧/新批次存在时间顺序偏差时明确披露。
4. 每次记录受理到可读总时长、上述分段、模型调用数、去重后的模型 span 耗时、输入/缓存/输出 tokens、TTFT（有则记）、工具时长、首次真实语义报告延迟、正文长度、错误/重试。不可取得的指标写未知；不保存或展示模型私有推理正文。
5. 人工核对来源忠实、知识点覆盖、受众/深度匹配、解释正确性、图片/脚注引用、无截断和无跨 KP 越界；与旧产物按同一检查表比较。耗时下降但内容缩水不算优化通过。
6. 核对实际工具轨迹不再出现材料任务为交付而复制结构、回填指针及全书材料存在性校验。合法读取输入结构仍允许。
7. 报告每次值、中位数和范围；不承诺固定百分比。如结果相反，先区分模型波动、内容长度、缓存、外层开销与真正新增工作，再决定是否扩大样本。不要同时改模型或推理强度掩盖结果。

**进入下一阶段的条件：** 交付冗余已从真实轨迹消失，正确性/权限/进度/恢复无回归，代表性材料质量合格；耗时无解释不了的持续退化。速度差异不明确可标注后进入大教材测量，不宣称已证明提速。

### Task P5：REX 3e SB3 大教材测量与后续决策

**启动条件：** 用户明确告知可以启动，P4 条件满足。以下是后续实测方案，不在本次写计划或代码实现中自动执行。

1. 记录来源大小、页数、Markdown 行数/字节、图片数/总字节、解析状态；区分首次上传解析与已有解析产物的“添加并分析”。
2. 完整执行一次结构分析，记录节点/KP 数量、模型轮次/输出量、结构修订与校验次数、资产冻结和 staging 耗时。该次是新版本大教材基线，不冒充旧/新配对提速结果。
3. 从开头/中间/末尾选 10–15 个 KP，覆盖长文本、图片、脚注和跨页；先少量逐项生成，再小批量，检验一份完成即可阅读，以及取消/重试/旧讲义保留。
4. 按真实占比决定下一项优化：若模型建树/切分占主导，单独分析结构任务；若资产复制占主导，再设计按需 staging/冻结异步化；若外部模型限流占主导，再讨论并发和重试。均不在本计划中预设实现。
5. 稳定后另行约定持续负载批次，建议先 2 小时，再按需要 8–12 小时；明确并发、真实模型次数/成本、停止条件与专用数据范围。主要用有界模拟检验资源，再配少量真实任务，不连续无上限生成讲义。

## 四、回归、发布与回退

- 在切换窗口一次启用匹配的 schema、Skill 与 managed prompt，检查全部 queued/running/recovering 项；保留旧版服务直到在途项结束。不能仅重启进程就假定旧冻结任务兼容。
- 代码任务完成后运行后端单测 `uv run pytest tests/unit -q`、`make lint`，记录既有失败与本轮变化；针对改动运行 Ruff。前端未改则不为本计划重复整套浏览器测试，但小样本仍检查工作台的可读、状态与进度真实行为。
- 需要重启时沿用 8000/5177 与现有 .env，先核对无在途任务；不改共享 Docker 资源、不丢失挂载数据。前端继续 `0.0.0.0:5177`。
- 回退采用对应优化提交的可审阅逆向改动，禁止 reset 用户工作。先排空新契约任务，再切回匹配版本；已成功提交的讲义仍由现有材料记录读取，不回滚业务数据。
- 性能结果与质量结果分开写；未执行的 SB3/长负载明确标记未执行。仅在实际验收结束后补充原实施计划的“后续优化”链接，不改变原 Task 8 的完成依据。

## 五、审阅要点

1. 是否同意先修交付契约与托管提示，再小样本验证、最后启动 SB3？
2. 是否接受 Skill 仅增加明确的宿主契约例外，独立模式继续原有行为？
3. 是否接受本轮保持模型/推理强度、调度和前端不变，以便归因？

审阅通过前停留在本文档。开发授权与大教材/持续负载启动分别以用户后续指示为准。
