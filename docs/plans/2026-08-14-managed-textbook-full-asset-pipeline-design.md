# 受管教材完整资产管线设计与评审规范

## 背景与结论

家庭教材当前的受管 PTC 任务只把 `book-to-skill` 和
`the-knowledge-guy` 的短受管段落拼进一条提示词，且没有把
`skill_contexts` 传给 Skills middleware。它只回收一份教学包 JSON，因而
无法产出普通 PTC `book-to-skill --complete --practice` 所提供的章节工具包、
全书知识索引、覆盖审计和练习资产。真实任务的长程账本、冻结输入、家庭授权和
私有 `education/` 归档必须保留。

本设计已由产品方向确认：PDF 仍由本地可替换提取器处理；教材教学加工是服务拥有
的 PTC Agent 长程工作，而不是 RAG 或 Celery 固定流水线；家长只面对一个阶段性
任务和审阅界面，不出现第二套聊天操作界面。

## 目标

1. 让两个内置 Skill 真正经 Skills middleware 在同一受管 PTC 根运行中按需激活，
   由 PTC 自己决定读取、调用、回查和汇总的顺序。
2. 从冻结的章节 Markdown 生成可复核的丰富资产，语义上覆盖
   `book-to-skill --complete --practice` 的 map、reduce、audit 和 practice 阶段，
   再由 `the-knowledge-guy` 为中国学生生成教学包。
3. 将经校验的资产写入私有 `education/` 前缀，并向家长提供安全的审阅投影；
   学生仍只消费已发布快照中的教学材料和自动判定题。
4. 保持长程任务的心跳、取消、恢复、immutable attempt、家庭权限和 storage-key
   隔离。失败或重试不能覆盖既有教材、教学包或对象。

## 不纳入本次范围

- 不改变本地 PDF 提取器，也不接入 Datalab、网络抓取或外部 RAG。
- 不向学生开放 Agent 原始工作目录、HTML artifact、模型文本、技能原文或自由聊天。
- 不开放开放题判分、可运行代码实验、富文本编辑或公开 MinIO 链接。
- 不删除、重命名或回填既有 `legacy-local-v1` 教学包。

## 备选方案

### 方案 A：继续单一候选 JSON，只扩写提示词

实现最小，但不能表达章节工具包、知识图谱、审计和练习集，也不能证明来源覆盖；
不采用。

### 方案 B：让服务在一次根运行起始时预注入两份完整 Skill

可使 middleware 实际加载 Skill，但会在任务开始时无条件消耗两份超长交互文档的
上下文，并替 PTC 决定使用顺序；不采用。

### 方案 C：推荐，单一自主 PTC 根运行

服务把两项内置 Skill 的完整静态目录 stage 到本次受管 sandbox，并仅在系统提示中
给出任务目标、冻结输入、输出合同和安全边界。PTC 根据任务自行读取
`book-to-skill`、`the-knowledge-guy` 及其引用资料；PTC mode 的 Skills middleware
在读取对应 `SKILL.md` 时记录实际加载。允许受管的内置子任务继承同一 policy，以便
章节 map/reduce/audit 的调度仍由 Agent 决定；禁止用户配置的子代理、MCP、web、Vault
和普通 workspace。

服务不调度 Skill 阶段，也不消费中间产物来触发下一步。它只维持一个持久 root run、
心跳、取消、恢复和最终 bundle 校验。PTC 自己写出安全的里程碑事件，界面把这些事件
投影成连续进度，而不是第二套聊天或流程控制界面。

## 运行与数据流

```text
冻结内容 Markdown + 完整静态 Skill 目录
  -> 一个受管、持久 PTC 根运行
  -> PTC 自主加载/调用 book-to-skill、the-knowledge-guy 和受限子任务
  -> 章节知识表示、toolkit、practice、coverage audit、concept index、中文教学包
  -> 服务端终态白名单校验与 SHA-256
  -> 私有 education/ 资产 bundle + 数据库安全 manifest
  -> 家长审阅 -> 发布快照 -> 学生学习
```

PDF 提取发生在此链路之前，继续冻结为内容版本。PTC 的全部调度均以同一
`content_chapter_id`、位置和 Markdown SHA-256 为唯一输入事实；重新运行生成新教学
包 attempt，不修改已审阅或已发布版本。

## 受管资产合同 v2

服务根据冻结 manifest 派生每个输出位置，Agent 只能写下列固定相对路径：

```text
outputs/knowledge/concept-index.json
outputs/knowledge/coverage-audit.json
outputs/chapters/<position>-<slug>-knowledge.json
outputs/chapters/<position>-<slug>-toolkit.md
outputs/chapters/<position>-<slug>-practice.json
outputs/teaching-package.json
```

每个 `knowledge.json` 必须包含章节标识、内容哈希、概念、关系、证据摘录定位和
先修关系；每份 toolkit 必须包含学习目标、关键概念、易错点、中文学习者解释、例子
和章内复习提示；每份 practice 包含自动判定题、题目与知识点的逐字关联和题目意图。
coverage audit 必须对每个冻结章节给出覆盖状态、缺项和引用的资产类型。全书
concept index 只可引用已冻结章节及已生成概念。

`coverage-audit.json` 的顶层必须是 `format` 与 `chapters`；`chapters` 是每个
冻结章节恰好一项的数组，每项必须保留冻结 ID、SHA-256、`status: "complete"`、
空 `missing` 和完整 `asset_kinds`。`coverage`、`items` 或其他替代顶层字段不是
兼容形式，必须在候选归档前拒绝。

服务不信任任何模型给出的路径或哈希：它自行构造完整的预期路径集合、逐项直接下载、
限制字节数、解析格式、验证章节集合/哈希/交叉引用和重算摘要哈希。通过后，服务
生成不可变的 `manifest.json`、README 和稳定相对路径，再写入新的
`education/<household>/<textbook>/v<content>/teaching/v<package>/` 前缀。API 只返回
资产种类、章节关联、大小、校验状态和由服务端读取的文本内容，绝不返回 object key、
URL、sandbox 路径、原始模型输出或凭据。

## 持久化与长程恢复

教学 package 保存一份安全 asset manifest：格式版本、内容版本、章节资产摘要、
全书资产摘要、完整性结果和归档时间。数据库保存关系与安全元数据，MinIO 保存可读
资产；任何客户端请求都须先以家长/家庭授权定位 package，再由服务用内部 manifest
读取确定的对象。

一个 attempt 只拥有一个根运行和相应 checkpoint。任务 UI 从 PTC 自主声明、服务端
白名单化的里程碑投影“知识资产构建、覆盖审计、教学材料生成、校验、待审阅”；它们
不是服务对 PTC 的调用顺序。取消由同一根运行接收；恢复只为同一冻结输入建立新
attempt，旧 attempt、checkpoint 引用和 bundle 保持不可变。跨 worker 的真相仍在
PostgreSQL/Redis/现有 RunCoordinator，而不放入模块级内存。

候选已通过校验后，服务先将已验证的固定输出集合和服务生成的教学包暂存到一条
attempt 绑定的内部 PostgreSQL 归档记录，再只对自身派生的同一 `education/` 私有对象
执行有界归档重试。暂存记录是大小受限的可恢复传输副本，不是可读教材的正式来源，
不进入 API、SSE、manifest 或浏览器；MinIO 仍是正式可读资产的唯一存储。当前窗口为
5、10、20、40、60 秒，用于跨越瞬态连接中断。窗口耗尽时，任务投影为安全的
“等待私有归档”可恢复状态；家长的继续操作只重试归档，不创建 PTC attempt、不重跑
已经完成的 Agent 工作。归档成功后删除暂存记录。整个过程不枚举、删除、公开或切换
MinIO 对象路径，取消或新的 PTC attempt 不能让旧暂存记录发布。

## 细粒度进度与长程等待

PTC 在完成真实工作单元后写一条 `EDUCATION_PROGRESS`，但服务不把该事件解释为下一步
命令。允许的 `phase` 为 `planning`、`chapter_mapping`、`concept_linking`、
`coverage_audit`、`practice_build`、`teaching_build`、`bundle_assembling` 和
`validating_bundle`；可选章节和 asset kind 仅可引用冻结章节及固定资产种类。服务从
冻结 manifest 推导总章节数和每章所需资产数，并用本地中文模板生成摘要；模型提供的
自由文本、路径、计数、URL 和错误不会进入数据库或浏览器。

家长运行详情显示最近里程碑、逐章已报告资产类型、总量、开始后的耗时、最近持久心跳
和“正在等待 Agent/模型响应”的安静状态。里程碑在最终 bundle 校验前标记为“Agent
已报告”，终态校验后才标记为“已验证”；页面既有细节，也不把模型自报伪装成服务证明。
浏览器刷新、关闭、SSE 断开和网络安静均不取消任务。

教材任务须使用独立的部署级可配置时限，默认 24 小时，而非短聊天的全局 6 小时。
LocalRunExecutor 的无连接回收和 RunSSEProducer 的硬时限都必须使用这项受管任务值；
超过该期限应生成可恢复、脱敏的失败状态，显式取消始终可用。15 秒 attempt heartbeat、
持久 checkpoint、Redis replay 和 worker 对账继续运行，因此等待不依赖打开的浏览器。

## 家长与学生界面

教材详情继续以“资料、内容、知识资产、教学、审阅、发布、分配”作为单一工作流。
运行抽屉显示阶段、章节进度、尝试次数、可重试状态和安全摘要；它不是聊天窗口。
知识资产标签显示每章覆盖结果、概念清单、toolkit 与题组摘要；教学标签显示面向中国
学生的材料和冻结题。发布保持现有门槛：必须是完整覆盖、校验通过、家长可审阅的
package。学生页面无需改变权限范围，只读取发布时冻结的教学材料和题目。

## 评审规范

合并前和真实服务验收都必须按以下标准逐项给出证据。

| 维度 | 必须满足的标准 | 证据 |
| --- | --- | --- |
| Skill 真实性 | PTC 从 staged 内置目录按需读取 Skill；middleware 记录实际加载的 `book-to-skill` 与 `the-knowledge-guy`，服务不强制其顺序 | 图/Skills middleware 单测、根运行 checkpoint/安全事件 |
| 冻结与覆盖 | 每个冻结章节恰好拥有 knowledge、toolkit、practice 和教学投影；哈希与 ID 全部匹配；coverage audit 必须以 `chapters` 顶层逐章列出完整资产，禁止 `coverage`、`items` 等替代字段 | 验证器/Skill 合同单测、bundle manifest |
| 深度 | 有全书 concept index 和 per-chapter coverage audit；toolkit 包含概念、关系、难点、例子和复习；practice 与知识点双向关联 | fixture 校验、家长审阅 API/UI |
| 中国学生教学质量 | 目标、前置、难点、中文解释、例子和自动判定检查均完整，题目不脱离章节证据 | schema/质量门单测、真实审阅 |
| 安全 | API/UI/错误/SSE 不含 storage key、MinIO URL、sandbox 路径、provider、密钥或原始模型文本 | 负向 API/UI 测试、真实网络记录 |
| 家庭权限 | 只有同家庭家长可查看候选资产和控制任务；学生仅见发布快照且不能写家长字段 | 路由服务单测、真实角色验收 |
| 长程可靠性 | 心跳、取消、恢复和终态对账仍作用于唯一根运行；旧 attempt 不能发布新结果；已校验候选先进入 attempt 绑定的内部短期暂存，私有归档有界退避耗尽后可只重试归档，绝不重跑 Agent | 生命周期/存储故障注入/归档恢复单测、真实长程运行记录 |
| 进度可信度 | 进度由 PTC 自主声明但只接受白名单 milestone；UI 区分已报告与终态已验证，安静等待不误报失败 | parser/DB/UI 单测、真实长程轮询 |
| 存储 | 仅服务端向新 `education/` 前缀写入；不枚举、覆盖或删除无关对象 | storage mock 单测、真实请求/日志边界 |

## 验收定义

完成不以 mock E2E 通过为准。必须在当前 worktree 启动的 `0.0.0.0:5177` 和
`0.0.0.0:8000` 上，使用真实登录家长完成一次 PDF 来源选择、内容提取、受管完整资产
加工和家长审阅。报告须分列真实网络/控制台证据、后端单元测试、mock E2E、构建/lint
和前后端进程来源。安全测试学生存在时，再验证答题与家长只读记录。
