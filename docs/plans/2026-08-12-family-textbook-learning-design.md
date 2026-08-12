# 家庭教材学习架构设计

**状态：已批准，2026-08-12。**

## 目标

在 LangAlpha 现有的家庭教育模块内提供可复用、可发布、可追溯的教材学习资产。
教材归家庭所有，学生只在自己的 Flash 与教育 API 边界内消费已发布快照；PTC 仅
用于家长显式启动的教材加工和后续受控的学习辅助，不能成为教材内容的唯一副本。

首期垂直切片的闭环为：家长上传受限附件 -> 建立教材草稿并选择来源 -> 显式启动
本地加工 -> 审阅候选目录、章节、材料与客观题 -> 发布冻结快照 -> 分配给学生 ->
学生浏览章节、作答并留下进度/证据 -> 家长只读查看。

## 边界与非目标

- 继续使用 FastAPI、异步 psycopg、Alembic 原始 SQL、React Query、Vite 和现有
  Quiet Workspace 组件。教育领域不创建第二个运行时、认证体系、对象存储客户端或
  前端状态容器。
- 学生无法调用 PTC workspace、sandbox、Vault、MCP、自定义 Skills 或自动化；所有
  教材读取和作答使用教育 API。学生界面不呈现监护提示。
- 首期不实现 Datalab、OCR/扫描件识别、Markdown 富编辑、开放题 LLM 判分、打印、
  计划/打卡、章节锁定或多教材课程编排。文本层 PDF 由本地 `pypdf` 适配器处理；
  扫描件和不受支持资料退回为确定性导读。提取器接口和持久化任务契约为 PTC/Datalab
  适配器预留稳定位置。
- 已发布版本绝不修改。新来源、重新加工和教学材料修改只创建新的候选内容/教学包；
  已分配学生不会自动升级。

## 持久化模型

迁移新增 `education_textbooks`、`education_textbook_versions`、
`education_textbook_sources`、`education_processing_jobs`、
`education_textbook_chapters`、`education_chapter_questions`、
`education_textbook_publications`、`education_textbook_assignments`、
`education_learning_progress`、`education_learning_answers` 和
`education_learning_spaces`。

`education_textbook_versions` 是一次冻结的候选内容和教学包输入；其状态为
`draft -> processing -> review -> published`，失败的处理状态为 `failed`。教材本身仅
保存规范名称、家庭所有权和当前已发布版本的便捷指针，不作为内容真相来源。

发布创建一个不可修改的 `publication`，引用一个 `version`；分配引用 publication，
从而将学生学习资产固定在当时的章节、题集和材料上。所有进度与作答都以
`assignment_id + chapter_id + question_id` 为作用域，不能被新发布版本污染。
`education_learning_spaces` 则将一个 assignment 绑定到学生私有 Flash workspace
中的唯一 conversation thread；阅读器重载不会创建新会话，家长只能通过 assignment
范围的只读投影查看原始文本对话。

## 对象存储和可恢复包

对象只写入 `education/` 前缀，路径由家庭、教材 slug、版本号和可读章节 slug 组成。
每个版本写入以下对象包：

```text
education/<household>/<textbook-slug>/v<sequence>/
  README.md
  manifest.json
  sources/<asset-id>-<safe-filename>
  chapters/01-<chapter-slug>.md
  teaching/01-<chapter-slug>-material.md
  teaching/01-<chapter-slug>-questions.json
```

`README.md` 面向恢复操作人员，`manifest.json` 包含版本、输入来源、章节顺序、页码、
对象键、SHA-256、加工器名称及版本。数据库保存关系、授权和索引；对象包可用于重建。
数据库/API 绝不返回存储键或公开对象 URL。原始附件复用既有 `education_assets`，通过
授权服务读取而不是复制或覆盖。

## 加工和重试

家长启动时，服务验证家庭所有权、至少一个同家庭来源以及版本仍为 draft，然后在单一
数据库事务中冻结来源并创建 `queued` job。处理 worker 通过 `FOR UPDATE SKIP LOCKED`
领取 job；job 记录尝试数、阶段、错误和 15 分钟租约。重试允许 `failed` job 或租约
已过期的 `processing` job 重新入队，保留冻结来源且不能偷偷加入后续上传资料。

首期本地适配器对有文本层的 PDF 使用 `pypdf`，按每十页稳定分章；无文本层或其它
受限来源则生成确定性导读、教学材料和单选题。对象包会记录 `book-to-skill` 与
`the-knowledge-guy` 作为后续 PTC 教学增强的知识基础，但当前任务由同一 API 进程中
家长显式触发的本地适配器执行，不另起教育运行时。未来 PTC worker 或 Datalab adapter
复用同一 claim/complete/fail/retry 契约。产物先写对象包，再把数据库版本推进到
`review`。任何失败都将 job/version 标记为 failed，保留可审阅的错误，不影响已发布
快照。

## 授权与 API

服务层是最终授权点：

| 操作 | 家长 | 学生 |
| --- | --- | --- |
| 管理家庭教材、来源、加工、发布、分配 | 仅本家庭 | 拒绝 |
| 阅读候选版本、来源、加工错误 | 仅本家庭 | 拒绝 |
| 阅读已发布章节/材料 | 本家庭管理视图 | 仅自己的 assignment |
| 作答、更新学习进度 | 拒绝 | 仅自己的 assignment |
| 阅读学生进度与作答 | 仅本家庭、只读 | 仅自己的记录 |
| 阅读学习问答原文 | 仅本家庭、assignment 范围只读 | 仅自己的 Flash learning space |

教育路由返回内容正文而非签名对象 URL，以保持存储私有并让权限校验可审计。学习聊天
必须使用 assignment 的唯一 Flash thread，并在服务端把 assignment 和当前发布章节写入
请求上下文，不能以检索结果替代发布资产。家长没有向该 thread 发送、编辑、删除或
重放为本人对话的接口，只能读取教育服务投影的学生/助手原文。

## 用户体验

家长 `/education` 默认看到紧凑的教材表格，并可进入详情页的概览、目录、教学包、版本
和学生标签。详情页提供上传来源、开始/重试加工、审阅、发布及分配学生操作。旧作业页
继续可访问，不改写其数据或流程。

学生 `/education` 默认是“我的学习”列表。选择教材后进入稳定的
`/education/learn/:assignmentId/:chapterId` 阅读器：桌面三栏（目录、阅读、知识检查），
移动端把目录和检查置入面板。当前切片在正文下方提供受控 Flash 章节问答，右栏显示题目
与结果；没有排行榜、监控标识或营销式奖励。家长记录弹窗只显示进度、答案汇总和只读
学习问答原文。

## 测试与验收

后端单元测试验证状态机、冻结来源、同家庭边界、发布不可变性、assignment 访问、客观
题判定、重试、PDF 分章、canonical learning space 和家长只读聊天投影。路由测试验证
HTTP 映射而不接触真实 MinIO。对象包写入通过存储适配器的单元测试覆盖，并可复用现有
可选 MinIO integration test。

前端 Vitest 覆盖按角色渲染、家长开始加工/发布/分配、学生阅读/作答，以及学生不出现
管理控件。完成前执行 backend focused tests、Ruff、frontend test/typecheck/build；启动
前端于 `0.0.0.0:5177` 并以现有浏览器 E2E/访问探针验证页面可由 LAN 到达。
