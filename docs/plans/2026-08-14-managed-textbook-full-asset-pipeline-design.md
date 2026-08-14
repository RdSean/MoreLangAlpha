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

1. 让两个内置 Skill 真正经 Skills middleware 激活，并在相互隔离的受管阶段中
   使用其完整能力边界。
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

### 方案 B：让一次根运行同时注入两份完整 Skill

可使 middleware 实际加载 Skill，但两份超长交互文档同时占用上下文。此前真实运行
已经显示这会诱发压缩和阶段混淆；不采用。

### 方案 C：推荐，阶段隔离的完整受管资产管线

一个家长可见的教学任务拥有连续阶段和同一冻结输入；内部依次运行
`book-to-skill` 资产构建阶段和 `the-knowledge-guy` 教学构建阶段。每个阶段只激活
本阶段的完整 Skill，仍使用受限 sandbox、持久根运行和安全进度投影。阶段输出是
固定白名单资产，服务端逐项下载、验证和归档，而不列目录或接受模型指定路径。

采用方案 C。它保留 PTC Agent 的长程自主处理，同时避免把家长当作等待聊天的操作员，
也不让“阶段摘要”和“原始 PTC 界面”重复出现。

## 运行与数据流

```text
冻结内容 Markdown + manifest
  -> 受管 book-to-skill 阶段
  -> 章节知识表示、toolkit、practice、coverage audit、concept index
  -> 受管 the-knowledge-guy 阶段
  -> 中国学生教学材料、关联知识点、自动判定题
  -> 服务端白名单校验与 SHA-256
  -> 私有 education/ 资产 bundle + 数据库安全 manifest
  -> 家长审阅 -> 发布快照 -> 学生学习
```

PDF 提取发生在此链路之前，继续冻结为内容版本。每个阶段均以同一
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

一个 attempt 可拥有顺序阶段运行记录。每条记录绑定 attempt、阶段名、根运行 ID、
开始/心跳/终态和脱敏错误。任务 UI 仍投影为一条连续状态：知识资产构建、覆盖审计、
教学材料生成、校验、待审阅。取消会阻止后续阶段启动；恢复只为同一冻结输入建立新
attempt，旧阶段和 bundle 保持不可变。跨 worker 的真相仍在 PostgreSQL/Redis/现有
RunCoordinator，而不放入模块级内存。

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
| Skill 真实性 | 每个受管阶段通过 `configurable.skill_contexts` 激活恰当的内置 Skill；不同时注入另一阶段完整正文 | 图配置单测、阶段运行记录 |
| 冻结与覆盖 | 每个冻结章节恰好拥有 knowledge、toolkit、practice 和教学投影；哈希与 ID 全部匹配 | 验证器单测、bundle manifest |
| 深度 | 有全书 concept index 和 per-chapter coverage audit；toolkit 包含概念、关系、难点、例子和复习；practice 与知识点双向关联 | fixture 校验、家长审阅 API/UI |
| 中国学生教学质量 | 目标、前置、难点、中文解释、例子和自动判定检查均完整，题目不脱离章节证据 | schema/质量门单测、真实审阅 |
| 安全 | API/UI/错误/SSE 不含 storage key、MinIO URL、sandbox 路径、provider、密钥或原始模型文本 | 负向 API/UI 测试、真实网络记录 |
| 家庭权限 | 只有同家庭家长可查看候选资产和控制任务；学生仅见发布快照且不能写家长字段 | 路由服务单测、真实角色验收 |
| 长程可靠性 | 心跳、取消、恢复和终态对账仍作用于阶段根运行；旧 attempt 不能发布新结果 | 生命周期单测、真实长程运行记录 |
| 存储 | 仅服务端向新 `education/` 前缀写入；不枚举、覆盖或删除无关对象 | storage mock 单测、真实请求/日志边界 |

## 验收定义

完成不以 mock E2E 通过为准。必须在当前 worktree 启动的 `0.0.0.0:5177` 和
`0.0.0.0:8000` 上，使用真实登录家长完成一次 PDF 来源选择、内容提取、受管完整资产
加工和家长审阅。报告须分列真实网络/控制台证据、后端单元测试、mock E2E、构建/lint
和前后端进程来源。安全测试学生存在时，再验证答题与家长只读记录。
