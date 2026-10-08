# 教材学习会话的 HITL、Artifact 与消息样式实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 教材学习追问接入已有 Flash 的确认、任务、作品和恢复能力，用户消息采用 Flash 风格的气泡、时间和头像，长代码块限制默认高度并可展开/收起，同时保留讲义与追问的连续滚动。

**Architecture:** 复用现有 ChatAgent 会话事件、历史投影、运行恢复和交互组件，在 education 模块增加教材上下文及权限适配。学习会话仍使用 Flash；教材加工继续使用独立的托管 PTC 和 job/item 状态。共享组件不复制实现，教育业务不进入通用运行机制。

**Tech Stack:** React 19、TypeScript、React Query、现有 ChatAgent session 模块、FastAPI、async psycopg、PostgreSQL checkpoint、Redis SSE、现有 HTML iframe 渲染器。

---

## 范围与约束

- 工作目录固定为 `/Users/seanlee/.config/superpowers/worktrees/langalpha/more-to-skills-textbook-refactor`，继续 `feature/more-to-skills-textbook-refactor`，不新建分支或回主仓库实施。
- 本文件只是计划，未执行代码变更。实施前再次检查根目录、`web/`、`src/server/` 的 AGENTS.md 和 git 状态；保留已有业务文档及教材 PDF。
- 家长端接入现有创建工作区、派发 PTC、澄清提问等 HITL，批准后执行既有工具流程。
- 学生端接入其权限范围内的会话状态、澄清交互和获授权作品展示；学生仍不能创建通用 PTC workspace、访问家长 sandbox/Vault/MCP 或派发通用 PTC。
- 学生自动调用受限教育 PTC、教育作品独立归档及版本管理属于后续能力，不通过本次恢复事件绕过权限。若本次遇到跨工作区作品分享需求，使用明确授权的教育读取设计，不能直接给学生开放通用文件接口。
- 原教材解析、讲义生成、重新生成、加工时间线、取消和重试沿用当前链路；学习会话事件不得更新教材加工成功状态。
- 不自动批准当前待确认请求，不为测试创建真实工作区或派发模型任务。真实付费验收须明确标识，浏览器 mock 不冒充真实运行证据。

## 已核对的现状

| 位置 | 当前行为与缺口 |
|---|---|
| `web/src/pages/Education/components/LessonConversation.tsx` | 本地结构只有 question/answer/error；只处理助手文字、error、retry；没有 HITL、artifact 和运行恢复 |
| `web/src/pages/Education/api.ts:askBookLesson` | 使用通用 Flash 发送接口并携带教材上下文，但没有完整的 session 生命周期 |
| `src/server/services/education_book_study.py:get_book_study_history` | 读取既有 replay 后转成纯文字，学生按知识点筛选历史 |
| `src/server/services/education_learning_transcript.py:_messages_from_replay_items` | 保留原始文字和时间；该只读转录契约应继续保留 |
| `web/src/pages/ChatAgent/hooks/useChatMessages.ts` | 已有 HITL、历史、重连、请求去重和后台任务订阅；同时耦合聊天导航和面板回调 |
| `web/src/pages/ChatAgent/utils/api/messages.ts:sendHitlResponse` | 现有签名未携带教材上下文；学生学习线程拒绝无 assignment/知识点的普通消息 |
| `web/src/pages/ChatAgent/components/messageList/MessageBubble.tsx` | 已有用户气泡、头像、时间格式和长消息折叠，可作为共享实现的来源 |
| `src/server/services/education_managed_runs.py` | 托管加工独立构图，关闭 plan mode 和子代理；不经过 LessonConversation |

## 展示与事件规则

| 内容 | 教材页规则 |
|---|---|
| 用户消息 | 右对齐的 Flash 风格气泡，右侧头像，气泡上方显示提问时间；不用 h2 或大号粗体作为问题正文 |
| 助手回答 | 保持教材 Markdown 主题及阅读宽度，以连续内容展现 |
| 长代码块 | 默认限制最大高度，代码区内部滚动，支持展开完整代码和重新收起；短代码不显示无效的切换按钮 |
| `interrupt` | 在对应回答位置显示待确认卡片；批准/拒绝期间防重复，已处理后同步状态 |
| `artifact` | 展示可交互 HTML、任务、文件及预览入口；支持刷新重现，权限不足时明确提示 |
| 工具调用与推理 | 复用 Flash 活动分组，默认紧凑/折叠；不将内部过程混入讲义正文 |
| 运行状态 | 区分正在回答、等待确认、后台制作、完成、取消、失败，流结束不等于业务成功 |
| 模型/上下文/来源/用量 | 维护对应状态，按需展示紧凑提示或详情，不在正文堆积技术信息 |
| metadata/游标/传输控制 | 内部管理运行身份、订阅、重连和去重，无需逐条显示 |

气泡复用 Flash 现有颜色、圆角、间距和字体，跟随系统主题，不增加平行 token。时间使用 `createDateFormatter` 和既有 locale/timezone 规则；恢复时使用持久化时间，不生成“刷新时间”。头像使用实际消息作者，失败或缺失时使用已有回退图标；不能在查看学生历史时显示家长头像。

讲义、用户消息、助手回答、确认卡片和作品处于同一滚动容器。保留各轮浅色分割线、底部固定输入栏、上一轮无缝可见、新提问平滑定位及减少动态效果选项。作品尺寸变化不能持续拉走正在阅读历史的用户；手机长问题换行，长消息折叠沿用 Flash 行为，不强制单行胶囊。

## Task 1: 固定会话契约与权限回归

**Files:**
- Test: `web/src/pages/Education/__tests__/LessonConversation.test.tsx`
- Test: `tests/unit/server/services/test_education_book_study.py`
- Test: `tests/unit/server/services/test_education_learning_chat.py`
- Test: `tests/unit/server/services/test_education_access.py`
- Reference: `tests/unit/server/services/history/test_event_ledger.py`
- Reference: `web/src/pages/ChatAgent/session/runtime.ts`

1. 写失败用例：文字后 interrupt 显示确认卡片并停在待确认；artifact 可展示；文字流结束后不误判等待确认或失败为完成。
2. 写后端用例：学习历史按教材/assignment/知识点隔离，HITL continuation 仍归属原知识点；跨用户和跨家庭不可读取。
3. 写学生限制回归：可回复获授权澄清问题，通用 workspace/PTC 权限依旧拒绝；家长查看学生转录保持只读。
4. 运行聚焦测试，确认新用例在当前缺失能力处失败，既有契约仍通过；不能把所有失败都归因于 fixture。
5. 产出事件能力表和接口类型，明确哪些事件是内部状态、可折叠活动、直接交互；沿用现有 SSE 名称，不引入重复协议。

## Task 2: 提供保留结构化事件的教材历史

**Files:**
- Modify: `src/server/services/education_book_study.py`
- Modify: `src/server/app/education/textbooks.py`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/types.ts`
- Test: `tests/unit/server/services/test_education_book_study.py`
- Test: `tests/unit/server/app/education/test_textbooks.py`
- Reference: `src/server/services/history/replay/__init__.py`
- Preserve: `src/server/services/education_learning_transcript.py`

1. 在现有 questions 纯文本接口之外，增加获授权的教材 conversation replay 入口；建议 `GET /education/textbooks/{textbook_id}/knowledge-points/{knowledge_point_id}/conversation/replay`，学生带 assignment_id。复用 checkpoint/history 服务，不另存事件表。
2. 对齐通用 replay 的稳定事件身份、turn/run 归属和 widget data_ref 解析；禁止用时间随机 ID 重建同一确认卡片。
3. 服务端先校验教材权限和 thread 归属，再筛选知识点 turn 及其 continuation。无 turn_index 的 artifact/interrupt 通过既有因果锚点关联，不能直接丢弃或无条件混入其他知识点。
4. 保留时间、HITL 状态、任务和作品引用，依据当前权限处理文件入口。普通父母查看学生转录继续使用原只读文字接口。
5. 检验授权撤销、旧数据缺少知识点 metadata、未完成 run、不可用 checkpoint 的既有 fallback；不能以内容标题作为新增数据的唯一归属规则。
6. 聚焦回归通过后更新中文 CHANGELOG，并提交这一项变更。

## Task 3: 复用会话状态并适配教材上下文

**Files:**
- Modify: `web/src/pages/ChatAgent/hooks/useChatMessages.ts`
- Modify: `web/src/pages/ChatAgent/utils/api/messages.ts`
- Modify: `web/src/pages/Education/components/LessonConversation.tsx`
- Modify: `web/src/pages/Education/queries.ts`
- Create: `web/src/pages/Education/hooks/useLessonConversationSession.ts`
- Test: `web/src/pages/Education/__tests__/LessonConversation.test.tsx`
- Reference: `web/src/pages/ChatAgent/session/stream/processStreamEvent.ts`
- Reference: `web/src/pages/ChatAgent/session/history/replayHistory.ts`
- Reference: `web/src/pages/ChatAgent/session/stream/lifecycle.ts`

1. 检查 hook 各入口的耦合，用可选 session 配置承接教育上下文、历史加载器和导航行为；旧调用保持默认行为。优先适配现有 hook，只有真实依赖阻碍时才提取小型共享函数，不在本次重写通用 hook。
2. 教材 adapter 固定 chat-space 返回的 workspace/thread，不用 localStorage 最近会话替代，不因创建作品工作区自动跳离教材页。
3. 发送、HITL resume、retry 等相关入口携带并校验教材上下文；恢复对应原问题的知识点，不采用用户切换后的当前知识点。复用请求 key 去重和 server run admission。
4. 通过共享 session 保留完整消息、运行 ID、pending interrupt、artifact、任务状态和重连游标，替换 question/answer 字符串拼接结构。
5. 知识点切换只清理当前视图订阅；离开页面不等于取消后台执行。实现重新进入时按权威状态恢复；学习“已提问”状态明确记录成功回答的口径，不能由收到部分文字推断完成。
6. 聚焦测试通过后更新中文 CHANGELOG 并提交；普通 Flash/PTC 发送与 HITL 回归一起运行。

## Task 4: 接入 HITL 卡片与跨页面状态

**Files:**
- Modify: `web/src/pages/Education/components/LessonConversation.tsx`
- Reference/Reuse: `web/src/pages/ChatAgent/components/CreateWorkspaceCard.tsx`
- Reference/Reuse: `web/src/pages/ChatAgent/components/PTCAgentCard.tsx`
- Reference/Reuse: `web/src/pages/ChatAgent/components/UserQuestionCard.tsx`
- Reference/Reuse: `web/src/pages/ChatAgent/components/SecretaryConfirmCard.tsx`
- Reference/Reuse: `web/src/pages/ChatAgent/components/messageList/MessageActionsContext.tsx`
- Reference/Reuse: `web/src/pages/ChatAgent/session/interrupts/fromLiveEvent.ts`
- Reference/Reuse: `web/src/pages/ChatAgent/session/interrupts/fromHistoryEvent.ts`
- Test: `web/src/pages/Education/__tests__/LessonConversation.test.tsx`
- Regression: `web/src/pages/ChatAgent/hooks/__tests__/useChatMessages.interruptDedup.test.ts`
- Regression: `web/src/pages/ChatAgent/hooks/__tests__/useChatMessages.duplicateRequest.test.ts`

1. 复用现有卡片、action context 和 interrupt 投影，将卡片插入对应回答顺序；其所在轮保持可见，用户可以拒绝。
2. 待确认状态明确提示，按钮提交期间禁用；不将输入新追问误当作普通下一轮，沿用已有 HITL feedback 语义或清晰限制输入。
3. 对齐教材页和普通 Flash 页的现有 lifecycle/mux 订阅；一处批准后另一处更新已处理状态。重复确认不得创建第二个 workspace 或派发第二次任务。
4. 检验刷新、断线重连、再次 interrupt、拒绝、请求失败重试、授权撤销；未知动作显示可理解的不可处理状态，不能静默忽略。
5. 更新中文 CHANGELOG，提交通过验证的 HITL 集成。

## Task 5: Artifact、后台任务与执行状态

**Files:**
- Modify: `web/src/pages/Education/components/LessonConversation.tsx`
- Modify: `web/src/pages/Education/components/LessonConversation.css`
- Reference/Reuse: `web/src/pages/ChatAgent/components/messageList/MessageContentSegments.tsx`
- Reference/Reuse: `web/src/pages/ChatAgent/components/viewers/html/InlineWidget.tsx`
- Reference/Reuse: `web/src/pages/ChatAgent/components/viewers/html/useHtmlSandbox.ts`
- Reference/Reuse: `web/src/pages/ChatAgent/components/viewers/html/useHtmlActions.ts`
- Reference/Reuse: `web/src/pages/ChatAgent/hooks/useReportBackWatch.ts`
- Reference/Reuse: `web/src/pages/ChatAgent/utils/agentPaths.ts`
- Test: `web/src/pages/Education/__tests__/LessonConversation.test.tsx`
- Regression: `web/src/pages/ChatAgent/hooks/__tests__/useChatMessages.reportBack.test.ts`
- Regression: `web/src/pages/ChatAgent/components/viewers/html/__tests__/InlineWidget.test.tsx`

1. 复用 HTML widget、任务和文件/预览展示；为教材正文保留 EducationMarkdown 渲染入口，避免整体套入通用聊天字体或第二层独立滚动容器。
2. 复用 artifact path routing；文件读取与预览通过已授权接口。HTML 沿用现有 iframe 隔离、postMessage 来源检查，不加入 allow-same-origin。
3. 为后台 PTC 显示运行状态、失败和回传结果；主 Flash 结束后继续订阅所需任务，刷新后任务和作品都可恢复，避免仅留“已派发”卡片。
4. 静态 widget 支持既有全屏、下载等操作；动态 preview 由现有启动/恢复接口处理，不把临时 URL 当永久作品。临时链接失效要有可理解的恢复或失败状态。
5. 工具活动默认折叠，警告/模型切换紧凑展示；metadata、run_end 等维护运行状态。复用既有类型和状态表，不建立另一份状态字典。
6. 控制长历史中的 iframe 数量和事件重渲染，按需加载重型查看器；测试错误/取消/interrupt 后状态不误显示成功。
7. 更新中文 CHANGELOG 并提交。已有存储/回放不足之处明确记录，不以 UI 卡片宣称教育作品独立归档已实现。

## Task 6: 用户消息气泡、时间与头像

**Files:**
- Modify: `web/src/pages/Education/components/LessonConversation.tsx`
- Modify: `web/src/pages/Education/components/LessonConversation.css`
- Modify only if needed: `web/src/pages/ChatAgent/components/messageList/MessageBubble.tsx`
- Create only if shared extraction is needed: `web/src/pages/ChatAgent/components/messageList/UserMessagePresentation.tsx`
- Test: `web/src/pages/Education/__tests__/LessonConversation.test.tsx`
- Regression: `web/src/pages/ChatAgent/components/messageList/__tests__/MessageBubble.userQoL.test.tsx`
- Reference: `web/src/lib/format.ts`

1. 写失败用例：提问不是 heading；显示真实作者头像和时间；长文字可换行/折叠；历史时间在刷新后稳定。
2. 优先复用现有 MessageBubble 的用户展示能力；若必须共享提取，只提取用户气泡、作者和时间，不把编辑/反馈/导航等无关动作一起复制到教材页。
3. 右对齐、头像在右、时间在气泡上方，气泡填充/圆角/字号与 Flash 一致；无头像使用现有图标，不增加装饰或独立颜色。
4. 保持分割线和同一瀑布流，删除 `.lesson-turn-question h2` 的标题样式；新轮滚动目标包含消息元信息，HITL resume 不制造虚假的用户气泡。
5. 检验亮暗主题、主题色切换、375/390/768/1440px、长中文/英文/公式、缺失时间/头像、减少动态效果。作者和时间不挤占问题正文。
6. 更新中文 CHANGELOG 并提交。此任务可在 session 契约稳定后实施，不需要等待真实 PTC 产物生成。

## Task 7: 长代码块的高度约束与展开/收起

**Files:**
- Modify: `web/src/pages/ChatAgent/components/Markdown.tsx` 中共享 `CodeBlock`
- Modify only if needed: `web/src/pages/Education/components/EducationMarkdown.tsx`
- Modify only if needed: `web/src/pages/Education/components/EducationMarkdown.css`
- Create: `web/src/pages/ChatAgent/components/__tests__/CodeBlock.test.tsx`
- Regression: `web/src/pages/ChatAgent/components/__tests__/MarkdownTheme.test.tsx`
- Regression: `web/src/pages/ChatAgent/components/__tests__/MarkdownMath.test.tsx`
- Test: `web/src/pages/Education/__tests__/LessonConversation.test.tsx`

1. 写失败用例：长代码默认限制高度、有展开/收起操作；短代码自然高度、无切换操作；复制取得完整代码而非可见部分。
2. 在共享 CodeBlock 实现一次高度约束，覆盖 Flash 和教材使用的 chat/panel/compact 渲染路径，不为教材复制另一套代码组件。默认建议桌面 320px、手机 240px，作用于代码正文区，语言标签和复制按钮保持可达；以实际溢出判断是否需要切换，不只用行数估计。
3. 受限状态保留纵向内部滚动和长行横向滚动；展开后完整展示代码，按钮切换为收起。控件采用 lucide 展开/收起图标及简短动作文字，提供 aria-expanded 和 aria-controls，支持键盘操作。
4. 代码流式增长超过阈值时自动出现切换入口，默认保持高度受限；用户已经展开时，后续 chunk/主题切换不重置选择。组件身份保持稳定，不因为代码字符串每次变化而重建。
5. 展开/收起仅改变展示，不裁剪代码文本、语法高亮或下载内容；inline code、数学公式和真正的 HTML artifact 不套用代码折叠。现有导出/打印完整展示代码，不把屏幕高度限制或控制按钮带入输出。
6. 在教材连续滚动中验证展开/收起不触发“新提问”自动定位；收起长块时保留可预测的阅读锚点，按钮不会瞬间跳离视口。已有原文 data-source-start/end-line 定位不得丢失。
7. 浏览器验证数百行代码、无语言 fenced code、JSON、长行、流式生成、多个代码块、亮暗主题和手机横向溢出；高度约束不替代长代码渲染的性能验证。
8. 运行共享 Markdown 和教材回归，通过后更新中文 CHANGELOG，并提交此项独立变更。

## Task 8: 浏览器、权限和通用链路验收

**Files:**
- Create: `web/e2e/education-textbook-conversation.spec.js`
- Regression: `web/e2e/education-textbook-learning.spec.js`
- Regression: `web/e2e/education-textbook-workbench.spec.js`
- Regression: `web/e2e/education-textbook-processing.spec.js`
- Create: `docs/plans/2026-10-08-textbook-agent-conversation-results.md`

1. 使用合成 SSE/replay fixtures 验证文字、HITL、工具、HTML、文件、后台任务回传、失败/取消、重连和刷新；通过真实卡片操作验证请求 body，不能只测试卡片静态出现。
2. 验证教材页与 Flash 页同时打开，一边处理确认后另一边不再可执行旧请求；切换知识点后旧事件不污染新视图。
3. 学生账号验证通用 PTC/workspace 仍被后端拒绝、非法 artifact 引用不可读取；家长查看学生转录没有执行动作。成功路径和拒绝路径都需覆盖。
4. 回归教材生成时间线、取消/重试、原文件阅读、目录折叠，以及通用 Flash/PTC 发送和历史恢复。
5. 真实浏览器在桌面/手机亮暗主题检查气泡、时间、头像、卡片和 iframe 不溢出；长代码默认高度受限且可展开/收起，复制仍包含全文；平滑定位后旧内容仍可连续滚动查看。
6. 保持 `0.0.0.0:5177`，核验本机与 LAN 可访问。当前用户待确认请求只读保留，真实执行测试使用独立可控数据。
7. 如改动共享后端 admission/resume 或持久化流程，按 `src/server/AGENTS.md` 执行相应双 worker 验证；仅 UI 与教育 replay 投影改动不宣称已经验证共享运行机制。

## 验证命令

所有命令在上述 worktree 执行；前端命令的工作目录为该 worktree 的 `web/`。

```bash
pnpm exec vitest run src/pages/Education/__tests__/LessonConversation.test.tsx
pnpm exec vitest run src/pages/ChatAgent/components/__tests__/CodeBlock.test.tsx src/pages/ChatAgent/components/__tests__/MarkdownTheme.test.tsx src/pages/ChatAgent/components/__tests__/MarkdownMath.test.tsx
pnpm exec vitest run src/pages/ChatAgent/hooks/__tests__/useChatMessages.interruptDedup.test.ts src/pages/ChatAgent/hooks/__tests__/useChatMessages.duplicateRequest.test.ts src/pages/ChatAgent/hooks/__tests__/useChatMessages.reportBack.test.ts src/pages/ChatAgent/components/messageList/__tests__/MessageBubble.userQoL.test.tsx src/pages/ChatAgent/components/viewers/html/__tests__/InlineWidget.test.tsx
pnpm exec vitest run src/pages/Education/__tests__ src/styles/__tests__/tokenRefs.test.ts
pnpm typecheck
pnpm build
pnpm exec playwright test e2e/education-textbook-conversation.spec.js e2e/education-textbook-learning.spec.js e2e/education-textbook-workbench.spec.js e2e/education-textbook-processing.spec.js
```

```bash
uv run pytest tests/unit/server/services/test_education_book_study.py tests/unit/server/services/test_education_learning_chat.py tests/unit/server/services/test_education_learning_transcript.py tests/unit/server/services/test_education_access.py tests/unit/server/app/education/test_textbooks.py tests/unit/server/services/history/test_event_ledger.py -q
git diff --check
```

对实际改动文件运行 ESLint/Ruff。共享 hook/API 有新增修改时按受影响契约补跑现有 planMode、historyIdempotency、reconnectCursor、stop 和模型状态回归。预期最终所有聚焦测试、类型、构建和浏览器验收通过；当前编写计划阶段未执行这些实现验证。

## 完成口径

- 教材页能展示并回应当前 Create Workspace 类 HITL，刷新后待确认仍在；原 Flash 页能力不退化。
- 用户问题采用 Flash 风格气泡、时间和头像，讲义与所有问答连续可见，固定输入栏和新轮平滑定位保留。
- 长代码块默认不撑高整页，正文内部可滚动并支持展开/收起；短代码保持自然高度，复制、下载、打印仍保留全文。
- 获授权的作品与后台任务在实时和历史视图都可见；未完成、失败和权限不足不显示为成功。
- 同一请求/interrupt 不重复创建工作区或派发任务，知识点与作者归属准确。
- 学生权限和家长只读转录契约保留；教育专用 PTC、归档/版本功能的未完成部分明确列为后续范围。
- 教材加工业务状态和现有 runtime、SSE、checkpoint 机制保持既有契约；无重复事件库、无凭据或生成本地文件入库提交。
- 每项实质变更验证后更新中文 CHANGELOG 并创建原子提交，只 stage 本项文件；不提交已有用户业务文档/PDF，不 merge/push。
