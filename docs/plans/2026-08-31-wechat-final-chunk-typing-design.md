# 微信 iLink 最终分块发送与 Typing 设计

## 目标

为 LangAlpha 的通用 Channel Gateway 补齐微信 iLink 的可靠消息交付体验，采用
Hermes 微信适配器已经验证过的策略：Agent 运行期间发送 typing 状态，Agent
完成后将最终稳定文本按 Markdown 语义块和平台长度顺序发送。微信端不做
token-by-token 推送，不编辑已经发送的消息，也不使用未经验证的
`GENERATING` 消息更新。

## 参考实现

### Hermes

- `gateway/platforms/base.py`（NousResearch Hermes，commit
  `1f99a4b2f2982fbef06df00ad673ade4e1895668`）
  - `supports_draft_streaming()`、`send_draft()` 和
    `prefers_fresh_final_streaming()` 是平台能力声明；不支持的平台可以回退
    到普通最终发送。
  - `render_message_event()` 只把结构化文本事件映射到 sink；
    `format_tool_event()` 允许适配器返回 `None` 吞掉工具 chrome。
  - `_keep_typing()` 负责周期刷新和取消清理，typing 错误不会破坏 Agent turn。
  - 流式呈现是 presentation-only，不改变 Agent 历史。
- `gateway/stream_dispatch.py`：只做事件路由，不包含平台 HTTP 逻辑。
- `gateway/platforms/weixin.py`（Hermes tutorial，commit
  `babc17a066858fa8d32e1152a9e202ce523c1f74`）
  - 持久化 `(account_id, user_id) -> context_token`。
  - 入站后异步预取 `typing_ticket`。
  - `send_typing(status=1)` 和 `send_typing(status=2)` 由适配器实现，刷新循环
    由基类负责。
  - `send()` 先格式化 Markdown，再按语义块和 `MAX_MESSAGE_LENGTH` 分片。
    每个分片使用新 `client_id` 和 `message_state=FINISH`，共享当前
    `context_token`。
  - 该实现没有可靠的微信 draft/edit 流；其“分块”是最终内容发送。

### wechatbot SDK

本地完整 checkout：`/Users/seanlee/DevelopCode/MoreAlpha/wechatbot/python`。

- `wechatbot/protocol.py`：复用 `ILinkApi` 的 endpoint 和 wire message 构造，
  包括 `send_message`、`get_config`、`send_typing`、`notify_start`、
  `notify_stop`、`build_text_message`、`build_media_message`。
- `wechatbot/client.py`：作为文本、图片、视频、文件、语音入站解析和 CDN
  媒体格式的参考；其高层客户端的 context token 只在内存中保存，不能替代
  LangAlpha 的 PostgreSQL 持久化。
- SDK 高层发送管线覆盖文本、图片、视频、普通文件；没有完整的出站语音
  发送分支，因此语音 wire 格式仅作为兼容参考，不假设 SDK 已替我们完成
  语音发送。
- 协议要求回复使用入站消息的 `context_token`。独立最终分片使用不同
  `client_id`，每条消息使用 `message_state=FINISH`。

## 架构

### 通用 ChannelAdapter

`ChannelAdapter` 继续承担两类职责：

1. provider transport：收取更新、规范化入站消息、发送最终消息、处理媒体；
2. provider presentation：声明 typing、代码块和结构化事件的呈现能力，提供
   `render_message_event()`、`format_tool_event()` 等默认策略。

通用层不出现 WeChat/iLink 字段。typing 的接口使用抽象的
`BindingCredentials`、`ReplyContext` 和 `peer_ref`，具体 ticket 获取与 API
调用留给适配器。

### WeChatILinkAdapter

微信适配器负责：

- 通过 `ILinkApi` 发送 `FINISH` 文本消息；
- 对最终文本做微信友好的 Markdown 规范化和语义分片；
- 使用当前入站 `ReplyContext` 中的 `context_token`；
- 缓存或重新获取短期 `typing_ticket`，发送 status 1/2；
- 连接生命周期调用 `notify_start`/`notify_stop`，失败只记录日志；
- 继续使用已有的图片入站解密与校验；媒体扩展点沿用 SDK 的 item/media 结构。

微信适配器明确不实现 `send_draft()`、消息编辑或逐 token 推送能力。

### GatewayRunner 与持久化

当前最终回复仍然必须经过 PostgreSQL `channel_delivery_outbox`。流式事件只
用于内部呈现过滤，不能把中间 reasoning/tool 内容写入历史或 outbox。

处理顺序保持：

```text
claim inbound
  -> 在 Agent turn 期间启动 typing refresh
  -> dispatcher 过滤结构化事件
  -> Agent 返回最终 AgentTurnResult
  -> adapter 格式化并按长度拆分 TextPart
  -> 原子 ack inbound + 写入有序 delivery outbox
  -> delivery worker 顺序发送每个 FINISH 分片
  -> finally 停止 typing
```

这样可以保留现有的 lease、binding epoch、重试、幂等 `client_id` 和会话顺序
约束。由于本期不做实时微信消息发送，不需要另建临时消息表，也不会出现
“已经实时发送后 outbox 再重复发送”的双写去重问题。

## Markdown 与分块规则

1. 先清理多余空行并规范标题；一级标题转换为微信易读的强调文本，普通标题
   使用粗体。
2. 表格转换为键值列表，避免微信纯文本环境下列对齐失败。
3. fenced code block 保持完整，不在代码块内部按自然换行拆散。
4. 顶层空行和未缩进的顶层行优先形成独立消息单元；缩进续行附着在上一行。
5. 单元超过微信上限时再按块组合和硬切分。
6. 每个最终文本分片均通过稳定的 outbox sequence 顺序发送，长度上限由
   `max_ilink_text_length` 控制，默认遵循现有配置。

## Typing 生命周期

- 入站消息已经持久化并被 claim 后，使用同一条消息的 `reply_context` 启动
  typing；没有 context token 时不调用 provider。
- 适配器优先使用短期 ticket 缓存；缓存缺失时用 `getconfig` 重新获取。
- refresh 间隔采用 iLink 约 5 秒的建议值；单次网络调用有超时，异常只记录
  日志并允许下一轮重试。
- Agent 正常完成、异常、取消、binding epoch 失效时都必须尽力发送
  `status=2` 并清理本地 typing 状态。

## 错误与恢复

- `sendmessage` 返回 session expired 时沿用现有
  `ChannelBindingExpiredError`，让 worker 标记重新授权。
- 单个分片发送失败由 outbox 的 lease/retry/dead 状态处理，不改变其他会话的
  顺序。
- typing 失败不应导致 inbound 被重试，也不能阻断最终 outbox 写入。
- worker 重启后，最终消息从 PostgreSQL outbox 恢复；context token 从加密的
  inbound reply context 恢复，不依赖适配器进程内存。

## 测试重点

- Markdown 标题、表格、代码块和超长文本的确定性分片；
- 每个分片共享 context token、使用独立且稳定的 client id；
- typing ticket 缓存命中、缺失重新获取、刷新失败和 stop 清理；
- notify start/stop 失败不影响连接生命周期；
- Agent 异常或 binding epoch 失效时 typing 必须停止，outbox 状态正确；
- reasoning/commentary/tool 事件不会进入微信最终消息；
- 现有 outbox 顺序、重试和 session timeout 测试保持通过。

## 明确不做

- 不实现微信端 token-by-token 流式；
- 不发送或编辑 `GENERATING` 消息；
- 不引入内存之外的临时流消息表；
- 不复制 Hermes 的本地 context token 文件存储；
- 本期不承诺出站语音，普通文件和图片/视频只沿用已验证的 wire/media 扩展点。
