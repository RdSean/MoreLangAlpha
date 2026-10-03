# more-to-skills 学科适配设计与实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 按当前知识点的真实学习目标选择讲义写法，去除数学等学科对英语阅读模板的误套，并独立验证内容准确性。

**Architecture:** 保留一份 more-to-skills 主 Skill，Step 2.1 从解析原文先判断语言再判断学科/领域，Step 4 明确中国学生受众与深度，Step 7 核对当前目标并按需读取数学、语言或通用学科 reference。自学语气、适量课外解释与共同约束留在主 Skill。复用已有目录级冻结哈希、只读 staging、宿主交付和进度，不新增数据库学科枚举、分类器或运行引擎。

**Tech Stack:** Markdown Skills/reference、Python/pytest、现有 PTC sandbox 与教育工作台。

## 设计边界

用户已确认执行顺序：执行契约/提示优化完成后实施学科适配，再经确认启动 REX 3e SB3 和长期负载。本轮不改变模型、推理强度、调度、前端、结构 schema 或知识点切分规则，也不自动增加第二模型审阅。

备选方案：只给现有英语模板补数学例外，改动小但规则冲突继续堆积；后端固定学科并选模板，强制性高但混合内容难处理且扩大产品状态；主 Skill 按当前学习目标路由 reference，保持运行机制并允许局部混合。本轮采用第三种。

### 路由与深度

2026-10-04 用户确认补充：中英文教材均有对应领域，先识别输入语言再判断领域；讲义面向中国学生自学，采用耐心、自然、逐步引导的语气。课外知识的适量补充规则放在主 Skill，具体讲义模板全部按需 reference 加载。

Step 1.5 只选择解析方式；Step 2.1 使用标题、目录和少量正文，不为识别重读全书或提前加载讲义模板。判断只作为本次上下文，不写入结构/数据库。只生成讲义跳过 Step 2.1 时，由 Step 7 用已有来源和结构补齐判断，不依赖先前任务的模型记忆。

1. 判断依据是当前 KP 的原文、任务目标、受众及用户要求，不以标题语言、`Task`、连续英文或全书学科标签单独判定。
2. 数学概念、运算、证明、量与图形关系读取 `reference/material-math.md`；英文数学说明也走此路。
3. 阅读理解、语言表达、语法、词汇等真实语言学习目标读取 `reference/material-language.md`；区分语文和英语/外语目标。原英语教材四族仅用于匹配的外语内容，不继续充当所有教材的默认模板。
4. 混合 KP 只组合完成原目标所需的部分；如计算旅程时长并用英语比较，应保留计算和表达，不套两份完整骨架。来源不足时用保守通用组织，不为了选择模板额外遍历全书或创造目标。
5. `摘要/讲义/精讲` 是深度，不是学科。数学精讲深化概念、每步依据、适用条件与原有例题，不强制语法、音标、词源；语言精讲只深化相应学习目标。
6. 模板是候选组织方式，不是必做清单。术语、易错点、批判性讨论、全单元复习、上下节串联只在目标与已读取来源支持时出现；用户限制范围优先。
7. 科学、历史、技术与其他领域按真实领域采用 `reference/material-general.md`，通用组织也渐进式加载；不把“没有专项模板”误当成“教材没有学科”。不为尚未测试的学科预建一批空模板。

### 内容质量与交付

共通约束继续放在主 Skill：单 KP 范围、独立可读、真实回指、图片读取、脚注/答案溯源、引用限额、材料文件与托管职责。脚注是来源内容，不自动变成必选词汇。数学用原题解释、核对计算与条件，区分数值、单位和实际量，例子不能冒充一般证明；确实无法核实的内容不写成确定结论。

主 Skill 的自学原则：面向学生说话，以相关问题/观察进入，逐步解释“怎么知道、为什么、接下来看哪里”，提供必要过渡而非机械套句；不假定同伴、教师或学生已回答问题，不把追踪日志、行号和文件操作当正文。溯源信息仍在头部及必要注释保留，独学引导不等于新增题组。

课外补充在用户范围允许时主动选少量可靠且紧贴当前难点的背景/类比/应用，随文帮助理解，不填固定拓展板块、不改为专题文章。事实与作者观点分开，教材内容、补充知识与生成示范可辨；历史日期、最新数据、健康结论等不能凭记忆制造权威背书，已有工具能够可靠核实才写必要具体断言，否则省略或明确限制。用户不增题、不扩展优先；不为补充强制联网。

数学 reference 不是知识答案库或针对几条错误写补丁；它强调检查“条件是否被丢掉、局部例子是否被泛化、算式/图示/文字是否一致”。能确定性核对的计算可用现有执行工具，不能由此推出整个讲义正确。保持直接写最终材料，不产生完整草稿副本、不新增交付报告。

提示只能降低错用模板和部分可避免错误的概率，不能承诺修复模型能力。验收分为模板适配、数学事实、来源忠实、受众适合、图/脚注保留和流程/耗时。格式合格、同模型自查或一次成功都不等于准确性通过。

## 实施清单

- [x] A：硬拷贝当前 36 文件，字节比对并单独提交（`eacd092fe`），目录在 `docs/skill-backups/2026-10-03-before-subject-adaptation/`。
- [x] B：改前行为基线，覆盖含 Task 的英文数学、无 Task 的数学精讲、语言技能、混合目标与非虚构；原真实样本错误作为事实检查集，不认定新旧因果。
- [x] C：Step 2.1/4/7、自学语气与课外补充、三份按需 reference；包装/冻结测试先失败再通过，聚焦 66 passed。独立复核的外语表达/引用规则冲突已澄清。
- [ ] D：独立行为复验、自动化回归与小样本真实运行，分开报告质量与速度。

### Task C：Skill 路由与 reference 包装

**Modify:** `plugins/langalpha_local/skills/more-to-skills/SKILL.md`（Step 2.1/4/7、Mode 3）。

**Create:** `plugins/langalpha_local/skills/more-to-skills/reference/material-math.md`、`reference/material-language.md`、`reference/material-general.md`。

**Test:** `tests/unit/server/services/test_education_book_skill_staging.py`、`tests/unit/server/services/test_education_book_structure.py`。

1. 在真实 `stage_book_skill` 测试中增加断言，必须 staging 三份 reference 的实际字节，备份路径不得进入上传清单；新增临时目录 reference 变动会使冻结身份拒绝 staging 的用例。
2. 运行 `uv run pytest tests/unit/server/services/test_education_book_skill_staging.py -q`，确认新资源断言失败而非路径/环境错误。
3. 修改主 Skill 的识别入口、受众/深度、自学叙述和补充原则；语言四族迁移至语言 reference 并补语文分支，通用骨架也迁入 reference，保留引用/来源/托管规则。
4. 用 `get_more_to_skills_identity()` 计算新目录哈希，更新结构测试的预期。schema 哈希不变；不得改历史任务哈希绕过校验。已有目录扫描包含 `.md` reference，无需修改 staging 实现。
5. 运行下方聚焦测试、diff 检查与独立复验，记录实际结果后中文 CHANGELOG 和原子提交；不改用户未提交的 business-activity 计划。

```bash
uv run pytest tests/unit/server/services/test_education_book_skill_staging.py tests/unit/server/services/test_education_book_structure.py tests/unit/server/services/test_education_book_jobs.py tests/unit/middleware/skills/test_native_book_learning_skills.py -q
```

### Task D：行为、真实样本与部署

**Record:** `docs/plans/2026-10-03-more-to-skills-subject-adaptation-results.md`。

1. 独立 Agent 使用新版 Skill 执行同类实际材料生成场景，不仅复述新规则；覆盖三种深度、中英文数学、语文/英语、科学/技术、混合目标、缺失来源与用户不增题限制。观察实际叙述是否引导独学、补充是否有助且可信，并区分原文与解释。文档记录公开产物片段和检查结果，不保存私有推理。
2. 逐条检查算术、分母/分子条件、数值相等与不同整体实物量、数轴间隔和刻度；这是一份人审检查集，不作为新增课文或每次强制查错清单注入 Skill。
3. 确认 queued/running/recovering 为零后安全重启 8000，保留现有 `.env`、5177 和共享容器/挂载。不处理正在运行任务的冻结身份，不删除既有教材。
4. 正常家长 UI 在专用验收教材运行小批讲义：短运算三次、原图脚注一次、跨章引用一次；启动前说明范围。模型和参数沿用原配置，原始要求一致；其他学科的 Agent 行为测试不能冒充该实际模型的实测。
5. 检查保存的讲义正文、图/脚注路径、目标与事实，关联服务分段和 LangSmith 公共指标。分别记录每次结果，无法取得指标就标未知；不展示私有模型推理，不把嵌套 span 重复加总。
6. `uv run pytest tests/unit -q`、`make lint`、改动 Python Ruff、`git diff --check`；前端未改不重复全套前端测试。检查 5177/8000 的本机和 LAN 状态，保留服务。
7. 增加总实施计划“后续优化”链接，原 Task 8 结论不变。若仍有事实问题，标出证据并停止质量完成声明；讨论模型/验证手段另立范围，不无上限加 prompt 和重跑。

## 基线证据

2026-10-03、Skill 改动前，两个独立 Agent 实际按旧规则产出五种场景。数学 Task 选择“技能族”，出现 `## 批判性思维`，尽管内容只是进位检查；无 Task 的英文分数精讲选择“正文族 + 精讲”，出现 `## 逐句语言点` 与 `## 词汇深挖`，并加入 fraction/whole/equal 的音标和词源。数学事实在这两个 Agent 样本中未见所列错误，但模板适配失败可复现。

语言技能与混合目标均选择旧“技能族”；混合材料恰能保留计算和英语表达，作为不应退化的边界。技术非虚构使用通用骨架，作为保留项。基线 Agent 与实际 deepseek 模型不同，不用于证明真实模型准确性或耗时。
