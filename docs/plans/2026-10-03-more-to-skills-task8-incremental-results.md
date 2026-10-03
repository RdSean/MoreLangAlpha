# Task 8 家长 Cookie、传输故障与完成结果恢复补验

日期：2026-10-03。分支：`feature/more-to-skills-textbook-refactor`。

## 范围与结论

本批补齐家长普通登录 Cookie 的首次添加与讲义生成、真实 MinIO 断连、真实 PostgreSQL COMMIT 确认丢失、模型完成但业务未提交时的跨进程恢复，以及新版动作/工具预算组合容量。普通 PTC、MCP、subagent 与 checkpoint 也已实测。总 Task 8 暂不标记完成：家庭作业 live 尚待专用验收学生的年级配置确认，前端全量仍有既有 Plugins storage-throws 失败。

只新增验收测试与记录，未修改产品实现、Skill、schema 或用户模型配置。`.env` 延续原分支的业务配置，S3 使用用户确认的 `localhost:9000`；本批末逐键比对仅 `LANGSMITH_API_KEY`、`LANGSMITH_TRACING` 有本地差异，保留原状，不输出值或覆盖配置。`agent_config.yaml` 仍字节一致。不导出家长 Cookie，不复制凭据。专用夹具、身份、日志、截图均不提交。

## 家长普通 Cookie 全链

用户在 Codex 内置浏览器完成正常登录，账号菜单确认指定家长身份。以下全部通过该登录标签页的正常 UI 完成，没有后台身份请求头：

1. 上传一页合成算术 PDF，正常检测并使用 AnyDoc Local 异步解析。
2. 从文档详情选择“用作教材”，命名 `Task 8 Parent Cookie Acceptance`，点击“添加并分析”，直接进入教材工作台。
3. 数据库只读核对：同一源只有一个教材、一个初始结构任务；首次结构任务约 `74.60s` 成功，产生一章、一个知识点，讲义 `0/1`。这是一页夹具的任务耗时，不是大型文件导入响应时间或性能承诺。
4. 阅读原文，提交快速摘要讲义，只讲原文比较规则和 `42 > 39`，禁止额外例题、练习、词表或图片。任务约 `56.02s` 成功，讲义可读、计数 `1/1`。运行时刷新，恢复同一 job 与知识点，没有新 attempt；终态历史和折叠诊断可回放。
5. 在第二个普通 Cookie 标签页对同一源再次“添加并分析”，返回原教材及原初始结构 job；数据库仍为一个教材、一个结构任务。这是顺序跨标签页复用证据，并非两个页面同一毫秒提交；并发边界沿用 PostgreSQL 集成覆盖。
6. 375px 下原文/讲义、活动关闭再打开可用，`documentElement.scrollWidth == innerWidth == 375`；临时视口已复原，临时第二标签页按本批收尾处理。

结构事件时间（Asia/Tokyo）：准备 `15:55:37.430`，阅读 `15:55:55.242`，整理层级 `15:56:10.940`，校验 `15:56:38.905`，宿主提交 `15:56:51.926`，可靠完成 `15:56:52.014`。本次没有报告“切分知识点”，不能把未上报阶段补造成事件；一次真实运行不证明所有模型都会及时报告。讲义确有原文示例，观察到“正在整理原文示例”，不因动作报告扩写内容。

## 真实传输故障

新增 opt-in 集成文件 `tests/integration/test_education_book_storage_faults.py`，复用现有隔离数据库夹具和材料任务种子。

### MinIO

本机一次性 HTTP 代理只接收当前测试 PUT，不枚举对象或停止 MinIO。测试 SDK 禁用自动重试，故意让断连可见；不改生产重试配置。

- 上传途中只读取部分 body 后断开，不转发至 MinIO：无对象、无材料提交、无成功终态。
- 完整转发至真实 MinIO，确认上游 `200` 后丢弃 HTTP 响应并断开：客户端报告存储失败，真实 GET 确认对象已经存在；业务 item 仍 running，材料和成功终态均为零。
- 两种情况均用同一 attempt、同一内容地址再次走正常上传/验哈希/数据库提交；最终只有一个材料、generation `1`、attempt `1` 和两条可靠终态事件。
- 候选收尾移除登记但保留已提交对象，真实 GET 仍逐字节一致。返回值 `1` 是收尾登记条数，不是对象删除条数。第一轮验收误把它断言为 `0`，纠正验收断言后重新完整执行，未改产品代码。

### PostgreSQL

一次性本机 TCP 代理只连接 `langalpha_test`，禁用代理链路 TLS以读取本地 PostgreSQL 协议。真实 COMMIT 已抵达服务器并产生 `CommandComplete(COMMIT)` 后，代理丢弃确认并关闭连接；不是在函数返回后人为抛异常。

客户端得到真实 `psycopg.OperationalError`。另一独立正常连接确认 item/job 成功、一个材料、generation/attempt `1`、两条终态。重复 `finalize_material` 返回原快照，所有计数不变；恢复扫描不再选择已成功 item。候选收尾后真实 MinIO 内容仍可读。

代理及连接均由测试 finally 关闭；只删除本次精确记录、独立 UUID 前缀下的测试对象。共享容器、bucket 其他对象、开发库与持久 volumes 未删。

执行（先加载本地 `.env`，不打印配置）：

```bash
TEST_DB_NAME=langalpha_test RUN_EDUCATION_ASSET_MINIO_TESTS=1 uv run python -c 'from dotenv import load_dotenv; load_dotenv(); import pytest; raise SystemExit(pytest.main(["-m", "integration", "tests/integration/test_education_book_storage_faults.py", "-q"]))'
```

注意：既有 integration fixture 会重建隔离库 public schema；必须显式指定隔离库，且与使用该库的活 worker/容量夹具串行执行。

## 真实模型完成后跨进程提交

在同一专用教材上执行一次受限摘要重做，不操作用户教材。临时 worker 仅监听 `127.0.0.1:8844`，通过正常 managed launch、已有家长模型配置、PTC 沙箱和 runtime 账本执行。

- 在同一数据库事务内创建并领取专用 job，避免开发 worker 抢领；临时 worker 不启动教材扫描，不干扰普通 worker。
- 模型确实生成完成，runtime 为 `completed`；临时 finalization 回调对这一个 job 抛出 `BookActivityWriteError`，进入现有延迟收尾路径。独立连接确认业务 item/job 仍 running、成功数/本 item 材料/终态均为零，旧讲义保持可读。
- 精确 SIGKILL 本批持有的临时进程，并仅把该 item 当前 token 的 lease 设为过期，以触发实际恢复扫描；这是假设租约已经到期的加速故障注入，不测默认租约等待时间。
- 原 8000 worker 约 `6.147s` 后重连原沙箱，验收并提交同一产物。item/job succeeded、attempt `1`、本 item 一份材料、两条终态；已有专用讲义只从 generation `1` 更新为 `2`。
- 前后 `run_id`、`execution_id`、`attempt_token` 完全相同，没有第二个 runtime 或重新调用模型。临时 worker 已退出，8844 无监听。

## 新版组合容量

教材集成 suite 完成后，另建隔离材料 item，使用真实 producer compact → observer → PostgreSQL，并把 compact 输出写入一次性 `127.0.0.1:6389` Redis。Redis `/data` 为 tmpfs、禁用持久化，随后只删除该具名临时容器。

输入：`150001` 个约 8 KiB 合成 raw delta、`2000` 工具开始 + `2000` 结果、`250` 个合法 action/stage 报告（覆盖八种动作）。为了独立测试容量，observer 使用递增模拟单调时钟，报告间隔模拟 `2s`；这不是实际运行了 500 秒或模型产生这些动作。

| 计量 | 结果 |
|---|---:|
| detail 总条数 | 1000 |
| tool 条数 / 字节 | 800 / 234580 |
| progress 条数 | 200 |
| detail 总字节 / 最大单条 | 298430 / 324 |
| 最长说明字符数 | 56 |
| 省略摘要 / 省略计数 | 1 / 3250 |
| 可靠终态条数 | 2 |
| Redis / producer 回放条数 | 1 / 1 |
| 私有 raw sentinel 泄漏 | 无 |

该输入正好保存 200 个业务事件，是总容量扣除 800 条工具后的结果，不是恢复“固定语义 200 条”限制。耗时 `6.076s` 仅为本次顺序合成验收；不作为模型、网络或长期吞吐指标。

随后使用隔离库的同一夹具，启动仅监听 localhost 的临时后端 `8843` 和前端 `5188`，通过 HTTP 回放实际账本。该页面使用合成夹具的测试身份，不复制家长凭据，不冒充普通 Cookie 验收；夹具没有源文件对象，因此“当前内容暂不可读”不计为阅读器证据。

- 1280px 桌面和 375px 移动端，默认折叠诊断时均为 203 条业务行（200 progress、一份省略摘要、两条终态）。
- 展开诊断后显示 797 条工具明细，总计 1000 个 `li`；客户端为可靠摘要/终态腾出空间，未丢掉业务行。
- 两种视口均 `documentElement.scrollWidth == innerWidth`，无横向溢出，无 `PRIVATE_RAW_SENTINEL`；截图已保存到私人临时目录，不提交。
- 视口已复原，临时标签页和 8843/5188 服务已关闭；仅删除具名 tmpfs Redis 及其可重新生成的一次性缓存，没有删除共享 Redis 或任何持久卷。

## 普通产品回归

普通家长 Cookie 新建 `Task 8 Parent PTC Acceptance` 工作区并发送专用合成测试：真实 ExecuteCode 写文件得到 `17*23=391`；Task 派发 general-purpose 子代理独立验算并交付；核心 WebSearch 查找公开 Python 文档，ExecuteCode 调用 MCP scrape 验证该页面。

没有可用的通用 MCP 搜索引擎，因此没有把核心 WebSearch 冒充 MCP 搜索；MCP 验收使用实际可用的 scrape 能力。持久 SSE 中包含 ExecuteCode/Task/TaskOutput/WebSearch/Read/Bash，scrape 相关调用及成功结果已核对。

刷新后同一线程继续第二轮，沿用前轮文件位置，用工具读取原文件和只读校验，得到相同结果、完整标记与 SHA256，未重写证明文件。数据库确认两轮均 completed，一条子代理 run completed、结果已交付、final checkpoint 存在；普通线程有 `70` 条 checkpoint 及非空 latest checkpoint 指针。这是普通续轮恢复，不冒充 OS 中断后的任意图节点续跑。

Flash 的普通学生 Cookie/真实模型/上下文持久化证据沿用上一批。图书馆本批正常 Cookie AnyDoc 上传解析通过，真实 Datalab 证据沿用前批。家庭作业页面、字典和创建表单可读；默认真实学生未提交任何作业，改选专用学生后遇到“未设置年级”。尚未改账号配置或把此表单检查写为作业完成链。

## 验证与剩余边界

- 新真实存储故障套件：`3 passed in 16.65s`。
- 教材 books/jobs/activity 加新故障套件串行全跑：`48 passed in 93.93s`；随后才运行隔离容量夹具。关闭临时容量服务后，提交前再次完整串行复跑为 `48 passed in 89.89s`；这次隔离 schema 重建也清除了容量夹具，不影响开发库中的专用真实教材。
- 本轮启动后、尚未新增验收文件时的全量：后端 `7930 passed, 8 deselected, 1 xpassed, 34 warnings`；前端 `2606 passed, 1 failed`，仍是既有 Plugins `connectReturn.test.ts:223`；make lint 0 error/55 既有 warning；build/typecheck 与 critical path `356.4 kB gzip` 通过。不把这些记录写为加入新测试后的全量重跑。
- 新测试 Ruff/format 与 diff whitespace 检查通过。没有为这些只读/故障验收改产品代码。
- 收尾确认 8843/8844/5188/6389 无监听，5177/8000 仍监听 `0.0.0.0`；本机与当前 LAN `192.168.1.252` 的前端首页/后端 health 均 HTTP 200。家长原标签页保留在本批成功教材，临时标签页已关闭。
- 总 Task 8 尚有家庭作业 live 与既有前端失败的收口；新版容量浏览器组合复验已补齐。大型教材、多类型来源及长期负载属于明确保留的额外覆盖边界，不保证全部模型提前上报。
