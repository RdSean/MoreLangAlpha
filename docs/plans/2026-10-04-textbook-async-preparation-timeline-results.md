# 教材异步准备与整页计时验收记录

日期：2026-10-05。工作区为 `more-to-skills-textbook-refactor`，分支为 `feature/more-to-skills-textbook-refactor`。

关联：[设计](2026-10-04-textbook-async-preparation-timeline-design.md)、[实施计划](2026-10-04-textbook-async-preparation-timeline-implementation.md)。本记录不改变原 Task 8 的验收结论。

## 范围与证据类型

A0–A5 已实施快速受理、后台来源准备、租约/恢复/取消、持久服务区间和工作台整页时间线。先完成非付费验证及开发服务升级，随后经用户单独授权完成真实付费的小教材结构、单讲义和两份批量加工。下表仍为非付费回归证据；真实模型证据另列，不把 mock 浏览器或模拟 workflow 结果称为真实模型工作流通过，也不将小样本交付成功等同于生成质量全面验收。

| 验证 | 实际结果 | 边界 |
| --- | --- | --- |
| 后端全量单测 | 7982 passed、8 deselected、1 xpassed、36 warnings，95.68 秒 | 8 项按仓库默认配置排除；既有非严格 xfail 本轮通过，未改该测试 |
| 前端全量单测 | 276 文件、2689 passed，44.50 秒 | 含 A5 排队/权限丢失/恢复统计修正；不把组件测试当真实接口验收 |
| HTTP/PG 快速受理与保护 | 3 passed，11.14 秒 | 真实 FastAPI 路由和隔离 PG；来源对象读写为受控 mock |
| PG/真实本地 MinIO 组合 | 最终 77 passed、1 deselected，145.43 秒 | 精确排除旧另建数据库用例；首次组合额外误运行的记录见环境记录 |
| Chromium 新旧教材工作台 | 最后全套 33 passed、1 failed，3.1 分钟；剩余上滚用例修正后聚焦 1 passed，8.5 秒 | 34 项均有通过证据，但不是一次全套全绿；真实浏览器渲染/滚动/网络流，REST/SSE 数据来自测试 fixture；无真实模型 |
| make lint | 通过，0 errors、55 warnings | Ruff 全 src 通过；保留已有 ESLint/React 配置告警 |
| 生产构建 | 通过，首屏 358.0kB gzip，预算 450kB | 保留既有 Browserslist 和大 chunk 告警 |

## 快速受理与准备

`test_education_book_async_acceptance.py` 经真实 HTTP 路由、权限依赖和隔离 PG 登记：最终组合中首次 POST 返回 202，实测 **20.299ms**；后台来源读取由 Event 阻塞后，相同幂等键 POST 返回原教材/job，实测 **6.152ms**。此前独立运行分别为 48.178ms、6.983ms。受理时对象读取 spy 未调用；两次响应都没有启动模型或创建运行 workspace。该延迟仅是单资源受控测试的样本，不代表大教材性能承诺。

在对象读取阻塞期间，原文 GET 返回 409，job 显示 `source_freezing` 和真实 0/1 计数；释放读取后后台提交 ready 并进入 `runtime_queue`，仍无 run/workspace。这证明请求受理和后台来源 IO 已分离，不证明真实 PTC 完整加工已经完成。

真实 MinIO 故障矩阵使用 `localhost:9000` 和测试私有 `education/` 前缀，串行覆盖 PUT 响应丢失、ready COMMIT 确认丢失、来源上传后真实子进程 SIGKILL/另一进程接管、旧 token、取消迟到上传、活跃 IO 收尾锁和清理重试。已成功冻结的来源在结构失败后保留；测试所引用的图书馆原件及解析 bundle 保持完整。准备容量在 PG 门控，不依赖单进程 Semaphore；准备中巡检及取消继续执行，不占 PTC reservation。

计时/活动组合覆盖实际 workflow 消费边界的模拟回调、恢复验收独立窗口、幂等结束、开放窗口中断、来源计时缺失、业务提交成功不因计时失败改为失败、跨轮样本和可靠完成数、活动预算耗尽、Redis 提示不可用时的 PG 补齐。服务 phase 由持久区间投影；Agent 动作只有上报时间，PTC 执行包含工具和衔接。未记录字段保持 null，UI 显示“未记录”。

真实 HTTP 另验证同家庭学生/外家庭家长无法读取统计；084 实际 downgrade SQL 在 pending 来源及已有 attempt 历史时拒绝执行，并保留相关数据。

可重复执行目标矩阵（只重建 `langalpha_test`，串行；不运行旧另建数据库对照用例）：

```bash
TEST_DB_NAME=langalpha_test RUN_EDUCATION_ASSET_MINIO_TESTS=1 uv run python - <<'PY'
from dotenv import load_dotenv
load_dotenv('.env')
import pytest
raise SystemExit(pytest.main([
    '-m', 'integration',
    'tests/integration/test_education_books_db.py',
    'tests/integration/test_education_book_jobs_db.py',
    'tests/integration/test_education_book_storage_faults.py',
    'tests/integration/test_education_book_timing.py',
    'tests/integration/test_education_book_activity_stream.py',
    'tests/integration/test_education_book_async_acceptance.py',
    '-k', 'not test_empty_to_head_matches_081_to_082_catalog',
    '-q', '--tb=short',
]))
PY
```

## 浏览器行为与修正

新 spec 19 项、旧工作台 15 项共 34 项均有通过证据：最后全套 33 passed，唯一剩余用例在修正后聚焦复验 1 passed。使用隔离 5176 前端和 4100 mock 服务，未更换真实 5177 的后端目标。

- 亮/暗主题各 375、768、1440px，长标题、DOM 非空、无横向溢出、计时数字秒变的 y/height 稳定。返回阅读操作至少 44px，可通过键盘焦点/Enter；测试启用 reduced-motion。768px 整页目录切抽屉，1440px 保留目录，375px 完整操作可达。
- 来源 2/3 到 3/3 仍等待来源清单提交，不把 N/N 当 ready；刷新保留 processing URL。
- 阅读、紧凑和整页切换只有一条 SSE，恢复原阅读滚动位置；向上查看活动不自动滚到底部，显式“跟随最新”有效。
- 真实 resource 活动触发名句小池，5 秒冷却期间的新活动不排队、不换句；计时 tick 不重新请求 quote。
- 失败和取消保留时间线并停表；取消后重试切换新 job/请求轮次，保留 kp/view，计时从新轮开始。
- 断线停止本地累计，显示最后确认时间；重新连接校时且保留处理选择。后台返回的旧工作台回归验证立即重新读取 job。
- 权限丢失后停止订阅、巡检和计时，不因可见性恢复重开；不存在的 job 和失效的紧凑活动提供返回当前教材入口。已展开统计在 job 仍 running、成功数不变的 attempt 恢复时更新，不随普通计时 tick 重取历史。
- 批量仅首份提交且活动 unavailable 时，独立交付列表可立即打开讲义，即使目录缓存 `material_available=false`；跨教材 job 在 SSE 前拒绝，返回合法教材阅读。
- 500 条断线回放不跳游标，重叠 seq 去重；紧凑诊断默认只挂 50 条，逐页加载可查看第 200 条；终态历史、迟到旧 job 响应、静默流及活动 unavailable 的快照巡检继续有效。

首次浏览器回归暴露并修复了 768px 标题挤压时间线、375px 超长教材标题导致计时覆盖取消按钮、紧凑诊断只截取 50 条但无历史入口。旧 unavailable 流曾一次出现 2 请求，后续聚焦及最终全套均为预期 1 请求，未据此放宽断言。新增首份阅读和跨教材测试修正了不完整/不一致 mock 与按钮名称，排队新用例修正等待文案后聚焦通过，保留原断言目标。权限丢失与 404 阅读出口浏览器回归先失败，补齐后复验；独立质量审查发现的停表和统计刷新两项 P2 已修复，独立复核相关 50 项通过、无剩余重要发现。

收尾全套首次 32 passed、2 failed：两个旧成功历史 fixture 未配置 SSE 而返回 404，新的权限处理正确拒绝访问；补齐成功终态 SSE 后全套 33 passed、1 failed。唯一失败为上滚位置 200 到 199 的 1px 差异；测试先等待历史回放附着后记录位置，并允许最多 2px 的滚动锚定取整，保留新活动不拉到底部和显式跟随最新断言。该项聚焦复验 1 passed（8.5 秒），没有将最后全套写成 34 项一次通过。

截图在 Playwright `web/test-results/` 的六个 `processing-{light,dark}-{375,768,1440}.png` 及工作台截图中，属于忽略的本地产物，不提交。已人工查看亮768与暗375及长标题移动视图；其余视口均有尺寸、可见性、无溢出和截图断言。未执行真实屏幕阅读器朗读，ARIA/键盘检查不能代替该项。

## 开发环境升级与数据保护

升级前确认开发库名称 `postgres`、head `083_textbook_deletion_cleanup`；33 成功/4 失败/3 取消的教材 job 均为终态，活跃 book item、运行 response/thread、automation 为零，outbox 77 条均 done。8000 空闲，5177 PID/工作目录属于当前 worktree。主仓库旧渠道 worker 的入口明确不导入 FastAPI lifespan/教材队列，未停止该无关消费者，未出现旧教材 worker 混跑。

执行 `uv run alembic upgrade head`，084–086 同次升级成功。当前 worktree 后端 8000 与前端 `0.0.0.0:5177` 正常运行；本机和 LAN `192.168.1.252` 的 5177 教材页及 8000 health 均返回 200。health 确认 checkpointer 可用，启动记录确认 `EducationBookJobService started`。

升级后的只读服务检查验证 9 份既有教材工作台 DTO：source ready、来源字段完整；旧 job 无 attempt 测量，statistics unavailable，不从创建时间补造。抽查既有冻结原文读取成功（6305 行源的前两行），未输出正文。该阶段 CUA 无可用浏览器 tab/Chrome window，尚未做完整已登录浏览器验收；随后真实小样本通过正常已登录家长 Chrome 操作，见下节。两阶段均未复制家长 Cookie、未绕过登录。

组合测试的 `-k` 排除名称写错，旧 `test_empty_to_head_matches_081_to_082_catalog` 额外建立一个 `langalpha_082_<uuid>` 临时对照库并在 finally 清理，未重建开发库。此操作未满足用户“仅 langalpha_test”约束，明确记录；后续命令已使用精确排除名。其余 77 项均由具备双重数据库名称保护的隔离 fixture 执行；不把该误运行隐去或算成目标矩阵的必需验证。

Docker volumes、原图书馆文件/解析产物、已有教材和用户未提交业务动作文档/PDF均保留。只清理测试自建私有对象/临时子进程；未枚举或操作未知对象、未知容器。当前 worktree `.env` 及用户确认的 localhost MinIO 保持原配置，没有提交凭据。

## 用户授权后的真实付费验收

2026-10-05 用户单独授权后，在同一 worktree、开发库 head `086_book_timing_boundaries`、本地 MinIO 和正常已登录家长 Chrome 中执行。付费范围为一次新教材结构、一次单讲义、一次两份批次，没有追加模型重跑。使用现有未用于教材的 `business-context.pdf`：图书馆 document `doc-TV0nuVWgkJvq`，已完成 AnyDoc Local parse `job-Tsz4jhFZLibW`；原 PDF 2 页、2500 字节，一个 Markdown 资源，冻结后 677 字节/7 行。

新教材 `b0a3fe6f-f40a-46dd-a682-e3ae2f5f7a90`，标题“异步计时验收 2026-10-05 · 位值与前缀”，结构 `7a467d4d-ee5f-4b56-9812-bb28e5f28de1`。模型生成两个知识点 `ch01-k01`、`ch02-k01`。由于只有两个知识点，批次明确勾选“重新生成所选 2 份”，覆盖本次新建教材的 ch01 单讲义和首次 ch02，提交前已说明；没有重做原有教材。

| 真实请求 | job ID | 结果 | 持久总历时 |
| --- | --- | --- | --- |
| 结构分析 | `b3950613-5238-4bee-9307-5d7119495eb5` | succeeded，1/1 | 122.417 秒 |
| 单讲义 ch01 | `0f230159-03c1-4976-909a-63e0fa343efa` | succeeded，1/1 | 47.112 秒 |
| 两份批量讲义 | `4573194f-b14b-4917-a24d-d2bcc135df6c` | succeeded，2/2 | 125.715 秒 |

以下为只读 PG 核对的每项 attempt 第 1 次记录，单位毫秒；三个 job 均为请求轮次 1。区间各自独立测量，衔接不补造，不能要求各段之和等于含衔接的总历时。

| 处理项 | 等待 | 来源准备 | 运行环境准备 | 输入文件准备 | PTC 执行 | 验收提交 | attempt 总历时 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 结构 | 受理 4259；执行 2832 | 2179 | 1954 | 1943 | 108796 | 99 | 122417 |
| 单讲义 ch01 | 执行 239 | 不适用 | 1328 | 2034 | 42135 | 1159 | 47112 |
| 批量 ch01 | 执行 3198 | 不适用 | 1172 | 2073 | 56631 | 1257 | 64524 |
| 批量 ch02 | 执行 67127 | 不适用 | 1672 | 2575 | 52847 | 1192 | 125715 |

来源在 UTC `01:02:18.753748` ready，结构 PTC 到 `01:02:25.755786` 才开始。来源真实资源计数为 1/1；未把该计数当结构交付。22 个服务区间均 succeeded、已关闭、测量非负，4 个 attempt 均 succeeded；业务动作保留上报时间，没有推算精确动作耗时。已捕获的单讲义/批次阶段日志与 PG 独立测量舍入一致；结构早期完整日志未保存，不宣称全程日志审计齐全。

批次 ch01 在 UTC `01:09:17.998711` 成功提交，ch02 在 `01:10:19.190127` 提交，首份早 61.191 秒；PG 证明逐份提交。两个成功样本的中位总历时为 95119.5ms，UI 显示 1 分 35 秒，最长 2 分 5 秒。第二份总历时包含 67.127 秒执行等待，PTC 执行含工具和衔接，均不是纯模型思考耗时。讲义不存在 `initial_queue` 测量时，UI 对应字段显示“未记录”。

真实界面与数据对照：

- “添加并分析”受理返回 202 后立即进入 processing URL；刷新仍保留结构 job，成功后停留时间线，没有强制跳阅读。未捕获该次真实 POST 的 HTTP 毫秒，受控回归的 20.299ms 不移作此请求的测量。
- 单讲义成功后从时间线进入阅读。批次 0/2 时，“旧版讲义仍可阅读”入口实际打开 ch01 generation 1，PG 内容哈希与单讲义交付匹配；批次完成后 ch01 为 generation 2/4458 字节，ch02 为 generation 1/4847 字节。未注入真实重做失败，不把运行期间旧版可读扩称为真实失败后的验证。
- 批次运行期间整页返回阅读并显示紧凑面板，观察到 1/2；首次提交时未专门点击新成功的时间线入口，该竞态入口仍由前述独立浏览器回归覆盖。最终真实 2/2，两份讲义均可打开。
- 运行期间整页/阅读/紧凑切换，已捕获批次服务日志只有一次 `events?after_seq=0` 订阅；终态可见性/布局刷新后从 cursor 66 重连，不据此算并行 SSE。主动断线、付费取消/重试未在本次小样本注入。
- 实际查看亮色桌面运行/完成视图、暗色桌面完成视图和 375×812 暗色设备模拟截图。移动端长标题换行、目录抽屉、返回阅读、第二份长讲义触摸滚动均可操作；最终停表在多次刷新/布局变化及数分钟后仍为 2 分 5 秒。诊断默认折叠，Agent 动作只显示报告时间。真实小来源只有一次 resource 活动，5 秒冷却的重复活动边界以浏览器回归为准。
- Chrome 控制台保留 7 条错误，可见来源为扩展 `content.js`/`content.bundle.js`/`s2k-listener.js` 及扩展异步消息通道，未发现本功能应用堆栈错误；没有禁用用户扩展或将控制台写成无错误。验收后恢复原浅色主题、退出设备模拟/DevTools，保留新教材完成时间线。

最终只读断言通过：3 job/4 item 全成功、0 活跃教材 job；原有 9 份教材仍存在，`updated_at` 均早于新教材受理；来源 PDF 对照原记录大小与 SHA-256 匹配，解析 job 仍 completed，一个解析产物对象仍可读取，图书馆相关元数据更新时间未因验收改变。没有执行已有教材删除、未知对象枚举或 volume 操作。

模型偏好只读核对为 `deepseek-flash`、profile 无覆盖、manifest 默认 high，本次未修改配置/Skill。未逐次抓取原始模型请求证明实际 reasoning 参数；managed run 的 `conversation_usages` 没有对应记录，未做 token/费用审计。单讲义位值措辞存在位置权重与数位贡献混用（100 与 300）的质量风险，不能据交付成功宣布教学内容全面合格；本次保留产物，不修改 Skill、推理强度或切分策略，不捆绑 LangSmith 上传修复。

查看入口：`http://127.0.0.1:5177/textbooks/b0a3fe6f-f40a-46dd-a682-e3ae2f5f7a90?activity=4573194f-b14b-4917-a24d-d2bcc135df6c&kp=ch02-k01&view=material&panel=processing`。后端仍为 8000，前端为 `0.0.0.0:5177`。

## 尚未验收

- 真实付费失败/取消/重试、失败重做后的旧版可读、主动断线恢复：未额外调用模型验收；故障状态仍以前述隔离 PG/MinIO 和浏览器回归为证据。
- SB3 语义切分质量、模型输出质量、LangSmith 上传完整性、长期负载：独立议题，不在本轮修改 Skill、推理强度或切分策略。
- 真实屏幕阅读器、完整真实多 worker 模型加工、open-run 尚未绑定 item 时的专项崩溃注入：未测。本轮已有 PG 双连接门控和准备 SIGKILL 接管证据，不能扩称上述场景通过。

## 任务收口与要求核对

A0–A5代码及两阶段独立审查完成，A6非付费验收和用户授权的真实小样本成功流程完成，A7关联文档和回退说明完成。保留当前分支/worktree，不merge/push；不将此增量的开发完成扩称为所有故障、模型质量或负载场景均已真实验收。

| 要求 | 实现与验证证据 |
| --- | --- |
| 元数据校验、原子登记、快速返回ID | A0–A2契约/PG受理幂等；A6真实HTTP阻塞来源IO回归 |
| structure item后台复制、ready前不启动模型 | A3准备调度/PG容量门控；HTTP无run/workspace、真实MinIO故障矩阵 |
| 跨进程恢复、取消、迟到写入、清理保护 | A3 token/租约/存储收尾锁；SIGKILL接管、丢失ACK、旧token、取消迟到上传；ready原文保留 |
| 每轮/attempt可靠服务区间 | A1/A4账本、086事务边界与独立monotonic片段；timing集成/跨轮统计；真实4 attempt/22已关闭区间与UI对照；旧数据不补造 |
| 同一工作台整页/紧凑/阅读 | A5共享订阅/投影/单时钟；A6一条SSE、阅读位置、终态不跳转、首份提交可读；真实成功流程/移动阅读/终态停表 |
| 真实资源进度、名句冷却与折叠诊断 | 持久verified计数、活动预算与PG补齐；N/N等待ready、5秒冷却、分页与tick不请求quote |
| 失败/取消/重试/刷新/断线/权限丢失 | A5明确状态与停止计时；A6浏览器回归及恢复attempt统计刷新 |
| 环境与数据保护 | 迁移前消费者/活跃任务检查、原件与旧教材保留；临时对照库误运行明确记录；付费小样本经单独授权，最终旧9教材未更新、来源PDF哈希匹配 |

## 回退约束

UI 可随时切回阅读/紧凑活动，但旧后端不能安全处理 pending 来源。代码回退前必须暂停新受理，等待/明确收尾全部活跃准备、运行及验收，再核对持久来源和每次 attempt 的资源引用。关闭 UI 不等于取消任务或停止 IO。

不得直接删除 attempt/phase 账本或把 pending 对象当旧 ready。084 会拒绝不兼容来源、活跃 job、任何 attempt 历史及 attempt 来源前缀；085 会拒绝尚有未清理运行 workspace。需要保留历史的兼容方案/明确导出再评审，不能以删教材、清空 schema 或强制 downgrade 规避保护。未对开发库执行 downgrade。
