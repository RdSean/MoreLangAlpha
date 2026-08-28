# 微信 iLink Bot 通道网关设计

## 状态与目标

本文记录 2026-08-28 已确认的微信 iLink Bot 接入设计，作为
`feature/wechat-ilink-bot` 的实施依据。目标是在不侵入 LangAlpha PTC
运行时主干的前提下，为所有用户提供一个可通过个人微信使用 Flash Agent
的入口，并建立可复用的通道网关抽象。

第一期不是“微信专用网关”。微信是第一个 `ChannelAdapter` 实现；未来可在
同一边界下接入钉钉、飞书、Telegram 或其他消息平台。

## 已确认的产品决策

- 每个 LangAlpha 用户第一期最多绑定一个个人微信 iLink Bot。
- 所有登录用户均可使用，包括学生。学生微信消息仍只进入其私有 Flash
  workspace，继续受既有学生 Flash 权限边界约束；不会获得 PTC workspace、
  Sandbox、Vault、MCP 或自动化能力。
- 微信入口固定使用 Flash Agent，不跟随网页端最近一次选用的 Agent。
  Flash 仍可按既有机制调度更深的 PTC 工作，但网关不理解这种内部实现。
- 首期支持微信单聊中的文本和图片入站；文本作为最终回复发送回微信。
- 入站视频、语音和微信 `FILE` 类附件均直接跳过：不下载、不解密、不进入
  Flash、不创建回复，也不消耗模型额度。只保留推进游标与去重所需的最小元数据。
  此处的 `FILE` 包含 PDF 等文件附件，后续如需支持应作为新的明确范围。
- 当前 Flash 可在模型具备视觉能力时分析图片输入，但没有图片生成工具、媒体
  资产输出契约或文件系统。因此本期不让 Flash 原生发送图片回微信。微信适配器
  的出站模型会预留媒体片段，待 LangAlpha 产出受信任的图片资产后再启用。
- iLink Bot 在普通微信群中的事件通常不可靠，第一期仅实现私信。未来仅在
  iLink 实际推送群事件的前提下支持群聊，不能尝试绕过平台限制。
- 同一微信联系人在 `idle_timeout` 内复用 LangAlpha thread；默认 6 小时，
  用户可在设置中修改。超过阈值的下一条入站消息创建新 thread，旧 thread
  不再作为模型上下文。
- 闲置判断使用通道会话自身的 `last_inbound_at`，不使用
  `conversation_threads.updated_at`。后者会被模型回复、标题或后台维护更新，
  不能代表用户最后一次发言。
- 绑定微信账号本人的 `from_user_id` 才可进入该 LangAlpha 用户的绑定。该
  校验是后端纵深防御：正常扫码流程中其他人通常无法发现 iLink Bot，但若协议
  将其他私信推送到该绑定，也不能借用绑定人的账号和模型额度。

## 参考资料与采用结论

### 微信 iLink 协议与 SDK

| 资料 | 采用的结论 | 不采用的部分 |
| --- | --- | --- |
| 本地协议整理：`/Users/seanlee/DevelopCode/MoreAlpha/protocol-spec.md` | 二维码状态机（包括手机端可能要求的短配对码）、`getupdates` 长轮询、`context_token` 的逐消息回复语义、`-14` 登录失效、CDN AES-128-ECB 媒体流程与文本分片约束。 | 语音、文件、视频的媒体处理留到后续范围。 |
| [corespeed-io/wechatbot](https://github.com/corespeed-io/wechatbot) | 采用 `wechatbot-sdk` 的低层 `ILinkApi`、协议类型和 CDN 加解密实现；本地副本位于 `/Users/seanlee/DevelopCode/MoreAlpha/wechatbot`。 | 不使用高层 `WeChatBot.run()`、SDK 文件凭证存储或进程内 context-token 缓存。LangAlpha 必须自行持久化状态。 |
| [SDK 架构说明](https://github.com/corespeed-io/wechatbot/blob/main/docs/architecture.md) | 借鉴扫码、长轮询、媒体上传下载和文本分片的职责划分。 | Node SDK 的 `silk-wasm` 语音转码不进入本期；不会在 Python gateway 中隐藏引入 Node 运行时。 |
| [SDK 协议说明](https://github.com/corespeed-io/wechatbot/blob/main/docs/protocol.md) | 使用文本、图片、语音、文件、视频的 iLink 类型映射作为通道契约的前瞻参考。 | 不把“协议支持某媒体”误写成“当前 Flash 已能消费或产生该媒体”。 |

关键协议事实：iLink 的 `context_token` 是当前对话的回复能力令牌，不等同于
用户 ID。每个出站 `sendmessage` 必须携带对应入站消息的 token；队列中的旧消息
绝不能使用“此联系人最新收到的 token”。

### Hermes 与本地 Gateway 参考

| 资料 | 采用的结论 | 不照搬的原因 |
| --- | --- | --- |
| [Hermes 微信指南](https://hermes-agent.nousresearch.com/docs/zh-Hans/user-guide/messaging/weixin) | iLink Bot 以私信为可靠主路径、长轮询、二维码、context token、去重、输入状态和 `-14` 重登录处理。 | Hermes 的配置文件与本地磁盘凭证模式不符合 LangAlpha 的数据库和多实例部署。 |
| [Hermes BasePlatformAdapter](https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/base.py) | 平台能力需封装在 adapter；消息入口应快速返回；平台发送、格式限制、typing 等属于适配器。 | 基类已混入命令、Agent 会话、流式回复、HITL、TTS、平台 UI 等大量职责，直接继承会让 Gateway 知道 Agent 实现。 |
| [Hermes DingTalk Adapter](https://github.com/NousResearch/hermes-agent/blob/main/plugins/platforms/dingtalk/adapter.py) | SDK 回调应先确认接收、再后台处理；适配器通过规范化入口与核心编排解耦。 | 不复制 DingTalk 的机器人 SDK、事件格式或本地任务管理。 |
| [Hermes Gateway 概念教程](https://github.com/az9713/hermes-agent-tutorial/blob/main/docs/concepts/gateway.md) | 采纳“平台接入”和“Agent 调用”之间设置 Gateway 编排层的思路。 | 不采用多本地 CLI Agent 的选择和会话管理模型。 |
| [Hermes 教程微信实现](https://github.com/az9713/hermes-agent-tutorial/blob/babc17a066858fa8d32e1152a9e202ce523c1f74/gateway/platforms/weixin.py) | 借鉴 iLink 长轮询与回复上下文处理。 | 不使用其进程内状态或文件持久化。 |
| 本地参考实现：`/Users/seanlee/DevelopCode/MoreAlpha/agent-gateway/` | `gateway.py`、`feishu_adapter.py`、`session_manager.py`、`agent_invoker.py` 展示了“平台回调 -> 会话 -> Agent 调用 -> 回复”的最小管道。 | 该实现面向本地 Claude/Codex，使用 JSON 文件、单进程状态和单一处理标志，不能用于 LangAlpha 的多 worker 生产模型。 |

### LangAlpha 现有实现

| 位置 | 对本设计的约束或复用点 |
| --- | --- |
| `src/server/models/chat.py` | `ChatRequest` 已有 `agent_mode="flash"`、`platform` 和 `external_thread_id`。外部会话可复用现有 thread 创建与查找路径。 |
| `src/server/app/threads/messaging.py` | 现有 Chat API 可通过 `X-Service-Token` 与 `X-User-Id` 代表指定用户运行 Flash，并以 SSE 输出结果。Gateway 不应直接调用 Flash graph。 |
| `src/server/handlers/chat/flash_run.py` | Flash 复用用户私有 Flash workspace；图片和模型支持的 PDF 可作为输入，普通文件在 Flash 模式没有 Sandbox 时会被忽略。 |
| `src/server/utils/multimodal_context.py` | 图片以 data URL/`image_url` 内容块传入模型，并按模型输入模态过滤。微信入站图片应复用此入口。 |
| `src/ptc_agent/agent/flash/agent.py` | Flash 没有 Sandbox、MCP 或图片生成工具；其当前工具集不提供图片资产输出。因此不能假设 Flash 可以向微信发送原生图片。 |
| `src/server/database/vault_secrets.py` 与 `src/server/database/encryption.py` | 现有 `pgp_sym_encrypt/decrypt` 和 `BYOK_ENCRYPTION_KEY` 是绑定凭证、游标和回复上下文的静态加密模式。通道凭证不应放进用户可见的 workspace Vault。 |
| `src/server/services/education_access.py` | 学生用户只能使用 Flash workspace；Adapter 必须通过既有内部 Chat API 进入这一权限路径。 |
| `src/server/database/runs/outbox.py` | 现有运行期 outbox 的 claim/retry 语义可作为数据库 outbox 的实现风格参考，但 channel delivery 需保持独立的协议和生命周期。 |

## 架构决策

### 选定分层

```text
WeChatChannelAdapter --+
Future DingTalkAdapter -+--> GatewayRunner --> AgentAdapter
Future FeishuAdapter --+                         |
                                                   +-> LangAlphaFlashAdapter
```

`GatewayRunner` 不知道 WeChat SDK、LangGraph、Flash graph、PTC graph 或具体
模型。它只理解标准入站、出站、会话和 Agent 调用结果。

#### ChannelAdapter

ChannelAdapter 负责特定平台的传输协议，不访问 LangAlpha thread 表，也不调用
Agent。其责任是：

- 创建和查询平台绑定挑战，例如微信二维码；
- 使用给定凭证和游标拉取 webhook/长轮询更新；
- 将平台更新规范化为 `InboundMessage`；
- 将 `OutboundMessage` 发送至平台；
- 声明平台能力和限制，例如最大文本长度、是否支持 typing、支持哪些媒体。

建议的抽象输入/输出：

```python
class ChannelAdapter(Protocol):
    channel_type: str

    async def begin_link(self) -> LinkChallenge: ...
    async def poll_link(self, challenge: LinkChallenge) -> LinkStatus: ...
    async def fetch_updates(self, binding: BindingCredentials, cursor: str) -> UpdateBatch: ...
    def normalize(self, update: object, binding: BindingView) -> InboundMessage: ...
    async def deliver(self, binding: BindingCredentials, message: OutboundMessage) -> DeliveryReceipt: ...
```

这些方法不持有数据库连接，也不启动永久 `run()` 循环。游标、链接状态、租约和
消息重试均由 GatewayRunner 管理。

`WeChatChannelAdapter` 内部会使用 SDK 的低层 iLink API。它只实现首期文本、
图片解析和文本发送；语音、文件和视频更新会被规范化为 `ignored`，以便安全推进
游标，但不会触发下载或 Agent 调用。

#### GatewayRunner

GatewayRunner 是通用的可靠性层，负责：

- PostgreSQL 绑定租约，保证同一微信 token 同一时刻最多一个 worker 长轮询；
- 入站消息持久化、平台消息 ID 去重、会话顺序和闲置超时轮换；
- 以稳定的请求键调用 AgentAdapter，恢复进程崩溃中断的请求；
- delivery outbox 的写入、领取、重试和终态记录；
- 指数退避、`-14` 失效与可观测的无敏感状态。

GatewayRunner 作为独立 worker 进程运行，不嵌入 FastAPI 的 request 生命周期。
API 服务负责设置页和绑定接口；worker 负责轮询与消息处理。两个进程共享
PostgreSQL 和配置，worker 通过数据库租约实现多实例安全。

#### AgentAdapter 与 LangAlphaFlashAdapter

AgentAdapter 是 Gateway 访问 Agent 的唯一端口。它管理不透明的
`agent_session_ref`，例如：

```python
class AgentAdapter(Protocol):
    async def open_session(self, request: OpenSessionRequest) -> AgentSession: ...
    async def run_turn(self, session: AgentSession, turn: AgentTurn) -> AgentTurnResult: ...
```

第一期唯一实现为 `LangAlphaFlashAdapter`。它不 import 或运行 Flash graph；而是
调用既有内部 Chat API：

- 新通道 session：`POST /api/v1/threads/messages`，请求设置
  `agent_mode="flash"`、`platform="wechat"`、唯一的 `external_thread_id`；
- 已有通道 session：`POST /api/v1/threads/{thread_id}/messages`；
- 每次请求携带 `X-Service-Token`、`X-User-Id` 与由 inbound message 推导的稳定
  `request_key`；
- 消费 SSE 的 `message_chunk`、终态事件和错误事件，最终仅返回文本结果给
  GatewayRunner。

`agent_session_ref` 对 Gateway 保持不透明。第一期它是 Flash thread ID，未来即使
增加其他 AgentAdapter，也不要求 ChannelAdapter 或 GatewayRunner 变更。

## 持久化模型

表名使用通用 `channel_*` 前缀，避免 `wechat_gateway` 将第一种平台写进运行时
骨架。字段类型和约束在实施计划中确定，以下是逻辑模型。

### `channel_bindings`

- 绑定 ID、LangAlpha `user_id`、`channel_type`、状态（`active`、`reauth_required`、
  `disabled`）；
- 首期唯一约束：每个 `(user_id, channel_type)` 一条绑定；
- 加密凭证包：token、base URL、iLink bot ID、扫码微信 ID；
- 加密 iLink 游标 `get_updates_buf`；
- `idle_timeout_seconds`，默认 21600；
- 绑定租约持有人与过期时间、最后错误码和无敏感错误摘要。

绑定凭证和游标使用 pgcrypto 加密。日志和普通 JSONB 不写 token、完整 API 响应、
二维码 token 或 context token。

### `channel_link_attempts`

- 关联用户和通道类型；
- 加密二维码轮询 token，展示用二维码 URL、状态和失效时间；
- `wait`、`scaned`、`need_verifycode`、`confirmed`、`expired`、`cancelled` 和失败状态；
- 并发轮询时使用事务锁，确保一次 `confirmed` 只物化一个 binding。

当 iLink 返回 `need_verifycode` 时，设置页展示短配对码输入框。该码只随本次
`get_qrcode_status` 请求传给 Adapter，不写入 link attempt、日志、浏览器存储或
普通 API 响应；多次失败导致 `verify_code_blocked` 时将该尝试标记失败并要求重新
获取二维码。

### `channel_sessions`

- 关联绑定；
- 以加密的 peer 路由信息和不可逆的 peer lookup hash 标识联系人；
- session UUID、`agent_session_ref`、`last_inbound_at`、当前状态；
- 一个绑定和一个 peer 的历史 session 可多条，但只有一个活跃 session。

LangAlpha 的 `external_thread_id` 必须由 `binding_id + peer + session_uuid` 派生，
不能只用微信用户 ID。这样 6 小时后新 session 创建新 thread，且现有
`(platform, external_id)` 唯一索引仍保持有效。

### `channel_inbound_messages`

- 绑定 ID、session ID、平台消息 ID、消息类型、到达时间、处理状态；
- `(binding_id, provider_message_id)` 唯一去重；
- 文本与图片处理所需的规范化 payload；
- 加密的 `reply_context`，其中包括该条入站消息对应的 `to_user_id` 和
  `context_token`；
- 视频、语音、文件仅保存类型和去重元数据，状态直接为 `ignored`。

### `channel_delivery_outbox`

- 引用 inbound message、session 和 binding；
- 出站文本或未来 `MediaPart` payload、确定性的 provider `client_id`、投递状态、
  尝试次数、下次尝试时间和最终错误摘要；
- 发送时读取所引用 inbound message 的加密 `reply_context`，而不是 session 中的
  最新上下文；
- 重试保持相同 `client_id`，让平台有机会去重。

## 运行数据流

### 二维码绑定

1. 设置页调用通用的“创建微信绑定挑战”接口。
2. API 经 WeChatChannelAdapter 调用 `get_bot_qrcode`，持久化 link attempt 后返回
   展示用二维码 URL 和 attempt ID。
3. 前端轮询 attempt 状态；API 通过 Adapter 调用 `get_qrcode_status`。
4. `wait` 和 `scaned` 只更新状态；若返回 `need_verifycode`，前端将一次性输入的
   手机端配对码传回同一 attempt 的状态查询；`expired` 允许用户重新创建二维码。
5. `confirmed` 在一个事务中写入加密凭证、绑定微信 ID和默认 6 小时超时，随后
   GatewayRunner 可取得 binding 租约并开始轮询。

二维码和凭证均不返回给前端日志、浏览器存储或普通 API 状态对象。二维码图片 URL
仅在该 attempt 存活期间返回；配对码不持久化也不回显。

### 入站与 Flash 调用

```text
iLink getupdates
  -> WeChatChannelAdapter.fetch_updates
  -> DB transaction: 更新游标 + 插入去重的 inbound records
  -> GatewayRunner 按 channel session 串行领取一个 pending record
  -> (文字/图片) LangAlphaFlashAdapter.run_turn
  -> DB transaction: 写入 delivery outbox
  -> delivery worker 领取 outbox 并调用 WeChatChannelAdapter.deliver
```

关键点：游标在入站记录安全写入后即推进，不等待 Flash 结束。否则慢模型回复会阻塞
收消息，重启时也会重复拉取。

图片入站时，Adapter 从 iLink CDN 下载并解密，验证 MIME、字节大小和图片尺寸后，
把 data URL 作为现有 `additional_context` 图片传给内部 Chat API。Flash 依据实际
模型的视觉能力决定是否原生理解图片；不支持视觉的模型沿用既有“附件不可理解”提醒。

同一 channel session 串行运行，避免两个消息同时写同一个 LangAlpha thread。不同
联系人可并行处理。若 worker 在 Flash 接受请求后、写 outbox 前崩溃，会使用相同
`request_key` 恢复既有 Flash run，而不是创建第二个模型 turn。

### delivery outbox 的含义

delivery outbox 不是给 FlashAdapter 的队列。它是 Flash 已经返回最终答案后，
“尚未确认发到微信”的可靠发件箱：

```text
微信入站 -> PostgreSQL 收件箱 -> Flash -> PostgreSQL 发件箱 -> 微信
```

先持久化 outbox，再调用微信发送，可避免“答案已经生成但进程在发送前重启”导致
用户永远收不到回复。发送成功标为 `delivered`；网络异常保留记录重试。若“微信
已收到但 worker 尚未来得及标记 delivered”发生，重试会使用同一个 client ID，
降低重复可见消息风险。

### 闲置会话轮换

当一个 pending 入站消息被领取时，Runner 比较其到达时间和该 peer 的
`last_inbound_at`：

- 差值不超过 `idle_timeout_seconds`：复用活跃 channel session 和 Flash thread；
- 差值超过阈值：原 session 结束，创建新 session UUID 和新 Flash thread；
- 更新 `last_inbound_at` 仅在入站消息成功被接纳时进行，模型回复、出站重试和
  thread 标题更新都不影响这个时钟。

## 异常、安全与恢复

- iLink 普通失败先短暂重试，连续失败后退避；长轮询本地超时视为正常并立即重开。
- `ret=-14` 或 `errcode=-14` 表示绑定登录已失效：停止轮询、清除不可再用的凭证和
  游标、状态改为 `reauth_required`，设置页提示重新扫码。历史 LangAlpha thread
  不删除。
- Adapter 仅接受绑定微信 ID的入站消息。其他发件人记录为拒绝的最小审计事件，不
  进入模型，也不回显任何账户信息。
- 永不记录 Bearer token、`context_token`、二维码轮询 token、完整 iLink 原始载荷或
  图片字节。错误文本使用脱敏摘要。
- 图片下载只使用 iLink 所给 CDN 引用，不接受由用户输入的任意 URL；下载前后实施
  类型、大小和像素上限，以防内存耗尽和伪造媒体。
- 解绑是可恢复的用户操作：停用 binding、使租约失效、删除加密凭证和游标，保留
  不含秘密的历史对话与最小投递审计。

## 设置页与 API

在 `/settings` 增加独立“通道”页签，面向所有登录用户。它不属于“模型”页，因为
它描述的是对话入口；未来多个平台也可并列展示。

微信卡片状态：

```text
未连接 -> 配置微信 -> 展示二维码 / 等待扫码
                         -> 已扫码，等待手机确认
                         -> （如微信要求）输入手机端短配对码
                         -> 已连接
                         -> 二维码过期或绑定失效，可重新开始
```

已连接卡片显示连接状态、可编辑的会话闲置超时（默认 6 小时）和断开连接动作。前端
只拿到安全状态、二维码展示 URL 和超时设置；不取得 iLink 凭证、微信 ID或回复 token。

API 使用 `/api/v1/channels/...` 通用前缀，而不是 `/wechat_gateway/...`。第一期
需要的操作为：读取通道状态、创建/取消/查询绑定挑战、更新闲置超时和解绑。具体
路由命名及 Pydantic 模型在实施计划中锁定。

## 明确不在第一期内

- 视频、语音和文件/PDF 的下载、转码、OCR、转写、输入和原生输出；
- Flash 生成或发送原生图片。该能力需要独立补足图片生成工具、受信任资产存储和
  Agent 媒体输出契约；不是微信 Adapter 可以单独补齐的能力；
- 多微信绑定、共享或公共 Bot、联系人白名单管理、主动消息推送；
- 微信流式消息气泡。可发送 typing 状态，但正式回复以最终文本为准；
- 群聊保证、绕过 iLink 的群消息限制，或直接调用 PTC/Flash graph；
- 将通道凭证暴露到 workspace Vault、浏览器或本地文件。

## 验收与测试范围

### 单元测试

- 微信二维码状态映射、凭证解析和 `-14`；
- iLink 文本/图片规范化、绑定发件人校验、图片 MIME/大小校验；
- `context_token` 必须从被引用 inbound message 读取；
- 文本分片、确定性 client ID、delivery 重试；
- session 6 小时轮换与 `last_inbound_at` 而非 thread `updated_at`；
- Flash SSE 的 chunk/finish/error 汇总和稳定 request key；
- 被跳过的语音、文件、视频绝不触发下载或 Flash。

### 数据库与 worker 测试

- 游标和 inbound record 在同一事务内保存；重叠的 getupdates 不重复运行；
- 同一 binding 的租约互斥，同一 channel session 串行，不同 session 可并行；
- Flash 成功、worker 在 outbox 前后中断、delivery 重试和恢复；
- `-14` 会停止绑定且要求重新扫码；解绑后 worker 不再领取消息。

### API 与前端测试

- 绑定接口的所有权校验，学生用户可绑定但仍以自己的 user ID 调用 Flash；
- 二维码等待、已扫码、确认、过期、失效、取消和解绑状态；
- 6 小时默认值和更新校验；
- 通道页签、微信卡片、Dialog 关闭清理和 React Query 缓存刷新。

不使用真实微信账号、真实 token 或真实 iLink 服务进行自动化测试；全部协议交互由
mock adapter 覆盖。最终实现仍需运行后端聚焦测试、Ruff、前端类型检查和构建，并按
项目规范在 `0.0.0.0:5177` 进行前端可达性验证。
