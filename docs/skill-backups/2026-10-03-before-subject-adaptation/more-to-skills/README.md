<h1 align="center">more-to-skills</h1>


格式定义见 [`schemas/SPEC.md`](schemas/SPEC.md)

<p align="center">
  <strong>把任何一本书、一个文档目录、或一批零散材料，拆成带原文行号锚点的结构化数据与可独立学习的知识块。</strong>
</p>

<p align="center">
  <a href="#-为什么需要它">为什么</a> ·
  <a href="#-它产出什么">产出什么</a> ·
  <a href="#-怎么用">怎么用</a> ·
  <a href="#-它是怎么工作的">怎么工作</a> ·
  <a href="#-不止于书">不止于书</a> ·
  <a href="#-常见问题">FAQ</a>
</p>

**三步：**

***

## 🤔 为什么需要它

你买了一本好书，读了一遍。三个月后，你连第 7 章存在过都想不起来。

常见的绕路都不管用：

**more-to-skills 的做法是：先把书的结构一次性抽干净，让之后的每一次提问都只付「答案」的钱，不用重复付「找答案」的钱。**

结构一旦落成文件，它就不再依赖某一次对话：

***

## 📦 它产出什么

产物落在**当前工作目录**下的 `output/<book-slug>/`：

```
output/<book-slug>/
├── book-structure.json          # ★ 主交付物：递归章节树 + 行号锚点 + 知识单元
├── book-structure.schema.json   # schema 副本，跟着数据走，方便下游校验
├── validation-report.md         # 校验结果（通过也留档）
├── blocks.json                  # 候选块表（中间物，可追溯）
├── chapters/                    # 讲义，文件名对应知识点 id
├── glossary.md                  # 术语表（按字母序，带节点引用）
├── patterns.md                  # 方法 / 模式 / 反模式汇总
└── cheatsheet.md                # 速查表：决策表与快速参考
```

### `book-structure.json` 有**两层视图**，别混

一句话：`nodes` 回答「书里有什么、在哪」，`knowledge_points` 回答「学生该学几块」。

### 三种消费者

**① 下游代码** —— 加载 JSON 递归 `children` 建树、渲染目录；点任一节点，用 `anchor` 的行号区间直接切出原文。

**② 知识点视图** —— 按 `knowledge_points` 分组、计数、逐条勾选生成。

**③ 阅读者** —— `chapters/`、`glossary.md`、`patterns.md`、`cheatsheet.md` 是提炼后的阅读材料，**按需加载**。

***

## 🚀 怎么用

技能安装在 `~/.workbuddy/skills/more-to-skills`，WorkBuddy 会自动发现，**无需注册或安装**。

**最小用法：**

```
用 more-to-skills 拆解这本书：/path/to/some-textbook.pdf
```

也可显式给一个 slug（决定输出目录名）：

```
more-to-skills ./some-textbook.pdf reading-explorer-3-3e
```

支持扩展名：`.pdf` `.epub` `.docx` `.txt` `.md` `.markdown` `.rst` `.adoc` `.html` `.htm` `.rtf` `.mobi` `.azw` `.azw3`；
也接受**目录**与**通配符**（多个文件可合成一份结构）。

### 跑起来之后会被问三个问题

**① 素材属于哪一类？** —— 决定抽取方式。

| 选项            | 抽取方式                                    |
| ------------- | --------------------------------------- |
| 教材 / 教辅       | 源文件是 PDF/DOCX 时**自动改用结构感知抽取**（保住表格与活动框） |
| 技术类（代码、表格、公式） | 结构感知抽取（Docling，约每页 1.5 秒）               |
| 文字类（以散文为主）    | 最快抽取器，通常几秒                              |
| 不确定           | 走快路径，有问题会提示                             |

**② 成本预估，要不要开始？** —— 拆成两段：① 结构 + 切分（便宜，必跑）② 逐条讲义（贵，可分批）。
你可以回「开始」，也可以回\*\*「只要结构」\*\*——那得到的是第 ① 段：**结构 + 知识点，没有讲义**。成本一律报 token 数，不写死金额。

**③ 材料拿来做什么？** —— 决定深度档：

| 档            | 单条篇幅           | 适合               |
| ------------ | -------------- | ---------------- |
| `摘要`         | 约 800 tokens   | 复习速览、检索          |
| **`讲义`（默认）** | 约 3,500 tokens | 学生学习，能直接读懂的讲解    |
| `精讲`         | 约 7,000 tokens | 精读课，含逐句语言点、词源、辨析 |

深度档是**运行参数，不写进 JSON**，随时可换，改了不影响结构。

> 教材类还有三件事会在跑之前讲明（格式使然，不是出错）：
> ① 图内文字抽不出来（信息图、地图上的字是像素），只留一行图片引用；
> ② 答案页与 Video/Audio 脚本常整段缺失（单独成册或只在教师版）；
> ③ 目录页里的课时名会被误当正文标题，程序会剔除。

### 五种模式

| 你说的话                            | 模式                            | 它会做什么                         | 产出                       |
| ------------------------------- | ----------------------------- | ----------------------------- | ------------------------ |
| 给一个文档路径，无其它说明                   | **1 · Full Conversion**（默认）   | 跑完整流程                         | 结构 JSON（含知识点）+ 讲义 + 附加材料 |
| 「只要结构」「先出 json」「不要讲义」           | **2 · Structure Only**        | 跑完结构 + 知识点切分，过校验门即停             | 结构 JSON**（含知识点）** + 校验报告 |
| 给一份**已过校验**的 JSON，要「重做材料」       | **3 · Reading Material Only** | 树不动，可整本重做，也可只做指定的几条            | 材料写回原目录                  |
| 给一份**已存在**的 JSON，要**补录 / 修正结构** | **4 · Update / Fold-in**      | **改树**（先备份）→ 重跑校验 → 只重做受影响的材料 | 更新后的 JSON                |
| 给一份 JSON，要「切知识点」「重新切一次」         | **5 · Knowledge Points Only** | 只重跑切分（替换该单元旧知识点）              | 更新后的 JSON                |

**Mode 3 与 Mode 4 的区别**：Mode 3 只重做材料、**树不动**；Mode 4 是**改树**。
两者的共同前提是既有 JSON 先过 L1 校验门。**它不会静默覆盖**——输出目录已有同名产物会先征求确认。

**关于 Mode 2 与 Mode 5**：`knowledge_points` 是 `book-structure.json` 里的一个键，所以「结构」本该包含它——Mode 2 **默认就切知识点**，不需要额外吩咐。
真想要「只要节点树、连知识点都先不切」，说「**只出节点树**」即可（省一次切分；代价是日后回来补讲义时，粒度会退回节点级）。
Mode 5 是另一回事：它不重跑抽取与结构，**只对已有 JSON 重新切分**，用于调参或重切。

**讲义可以点着做，不必从头顺着跑。** 任意一条知识点都能单独生成——想补哪条、想重做哪条、想跳过前面先做后面，都可以。
材料之间虽然有连载感（开篇承接上一条、收尾预告下一条），但**前文不存在时不会卡住**：程序会用上一条的原文片段、单元目录和相邻标题把上下文补齐，成品照样完整。
唯一的红线是**不许编造前文讲过什么**——只依据真读到的材料或原文。

***

## 🧾 The Discovery Loop Tax

读 PDF 的 agent 并不只是「读」，它在**导航**：反复重取目录、回退、每一轮都把整块重新过一遍。
more-to-skills 把这份结构化成本在转换时**一次性付清**，于是查询成本与答案成正比 ——
相比把整本书灌进上下文，**省 24×–51× 的 token**，这是在真实书籍上测得的。

这个数字是上游 `book-to-skill` 在其产物格式上测的；本分支的产物形态不同，但原理一致：
**成本与输出成正比，而不是与源文件成正比。** 想在自己的书上实测，用 `tools/discovery_tax.py`。

***

## ⚙️ 它是怎么工作的

两半：一个确定性的 Python **抽取器**（文档 → 干净文本 + 元数据），
和一个规范驱动的**生成器**（Agent 按 `SKILL.md` 把文本变成结构化数据）。

`v2.1.0` 的关键设计是\*\*「脚本出骨架 → 模型做选择 → 脚本兜坐标」\*\*：

| 阶段        | 谁做                                | 产出                                      |
| --------- | --------------------------------- | --------------------------------------- |
| 3C 骨架扫描   | `tools/scan_outline.py`           | 标题骨架 + 行号锚点                             |
| 3D-a 机械分块 | `tools/split_blocks.py`           | `blocks.json` —— 候选块表，零语义               |
| 3D-b 语义切分 | **模型**                            | 只输出**块编号分组**（`segments.json` 里没有行号字段可填） |
| 3D-c 锚点换算 | `tools/build_knowledge_points.py` | 块编号 → 行号，包络取值、校验、合入                     |

**模型任何一步都不许直接写行号。** 行号、锚点、块编号一律由脚本产出——这样模型没有机会编造坐标。

校验分三层，写进 `validation-report.md`：**L1 格式门**（唯一会阻断）/ **L2 一致性** / **L3 提示**。
**L2 / L3 不为 0 不代表失败**，但会如实列出。

***

## 🏢 不止于书

名字叫 book，输入其实是任何结构化的长文本。同一套抽取对你会反复翻的东西一样有效：

只要一份文档你重开得足够频繁、频繁到希望自己背下来过，它就是候选。

非教材类书没有预设模板时，Step 7 会退到通用骨架（核心内容 / 脉络 / 术语与表达 / 结构与写法 / 要点 / 关联）。

***

## 🧭 拿到 JSON 之后怎么用

```python
import json
d = json.load(open("output/<slug>/book-structure.json"))

# 建树：递归 children
def walk(node, depth=0):
    print("  " * depth + node["title"])
    for c in node.get("children", []):
        walk(c, depth + 1)
for n in d["nodes"]:
    walk(n)

# 知识点视图：content_file 有值 = 这条讲义已生成
for kp in d["knowledge_points"]:
    print(kp["id"], kp["title"], kp.get("content_file") or "（未生成）")
```

```bash
# 回读原文：用锚点直接切出来
sed -n '337,365p' "/path/to/source.md"
```

`anchor` 是 `{start_line, end_line}`（1 起闭区间，口径同 `sed -n '<N>p'`）；
`content_file` 是**相对路径**，指回 `chapters/` 下那一份。

***

## ⚠️ 最容易踩的六个坑

***

## ❓ 常见问题

**「为什么不直接把 PDF 丢进上下文？」**
因为每次提问都要重新导航——重取目录、回退、重新处理一遍。见上面的 [Discovery Loop Tax](#-the-discovery-loop-tax)。

**我的书是扫描版，能用吗？**
不能直接用。扫描版是没有文字层的页面图片，抽取器会检查前几页并**立刻停下说明**，而不是把整本书跑完再给你一份空产物。先 OCR：

```bash
ocrmypdf input.pdf output.pdf
```

**能一次处理多个文件吗？**
能，但**必须合成一份结构**。一份 JSON 只有一套行号坐标系（单源假定）——多文件要先合并成一份文本，或者分别跑、各出一份，**不允许往同一棵树里塞两套行号**。

**成本怎么算？**
报 token 数，不写死金额（单价与模型名变得太快）。估算会拆成「结构+切分」与「逐条讲义」两段，后者可以分批、可以中途停。

**它会覆盖我已有的产物吗？**
不会。输出目录已有同名产物、或输入本身就是一份旧输出目录时，都会先停下来问你要干什么。

**不是教材，是技术书 / 管理书，可以吗？**
可以。Step 1.5 会让用户选内容类型，非教材类走通用骨架。

**锚点会失效吗？**
会——源文件一改就全失效。这也是为什么 `source` 里记着文件的标识信息。

***

<details>
<summary>🔧 <strong>环境依赖</strong></summary>

抽取器按格式依次尝试多个工具，用第一个可用的。什么都没装时它会告诉你要跑哪条命令。
纯文本、Markdown、reStructuredText 与 AsciiDoc 无需任何额外依赖。

> **一条命令检查环境：** `python3 ~/.workbuddy/skills/more-to-skills/scripts/extract.py --check`
> 会打印每种格式用到了哪个抽取器、以及缺什么时该跑哪条安装命令——不需要提供文件。

**PDF —— 按书的内容类型选工具：**

| 书籍类型              | 工具                    | 安装                               | 速度        |
| ----------------- | --------------------- | -------------------------------- | --------- |
| 文字为主（散文、少表格）      | `pdftotext` (poppler) | `sudo apt install poppler-utils` | ⚡ 瞬时      |
| 文字为主 · 备选         | `pypdf`               | `pip3 install pypdf`             | ⚡ 瞬时      |
| 文字为主 · 备选         | `pdfminer.six`        | `pip3 install pdfminer.six`      | ⚡ 瞬时      |
| **技术类（代码、表格、公式）** | **`docling`**         | `pip3 install docling`           | \~1.5 秒/页 |

> 抽取开始前，技能会问你这本书是**技术类**还是**文字为主**，并自动选工具。
> Docling 保留 Markdown 表格与代码块；纯散文书用 pdftotext 更快。

> **扫描版 PDF 需要先 OCR。** 没有文字层的页面图片——拍下来的或扫描的书——这些工具无从下手。
> 抽取器会检查前几页并立即带说明停下，而不是把整本书跑完却产出一份空结果。自己先跑 OCR，再转换产物：
>
> ```bash
> ocrmypdf input.pdf output.pdf
> ```

**EPUB：**

| 工具                            | 安装                                     | 质量      |
| ----------------------------- | -------------------------------------- | ------- |
| `ebooklib` + `beautifulsoup4` | `pip3 install ebooklib beautifulsoup4` | ⭐⭐⭐ 最佳  |
| 标准库 `zipfile`                 | 内置，无需安装                                | ⭐⭐ 永远可用 |

**其他格式：**

| 格式                                           | 工具                                     | 安装                                   |
| -------------------------------------------- | -------------------------------------- | ------------------------------------ |
| DOCX                                         | `python-docx`（退化：标准库 ZIP/XML）          | `pip3 install python-docx`           |
| HTML                                         | `beautifulsoup4`（退化：标准库 `html.parser`） | `pip3 install beautifulsoup4`        |
| RTF                                          | `striprtf`（退化：正则）                      | `pip3 install striprtf`              |
| MOBI / AZW / AZW3                            | Calibre `ebook-convert`（外部应用，非 pip）    | <https://calibre-ebook.com/download> |
| TXT / Markdown / reStructuredText / AsciiDoc | 内置                                     | —                                    |

</details>

<details>
<summary>📐 <strong>格式规范</strong></summary>

`book-structure.json` 的完整定义在 [`schemas/SPEC.md`](schemas/SPEC.md)，机读定义在同目录的
[`schemas/book-structure.schema.json`](schemas/book-structure.schema.json)。

**若本文与** **`SPEC.md`** **冲突，以** **`SPEC.md`** **为准。**

要点：

</details>

<details>
<summary>📁 <strong>仓库结构</strong></summary>

```
more-to-skills/
├── SKILL.md              # 流水线规范 + 逐步指令（Steps 0–10）
├── schemas/
│   ├── SPEC.md           # book-structure.json 格式规范
│   └── book-structure.schema.json  # 机读 JSON Schema
├── reference/
│   └── parsing-traps.md  # PDF → Markdown 解析坑（P1–P10）
├── scripts/
│   └── extract.py        # 抽取入口包装
├── more_to_skills/       # 模块化抽取包
│   ├── cli.py            # CLI 入口
│   ├── config.py         # 扩展名、路径、依赖常量
│   ├── dependencies.py   # 可选依赖探测 + --check
│   ├── exceptions.py     # ExtractionError（单源失败不影响批处理）
│   ├── sanitize.py       # 隐形字符剥离
│   ├── utils.py          # CLI 解析、多源展平、章节识别、运行器
│   └── parsers/          # 各格式解析器（pdf、epub、docx、html、rtf、calibre、text）
├── tools/
│   ├── scan_outline.py            # Step 3C —— 骨架扫描
│   ├── split_blocks.py            # Step 3D-a —— 确定性分块
│   ├── build_knowledge_points.py  # Step 3D-c —— 锚点换算 + 校验 + 合入
│   ├── validate_structure.py      # L1 / L2 / L3 校验门
│   ├── fixtures/                  # 样例 book-structure.json + segments.json
│   ├── tests/                     # 校验器的 pytest 套件
│   ├── discovery_tax.py           # 上游继承 —— token 成本测算
│   ├── validate_skill.py          # 上游继承 —— SKILL.md 宿主规则审计
│   ├── scan_generated_skill.py    # 上游继承 —— 生成物注入扫描
│   └── evals/                     # 上游继承 —— 合成轨迹评测台
├── SECURITY.md / SECURITY-NOTICE.md
├── LICENSE.md            # MIT（上游 © 2025 virgiliojr94）
└── README.md             # 本文件
```

</details>

***

## ⚖️ 版权与合理使用

more-to-skills **不附带任何书籍内容**——一页都没有。它是一个转换器，你把它指向自己已经拥有的文件。

拿不准时，遵循源文档的许可或条款。本工具只是工具，怎么用在你。

***

## License

MIT —— 适用于本仓库中的转换器（代码 + 技能定义），**不适用于**你用它处理的任何书或文档。
