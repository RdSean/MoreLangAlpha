# 教材业务动作时间线设计与实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让用户看到真实发生的跨学科加工动作及可靠提交结果，完成后仍可回看；上报不改变讲义要求。

**Architecture:** 沿用 `report_progress`、教育活动账本和 SSE。在现有 stage 上增加可选 action，服务端按 item/stage 白名单翻译文案。Skill 先决定实际工作再选择报告，界面保存业务历史，工具日志默认隐藏在诊断明细。

**Tech Stack:** Python/LangGraph、async psycopg/PostgreSQL、React/TypeScript、pytest/Vitest/Playwright。

---

**状态：用户已批准，本增量已实施并通过聚焦与两项真实加工验收。** 本文是[总实施计划](2026-09-30-more-to-skills-implementation.md) Task 4/4A/5 的增量补充，验收并入 Task 8。保留[原语义进度设计](2026-10-02-managed-textbook-progress-design.md)及其[实施计划](2026-10-02-managed-textbook-progress-implementation.md)的历史记录；实际证据及限制见[本增量验收记录](2026-10-03-textbook-business-activity-results.md)。总 Task 8 仍未完成。

## 设计边界

- 用户已认可动作可选、工具日志隐藏、进度与提交分离；词汇专用动作改为跨学科的“澄清概念与术语”。后续实施以本补充调整 10-02 设计中“只突出当前阶段”“不修改 Skill”及工具/语义共用全部预算的旧限制，其余既有契约继续有效。
- `report_progress(stage, action=None)`：stage 保留原契约；action 是受限标识符，不接收正文、自由文案、业务 ID、完成计数。artifact_id 保持 stage，payload 增加可选 action。observer 按绑定 item 和 stage 校验 action，中文只能由服务端映射。
- 材料动作：补充前后文背景、解读原文图表、澄清概念与术语、安排讲解顺序、整理原文示例、编写辅助示例、组织练习解析、核对来源与引用。动作依据内容和原有要求选择，概念可来自数学/科学/语言/人文；例子、图表、练习不能因可报告而新增。
- 结构和全书附加材料保留已有阶段说明，本轮不扩展其动作词表。每项任务只下发适用 action 的 stage、公开说明和触发条件，列表不是必做清单。
- Skill 增加通用可选报告约定和局部提醒；无工具、无匹配动作或上报不可用时继续原加工。禁止用 shell 伪造报告，禁止重试进度导致工作循环。工具及提示不把 stage/action 顺序当状态机。
- 历史语义事件按 seq 展示，连续相同 item/stage/action 合并，跨动作回退保留。进入动作只用中性标记；只有服务端 succeeded 提交事实用完成标记。运行中仍突出当前动作；终态不展示假当前阶段。
- 诊断明细默认收起，展开才渲染底层工具行；业务视图不展示 Bash/Edit，也不通过解析工具参数猜业务动作。
- 总明细预算仍为 1000 条/1 MiB，单条 2 KiB/512 字符。工具最多占 800 条/768 KiB，在相同 PG 锁事务中检查，使至少 200 条/256 KiB 的总容量不会被工具消耗；业务事件已消耗的容量不重复预留。工具预算耗尽只停止工具投影，语义仍可写；总预算耗尽才停止所有明细，省略摘要继续合并。终态仍在原事务内写入。
- 客户端 1000 条保留策略优先保留非工具事件，剩余位置保留最近诊断行，所有事件消费游标仍正常推进。无新表、无迁移、无运行时调度变化。

## Task 1：工具与教育动作契约

Files: `src/ptc_agent/agent/tools/report_progress.py`、`src/server/services/education_book_progress.py`、`src/server/services/education_book_activity.py`、`src/server/services/education_book_jobs.py`；对应 unit tests。

1. 红测试：工具透传合法 action，非法 action 不发送且不阻断；observer 翻译受控文案，拒绝跨 stage/item action，节流按 stage/action 分开。
2. 最小实现：可选 action 参数；材料任务 `allowed_actions` 带 stage/message/when；现有无 action 调用与记录继续可读；不允许模型 status/message 覆盖公开内容。
3. 验证：`uv run pytest tests/unit/ptc_agent/agent/tools/test_report_progress.py tests/unit/server/services/test_education_book_progress.py tests/unit/server/services/test_education_book_activity.py tests/unit/server/services/test_education_book_jobs.py -q`。

## Task 2：保护语义预算

Files: `src/server/database/education_book_activity.py`、`src/server/services/education_book_activity.py`、`tests/integration/test_education_book_activity_stream.py` 及 observer unit tests。

1. 红测试：工具预算耗尽后合法语义仍存储；混合批次剩余工具正确累计；真实 PG 行数/字节两种工具上限都不能耗尽语义预留，终态/旧 attempt fence 不变。
2. PG 聚合同时计算总明细与工具行数/字节，在现有 job/item 锁内做拒绝决策，新增 `tool_budget_exhausted` outcome；observer 分别处理工具/总预算。
3. 隔离数据库串行验证：`TEST_DB_NAME=langalpha_test uv run pytest -m integration tests/integration/test_education_books_db.py tests/integration/test_education_book_jobs_db.py tests/integration/test_education_book_activity_stream.py -q`。不得与该库活 worker 同时运行，开发库与共享 Redis 不作为故障目标。

## Task 3：业务历史与隐藏诊断

Files: `web/src/pages/Education/components/bookActivityProjection.ts`、`web/src/pages/Education/components/BookActivityPanel.tsx`、`web/src/pages/Education/queries.ts`、`web/src/pages/Education/__tests__/BookActivityPanel.test.tsx`、`web/src/pages/Education/__tests__/BookActivityQueries.test.tsx`、`web/e2e/education-textbook-workbench.spec.js`。

知识点标题接线另涉及 `src/server/database/education_book_jobs.py` 的 `get_book_job_for_parent`、`src/server/app/education/book_models.py` 的 `BookJobItemResponse`、`web/src/pages/Education/types.ts` 的 `BookJobItem`；测试补在 `tests/integration/test_education_book_jobs_db.py`、`tests/unit/server/app/education/test_book_models.py` 和上述前端测试。

1. 红测试：完成后仍可读实际语义动作，进入动作不是成功；重复相邻动作合并，回退/不同 item 不合并；工具只在手动打开诊断后存在；大量工具不会挤掉语义历史。
2. 在任务快照补充服务端知识点标题，按细则 D 实现知识点分组及当前对象标注；保持 seq 顺序与数据库 item 决定当前动作。默认隐藏诊断，键盘可打开；依照 DESIGN.md 使用共享 Loader。
3. 聚焦 Vitest、Playwright、build/typecheck 和改动文件 ESLint。桌面/375px 验证终态历史、诊断开关、刷新回放和宽度。

## Task 4：Skill 行为与收口

Files: `plugins/langalpha_local/skills/more-to-skills/SKILL.md`、`src/server/services/education_book_jobs.py` 的 `managed_item_prompt`、`tests/unit/server/services/test_education_book_structure.py`、`tests/unit/server/services/test_education_book_jobs.py`、总计划/语义计划/Task 8 记录、`CHANGELOG.md`。

1. 修改前独立 Agent 应用场景基线：纯数学定义无例题、语言定义带原文例子、CLI 无进度工具。记录原行为，不宣称模拟等同真实教材模型运行。
2. 最小 Skill 增补：内容要求优先，动作列表可选；在读取上下文、组织模板、写材料及校验附近提示按真实动作报告。无工具时不改变产物；无图表/例题时不添加对应内容。
3. 修改后独立 Agent 重跑场景，加入报告不可用和尝试目录外动作的情形；后者由 observer 拒绝，不假设通用工具能收到教育白名单拒绝的 ACK。保留原内容范围。自动化测试证明提示/契约暂存、公开投影及 UI 闭环，真实模型验收另行如实标记。
4. 核对无用户加工中的 run 后再决定后端是否需要重载；保留 5177/8000，实测 LAN 可达。更新中文日志、检查 diff、原子提交。Task 8 剩余存储/恢复/普通产品验收不因此自动完成。

## 开发细则 A：动作契约与通用性

动作以认知/加工行为命名，不以学科或输出模板命名。“通用”表示多个学科能够按需使用，不表示每次加工必须调用。第一版只给 `material` 下发以下八项；structure/supplementary 继续使用原阶段。不得给材料自动加词汇站、例题、练习或图片来填满列表。

| action | allowed stages | 服务端中文 | when（下发给 Agent 的条件） |
|---|---|---|---|
| `reading_context` | `material_reading` | 正在补充前后文背景 | 当前内容确需参考相邻原文、目录或已有材料；只引用实际读到的内容 |
| `examining_visuals` | `material_reading` | 正在解读原文图表 | 来源中确有相关图表，且当前实际读取、解读；不为此新增图片 |
| `clarifying_concepts` | `material_organizing`, `material_writing` | 正在澄清概念与术语 | 正在梳理定义、概念关系、术语含义；覆盖数学、科学、技术、人文和语言，不要求词表 |
| `organizing_explanation` | `material_organizing` | 正在安排讲解顺序 | 正在决定本份材料的讲述次序；不表示学生学习状态分析或全课程规划 |
| `explaining_source_examples` | `material_writing` | 正在整理原文示例 | 原文确有相关例题、案例、代码或例句，当前正在讲解它们 |
| `creating_examples` | `material_writing` | 正在编写辅助示例 | 原有任务/材料深度确需新增解释性例子且未被用户禁止；上报权限本身不授权新增内容 |
| `explaining_exercises` | `material_writing` | 正在组织练习解析 | 当前任务范围内确有待讲解的练习，且当前实际处理；不要求非练习类材料新增练习 |
| `checking_sources` | `material_validating` | 正在核对来源与引用 | 实际核对来源、引用和锚点；这条声明不证明校验已经通过 |

“原文示例”替代仅适合数学的“原文例题”，但原文已有与模型补充必须分开。无法找到匹配 action 时只报告原 stage，或者不报告；不提供自由文案兜底。不根据文件名、Bash 命令或模型思考文本推断动作。

任务契约的新增部分示例（其余身份、来源、输出字段保持原样）：

```json
{
  "progress": {
    "tool": "report_progress",
    "allowed_stages": ["material_reading", "material_organizing", "material_writing", "material_validating"],
    "allowed_actions": {
      "clarifying_concepts": {
        "stages": ["material_organizing", "material_writing"],
        "message": "正在澄清概念与术语",
        "when": "当前正在梳理定义、概念关系或术语含义；不要求新增词表。"
      }
    }
  }
}
```

上面只展示一个 action，实际 material 任务下发上表八项。非材料任务下发空 `allowed_actions` 对象，所有返回容器都是新对象，避免调用方修改模块词表。stage/action/message/when 由 `education_book_progress.py` 同一目录生成；Skill 不复制固定动作码目录，前端不维护另一份中文映射。

一次真实调用及事件示例：

```python
report_progress(stage="material_writing", action="explaining_source_examples")
```

```json
{
  "artifact_type": "report_progress",
  "artifact_id": "material_writing",
  "status": "running",
  "payload": {"stage": "material_writing", "action": "explaining_source_examples"}
}
```

工具只校验标识符格式/长度（stage 与非空 action 均为 `[a-z][a-z0-9_]{0,63}`），不导入教育白名单；observer 校验 item → stage → action 的组合。无 action 时使用 stage 文案，有 action 时使用 action 文案。未知、跨类型或跨阶段 action 整条忽略，不能退回 stage 后冒充成功接受，也不能写入正文/用户提供的 message/status。合法事件入库仍为 `kind=progress, status=running`，metadata 只含 stage 和可选 action。

工具返回“已报告”仅意味着已交给 stream；持久化失败仍沿用 `activity_status=unavailable`，不得把工具返回值当数据库 ACK。非法参数返回固定短提示并继续任务；工具缺失/返回不可用后停止尝试报告，继续产物工作。工具执行器对类型错误的既有处理不应因该工具改写；正常的受限错误不应成为教材失败理由。

节流键从 stage 扩展为 `(stage, action-or-empty)`：同动作一秒内合并，不同动作即使同一秒发生也保留。dedupe key 沿用服务绑定的 item/attempt 并包含 stage/action/时间桶；核对最长组合不超过当前 255 字符限制。有限白名单使节流状态本身有界。真实回退、重试允许再次进入动作，不推导百分比或完成状态。

## 开发细则 B：Skill 修改草案与发布约束

修改位置限定在 `plugins/langalpha_local/skills/more-to-skills/SKILL.md`，不顺便重写模板族、内容深度或解析脚本：

1. 在 Modes 前增加“可选的宿主进度报告”小节。下面是待实施的正文草案，并非已修改 Skill：

   > 先按用户范围、来源内容与材料深度决定实际工作，再从宿主提供的进度契约中选择匹配的阶段/动作。该目录是可报告的词表，不是必做清单，也不规定顺序。不要为了上报新增例子、练习、词汇板块或额外材料。
   >
   > 当前环境确有契约指定的进度工具时，在进入有意义的新动作时报告一次；同一动作中的连续读写无需逐次报告。找不到匹配动作可以仅报告阶段。没有工具或契约则照常工作，不安装工具、不写 shell 命令模拟事件。报告不可用时停止报告并继续加工，不反复重试，也不把报告当成产物或校验结果。

2. 在 Step 7“模板族：先定族，再填骨架”旁提醒：只报告实际发生的组织/概念处理动作，报告词表不决定模板族。
3. 在 Step 7“每条 KP 一次调用：要喂什么”旁提醒：上下文/图表动作以实际读取为准，空来源不能报“已读图表”。
4. 在材料写入/校验的说明旁提醒：原文示例与补充示例按来源区别，提交前的报告只是进入核对动作；完成与入库由宿主确认。
5. Step 3/Step 8 至多引用一次上述通用约定，仍使用各自允许 stage；不得以新材料 action 跨类型调用。frontmatter 不把可选宿主工具变成 CLI 的必需依赖。

`managed_item_prompt` 保留 normal Read/Bash/ExecuteCode 能力，只补一句以任务 progress 目录和 Skill 的可选报告约定为准。tool docstring 说明 action 参数及报告不可用的处理，遵守 `src/tools/AGENTS.md`，不重复整份八项词表。

**必须先处理 Skill 摘要变化的真实影响：** 当前 `_validate_book_execution_identity` 会拒绝“入队后 Skill 改变”的任务；Skill 目录 manifest 摘要有固定单元测试。开发者在修改实际 Skill 文件前，应只读核对本开发环境的 queued/running 教材任务、相关 runtime 和精确进程工作目录；有在途任务时先完成不影响其身份的测试/文档工作，等其正常结束再切换 Skill。不要改旧 job 的摘要，也不要绕过身份校验以让旧队列继续跑。

修改后用现有 `get_more_to_skills_identity()` 计算真实摘要，更新 `test_education_book_structure.py` 的锁定值并复验暂存/只读封存。schema 没变则 schema 摘要和 schema 版本应保持原值。新 job/retry 路径现已读取当前 identity，需用测试核对；不引入第二套摘要计算或版本迁移。生产滚动发布若允许旧队列持续存在，需要另行设计版本路由，本轮本地空队列切换不冒充已解决该场景。

## 开发细则 C：预算和异常处理

采用“总上限 + 工具子上限”，不是固定把语义限制为 200 条。工具最多 800 条/768 KiB，业务语义可使用所有尚未消耗的总明细预算。例如只有语义事件时，仍可最多 1000 条/1 MiB；总容量中至少 200 条/256 KiB 不会被工具占用，但应扣除业务事件自身已经消耗的份额，不能承诺任意时刻仍有这些空余。终态继续走原有预算豁免事务。

在现有按 job 索引的有界聚合中增加 `FILTER (WHERE kind='tool')` 的 count/sum；继续使用现有 job/item `FOR UPDATE` 和 attempt fence，避免两 worker 分别判断还有容量后同时超额。这里只做短 SQL 事务，不在锁内访问模型、Redis 或存储。采用 Postgres best-practices 的短事务原则，不新增容量表或跨进程内存计数器。

预算结果处理表：

| outcome | observer 行为 |
|---|---|
| stored / duplicate | 沿用已有行为；仅 stored 发布提示 |
| stale | 拒绝旧 attempt，不产生业务事实 |
| tool_budget_exhausted | 只关闭本 attempt 的后续工具明细投影，合法语义仍尝试写入；后续工具计入省略摘要 |
| budget_exhausted | 沿用总预算耗尽降级，后续合法公开事件只累计省略摘要 |
| 写入异常 | 沿用停止详细投影和持久 `activity_status=unavailable`；不改变任务执行/提交结果 |

工具与总预算在同一事务中判定：对工具先检查工具子上限，再检查总上限；达到工具子上限绝不能设置全局 `_budget_exhausted`。一条事件放不下即进入相应预算降级，不追求填满最后几个字节。仍保持所有实际写入总和不超过上限。

省略摘要仍每 job 一条，不扩展为每工具/每动作一条；重复工具批次剩余项、开始/结果对、合法语义和未知语义的统计规则必须分别覆盖。工具自身的 report_progress 开始/结束、raw delta、未知或被节流的 action 不计省略。摘要更新至少间隔一秒，流结束 flush 最后计数。

观察器新增工具预算状态只属于当前执行上下文。新的 observer/worker 必须重新由 PG 判定预算，不能依赖旧进程标志。已有历史 job 超过新工具子上限时停止新增工具记录，保留原数据；没有清空历史或迁移行为。

## 开发细则 D：前端业务历史、诊断和游标

`projectBookActivity` 输出业务时间线，保留服务事实和通过现有 item/stage 检查的 progress，按 seq 排序。action 文案直接来自受控 API `message`，不再建立一份前端翻译表。旧的 stage-only 事件同样能成为历史，不因扩展 action 消失。

### 知识点对象与标题分组

“位值”是被处理的知识点，不是新增 stage/action，也不由 Agent 上报。当前已具备 `event.item_id → job.items[].knowledge_point_id` 关联，但任务快照没有知识点标题，活动面板也尚未按标题展示；本补充明确将这部分接线纳入 Task 3。

- **标题来源：** 在已授权的 `get_book_job_for_parent` 查询中，复用现有知识点 LEFT JOIN，将 `points.title` 投影为 item 的 `knowledge_point_title: string | null`，同步后端 DTO 与前端类型。非 material item 返回 null。使用已入库教材结构的标题，不另让模型生成，不从事件正文、文件名或当前阅读选中项猜测；不新增数据库列或迁移。
- **事件归属：** observer 继续绑定可信 item 身份，`report_progress` 参数不增加知识点 ID、标题或序号。前端用事件 `item_id` 查该 job 的 item，再取标题；标题只在快照中提供，不复制进每条进度 metadata，也不新增“知识点标题”事件。
- **历史分组：** 先按 seq 排序并按原规则合并重复动作，再将相邻同 item 的业务行放进带标题的组。分组身份是 item_id，不能用标题；同名知识点保持独立。不同 item 或 job 级事件打断组；同 item 之后再次出现则重复组标题，不为凑成整组而重排事件。工具行不影响业务分组。
- **显示标签：** 材料组标题为“知识点：位值”。若显示顺序，使用“本次任务第 N 项”（来自 item.position），不能把批量选中的第一项写成全书“知识点一”。structure/supplementary 分别显示“教材结构分析”“全书附加材料”；`item_id=null` 的任务级事实或省略摘要单独显示，不归到最近一个知识点下。
- **当前对象：** 正在执行时在当前动作旁显示数据库 running item 的对象名称，例如“位值 · 正在整理原文示例”。尚无动作时可显示“位值 · 正在生成讲义”；无 running item 时只展示任务级等待/处理说明，不将最近成功项或当前阅读页当作正在加工对象。历史中同一当前动作避免重复播报。
- **完成与回放：** item 状态与计数仍来自服务端快照，提交行来自既有可靠服务事件；组标题本身不表示已开始或已完成，也不生成成功事件。无 Agent 进度也可显示已收到的服务事实。终态与刷新后仍通过任务快照和事件回放恢复标题及分组，不依赖当前章节选择。
- **缺失与文本安全：** material 标题为 null/空白时显示“讲义任务（本次第 N 项）”；事件 item_id 暂无法匹配快照时显示“教材处理项”，保留事件和顺序，不借用其他项标题。标题按普通文本渲染，不解析 HTML/Markdown，长标题换行。标题来自当前已入库结构，本轮不承诺独立的历史标题版本快照。

预期展示示例（动作是否出现以真实报告为准）：

```text
知识点：位值
  正在澄清概念与术语      ← Agent 进度，中性标记
  正在整理原文示例        ← Agent 进度，中性标记
  讲义已提交              ← 服务端提交事实
知识点：小数比较
  正在澄清概念与术语      ← 属于另一 item，不与上一组合并
```

### 业务行与诊断规则

业务行规则：

- 忽略穿插的工具行后，相邻相同 item/stage/action 的进度合并为一行，保留最后 seq/时间；阶段回退 `A → B → A` 保留三次，跨 item 不合并，服务事实打断合并。只是显示合并，游标必须消费每条事件。
- Agent 声明使用中性动作标记；当前动作可用共享 Loader。不得将原始 `running` 历史改成 `succeeded`，也不因为后续动作出现就打完成勾。
- 可靠 succeeded 服务事实才有完成标记，failed/cancelled/省略各按实际类型表示；预算摘要不显示绿色勾。完成数量仍来自 job/items，不从动作条数推导。
- 活跃时当前动作以数据库运行 item 为准；item 改变且暂时没有动作时显示该 item 的通用说明。完成后不显示当前 spinner，但业务历史保留。避免“头部当前动作 + 时间线最后一行”重复朗读同一段状态。
- 暂不可用时保留之前收到的历史并显示说明，当前描述回退到任务快照；不能伪造后续动作。

“诊断明细”默认关闭，按钮可通过键盘打开，`aria-expanded` 与实际渲染同步。关闭时底层事件列表不挂载到 DOM；打开后可读，再关闭不会丢失其缓存或改变阅读位置/URL。切换 job 时恢复默认关闭，同一 job 新事件不强制展开。可采用受控 details 或 button + 条件列表，选项目现有可访问模式。客户端仅隐藏展示，不另外建立日志数据库。

**显示缓存与消费游标必须拆开。** 当前 `useBookActivity` 用 `eventsRef.current.at(-1)?.seq` 重连；业务优先保留后，最新已消费的工具事件可能不在缓存中，继续这样取游标会反复重放。实施时增加仅属该订阅的 `lastProcessedSeqRef`：

1. 只在页面成功解析并合并后，用页面事件的最大 seq 推进；空页/只有 high_water 不推进。
2. 同一 job 前后台或订阅重建使用独立消费游标，不从渲染后的、折叠后的或淘汰后的数组取值。
3. job 切换、授权失效或 `cursor_expired` 重置游标与缓存；旧订阅 disposed 后不能写入新 job 的游标。
4. 新窗口/刷新无本地缓存时从零回放。终态必须读完 `has_more`，不因为快照已经 succeeded 就提前结束。

合并后仍限 1000 条：优先保留最近的非工具事件，再用最近工具事件补足剩余位置，最后统一按 seq 排序。如果非工具自身超过 1000，保留最近 1000，避免承诺无限历史。省略摘要在服务端更新 seq 后，客户端应以该 job 的预算摘要身份替换之前摘要，避免“同一摘要移动 seq”变成多条里程碑；当前只有 `kind=summary,status=truncated` 的预算摘要，实施时核对分类范围，不吞掉其他业务事件。保留末次消费游标始终独立于此合并。

## 开发细则 E：测试用例与命令

所有测试先出现预期失败再实现。修改行为契约时同步更新旧断言，禁止仅删失败测试。下列步骤按序执行，实际改动文件及命令结果记入本计划最终检查点。

| 层 | 必须增加/调整的行为测试 |
|---|---|
| tool | stage-only 形状不变；合法 action 发出；无效 action 格式/超长不发送；stream 不可用不抛出业务失败；公开 payload 无自由文本/身份 |
| contract | 八项 action 覆盖上述条件；非 material 空 action；返回副本可修改不污染目录；清晰区分原文示例与辅助示例；不以学科作为必选流程 |
| item title/API | 授权快照中的 material 标题与关联知识点一致，非 material 为 null；DTO 可接收缺失标题；跨家庭不能读取标题；Agent 事件不能覆盖快照标题或身份 |
| observer | stage/action 同秒不同动作保留；同动作一秒内节流；未知、跨 item/stage action 拒绝；模型 message/status 不生效；原有 stage-only 仍可接收 |
| budget unit | 工具封顶后仍接收语义；工具批次剩余项和结果正确计省略；report_progress 自身噪声不计；总预算耗尽/unavailable/final flush 沿用 |
| PostgreSQL | 行数先达工具上限、字节先达工具上限两种场景；新的 observer 不能绕过；并发连接不超总额；保留语义与同事务终态；迟到 token 不写入 |
| projection | 完成后仍有业务历史；动作进入无完成勾；相邻重复合并但回退和不同 item 保留；不出现工具正文；stage-only 历史能读 |
| item grouping | 两知识点的同一动作分别展示；同名不同 item 不合并；A→B→A 保持顺序并重复组标题；任务级事件/摘要独立；标题缺失安全回退；子集任务序号不冒充全书顺序；无语义报告仍可展示服务事实 |
| query hook | 超过 1000 混合事件后语义保留；最新事件被淘汰后重连仍用已消费游标；后台恢复、旧响应、cursor_expired、终态分页均不退化；预算摘要移动不会累积多份 |
| component/browser | 诊断关闭时 Bash/Edit 不在 DOM；键盘打开/关闭；375px 无溢出；reader scroll/URL 不变；成功后刷新仍有业务历史；unavailable 不假装任务失败 |
| title rendering/browser | 当前对象与 running item 一致，切换阅读章节不改变加工对象；任务完成/刷新后仍能恢复标题分组；长标题与含 HTML 字符标题以纯文本安全换行 |

后端聚焦命令（worktree 根目录）：

```bash
uv run pytest tests/unit/ptc_agent/agent/tools/test_report_progress.py tests/unit/server/services/test_education_book_progress.py tests/unit/server/services/test_education_book_activity.py tests/unit/server/services/test_education_book_jobs.py tests/unit/server/services/test_education_book_structure.py -q
uv run pytest tests/unit/server/app/education/test_book_models.py -q
TEST_DB_NAME=langalpha_test uv run pytest -m integration tests/integration/test_education_books_db.py tests/integration/test_education_book_jobs_db.py tests/integration/test_education_book_activity_stream.py -q
```

前端聚焦命令（`web/`，沿用独立 5176/4100 E2E 配置，不占用户端口）：

```bash
pnpm exec vitest run src/pages/Education/__tests__/BookActivityPanel.test.tsx src/pages/Education/__tests__/BookActivityQueries.test.tsx src/pages/Education/__tests__/TextbookWorkbenchPage.test.tsx
pnpm exec playwright test e2e/education-textbook-workbench.spec.js --project=chromium
pnpm build
pnpm exec eslint src/pages/Education/components/BookActivityPanel.tsx src/pages/Education/components/bookActivityProjection.ts src/pages/Education/queries.ts src/pages/Education/__tests__/BookActivityPanel.test.tsx src/pages/Education/__tests__/BookActivityQueries.test.tsx
```

后端改动文件单独执行 Ruff check/format check；完成这一功能批次再在根目录执行 `uv run pytest tests/unit -q`、`make lint`，在 `web/` 执行 `pnpm test`。前端已有 Plugins storage-throws 失败仅作为既有记录，不能预先假定此次仍是同一失败，也不顺便修改无关模块。没有新代码或新失败时不反复跑全量检查。

## 开发细则 F：Agent 场景验收与证据范围

修改前已完成一次只读独立 Agent **提示应用基线**，不是实际生成/工具调用：数学定义与前缀说明均选择原四个 stage；CLI 无工具时不报告；显式用户限制下没有硬加例题/词汇。失败点是当前契约无法表达细动作，不能把基线写成“已经观察到 Agent 硬加例题”。Agent 对上报不可用的处理来自它对 optional 的解释，原 Skill 没有明确约定。

修改后使用同样输入和约束比较以下场景，输出实际选择、产物内容范围、调用序列、次数及失败回退：

| 场景 | 应出现/允许 | 必须不出现 |
|---|---|---|
| 数学定义，只要短摘要，无例题练习 | 概念梳理、必要的讲解组织/来源核对；也允许只报 stage | 为填时间线新增例题、练习、词汇站 |
| 语言前缀，只解释给出的两个例子 | 概念与术语、原文示例 | 新增例词、强制词表、把两个原例报为模型新增 |
| 技术代码/人文案例 | 确有相关来源时用“原文示例” | 仅因学科非数学而拒绝示例动作 |
| 用户要求辅助例子，原文无示例 | 编写辅助示例 | 声称整理原文示例 |
| 有图表与无图表两份来源 | 只在实际读取相关图表时报告解读 | 无图也报告解读，或只拿到占位路径就声称读过图 |
| 无进度工具或返回不可用 | 内容工作继续；不可用后停止报告尝试 | 安装工具、模拟事件、重试循环或拒绝产物 |
| 动作不在目录/跨 stage | 忽略报告，继续实际工作 | 动态扩大白名单或更改工作来适配词表 |
| 合法动作重复、交错、回退 | 根据实际工作选择，无强制顺序 | 为一次性完成清单而伪造阶段 |

独立 Agent 提示应用实验只能证明它如何理解说明。功能交付前还应在专用验收教材上做真实托管模型运行，沿用已获授权账号的现有配置、不复制凭据；至少覆盖数学无示例约束和语言原文示例两个输入，核对产物及数据库/SSE/browser 的 action 一致性。若只完成模拟或仅有单次真实成功，按实际范围报告，不宣称所有模型均保证及时上报。

记录同一模型/相同材料/深度下新旧运行的总工具调用数、progress 调用数、耗时和实际可取得的 token 数据。报告会增加开销，少量样本只用于发现明显回归，不写吞吐或零开销承诺。验收失败时先判断动作约定还是原有模板导致内容变化；原有模板的跨学科扩展另列事项，不在这次事件改动中偷偷重写。

## 实施顺序、提交与完成条件

1. **检查点 P0：本文档。** 用户审阅后再开始产品开发；本轮仅文档，不运行模型或修改数据库。
2. **P1：代码红测试。** 明确工具/observer/query/终态展示的预期失败。先完成契约和预算，再做前端；诊断默认隐藏的行为用 DOM 可见性与挂载检查双重验收。
3. **P2：后端与 UI 绿测试。** 原活动协议保留，不新增 chat SSE 类型，不改变教育 run admission/finalize/retry。对齐新 UI 和 stage-only 历史后进行浏览器验证。
4. **P3：Skill 变更。** 核对无旧身份在途任务后修改 Skill、摘要锁定与提示，跑修改前后场景和真实模型验收。不能用取消用户任务来腾出验收窗口。
5. **P4：收口。** 更新总计划 Task 4A/5 补充、Task 8 新验收记录及语义计划，中文 CHANGELOG，提交已验证的完整功能。可以把契约/预算和 UI/Skill 分为内部原子提交，但须在最终交付前使整条链一致，不能仅交付隐藏日志就宣称业务时间线完成。

本补充完成需同时满足：真实动作可接收并可回放；完成后历史仍可读；普通视图无底层工具日志；工具压力不挤掉预留业务预算；重连不依赖显示缓存；数学/语言场景无因上报而产生的内容扩张；现有提交/取消/fence/权限不退化。阶段可以缺失，未发生的动作不强求覆盖率。

总 Task 8 的真实 MinIO/COMMIT ACK、模型完成后跨进程提交恢复、家长 cookie 添加与普通产品 live 剩余项仍保持未完成。本补充的老压力结果也只代表旧预算：新工具上限生效后必须重新验证，不能把过去“1000 工具明细”数字当成新版本预期。

## 当前检查点

2026-10-03：开发计划细则已补写，待用户审阅后开发。本轮只创建/修改计划与索引文档；产品代码、Skill、数据库和运行服务均未修改。已完成只读代码依赖检查和一次提示应用基线，未执行本计划中的红绿测试、真实模型加工或浏览器验收。

同日补充：明确知识点标题由授权任务快照提供，前端按 item 身份分组并标注当前对象；补齐 API/类型接线位置、缺失标题回退、同名/子集/回放规则与验收。仍仅修改文档，未实施。

### 用户批准后的实施检查点

- P1/P2 已完成：工具/observer/预算/title 红绿测试，后端契约提交 `a4fb1bc9d`；前端业务历史、诊断折叠、游标与授权失效处理提交 `26a4e0882`。聚焦后端 119 passed、真实 PostgreSQL 三套 45 passed、前端聚焦 49 passed、工作台 Chromium 11 passed。
- P3 已完成：修改 Skill 前开发库 queued/running 教材任务为 0；增加通用可选报告及局部提醒，不改模板/脚本/schema。Skill manifest 为 `46ca820bfd66b3adaba0b8cbd405e71af27276caf891202c8376a3897c961495`，schema/version 不变。修改前后只读独立 Agent 场景符合内容范围，但基线本来也没有硬加例子，不能记为真实模型失败到通过。
- 专用教材经正常图书馆 PDF 上传/解析、真实结构分析后，数学无例题摘要与语言两原例讲义分别成功。实际接收 action，PG 与完整 HTTP SSE 逐条一致；工作台桌面/375px 可回放知识点及动作，默认无工具行，展开可读。没有修改用户原教材、账号配置或数据卷。
- P4 已完成：更新总计划与语义计划/Task 8 索引及中文日志；保持本开发分支与 5177/8000，本机/LAN HTTP 200。全量后端 7928 passed；前端全量 2592 passed、1 个既有无关 Plugins storage-throws 失败，build/typecheck/lint 通过。未合并、推送或删除 worktree。
- 限制：新旧真实运行不是同材料/深度的配对实验，现有托管运行未持久化 token usage，不能量化进度上报的额外 token 或吞吐。新的工具压力以真实 PG 并发/预算测试验证，旧 150001 delta 组合实验没有在新版本重跑。总 Task 8 原有存储/COMMIT ACK、完成结果跨进程提交恢复、家长 cookie 添加及普通产品 live 剩余矩阵继续保持未完成。
