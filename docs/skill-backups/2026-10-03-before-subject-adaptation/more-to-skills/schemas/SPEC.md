# Book Structure JSON — 格式规范（SPEC）

> 版本：`schema_version = "2.1.0"`
> 机读定义：`schemas/book-structure.schema.json`　校验器：`tools/validate_structure.py`
> 压测实例：`tools/fixtures/example-book-structure.json`（真实书、真实行号，不是格式定义本身）
> 切分样本：`tools/fixtures/example-segments-u01.json`（模型的 3D-b 输入样例，配合它跑 `tools/build_knowledge_points.py`）

---

## 1. 这个文件解决什么问题

把**一本书**的章节结构，落成一份**机读的、递归的、可回指原文**的 JSON。两个消费场景：

1. **建树与回读**：数据库/界面加载它渲染树状目录；用户点任一节点，用 `anchor` 的行号区间直接切出原文，不需要重新解析 PDF。
2. **挂接附加材料**：节点（或知识点）上的 `content_file` 指回该单元的材料（讲义、词汇、习题解析）。

由此推出三条硬要求：**锚点必须精确到可切片**、**层级必须能无限递归**、**格式必须与书种无关**。

### 三条设计红线

**① 与书种无关。** schema 里没有任何教材专有字段。「单元 / 课时 / 板块」这类概念不写进字段名：

- 层级名称不写死，由 `level_names` 按书声明。教材是 `unit / lesson / section`，专著是 `part / chapter / section`，论文集是 `section / chapter / article`。
- 深度不写死，`children` 递归。
- 编号体系不写死：`number` 是**字符串**，`1`、`1.1`、`第一章`、`IV`、`A` 一律原样保存，不做数值解析。
- 页码体系不写死：`page_range` 允许为 `null`，且**锚点才是主定位手段**，页码只作展示辅助。
- `type` 只描述**内容性质**，不描述「第几级」——那是 `level` 的活。

**② 单源假定。** 一份结构 JSON 对应**一个源文件**，锚点因此只需 `start_line` / `end_line`，不需要声明「在哪个文件里数」。若一本书确实分属多个文件（正文 + 附录），两条路：先合并成一份文本再处理，或分别跑两次、各自出一份 JSON。

**③ 只有"格式"是硬的。** 校验分三层，只有 L1（格式门）会阻断流程。有序性、重叠、包含这类**跨记录推理**出来的问题只报告 —— 解析质量差的书不该因为"结构不够漂亮"而处理不下去。详见 §8。

---

## 2. 版本策略

- `schema_version` 为 `MAJOR.MINOR.PATCH`。
- **MAJOR**：破坏性变更。`2.0.0` 相对 `1.0.0` 的破坏点：`sources[]` 改为单 `source` 对象、锚点去掉 `source_id`、移除 `stats` / `role` / `attributes` / `path` / `sha256`、`type` 词表含义改变。消费方只应比较 MAJOR，不同 MAJOR 必须拒绝加载。
- **MINOR**：新增可选字段、扩充推荐清单取值。**`2.1.0` 相对 `2.0.0` 只加了可选的顶层键 `knowledge_points`**——不给这个键时，文件与 2.0.0 完全等价，旧消费方与旧产物都不受影响。
- **PATCH**：文案与描述修正，不影响数据。

---

## 3. 文档骨架

```jsonc
{
  "schema_version": "2.1.0",
  "generator": { "name": "more-to-skills", "version": "2.1.0", "generated_at": "2026-09-30T15:10:00+09:00" },
  "book":     { "title": "...", "title_source": "normalized", "language": "en" },
  "source":   { "path": "...", "format": "markdown", "total_lines": 6384, "anchor_mode": "source_lines", "line_offset": 4 },
  "level_names": ["unit", "lesson", "section"],
  "nodes":    [ /* 顶层节点数组，子层级递归在 node.children */ ],
  "knowledge_points": [ /* 可选：可独立学习的知识块，见 §6.5 */ ],
  "coverage": { "scope": "...", "excluded": [], "omitted": [], "gaps": [] }
}
```

必需键：`schema_version` / `book` / `source` / `nodes` / `coverage`。`generator` / `level_names` / `knowledge_points` 可选。

**未知键一律允许。** schema 不设 `additionalProperties: false`——书种特有的信息（作者、版次、DOI、阅读技能名……）**需要就自由加键**，不列进 schema、也不校验。

---

## 4. 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | string | ✅ | `X.Y.Z` |
| `generator` | object | | `name` / `version` / `generated_at`（RFC3339 带时区偏移）。记下谁生成的、什么时候 |
| `book` | object | ✅ | 见下 |
| `source` | object | ✅ | 锚点坐标系的唯一来源，见 §5 |
| `level_names` | array\<string\> | | 第 1..N 级的典型名称。缺省时下游按「第 N 级」显示 |
| `nodes` | array | ✅ | 至少 1 条顶级节点 |
| `knowledge_points` | array | | 知识单元：可独立学习的知识块，与 `nodes` 是两层平行视图。见 §6.5。**缺省表示本次不产出知识单元** |
| `coverage` | object | ✅ | 见 §7 |

### `book`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ✅ | 书名 |
| `title_source` | enum | | `original` / `normalized` / `generated` |
| `language` | string | | BCP-47，如 `en` / `zh-CN` |

`authors` / `original_title` / `subtitle` / `edition` / `series` / `volume` / `publisher` / `published_year` / `isbn` / `extent` 等**都不在 schema 里**——需要就自由添加。**未知的数值（如页数）不得估算，宁可留空。**

---

## 5. `source` 与锚点坐标系

锚点行号属于哪个文件、按什么规则数，全部由 `source` 声明。这是整个格式最关键的一节。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | string | ✅ | 绝对路径。**下游回读原文以它为准**——这是格式里唯一的文件入口 |
| `filename` | string | | |
| `format` | enum | | `markdown` / `text` / `rst` / `adoc` / `html` / `pdf` / `epub` / `docx` / `rtf` / `mobi` / `azw` / `azw3` / `other` |
| `total_lines` | integer | ✅ | `anchor_mode` 所指那个文件的总行数 |
| `source_total_lines` | integer\|null | | 原始文件（抽取前）的物理行数。与 `total_lines` 不一致说明清洗动过行结构 |
| `anchor_mode` | enum | | `source_lines` 或 `workdir_lines` |
| `line_offset` | integer\|null | 条件必填 | `source_lines` 时必填 |
| `workdir_text` | string\|null | 条件必填 | `workdir_lines` 时必填 |
| `page_label` | string\|null | | `pages` / `sections` / `spine_items` |

### 两档锚点模式

**`source_lines`（文本类格式：markdown / text / rst / adoc）**

这类格式的抽取是**逐行原样搬运**，只在前面加了一个三行 SOURCE 横幅加一个空行。因此存在恒定偏移：

```
原文件行号 = full_text 行号 − line_offset
```

实测：单源 Markdown 文件 `line_offset = 4`（第 1 行在 full_text 的第 5 行）。**这个偏移必须由抽取脚本写进 metadata，不能由模型推算。**

此时 `total_lines` = 原始文件的行数，`anchor` 里的行号可直接用 `sed -n '<start>,<end>p' "$path"` 切片。

**`workdir_lines`（PDF / DOCX / EPUB / HTML 等）**

这类格式的抽取不是逐行搬运，原始文件也没有稳定的「行」概念。此时 `anchor` 的行号指向 `workdir_text`（即 `full_text.txt`），`line_offset` 为 `null`。下游必须读 `workdir_text`，或改用 `page_range` 定位。**切勿把这类锚点当作原文件行号使用。**

### 行号口径（必须与下游一致）

- **行号一律 1 起、闭区间**，计数方式等同于 `text.splitlines()`，也就是 `sed -n '<N>p' <file>` 的行号。注意它比 `wc -l` 可能多一行——文件末行没有换行符时，`wc -l` 不数它，但 `sed` 会。
- **`line_offset` 由抽取脚本写入 metadata，不是模型推算的**。实测单源 Markdown 为 4。
- `source_total_lines` 用于**漂移检测**：抽取时会做一次不可见字符清洗，若清洗删掉了行分隔符，行数就会变，锚点随之整体错位。两者不一致时校验器报 L2-08，此时不要相信行号。

---

## 6. `node` 与递归

必填只有三个字段：`id` / `title` / `anchor`。**其余全部可选，缺省有明确语义。**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | 全书唯一、跨文件引用的稳定键。`^[a-z0-9][a-z0-9._-]*$`，≤64 字符。**不承载位置语义**：删除或省略节点后，其余节点的 `id` 不需要改动，允许跳号 |
| `title` | string | ✅ | 非空。原文标题，或清洗/生成的标题 |
| `anchor` | object | ✅ | `{ start_line, end_line }`，指向 `source.path` 的行号闭区间 |
| `title_source` | enum | | `original` / `normalized` / `generated` |
| `type` | string | | 内容性质，见 §6.1。**推荐清单，不校验** |
| `level` | integer | | 层级深度，第 1 级为 1。**缺省时按 `children` 嵌套深度推导** |
| `order` | integer | | 同一父节点下的次序号。**缺省时按数组顺序推导**。允许跳号，不要求 `1..n` 连续 |
| `number` | string\|null | | 原书印刷编号，原样保存 |
| `original_title` | string\|null | | 清洗前的原始标题文本 |
| `page_range` | object\|null | | `{ start, end, label, source }`，`source` ∈ `toc` / `printed` / `derived` / `unknown` |
| `summary` | string\|null | | 一句话概要（可为中文）。**不得整段摘抄原文** |
| `keywords` | array\<string\> | | |
| `processed` | boolean | | **本次是否处理了该节点正文**。结构登记与内容处理是两件事：整本书的结构应完整登记，但只有被要求处理的节点才 `processed: true` |
| `content_file` | string\|null | | 相对**输出根**的附加材料路径 |
| `notes` | array\<string\> | | 解析异常、层级可疑等人工说明 |
| `children` | array | | 无子节点时给空数组；**缺省等同空数组** |

### 6.1 `type` 推荐清单

**抽象原则：`type` 只回答「这段内容是什么性质」，不回答「它在第几级」。** 位置由 `order` / `anchor` 管，层级由 `level` / `level_names` 管。旧的 `unit` / `chapter` / `lesson` / `reading` / `video` 全被去掉，因为它们混了「层级名」和「教材版式」，换一本书就不成立。

| `type` | 性质 | 论文 | 技术书 | 数学教材 | 英语教材 |
|---|---|---|---|---|---|
| `front_matter` | 正文之前的附属材料 | 摘要、目录 | 前言、目录 | 前言、目录 | Scope & Sequence |
| `body` | **叙述主体的一节**（篇/章/节/课，不管原书叫什么） | 绪论、方法、结论 | 第 N 章 | 第 N 章 / 节 | Unit、Reading A |
| `exercise` | 需要读者作答或动手 | 习题、证明题 | 习题 | 习题、例题 | 各类练习 |
| `reference` | **查阅型**清单，不是用来通读的 | 参考文献 | 索引、API 速查 | 公式表 | 词汇表 |
| `back_matter` | 正文之后的附属材料 | 致谢、附录 | 附录、致谢 | 附录 | Credits、Index |
| `other` | 兜底 | | | | |

**这不是受控词表。** 校验器不检查取值，不在清单里只给一条 L3 提示。你（或模型）按书种自制 `type` 完全合法——例如数学书用 `theorem`、法典用 `article`。

### 6.2 `level_names` 与 `type` 的关系

`level_names` 是该级的**典型名称**，供界面显示（例如第 1 级显示为「单元」）。它与该级节点的 `type` 不要求对应——第 1 级若混入 `front_matter` 节点，`level_names[0]` 仍可写 `unit`。机器语义一律以 `type` 为准，`level_names` 只影响显示。

### 6.3 各类书的映射建议

| 书种 | `level_names` | 典型 `max_depth` |
|---|---|---|
| 教材 / 教辅 | `unit` / `lesson` / `section` | 3 |
| 学术专著 | `part` / `chapter` / `section` | 2–3 |
| 论文集 / 编著 | `section` / `chapter` / `article` | 3 |
| 技术手册 / 规范 | `chapter` / `topic` / `procedure` | 3 |
| 行业报告 | `chapter` / `section` / `subsection` | 2–3 |
| 学位论文 | `chapter` / `section` | 2–3 |
| 小说 / 传记 | `part` / `chapter` | 2 |

`type` 在各书种里的取值见 §6.1 的表，与上面的 `level_names` 是**两个正交维度**。

### 6.4 锚点的取值规则

- `start_line` = 该节点**自身标题所在行**（标题丢失时为它能确定的最早内容行）。
- `end_line` = 下一个兄弟节点开始前的最后一行；最后一个兄弟取父节点结束前的最后一行。
- 父节点的锚点是**包络**，不是子节点的严格并集：父可以外扩，以容纳自身标题行，以及位于第一个子节点之前的导语内容。
- 若某处因解析产物质损而划不出可信区间，**不要伪造锚点**：把该处记入 `coverage.gaps`，并给该节点 `title_source: "generated"`。
- **人工增删节点后建议重算祖先的区间包络**。`id` / `order` / `level` / `title` 不同步都只会得到 L2 报告，不影响流程；但父子区间关系坏了，下游按树切片就会串行（见 §8 末）。

---

## 6.5 `knowledge_points`（知识单元）

### 它解决什么

`nodes` 是一棵**穷尽登记**的导航树：书上印了几个标题，树里就有几个节点，方便定位与回读。但**「可独立学完的一块内容」并不等于「一个标题层级」**——同一篇课文可能要被切成两块，相邻的词表与词缀链接要合成一条，热身题则根本不该单独成篇。

用层级表达不了这件事：实测同一单元里既有 1 拆 3、也有 5 合 1，还有整体跳过。任何「取第 N 层」的规则都产不出这个结果。

所以设一个**平行数组**：`nodes` 管导航与穷尽登记，`knowledge_points` 管交付粒度。两者用 `nodes` 字段互相引用，谁都不必迁就对方。

### 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | 全书唯一。约定形如 `<unit-id>-k<序号>`，序号允许跳号 |
| `title` | string | ✅ | 知识点标题。**通常是生成的**（模板「主题 : 侧重点」），不是书上的原标题——书上叫 `Analyzing Infographics (1)`，这里写 `Analyzing Infographics (Reading Skill)` |
| `anchor` | object | ✅ | `{ start_line, end_line }`。**是消费范围的包络**，因此起点常早于正文标题——它吃进了相邻的热身/练习板块 |
| `unit` | string\|null | | 所属顶级节点的 `id`，供分组与计数。不改动 `nodes` 就能重组视图 |
| `nodes` | array\<string\> | | 覆盖的结构节点 `id`（反向引用）。合并成一条时列全部被合并的节点。用于 UI 跳转与 DB 外键 |
| `blocks` | array\<int\> | | 消费的块编号，来自 `tools/split_blocks.py` 的 `blocks.json`。**是可追溯的中间物**，不参与下游定位 |
| `content_file` | string\|null | | 生成后的材料路径，相对输出根。`null` = 尚未生成。相当于「这条材料还没做」的标记 |
| `notes` | array\<string\> | | |

除 `id` / `title` / `anchor` 外全部可选。**锚点仍是这里唯一的硬要求**——有它才能回读原文。

### 三种粒度操作怎么表达

| 想要的效果 | 怎么写 |
|---|---|
| **拆分**（一篇课文切成 2 条） | 两条 KP，`anchor` 各自落在同一个结构节点的区间内；`nodes` 都引用那个节点 |
| **合并**（词表 + 词缀链接 → 1 条） | 一条 KP，`nodes` 列两个节点，`anchor` 取两者的包络 |
| **丢弃**（热身板块不单独成篇） | 不建 KP；把它写进相邻 KP 的 `blocks` 里被吸收，确实无用的记进 `coverage.omitted` |

### 与 `nodes` 的关系约定

- 两层的锚点都在**同一个坐标系**里（`source` 声明的那个）。
- KP 的区间**允许跨结构节点**，但不允许在同一个 `unit` 内互相重叠（L2-10）——重叠会让下游按 KP 切片时重复取文。
- KP **不要求**覆盖 unit 的全部区间：覆盖不到的部分要么被相邻 KP 吸收，要么记进 `coverage.omitted`。覆盖率过低会得到 L3-09 提示。

### 生成顺序

KP 必须在结构树**通过 L1 之后**才切分，因为 `nodes` 要引用已定稿的节点 `id`。完整流程见 §9 的 Step 3D。

---

## 7. `coverage`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `scope` | string | ✅ | 本次处理范围，一句话说明 |
| `excluded` | array | | 被排除的非正文材料：`{ label, reason, anchor\|null }` |
| `omitted` | array | | 被**有意跳过**的正文内容：`{ label, reason, origin, anchor\|null }` |
| `gaps` | array | | 没人主动决定、纯因解析质量而缺失的内容：`{ label, node_id\|null, reason, severity }` |
| `notes` | string\|null | | 补充说明 |

### `excluded` / `omitted` / `gaps` 怎么分

判据是**两个问题**：它算正文吗？是有人主动决定不处理的吗？

| | `excluded` | `omitted` | `gaps` |
|---|---|---|---|
| 内容算正文吗 | 不算 | 算 | 算 |
| 有人主动决定不处理吗 | 有（**格式约定**，任何书都一样） | 有（**针对这本书**的决定） | **没有** |
| 谁决定的 | 书的版式 | 模型 或 你 | 没人 |
| 例（教材） | 封面、版权页、致谢、索引、图片版权 | 某个没价值的中间练习、你手工删掉的章节 | 图内文字读不到、Video 脚本缺失 |

先问「算正文吗」→ 不算 → `excluded`；算 → 再问「不处理是有人决定的吗」→ 是 → `omitted`（继续问谁决定 → `origin`）；不是 → `gaps`。

`omitted.origin` ∈ `low_value` / `model_dropped` / `manual_removal` / `user_scope` / `unknown`。

**同一段内容会因决定不同落进不同桶**，这是对的：一张信息图「图里的文字没解析出来」= `gaps`（没人决定跳过）；你事后决定「这张图不重要、不建节点」= `omitted/low_value`。

**三者的边界就一条**：`excluded` 是「本来就不是书的主体」，`omitted` 是「本来是正文，被有意跳过了」，`gaps` 是「本来是正文，丢了」。

### 前置/后置材料怎么放

| 材料 | 放哪 |
|---|---|
| 有结构意义的：书名页、目录、序/前言、附录、术语表 | **进 `nodes`**，`type` 用 `front_matter` / `back_matter` / `reference` |
| 纯清单类：致谢、索引、图片版权、广告页 | 进 `coverage.excluded`（不算正文，任何书都一样） |

判据是**它有没有结构**——能当"一节"读的进树，只能当"一页清单"看的进 `excluded`。目录页若含独有内容（如 SCOPE AND SEQUENCE 的能力矩阵），那是正文，进树或 `omitted`。

### 为什么必须登记

校验器会检查：顶层锚点没覆盖到的每一段，都必须能在 `excluded` 或 `omitted` 里找到归属（L3-02）。**登记了才能区分「本来没有」「有意跳过」「丢了」**——尤其 `gaps` 与 `model_dropped` 的区别，事后看 JSON 是分不出来的，所以生成时就要自报。

---

## 8. 校验规则

三层，分层的依据是**这条违规能不能靠一条记录自证**：

| 层 | 判据 | 级别 | 影响退出码 |
|---|---|---|---|
| **L1 格式门** | 只看**单条记录**：字段在不在、类型对不对、它声明的范围自身说不说得通 | ERROR | ✅ 阻断 |
| **L2 一致性** | 要**跨节点 / 跨层级**推理：有序性、重叠、包含 | WARN | ❌ 只报告 |
| **L3 提示** | 完整度、新鲜度、可读性 | INFO | ❌ 只报告 |

退出码：`0` = 无 L1；`1` = 有 L1；`2` = 用法/IO 错误。**没有把 L2 升级为阻断的开关**——书解析得不好时 L2 必然大面积报，用它阻断等于惩罚输入质量。

容错设计：`level` / `order` 缺失**不报错**，按 `children` 嵌套深度 / 数组下标推导后再跑 L2。因此「留白」与「显式给出且自相矛盾」能被区分开。

### L1 · 格式门（ERROR，唯一会阻断的一档）

| # | 规则 |
|---|---|
| L1-01 | 文件可解析为 UTF-8 JSON 对象（非数组、非标量） |
| L1-02 | `schema_version` 形如 `X.Y.Z`，且 MAJOR 在支持集内 |
| L1-03 | 必需顶层键齐全：`book` / `source` / `nodes` / `coverage` |
| L1-04 | `book` 是对象，且 `book.title` 是非空字符串 |
| L1-05 | `source` 是对象，且有非空 `path` 与 ≥1 的整数 `total_lines` |
| L1-06 | `nodes` 是非空数组，每个元素是对象 |
| L1-07 | 每个节点有非空字符串 `title` |
| L1-08 | 每个节点有 `anchor`，且 `start_line` / `end_line` 为整数、`1 ≤ start ≤ end ≤ source.total_lines` |
| L1-09 | `id` 存在、非空字符串、匹配 `^[a-z0-9][a-z0-9._-]*$`、≤64 字符 |
| L1-10 | `type` 若给出须为非空字符串；`title_source` 若给出须在枚举内；`children` / `keywords` / `notes` 若给出须为数组 |
| L1-11 | `level` / `order` 若给出须为 ≥1 整数；`processed` 若给出须为布尔；`number` 若给出须为字符串或 null；`content_file` 若给出须为非空字符串或 null；`page_range` 的取值须合法；`source` / `book` / `level_names` 的枚举与类型须合法；`generator` 若给出其字段须为非空字符串、`generated_at` 须为 RFC3339 |
| L1-12 | `coverage` 是对象且 `scope` 为非空字符串；`excluded` / `omitted` / `gaps` 若给出须为数组；条目的 `label` / `reason` 非空，`severity` / `origin` 若给出须在枚举内；条目的 `anchor` 若给出须满足与 L1-08 同款的范围检查 |
| L1-13 | `knowledge_points` 若给出须为数组；每条须有非空字符串 `id`（同 L1-09 的规则）、非空字符串 `title`、合法 `anchor`（同 L1-08）；`unit` 若给出须为非空字符串或 null，`nodes` 须为非空字符串数组，`blocks` 须为 ≥1 的整数数组，`notes` 若给出须为数组，`content_file` 若给出须为非空字符串或 null |

**净效果：只有「能不能解析、有没有标题、有没有一个说得通的范围」会阻断。**

### L2 · 一致性（WARN，只报告）

| # | 规则 |
|---|---|
| L2-01 | `id` 全书唯一 |
| L2-02 | 同一父节点下显式给出的 `order` 唯一（**不要求连续**） |
| L2-03 | `level` 与 `children` 嵌套深度一致（根为 1，子为父 + 1） |
| L2-04 | 同一父节点下的兄弟区间互不重叠 |
| L2-05 | 子节点区间落在父节点区间内 |
| L2-06 | 兄弟的 `order` 升序与 `start_line` 升序一致 |
| L2-07 | `level_names` 长度 ≥ 实际 `max_depth` |
| L2-08 | `source_total_lines` 与 `total_lines` 不一致（清洗动过行结构，锚点可能错位） |
| L2-10 | 同一个 `unit` 下的 `knowledge_points` 区间互不重叠 |

> **L2-04 / L2-05 不阻断，但代价是真实的**：它们不成立时，下游按树切片原文可能串行（父区间没包住子区间 → 切不全）。建议在**消费端**加一条切片断言，而不是靠校验器拦——毕竟读这棵树的代码是你自己写的。

### L3 · 提示（INFO，只报告）

| # | 规则 |
|---|---|
| L3-01 | 顶层锚点行覆盖率 < 阈值（`--min-coverage`，默认 90%） |
| L3-02 | 存在未覆盖区间，却未在 `coverage.excluded` / `omitted` 中登记 |
| L3-03 | `coverage.gaps[].node_id` 指向已不存在的节点 |
| L3-04 | `content_file` 指向的文件不存在（需传 `--out-root`） |
| L3-05 | `max_depth` 低于下限（`--min-depth`，默认 2） |
| L3-06 | 同一父节点下 `type` 与 `title` 都相同的兄弟（通常是解析重复） |
| L3-07 | 缺 `level_names` / 缺 `generator`；或 MAJOR 与消费方不一致 |
| L3-08 | `type` 不在推荐清单内；`children` 未给出（按空数组处理） |
| L3-09 | `knowledge_points` 对所属 unit 区间的覆盖率低于阈值（`--min-kp-coverage`，默认 80%） |
| L3-10 | `knowledge_points[].nodes` 引用了树中不存在的节点 `id`（引用已失效） |

> L3-09 的判据是**行覆盖**，不是「条数够不够」：知识点的锚点是消费范围包络，正常会吃掉 unit 里的大部分行。覆盖率低通常意味着有整段内容既没进任何知识点、也没登记进 `coverage.omitted`。

### S 层：正式 schema 校验（装了 `jsonschema` 才跑）

| # | 级别 | 规则 |
|---|---|---|
| S00 | INFO | 未安装 `jsonschema` 或找不到 schema，跳过该层并告知 |
| S01 | ERROR | 违反 `book-structure.schema.json`。**该 schema 的 `required` 与 L1 对齐**，因此 L2 / L3 不可能在这里被拦 |

### 未纳入机检的约定（靠生成方自律）

- 未知的 `extent` 等数值必须留空，不得估算。
- `title_source = generated` 的节点应在 `notes` 里说明生成依据。
- 不得整段照抄原文进 `summary`；`summary` 是概括而非摘录。

---

## 9. 生成流程与中断策略

三步闭环，各干各擅长的：

- **A · 骨架扫描（脚本，确定性）**：`tools/scan_outline.py` 逐行抓「像标题的行」——markdown 井号标题、setext 标题、`UNIT n` / `CHAPTER n` / `READING A` / `WARM UP` / `第N章` 等模式——产出候选骨架（行号 + 原文 + 命中模式）。**只找位置，不做判断。** 锚点因此天然精确。
- **B · 语义归一化（模型）**：读骨架与目录页线索做判断：哪些全大写行其实是正文强调、某节该挂到第几级、层级丢失处补哪一级、单元编号从哪来。然后写出 `book-structure.json`，**父区间按子节点包络重算**。
- **C · 校验门（脚本）**：`tools/validate_structure.py` 跑 L1 / L2 / L3。**只看 L1**——L1 通过就进 Step 7/8，L2 / L3 写进报告供人工复核。

**中断策略**：L1 连续 3 轮未通过 → 中断本次运行，写出 `book-structure.partial.json` 与 `validation-report.md`，**不再进入 Step 7/8**。中断原因与违规清单原样保留，供人工判断后重跑。

> 注：L1 只查格式，因此连续 3 轮过不了通常意味着**提取或生成环节有系统性错误**（拿错文件、行号口径不对），值得停下来看，而不是继续调。

### 9.1 Step 3D — 知识单元切分

当需要把书切成「可独立学习的知识块」时，在 **C 通过之后**再跑一小轮三步——形状与 A/B/C 完全同构，都是「**脚本出骨架 → 模型做选择 → 脚本兜坐标**」：

| 步 | 谁做 | 干什么 | 语义判断 |
|---|---|---|---|
| **3D-a** | 脚本 `tools/split_blocks.py` | 把源文件切成带编号的候选块，抽出脚注定义，产出 `blocks.json` | 无 |
| **3D-b** | 模型 | 只回答「哪些块归为一条」，并给每条生成标题 | **全部语义在这里** |
| **3D-c** | 脚本 `tools/build_knowledge_points.py` | 块编号 → 行号，写出 `anchor`，校验后合入 JSON | 无 |

```bash
# 3D-a：按单元范围分块（块编号始终按全文件计，分多次跑不会冲突）
"$PYTHON_BIN" "$SKILL_ROOT/tools/split_blocks.py" "<源文件>" \
  --range <unit.start_line>:<unit.end_line> \
  --json "$OUT_DIR/blocks.json" --render "$WORKDIR/blocks.txt"

# 3D-b：把 blocks.txt 交给模型，产出一份 segments JSON（只有标题与块编号）

# 3D-c：换算锚点并合入
"$PYTHON_BIN" "$SKILL_ROOT/tools/build_knowledge_points.py" "<segments.json>" \
  --blocks "$OUT_DIR/blocks.json" --structure "$OUT_DIR/book-structure.json" --merge
```

**为什么必须两段式**：模型直接输出行号不可靠，而块编号是脚本给的、天然可校验。让模型只做它擅长的事（判断哪些内容该在一块），坐标交给脚本。这也是为什么 `build_knowledge_points.py` 的入参里根本没有「行号」这个字段。

**为什么排在 C 之后**：`knowledge_points[].nodes` 要引用结构节点的 `id`，树没定稿就没有 id 可挂；何况 KP 的锚点包络也要能对齐树节点边界。

**幂等性**：`--merge` 默认**替换该 unit 已有的知识点**（`--no-replace-unit` 可改为追加），因此在同一 unit 上反复调参重跑是安全的。写入前会留一份 `book-structure.json.bak`。

---

## 10. 输出目录布局

产物集中写到运行目录（默认当前工作目录）下的 `output/`：

```
output/<book-slug>/
├── book-structure.json          # 主交付物，格式见本 SPEC
├── book-structure.schema.json   # 本格式的 schema 副本，随数据一起走
├── validation-report.md         # 校验结果（通过也留一份）
├── blocks.json                  # Step 3D-a 的候选块表（可追溯的中间物，供重跑切分时复用）
├── chapters/                    # Step 7 材料；按知识点切时文件名与 knowledge_points[].id 对应
├── glossary.md                  # Step 8
├── patterns.md                  # Step 8
└── cheatsheet.md                # Step 8
```

`book-structure.json` 里的 `content_file` 与 glossary 的条目出处，一律用节点 `id`（或知识点 `id`）而非「Ch N」，使材料可以挂到树的任意层级。

---

## 11. 边界情况处理

| 情况 | 处理 |
|---|---|
| 标题层级丢失（全被解析成同一级） | 按正文线索与目录页重划层级，`title_source: "normalized"` |
| 图注/练习短文被误析成标题 | 不作为节点；在 `coverage.gaps` 或 `coverage.omitted` 登记（区分"没人决定"与"有意跳过"） |
| 正文标题里没有编号（编号只在目录） | `number` 按目录顺序推导，`notes` 说明来源 |
| 编号与顺序不一致（跳号、重复） | `order` 只保证同父唯一与相对次序；原编号原样存进 `number`。**不为了凑连续而给节点补号** |
| 页码体系缺失或是罗马数字 | `page_range` 置 `null`，`source: "unknown"`；只靠锚点定位 |
| 内容被截断（解析产物不完整） | 截断处节点照常登记，`end_line` 取文件末行，并在 `gaps` 里记 `severity: high` |
| 只处理书中一部分 | 结构**完整登记**，被处理的节点 `processed: true`，其余 `false`；`coverage.scope` 写明 |
| 中间若干章无价值、有意跳过 | **不建节点**，但必须在 `coverage.omitted` 登记（`origin: low_value` / `model_dropped`） |
| 事后手工删掉某些章节 | 直接删节点：`id` / `order` / `level` / `title` 都不用改（最多得 L2 报告）。补一条 `coverage.omitted`（`origin: manual_removal`），并**重算受影响祖先的区间包络** |
| 一本书分属多个文件 | 先合并成一份文本再处理（锚点转 `workdir_lines`），或分别跑两次、各出一份 JSON。**不允许一份 JSON 里出现两套行号坐标系** |
| `level` / `order` 留白 | 完全合法：按嵌套深度与数组顺序推导，校验器不报错 |
| `type` 用了清单外的值 | 合法，只给 L3-08 提示。适配新书种时宁可自制也不要硬套 |
| 同一篇课文要切成两条知识点 | 允许，两条 KP 的 `anchor` 各落在该节点区间内、`nodes` 都引用它。但同 unit 内不许重叠（L2-10） |
| 相邻词表与词缀链接要合成一条 | 允许：一条 KP 的 `nodes` 列两个节点，`anchor` 取包络 |
| 某板块（热身、思考题）不单独成篇 | 不建 KP，写进相邻 KP 的 `blocks` 被吸收（锚点因此会向前扩张）；确实无用的记 `coverage.omitted` |
| 知识点覆盖不到 unit 的全部区间 | 正常，只给 L3-09 提示。但要确认漏掉的部分是**有意跳过**（记 `omitted`）还是**解析丢了**（记 `gaps`） |
| 脚注编号在书内重排（每课从 1 开始） | 靠 `{N}----` 页标记归属：定义行必须落在引用所在页或下一页。**绝不能用编号本身去重** |
| 图片是相对路径（`![](hash.jpg)`） | 是**真实路径**，不是占位符。`split_blocks.py` 会解析出 `resolved_path` 并检查文件是否存在，模型可直接读图 |

---

## 12. 增量合入与人工维护（Mode 4）

树不是一次成型的：新解析出一段内容要补进已有树，手工删章节后要留痕。这一节是**改树时的规矩**。

### 合并规则

| 事项 | 规则 |
|---|---|
| 已有节点 | `id` **保持不变**——它是 glossary 与 `content_file` 的外键，断了就找不到出处 |
| 新增节点 | 取一个**新的 `id`**；`order` 取插入位置附近的**未占用整数**，不重排已有节点的 `order` |
| 新增节点的锚点 | 必须落在**同一个 `source`** 的坐标系内。若它落在某个已有兄弟的区间**内部**，那个兄弟必须**让出**这段区间（收窄自己的 `end_line`），否则触发 L2-04 |
| 祖先区间 | **重算包络**（L2-05）。这是唯一必须动手的一项——L2 不阻断，但区间错了下游切片会串行 |
| 冲突 | 新旧内容矛盾写进 `coverage.gaps`，**不静默覆盖** |
| 删除内容 | 删节点即可：`id` / `order` / `level` / `title` 都不用改；补一条 `coverage.omitted`（`origin: manual_removal`），并重算受影响祖先的包络 |

**一处要留意**：若插入点夹在两个已有兄弟之间，`order` 可能取不到「未占用的整数」（如已有 `1,2,3`，要插进 1 和 2 之间）。此时**把该父节点下的 `order` 整体按坐标重排**（只动这一个父节点，`id` 不动），或干脆把该父节点下的 `order` 全部留白、交给下游按数组顺序推导。唯一不能做的是让同一父下出现重复 `order`——那是 L2-02 会反复报的点。

**次序的真实依据是坐标，不是 `order`**。`order` 只是辅助键：它允许跳号，L2-06（次序与坐标同序）也只是报告。所以合入时若两者冲突，以 `start_line` 为准。

### 消费端的切片断言

L2-04（兄弟重叠）与 L2-05（子区间含于父区间）**不阻断**，代价是真实的：它们不成立时，下游按树递归切片可能串行或切不全。

**补偿放在消费端**：读树的代码在 `sed -n '<start>,<end>p'` 之前加一条断言——「本节点区间含于父节点区间，且与相邻兄弟不重叠」，不满足就报错而不是静默切。这比在校验器里阻断更合适：输入质量不该阻断流程，但**读出的数据必须自证可信**。
