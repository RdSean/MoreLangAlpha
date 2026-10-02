# more-to-skills Task 7 切换记录

日期：2026-10-02。分支：`feature/more-to-skills-textbook-refactor`。

## 范围与授权

用户明确允许删除历史教材的处理记录、消息和任务专用 Docker 容器，不要求历史教材兼容。图书馆原始文档及解析产物、家庭作业、普通 PTC/Flash 会话和基础设施数据不属于删除范围。

本机沿用原 `codex/library-textbook-assets` 的 `.env` 与 `agent_config.yaml`；S3 使用用户确认的 `localhost:9000`，不依赖 AGENTS.md 中可能变化的办公室 IP。未复制、打印或提交凭据。

## 迁移前证据

迁移前已导出本次旧教材的准确 book/workspace/thread/run/sandbox IDs、对象 keys/ETags/大小及保护计数。私人清单位于本机 `/tmp/langalpha-textbook-cutover.EkPZSV/inventory.json`，不进入 git；它不是内容备份，临时目录需要在后续验收前保留。

开发库原为 081，有 3 本旧教材、10 个 generation jobs、10 个 attempts、3 个 processing jobs；运行账本均已终态。旧 assignments 与 learning_spaces 均为 0，因此没有学生学习线程需要删除。额外按服务端 `managed_execution.kind` 确认了 33 个旧教材 workspace，其中 23 个属于更早的孤立托管历史；未按名称猜测普通 workspace 的归属。

最终的 082 迁移会在删除旧归属表之前拒绝：活动旧任务或 run、未退役的 learning_spaces、任何旧教材 managed workspace。资源清单必须在应用迁移前保存，先按精确归属处理资源；不要把迁移当作 Docker/S3/Redis 清理工具，也不要只删除学生学习映射留下可交互线程。

## 实际删除与保护

| 资源 | 实际处置 |
|---|---|
| 开发数据库 | `081_book_pipeline_checkpoint` 升级为 `082_more_to_skills_textbooks`；旧教材表/字段删除并建立六个 book 领域表及新学习引用 |
| 旧托管 workspace/thread | 精确删除 33 个 workspace 及其 33 个 thread，关联 30 个 runtime response、102 个 workspace file 随关系删除；只处理已核实的旧 managed kinds |
| Checkpoint | 删除对应旧 thread 的 4,959 checkpoints、4,160 checkpoint blobs、14,488 checkpoint writes；不清空共享 checkpoint 表 |
| Docker | 移除 32 个已停止且无 mounts 的旧教材 sandbox 容器；另一个 workspace 没有 sandbox；未使用 `-v`/prune，未删镜像、volumes、网络 |
| 对象存储 | 删除 3 本旧教材精确前缀下 355 个派生对象，共 37,590,655 字节；删除前再次核对 key/ETag/size，删除响应无错误，删除后前缀为空 |
| Redis | 删除 17 个准确旧 thread 的 `replay:turn:v3` 缓存；旧运行流已经过期，复查这些 thread IDs 的残留键为 0；未运行 FLUSHDB |
| 基础设施 | `deploy-postgres-1`、`deploy-redis-1`、`deploy-minio-1` 与原挂载数据保留 |

S3 bucket versioning 未启用，旧对象未做内容备份；旧教材内容、运行记录和消息的删除不可恢复。保留的私人清单只能证明归属与范围，不能恢复正文。

通用内容寻址 `blobs/` 存储可能被同一用户的多个 workspace 共享，不作为教材专用对象删除或扫描；workspace 引用删除后的孤立 blob 继续交由既有引用检查与宽限期 GC 处理，避免删除普通 workspace 共用字节。

删除前后 23 项保护计数一致：2 users、1 household、2 memberships、1 student profile、1 education asset、3 homework tasks、3 task rules；作业相关 4 个关联表仍为 0；16 documents、22 parse jobs、362 artifacts、11 dataset items、4 datasets、23 inspections、11 usage records，tags/tag assignments 仍为 0；4 个普通 workspace、20 个普通 thread、40 个普通 response 未变。

## 代码清理

旧教材 SQL 模块、20 个旧服务、版本/加工/人工审阅/候选/讲义审批/发布 API 与 DTO、旧 book-to-skill 分发和注册、旧 JSONL helper 特例、旧快照 version/position 路径与 fallback 已删除。前面 Task 5/6 已删除独立旧页面并完成图书馆和学生接线。

新教材直接从仓库读取固定 more-to-skills 文件目录；实际暂存目录的全部路径与字节参与冻结摘要，上传前拒绝变更，上传完成后只读封存。个人技能发现和普通 PTC 文件能力保留。清理脚本同时接受准确的当前 textbook prefix 与历史 slug prefix，只选择显式教材派生子目录，不允许 education/household/textbooks 根路径。

显式剩余豁免：028–081 历史迁移、旧设计/变更日志、more-to-skills 的上游 MIT/fork 署名，以及仅允许 revision 033 的历史 `reset_household_llm_test_data.sql`。这些不是当前教材运行路径。未删除用户个人技能目录或未确认归属的 Docker 资源。

## 验证与未完成项

最新验证：后端 unit `7914 passed, 8 deselected, 1 xfailed`；迁移升级/catalog、book jobs/activity PostgreSQL 集成 `39 passed`；真实 managed Docker `1 passed`。前端 typecheck/build/关键路径检查、改动 Python 的 Ruff/格式检查与 `git diff --check` 通过。

浏览器旧教材 fixtures 已切换到当前结构/讲义/授权 DTO。统一 Playwright 聚焦复验 `12 passed`，覆盖图书馆一次添加并直达工作台、反查无 sandbox 依赖、家长学生授权、学生当前讲义与学习进度、旧链接提示、桌面/375px 阅读和批量控件；含 Chromium 与 documents-mobile 两个 project。三份改动 E2E 的 ESLint 与语法检查通过。仅使用模拟 API，不创建真实教材或变更开发库。

前端全量 unit 为 `2578 passed, 1 failed`，与教材无关的既有失败是 `Plugins/__tests__/connectReturn.test.ts` 的 storage-throws/onAbandoned 断言，聚焦复查仍可复现；本轮不改该功能。浏览器红灯基线另有三项非教材既有失败，其断言保持不变：解析方法显式选择、家长创建家庭作业、学生重交附件。没有宣称全量 CI 浏览器套件通过。

Task 8 未完成：真实模型结构与任意 KP/批量生成、取消/迟到回调、上传/数据库 finalise 故障、worker 中断、多标签/多 worker、完整学生权限、活动断线恢复与预算压力的全链验收。现有 DB/Docker 和 mock 浏览器证据不能替代这些场景。
