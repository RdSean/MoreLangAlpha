# 图书馆与教材正式资产集成设计

**日期：2026-09-16**

**状态：已批准。**

## 背景

当前系统同时存在两条资料链路：

- `/documents` 的 Document 知识库支持 PDF 上传、检查、解析任务和
  Markdown/图片 Artifact。
- `/education/textbooks` 的家庭教材库使用独立的 `education_assets` 与
  `pypdf` 提取，再从冻结章节启动受管 PTC 教学加工。

两条链路的入口和存储模型重复。教材加工产物虽然会归档到 MinIO，但只有教材详情页
的受控审阅接口可以读取；知识库无法看到一份解析结果被哪本教材、哪个版本或教学包
使用。用户也容易把 PTC sandbox 误认为正式资产的唯一存储位置。

本设计确定第一阶段的产品边界：图书馆负责高保真资料解析，教材库负责加工、审阅、
发布和学习。两者共享正式资产，但不在第一阶段承担语义结构分析。

## 目标

1. 用户可见的“知识库”统一改名为“图书馆”；现有 `/documents` 路由、Document
   数据领域和 API 路径暂时不改名，避免把文案调整扩大成全栈重命名。
2. 图书馆独立详情页可以查看原文、解析结果和正式教材资产。
3. 教材详情页可以查看来源、教学包和正式知识资产。
4. 正式资产由 PostgreSQL 关系和 MinIO 内容共同承载，不依赖 PTC sandbox 存活。
5. 教材加工可以消费一份或多份完整解析产物，并记录实际来源 provenance。
6. 第一阶段不做 Unit 识别、TOC 标准化、卷子与单元匹配或精确跨来源融合。

## 非目标

- 不要求图书馆解析器输出出版社级 Unit、标准 TOC、页码锚点或章节语义。
- 不把大模型结构分析放进图书馆解析阶段。
- 不在第一阶段实现“RE3 Unit 3 + 英语卷指定题目”的精确绑定。
- 不开放学生进入通用图书馆自选资料。
- 不允许学生使用 PTC、sandbox、Vault、MCP、自定义 Skills 或自动化。
- 不暴露 MinIO object key、签名 URL、sandbox 路径或原始模型输出。
- 不删除或改写既有教材、教学包、发布版本和历史学习记录。

## 术语

### 图书馆

用户可见的产品名称。数据和路由层仍使用 Document、Document Artifact 和
`/documents`。图书馆负责资料保存与高保真解析，不保证语义结构。

### 解析产物

一次完成的 Document Parse Job 发布出的 ArtifactBundle，包括主 Markdown、
嵌入图片、结构化数据和 manifest。解析产物可以独立重复生成；调用方必须引用具体
Artifact，不能只引用会变化的 Document。

### 教材内容版本

教材来源的不可变快照。第一阶段可以引用一份或多份完整解析产物，并把所需内容归档
到 `education/` 私有快照。知识库原文件以后被删除或重新解析，不影响既有版本。

### 教学包

受管 PTC 基于教材内容版本生成的正式教学资产，包括全书概念索引、覆盖审计、逐单元
知识资产、工具包、练习和中文教学材料。教学包只有在服务端校验和归档完成后才进入
`review`，之后可以发布给家庭学生。

### Sandbox

一次受管 PTC attempt 的临时执行环境。Sandbox 可以生成候选和中间文件，但不是
图书馆或教材详情页的正式数据源，也不承担长期查看职责。

## 总体架构

```text
Document
  -> Parse Artifact A/B
  -> Textbook Content Version
  -> Managed PTC Run
  -> Validated Teaching Package
  -> Private MinIO Bundle + PostgreSQL Manifest
  -> Library View + Textbook View
```

PostgreSQL 保存所有权、版本关系、状态、安全 manifest 和 Artifact 引用。MinIO
保存源文件、解析内容、冻结教材快照和正式教学资产。Sandbox 只存在于加工 attempt
的运行期。

图书馆和教材详情是两个只读入口，读取同一份正式资产，不复制两套内容。

## 数据关系

既有 Document、Parse Job 和 Artifact 表保持独立。教育模块新增或调整教材版本到
解析产物的来源关系：

```text
education_textbook_versions
  version_id
  textbook_id
  sequence
  status
  bundle_prefix

education_textbook_artifact_sources
  version_id
  document_id
  artifact_id
  position
  content_sha256
  safe_metadata
```

一个版本可以引用多份完整 Artifact。来源顺序由服务端固定，安全元数据只包含
filename、media type、大小、哈希和用户可见的 Artifact 类型。

旧的 `education_textbook_sources` 和 `education_assets` 保留用于历史版本读取，
不在第一阶段删除。新版本不再通过它们创建来源。

教材内容版本冻结时，服务执行以下步骤：

1. 验证 Artifact 属于当前请求者，且 Parse Job 已完成。
2. 读取精确 Artifact，计算服务端 SHA-256。
3. 把内容写入新的 `education/` 版本前缀。
4. 生成安全 source manifest，记录来源顺序和哈希。
5. 在数据库事务中创建来源关系和内容版本。

正式教材从此只读取冻结快照。删除图书馆文档、创建新解析任务或更换解析器都不会
改变既有教材版本。

## 教学加工

第一阶段有两种合法输入：

- 一份完整解析产物，作为整本教材来源。
- 多份完整解析产物，作为一个来源集合交给 PTC 自行尝试融合。

服务不声称知道来源内部的 Unit 结构。冻结 manifest 使用完整来源列表，不要求
Markdown 已经包含标准章节号。

受管 PTC 的读取边界继续限制在一个 job root：

```text
inputs/manifest.json
inputs/sources/<position>-<slug>.md
inputs/assets/
outputs/...
```

PTC 可以自行选择如何理解和组合来源，但必须只写白名单输出。服务端完成以下校验后，
才把结果视为正式资产：

- 每个来源都存在且哈希一致。
- 输出章节和知识资产引用合法来源。
- 全书概念索引和覆盖审计完整。
- 练习题与知识点关联。
- 输出数量和字节数在限制内。

多来源融合属于实验能力。第一阶段验收只要求来源被正确冻结、传递和记录，不把
Unit 级融合正确性作为发布门槛。

## 页面设计

### 图书馆列表

侧栏、页面标题、移动端导航、空状态和提示文案统一使用“图书馆”。URL 仍为
`/documents`。

### 图书馆详情

新增独立路由：

```text
/documents/:documentId
```

详情页包含三个主标签：

```text
原文 | 解析结果 | 教材资产
```

`原文`复用现有 PDF/文档预览。`解析结果`展示主 Markdown、图片 artifact 和解析
元数据。`教材资产`按以下层级展示：

```text
Document
  Parse Artifact
    Textbook
      Content Version
        Teaching Package
          Whole-book assets
          Unit assets
```

每个教学包卡片显示状态、版本、来源顺序、使用的 Artifact 和正式资产入口。图书馆
只读，不提供加工、取消、发布或分配操作。

当前右侧预览抽屉可以继续作为快速预览，但完整查看统一使用独立详情页。

### 教材详情

现有版本面板调整为：

```text
概览 | 来源 | 教学 | 知识资产 | 学生
```

`来源`展示内容版本实际使用的 Document 和 Parse Artifact，并链接回图书馆。
`教学`展示 PTC 生成的单元、材料和题集。`知识资产`展示正式 knowledge、toolkit、
practice、概念索引和覆盖审计。`学生`保持发布与学习记录。

知识资产只有在教学包完成校验和归档后才出现。运行中的 attempt 不提供半成品预览。

### 学生学习

学生只读取已发布教材：

- 不进入通用图书馆。
- 不查看解析任务、PTC attempt 或正式资产 manifest。
- 不调用 PTC/sandbox。
- 继续使用 assignment 和 unit/chapter 作用域的 Flash 学习会话。

## 状态与失败处理

用户可见状态统一分为：

```text
未解析
解析中
解析失败
已解析
教材加工中
等待审阅
已发布
加工失败
等待私有归档
```

处理规则：

- Parse Job 未完成时，Artifact 不能被教材选为来源。
- PTC 运行失败时不创建正式资产，只显示安全错误和恢复动作。
- 输出校验失败时 fail closed，不把候选写入 review。
- 私有存储暂时失败时保留服务端验证后的内部归档暂存，只重试归档，不重跑 Agent。
- 归档完成后，浏览资产不依赖 Redis 通知、PTC 服务或 sandbox。
- 已发布版本保持不变；重新选择来源或重新加工必须创建新版本。

## 权限

- 图书馆是 parent/owner 能力；学生第一阶段不可访问。
- Parent 可以查看本家庭的教材、来源和正式教学资产。
- Parent 不能通过图书馆接口读取其他用户或其他家庭的 Document。
- 教材来源冻结后，授权以家庭教材关系为准，不依赖原 Document owner 继续存在。
- 学生只读取自己 assignment 对应的已发布教学包。

## API 约束

图书馆继续使用既有 Document、Parse Job 和 Artifact API。新增教材来源查询时只返回：

- Document 和 Artifact 的安全标识。
- filename、media type、大小和 SHA-256。
- Textbook、Content Version、Teaching Package 的安全标识和状态。

教材详情继续使用既有教学包资产 API 读取内容。任何响应都不得包含：

- storage key 或 object URL。
- sandbox 路径。
- 原始 SSE 或模型文本。
- provider 凭据。

## 测试与验收

### 后端

- 新教材版本可以冻结一份或多份已完成 Artifact，并保持来源顺序和哈希。
- 非本人 Document、未完成 Parse Job 和缺失 Artifact 均被拒绝。
- 原 Document 或 Artifact 删除后，教材版本仍可读取冻结快照。
- Sandbox 不存在时，正式教学包和资产审阅 API 仍返回成功。
- 失败 attempt 不产生 review 资产。
- 归档重试不创建新 PTC attempt。
- API 不泄露 storage key、URL、sandbox 路径或模型原文。

### 前端

- 图书馆文案在桌面导航、移动导航、页面标题和空状态中完整替换。
- 独立详情页正确展示原文、解析结果和教材资产。
- 教材详情正确展示来源、教学包和知识资产。
- 加工中、失败、等待审阅、已发布和等待归档状态均可辨识。
- 两个页面链接到同一教学包，不出现重复内容副本。

### 真实服务验收

1. 在图书馆上传并完成一次 PDF 解析。
2. 在教材中选取该 Artifact，创建内容版本。
3. 启动受管 PTC 教学加工并完成正式归档。
4. 关闭或回收 sandbox 后，从图书馆详情和教材详情分别查看同一教学资产。
5. 发布并分配给学生，确认学生只能看到发布内容且没有图书馆或 PTC 入口。

## 后续扩展

以下能力在用户验证多来源融合效果后另行设计：

- AI 结构分析资产。
- 标准 TOC 和 Unit 草案。
- Unit 级来源选择和来源覆盖。
- 卷子题目与教材概念的精确映射。
- 家长确认低置信度结构。
- 学生只读图书馆与自选资料学习。

这些扩展应建立在现有正式资产、来源 provenance 和冻结规则之上，不得重新把
sandbox 变成唯一数据源。
