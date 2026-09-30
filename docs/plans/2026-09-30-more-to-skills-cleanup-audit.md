# more-to-skills 清理范围与验收清单

日期：2026-09-30。依据：worktree 的迁移 081 及当前生产代码、用户指定页面的只读检查。
这是源代码/迁移链审查，不等于已经连接运行数据库验证其实际 catalog。实施切换前必须比对 Alembic revision、pg_constraint、实际运行任务和对象清单；发现偏差先补此清单。本文不是已经执行的删除记录。

配套：[设计](2026-09-30-more-to-skills-design.md)、[实施计划](2026-09-30-more-to-skills-implementation.md)。

## A. 旧页面与路由：删除页面，不套壳改名

| 当前组件（web/src/pages/Education/） | 最终处理 |
|---|---|
| TextbooksPage.tsx | 重写为“从图书馆添加 + 教材列表”，去当前版本列和空教材创建步骤 |
| TextbookDetailPage.tsx | 删除；唯一详情由新 TextbookWorkbenchPage.tsx 承担 |
| BookProcessingPage.tsx、BookProcessingPage.css | 删除；活动由工作台中的 BookActivityPanel 展示 |
| TextbookStructurePage.tsx、TextbookStructurePage.css | 删除；新 BookNavigator/BookReader 直接读 skill 结构 |
| KnowledgePointReviewPage.tsx | 删除；候选接受/拒绝/拆分/合并功能退役 |
| KnowledgePointLessonReviewPage.tsx | 删除；原位生成及重做，不保留 revision/approve/publish 页面 |
| components/TextbookWorkflowStepper.tsx | 删除旧流程阶段组件 |
| components/ProcessingProfileDialog.tsx | 删除；新任务表单只有技能深度与要求 |
| components/GenerationProgressCard.tsx、.css | 删除旧 progress contract；新活动组件替代 |
| StudentTextbookLearningPage.tsx | 改接新 reader/授权/材料 DTO，保留学生阅读和学习行为 |
| PersonalizedSummaryPage.tsx、PersonalNotebook、StudentLessonFollowUp | 保留功能并改接 node/KP 引用；不属于家长加工的必经层级 |
| components/EducationMarkdown.tsx | 保留通用渲染；支持源行定位、授权资产、讲义相对链接 |

同步更新 web/src/components/Main/Main.tsx、routeChunks.ts、Sidebar/AppSidebar.tsx、Education/api.ts、queries.ts、types.ts、errorMessage.ts、web/src/lib/queryKeys.ts 和涉及的 locales。旧路由、懒加载 chunk、API 调用、查询轮询及类型必须一起清除。CSS/测试存在关联文件时随对应组件处理，不留孤立文件。

旧 /textbooks/:id/versions/:versionId/{processing,structure,candidates,knowledge/:kpId} 的入口退役，只用一个静态失效链接说明页覆盖旧路径；它不请求旧 API、不尝试翻译旧 ID。家长运行态只有列表和工作台两个路由层级。

图书馆接线：DocumentDetailPage、Documents/components/TeachingUsagePanel.tsx、Documents/{api,hooks,types}.ts 与对应测试；加“用作教材/打开教材”，移除 content_version、publication、旧资产包展示。不是只改 Education 页面。

## B. 服务层、API 与跨模块引用

下列路径均位于 src/server/services/，除明确说明外。

| 处置 | 文件/职责 |
|---|---|
| 删除旧生产链 | education_structure_jobs.py、education_book_pipeline_jobs.py、education_book_asset_jobs.py、education_lesson_jobs.py |
| 删除旧契约 | education_book_package.py、education_structure_validation.py、education_structure_scope_validation.py、education_lesson_validation.py |
| 删除人工审阅链 | education_structure_review.py、education_candidate_review.py、education_lesson_review.py |
| 删除旧进度链 | education_progress_collector.py、education_generation_progress.py、education_structure_progress.py；包括 helper、JSONL parser、阶段完成门禁 |
| 删除旧加工资产适配 | education_teaching_storage.py、education_textbook_storage.py、education_book_assets.py、education_reading_assets.py、education_source_refs.py |
| 删除旧偏好 | education_processing_profiles.py；旧 profiles 数据、校验、prompt 拼接全部取消 |
| 重写聚合服务 | education_textbooks.py 只保留教材身份/创建/读取/分配门面；删除 local_pdf/local_fixture package、旧 processing 重试、多来源拼接和版本状态机 |
| 重写数据库入口 | src/server/database/education_textbooks.py 的旧巨型 SQL 模块退役，由 education_books.py 与 education_book_jobs.py 按新领域拆分；学生查询移到 education_learning.py，避免复制旧 SQL 后继续修补 |
| 保留并简化运行装配 | education_managed_runs.py 复用 build_ptc_graph_with_session；显式传 job/item/execution IDs，不依赖 root 路径推断 job |
| 提取复用快照能力 | education_textbook_source_snapshots.py、education_textbook_snapshot_reads.py；保留安全读取/冻结/摘要校验，删除 version/position 旧目录契约和旧 DB import |
| 重接图书馆反查 | document_teaching_usage.py、src/server/app/documents.py、文档教学使用 DTO；不再 JOIN versions/structures/publications/多源 position |
| 重接学习功能 | education_learning_assets.py、education_learning_chat.py、education_learning_transcript.py；读新结构/KP/material/assignment，保留授权和私人 Flash 约束 |
| 更新消息入口 | src/server/app/threads/messaging.py 及请求模型中的学习上下文引用；冻结本轮实际材料，去“已发布 revision”依赖 |
| 保留通用教育模块 | education_access.py、education_tasks.py、education_homework.py、education_assets.py，及对应成员/家庭/作业服务；不可整目录删除 |

src/server/app/education/textbooks.py 必须按新 API 重写；src/server/app/education/models.py 只删除教材旧 DTO，保留家庭/作业 DTO，新教材 DTO 移到独立 book_models.py。setup.py 的 router 注释/注册与对应 OpenAPI 同步。

退役 API 组：旧 version processing/run/retry；book-pipeline/resume/checkpoint；structure generation/review/accept；candidate patch/accept/reject/merge/split；book-assets；lesson revision/approve；structure publish；旧 publication assignment。不能只让旧 API 返回成功空对象。

保留能力并更换 DTO/API：教材列表/创建/读取、来源候选、原文/图片读取、学生分配、学生阅读/进度/笔记/总结/追问。新任务 API 统一为 book jobs/items/activity；移除旧 polling hook，不能新旧任务同时被 UI 拉取。

## C. 数据库精确处置

表名取自当前迁移链；迁移时先导出范围内旧对象/执行 ID 的清单，再清空关系并解除循环外键，不使用宽泛 CASCADE。旧数据无迁移要求，但 schema 和其他产品功能必须完整。

| 旧表 | 处置 |
|---|---|
| education_textbooks | 保留身份表名并重建字段：单来源、当前结构，不再依赖版本表 |
| education_textbook_versions | 删除 |
| education_textbook_artifact_sources | 删除，多源/position 绑定归并为教材的单源描述 |
| education_processing_jobs | 删除旧内容准备任务 |
| education_textbook_chapters | 删除旧章节投影 |
| education_textbook_structures | 删除，替换为 education_book_structures |
| education_structure_units | 删除，树和语义层级保存在结构 JSONB |
| education_structure_knowledge_points | 删除，替换为 education_book_knowledge_points |
| education_textbook_scopes | 删除，reading_a/reading_b 专用范围不再存在 |
| education_content_nodes、education_content_assets | 删除，通用节点包不是新产物契约 |
| education_kp_lessons、education_kp_lesson_revisions | 删除，替换为单份当前成功 material |
| education_publication_kp_lessons、education_textbook_publications | 删除，取消逐讲义审批/发布快照 |
| education_processing_profiles | 删除 |
| education_generation_progress_events、education_generation_attempts、education_generation_jobs | 删除，替换为 book jobs/items/activity；只复用通用运行机制，不复用旧教育 schema |
| education_textbook_assignments | 清空旧记录并重建 FK/字段，改为教材与家庭学生的显式授权 |
| education_learning_kp_progress | 清空旧记录并改接新 assignment/KP |
| education_learning_items | 清空旧教材笔记/总结记录并改接新 assignment、node ID、KP；保留功能 |
| education_learning_spaces | 按下述专用会话收尾规则处理旧记录，改接新 assignment |

新表：education_book_structures、education_book_knowledge_points、education_book_materials、education_book_jobs、education_book_job_items、education_book_activity_events。job_items 保存当前 attempt token/run/租约及候选产物清单，实际运行历史由通用 runtime ledger/checkpoint 承担，不再机械新建一套旧 attempts 层级。

必须逐项去掉的旧字段/约束：version_id/sequence、publication_id、lesson revision/approval、processing_profile_id、scope_slot/reading_a/reading_b、candidate_status/candidate_key/content_node_id、book package/tree manifests、checkpoint_review/continuation flags、chapter_count 旧聚合。必要新字段从新模型定义，不能保留一堆 nullable 旧字段“以后再删”。node/KP 扩展字段放 JSONB，不沿用旧 confidence/point_type/summary 必填约束。

071 已经移除的历史表不重复当成本次新工作：education_textbook_sources、education_teaching_packages/jobs/attempts/events/archive_staging/package_chapters/package_questions、education_chapter_questions、education_learning_progress、education_learning_answers。保留 028–081 的历史迁移文件；新 head 的 catalog 中这些表应仍不存在。

不删除：documents/document_parse_jobs/解析资产表、education_households/memberships/student_profiles、education_assets、education_tasks/task_rules/作业关联表及字典、普通 users/workspaces/conversation_threads/runtime/checkpoint 表。不能把“教材历史不保留”扩大为清空整个 education schema。

## D. PTC、配置、资产与运行残留

| 位置 | 必须检查的收尾 |
|---|---|
| plugins/langalpha_local/skills/book-to-skill/ | 删除整个旧技能；more-to-skills 的 fork 署名保留，不修改用户个人技能目录 |
| src/ptc_agent/config/agent.py、config/plugins.py 的技能发现/暂存 | 教材任务直接固定到仓库内新技能及摘要，不通过个人技能 fallback 重新找回旧技能；普通用户自定义技能目录能力保留 |
| src/ptc_agent/agent/managed_execution.py | 合并旧五类教材 policy/purpose；去 progress.jsonl 专用分支，保留普通文件边界和编程工具 |
| src/ptc_agent/agent/agent.py | 移除 textbook-chapter-worker 的 fixed v2 asset 提示词及教材专用注册；普通 subagent 机制保留 |
| src/ptc_agent/core/session.py、core/sandbox/ptc_sandbox.py | managed 初始化改用统一 root/work/output；删旧目录模板，不影响普通 sandbox |
| src/server/services/runs/executor.py | 旧 education_teaching/lesson/book_pipeline kind 收敛；教材长运行的实际超时不能误退回短默认 |
| src/config/models.py、settings.py、config.yaml | 合并/重命名现有教材超时字段及调用方；保留基础设施必要配置，不扩展用户配置页 |
| src/server/services/runs/sse_producer.py | 保留 compact 限流；通用可选活动回调在持久化前工作，正常聊天 full 路径不变 |
| 维护/恢复入口 | 新教材 reconcile 挂到既有服务维护周期；移除旧教材专属重启、checkpoint continuation 调用 |
| tests/unit/server/app/test_skills.py、plugins/README.md | 技能发现与分发预期改新技能，许可引用是合法剩余命中 |
| scripts/education_purge_prefix.py | 复核并更新仅允许教材派生对象的准确范围；不对任意教育根路径运行 |

删除旧表前，从旧 job/source/lesson/publication 记录捕获：准确运行 ID、托管 workspace/thread/sandbox ID、固定源快照/生成文件键、旧 progress/checkpoint bundle 键。清单只包含本次重置教材的资源，不打印凭据、不提交私人内容。

收尾顺序：停旧教材入口 → 取消/结束准确运行 → 归属核实 → 释放任务专用资源 → 清理教材关系 → 新 schema 切换。Redis 按已知 thread/run key 删除/过期，不 FLUSHDB；MinIO 按准确键或已验证的任务专用前缀处理，不枚举整桶或其他 education 附件。

学习会话尤其不能只删 learning_spaces 映射：原有消息保护依赖映射判断。对明确归属旧教材的学习线程，走正常线程终止/删除或不可交互归档接口，并保持不可作为普通 Flash 继续；不删除学生其他私人聊天与共享 Flash workspace。若某资源无法安全确认归属，记录为明确的待处理项，不能宣称清理全部完成。

原始图书馆源文件和图片保留。旧教材派生快照允许按清单清理，但不能把源解析 bundle 当成派生产物删除。候选上传失败留下的文件由新任务记录逐键收尾，不增加扫描整个桶的垃圾回收器。

## E. 测试与文档处置

删除仅维护旧接口的测试：旧 book package/结构审阅/candidate/lesson approval/profile/reading scopes/JSONL parser/四阶段 checkpoint 用例及对应前端快照。将其中的真实保障转到新测试：跨家庭访问拒绝、attempt fencing、幂等、取消、文件路径/摘要校验、部分产物保留、普通 PTC 工具可用。

已有迁移历史的 DDL 测试可保留其历史断言；另加新 head catalog 与升级测试，不强迫历史迁移测试描述现行产品。不能为让旧 UI/API 测试继续通过而加兼容路由或旧字段。

必须重接的回归组：图书馆 teaching usage、学生 learning items/进度/追问上下文、managed sandbox、executor timeout、producer compact/full、event replay ledger、路由 lazy chunks/query keys、图书馆 Datalab 参数、家庭/作业。

旧 docs/plans 历史文档不批量删除；在与本次直接冲突的入口说明已被本设计替代。README/当前技能目录/当前产品流程只指向新路径。CHANGELOG 如实写删除项、迁移不可恢复性及测试证据。

## F. 清理完成的可验证定义

1. 源码运行路径不再 import 已删服务，不出现旧表 SQL/旧模型/旧 managed kind 或旧 UI 路由；许可署名、历史迁移、历史文档有明确豁免清单。
2. 新数据库 head 中旧表/字段/外键不存在，保留表和新表的外键全部指向有效对象；从空库与旧 head 升级得到相同 catalog。
3. 旧任务、映射和托管对象均有准确处理结果；无永久 running、悬空输入、无主学习线程、无界 Redis 流。不能只通过 grep 就声称资源已清理。
4. /textbooks/:id 只加载新工作台；旧 processing/candidates 页面 chunk 和查询不存在；图书馆直达工作台，学生能力通过新模型工作。
5. 真实结构-only、任意 KP、批量部分失败/取消/重试、重连、worker 中断、图书馆来源资产和学生权限验收通过。
6. 所有未完成清理项逐条列出，不以“新功能可用”替代本清单完成。
