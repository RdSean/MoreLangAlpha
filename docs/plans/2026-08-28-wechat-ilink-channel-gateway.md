# 微信 iLink Bot 通道网关实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 在不让平台协议接触 LangAlpha Agent 运行时的前提下，为每位登录用户提供个人微信 iLink Bot 到固定 Flash Agent 的可靠私信通道。

**Architecture:** `WeChatChannelAdapter` 将 iLink 扫码、轮询、媒体和发送收敛为通用 `ChannelAdapter` 契约；`GatewayRunner` 以 PostgreSQL 的绑定租约、收件箱、会话和发件箱编排可靠处理；唯一的 `LangAlphaFlashAdapter` 通过现有内部 Chat API 与 SSE 调用 Flash。设置 API 只管理绑定和状态，通道 worker 是独立进程，不运行在 FastAPI 生命周期内。

**Tech Stack:** Python 3.13、FastAPI、Pydantic、async psycopg、PostgreSQL/pgcrypto、httpx、`wechatbot-sdk>=0.3.0`、Pillow、React 19、TypeScript、React Query、Vitest、Tailwind/shadcn。

---

## 已锁定的接口与约束

- 路由前缀始终为 `/api/v1/channels/{channel_type}`；第一期唯一注册的 `channel_type` 是 `wechat`，而不是 `wechat_gateway`。
- API 路由：
  - `GET /api/v1/channels/wechat`
  - `POST /api/v1/channels/wechat/link-attempts`
  - `POST /api/v1/channels/wechat/link-attempts/{attempt_id}/poll`
  - `DELETE /api/v1/channels/wechat/link-attempts/{attempt_id}`
  - `PATCH /api/v1/channels/wechat`
  - `DELETE /api/v1/channels/wechat`
- `POST .../poll` 的 `verification_code` 是可选的一次性输入，只传给当前 iLink `get_qrcode_status` 请求；不持久化、不回显、不写日志。
- 每个用户最多一条 `(user_id, channel_type)` binding；首期始终是绑定人的个人微信向其自己的 Flash 发私信，学生也走自身的私有 Flash workspace。
- 只处理文本和图片入站，Flash 最终文本出站。语音、普通文件/PDF、视频的消息记录为 `ignored`，绝不下载、解密、调用 Flash 或生成回复。
- 所有敏感字段使用 `pgp_sym_encrypt(..., BYOK_ENCRYPTION_KEY)`：iLink token、cursor、二维码轮询值、已绑定微信 ID、peer 路由值、入站回复上下文、图片 CDN 解密引用。不能进入 JSONB、日志、浏览器存储或 Workspace Vault。
- `context_token` 只能从关联 inbound row 的加密 `reply_context` 读取。任何 outbox 发送绝不能使用联系人最近收到的 token。
- 会话以 `channel_sessions.last_inbound_at` 判断空闲，默认 `21600` 秒。下一条入站超过阈值时建立新 session 和新的 LangAlpha `external_thread_id`，旧 Flash thread 不再传入上下文。
- 所有 claim/ack/nack 都使用 PostgreSQL 持久化租约和 fence（`attempts` 或 lease generation），不以进程内字典作为真相。相同 channel session 串行，不同 session 可并行。

## 建议的新增模块

```text
src/server/channels/
  contracts.py
  adapters/base.py
  adapters/wechat_ilink.py
  agent_adapters/base.py
  agent_adapters/langalpha_flash.py
src/server/database/channels.py
src/server/models/channels.py
src/server/services/channels/gateway_runner.py
src/server/services/channels/worker.py
src/server/app/channels.py
```

`src/server/channels/` 只放可复用的通道/Agent 边界；SQL 只在
`database/channels.py`，编排只在 `services/channels/`，HTTP 路由只在
`app/channels.py`。不要让 Adapter import `conversation_threads`，不要让
GatewayRunner import Flash graph 或 PTC graph。

## 此 worktree 的本地调试约定

- `/Users/seanlee/.config/superpowers/worktrees/langalpha/wechat-ilink-bot/.env`
  已由开发者提供。启动本分支服务前先确认它存在，并让 backend、worker 与 migration
  使用这个 worktree 的环境；不读取或复制其他 worktree 的 `.env`。
- 另一个 Codex 会话已占用 backend `8000` 与 frontend `5177`。本分支的开发命令默认
  使用 backend `8010`、frontend `5187`，并设置
  `VITE_PROXY_BACKEND=http://127.0.0.1:8010`。启动前仍以 `lsof` 或 Docker 容器检查
  为准；若端口已被占用，选择另一个空闲端口并同步更新 Vite proxy。
- gateway worker 没有监听端口；它的 `GINLIXFLOW_BASE_URL` 必须指向本分支实际启动的
  backend，例如 `http://127.0.0.1:8010`。不能指向另一个会话的 `8000`，否则会把本
  分支的消息和数据库状态发给错误的服务版本。

### Task 1: 先建立通用通道与 Agent 契约

**Files:**
- Create: `src/server/channels/__init__.py`
- Create: `src/server/channels/contracts.py`
- Create: `src/server/channels/adapters/__init__.py`
- Create: `src/server/channels/adapters/base.py`
- Create: `src/server/channels/agent_adapters/__init__.py`
- Create: `src/server/channels/agent_adapters/base.py`
- Test: `tests/unit/server/channels/test_contracts.py`

**Step 1: Write the failing test**

定义 fixture adapter 和 agent adapter，验证通用 contract 能表示一个文本+图片入站、
忽略入站、文本或未来媒体出站、link challenge、fetch batch 以及不透明 session ref：

```python
@pytest.mark.asyncio
async def test_gateway_contracts_keep_channel_and_agent_opaque():
    inbound = InboundMessage.text_image(
        provider_message_id="msg-1", peer_id="peer-1", text="看这张图", images=[...],
    )
    assert inbound.kind is InboundKind.MESSAGE
    assert isinstance(await FakeChannel().fetch_updates(...), UpdateBatch)
    assert (await FakeAgent().open_session(...)).ref == "agent-ref"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_contracts.py -q`

Expected: FAIL because the `src.server.channels` contract package does not exist.

**Step 3: Write minimal implementation**

在 `contracts.py` 定义 frozen dataclass/enum/Protocol：

```python
class ChannelAdapter(Protocol):
    channel_type: str
    async def begin_link(self) -> LinkChallenge: ...
    async def poll_link(self, challenge: LinkChallenge, verification_code: str | None = None) -> LinkPollResult: ...
    async def fetch_updates(self, credentials: BindingCredentials, cursor: str) -> UpdateBatch: ...
    def normalize(self, raw_update: Mapping[str, Any], binding: BindingView) -> InboundMessage: ...
    async def deliver(self, credentials: BindingCredentials, reply_context: ReplyContext, message: OutboundMessage) -> DeliveryReceipt: ...

class AgentAdapter(Protocol):
    async def open_session(self, request: OpenSessionRequest) -> AgentSession: ...
    async def run_turn(self, session: AgentSession, turn: AgentTurn) -> AgentTurnResult: ...
```

`InboundMessage` 必须把 `provider_message_id`、peer、到达时间、文本、媒体引用与
`reply_context` 分开；`OutboundMessage` 使用 `parts: tuple[TextPart | MediaPart, ...]`，
即使本期只创建 `TextPart`。契约中不得出现 `thread_id`、FastAPI request、SDK 类或
LangGraph 类。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_contracts.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels tests/unit/server/channels/test_contracts.py
git commit -m "feat: add generic channel contracts"
```

### Task 2: 声明依赖与受控的通道运行配置

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/config/models.py`
- Modify: `src/config/settings.py`
- Modify: `config.yaml`
- Test: `tests/unit/config/test_channel_gateway_config.py`

**Step 1: Write the failing test**

测试 `InfrastructureConfig` 的 `channels` 配置具有保守默认值，并拒绝无效的并发、
图片字节数和像素上限：

```python
def test_channel_gateway_defaults_are_bounded():
    cfg = InfrastructureConfig()
    assert cfg.channels.default_idle_timeout_seconds == 21_600
    assert cfg.channels.max_image_bytes > 0
    with pytest.raises(ValidationError):
        InfrastructureConfig(channels={"worker_concurrency": 0})
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/config/test_channel_gateway_config.py -q`

Expected: FAIL because `channels` has not been modelled.

**Step 3: Write minimal implementation**

- 在 `pyproject.toml` 加入直接依赖 `wechatbot-sdk>=0.3.0` 和 `Pillow>=10`；不 vendoring
  SDK，也不使用 SDK 的文件凭证存储或 `WeChatBot.run()`。
- 在 `src/config/models.py` 增加 `ChannelGatewayConfig`：默认空闲 21600 秒、worker
  poll 间隔、binding/inbound/outbox lease、并发度、最大图片字节、最大图片像素、
  最大 iLink 文本长度与 retry 上限；字段加上下界/上界校验。
- 在 `InfrastructureConfig` 中使用该配置，并在 `settings.py` 增加一个
  `get_channel_gateway_config()` accessor。不要用新模块级环境状态。
- 在 `config.yaml` 明确展示默认值。`GINLIXFLOW_BASE_URL` 和
  `INTERNAL_SERVICE_TOKEN` 继续沿用现有内部服务调用配置，不新增同义环境变量。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/config/test_channel_gateway_config.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/config/models.py src/config/settings.py config.yaml tests/unit/config/test_channel_gateway_config.py
git commit -m "feat: configure channel gateway runtime"
```

### Task 3: 用迁移建立通用且加密的通道存储

**Files:**
- Create: `migrations/versions/042_add_channel_gateway.py`
- Modify: `tests/unit/migrations/test_generic_migration_chain.py`
- Test: `tests/unit/migrations/test_channel_gateway_migration.py`

**Step 1: Write the failing test**

测试 migration 链接在 `041` 之后，并断言 source 包含每张表、关键唯一索引、
外键、加密 `BYTEA` 秘密列契约及可逆 downgrade。`pgp_sym_encrypt`/`pgp_sym_decrypt`
属于 repository SQL，而不是 migration DDL：

```python
def test_channel_gateway_migration_follows_task_request_staging():
    migration = runpy.run_path(MIGRATIONS / "042_add_channel_gateway.py")
    assert migration["revision"] == "042"
    assert migration["down_revision"] == "041"

def test_channel_gateway_schema_has_durable_dedup_and_fences():
    source = (MIGRATIONS / "042_add_channel_gateway.py").read_text()
    assert "CREATE TABLE channel_bindings" in source
    assert "UNIQUE (binding_id, provider_message_id)" in source
    assert "credentials_ciphertext BYTEA" in source
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/migrations/test_generic_migration_chain.py tests/unit/migrations/test_channel_gateway_migration.py -q`

Expected: FAIL because revision `042` does not exist.

**Step 3: Write minimal implementation**

创建线性 migration，使用 UUID 主键、`TIMESTAMPTZ` 和 `users(user_id)` 外键：

- `channel_bindings`：`user_id`、`channel_type`、`status`、加密 credentials/cursor/
  bound peer、`idle_timeout_seconds`、binding lease owner/expiry/generation、无敏感错误
  摘要；唯一 `(user_id, channel_type)`。
- `channel_link_attempts`：用户、类型、状态、二维码展示 URL、加密 `qrcode` 轮询值、
  过期时间；没有 verify code 字段。
- `channel_sessions`：binding、不可逆 peer hash、加密 peer、session UUID、不透明
  `agent_session_ref`、`last_inbound_at`、状态；partial unique index 保证每个
  `(binding_id, peer_lookup_hash)` 仅一个 active session。
- `channel_inbound_messages`：binding/session、provider message id、kind、状态、
  文本/类型的最小非秘密 metadata、加密媒体引用与 reply context、attempt/lease/fence。
  `(binding_id, provider_message_id)` 唯一；ignored 行不存媒体解密材料。
- `channel_delivery_outbox`：inbound/session/binding、`sequence_no`、provider
  `client_id`、加密出站 payload、状态、attempt/lease/fence、retry 和终态错误；唯一
  `(inbound_message_id, sequence_no)`。

建立用于领取的部分索引。所有 cipher 字段是 `BYTEA`，加解密函数在 repository 的 SQL
中调用；migration 不保存任何秘密默认值。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/migrations/test_generic_migration_chain.py tests/unit/migrations/test_channel_gateway_migration.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add migrations/versions/042_add_channel_gateway.py tests/unit/migrations/test_generic_migration_chain.py tests/unit/migrations/test_channel_gateway_migration.py
git commit -m "feat: add channel gateway schema"
```

### Task 4: 实现数据库 repository 与不可泄漏的加密边界

**Files:**
- Create: `src/server/database/channels.py`
- Test: `tests/unit/server/database/test_channels.py`

**Step 1: Write the failing test**

为 DB cursor fake 写单元测试，覆盖下面每个语义：

```python
@pytest.mark.asyncio
async def test_store_updates_advances_cursor_only_with_inserted_inbound(mock_db):
    await store_update_batch(binding_id="b1", cursor="next", messages=[message])
    sql = mock_db.executed_sql()
    assert "pgp_sym_encrypt" in sql
    assert "ON CONFLICT (binding_id, provider_message_id) DO NOTHING" in sql

@pytest.mark.asyncio
async def test_delivery_claim_reads_reply_context_from_its_inbound_row(mock_db):
    await claim_due_deliveries(...)
    assert "JOIN channel_inbound_messages" in mock_db.executed_sql()
```

同时覆盖 attempt-fenced ack/nack、same-session 头部顺序、binding lease 的 compare-and-set、
6 小时轮换所需的 active session lock、解绑时删除 ciphertext 但保留最小审计历史。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_channels.py -q`

Expected: FAIL because repository does not exist.

**Step 3: Write minimal implementation**

在一个 `database/channels.py` 中实现清晰的 async 函数，不使用 ORM：

```python
async def claim_binding_lease(binding_id: UUID, worker_id: str, seconds: int) -> BindingLease | None: ...
async def persist_update_batch(binding: BindingView, cursor: str, messages: Sequence[PersistedInbound]) -> int: ...
async def claim_pending_inbound(limit: int, lease_seconds: int) -> list[ClaimedInbound]: ...
async def ack_inbound_and_enqueue_deliveries(claim: ClaimedInbound, result: AgentTurnResult) -> bool: ...
async def claim_due_deliveries(limit: int, lease_seconds: int) -> list[ClaimedDelivery]: ...
```

所有敏感入参以 `pgp_sym_encrypt(%s, %s)` 保存，读取时仅在 worker/API 确有需要的
select 使用 `pgp_sym_decrypt`。错误摘要必须由调用方传入无秘密的分类码，不保存 HTTP
响应、token 或原始 iLink 载荷。`ack_inbound_and_enqueue_deliveries` 在同一事务中完成
inbound 状态转换、agent ref 更新和按文本分片创建 outbox rows。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_channels.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/database/channels.py tests/unit/server/database/test_channels.py
git commit -m "feat: persist channel gateway state"
```

### Task 5: 实现微信 iLink 链接 Adapter

**Files:**
- Create: `src/server/channels/adapters/wechat_ilink.py`
- Test: `tests/unit/server/channels/test_wechat_link_adapter.py`

**Step 1: Write the failing test**

用 fake `ILinkApi` 写状态映射和隐私测试：

```python
@pytest.mark.asyncio
async def test_confirmed_qr_status_returns_credentials_without_writing_disk(tmp_path):
    result = await adapter.poll_link(challenge)
    assert result.status is LinkStatus.CONFIRMED
    assert result.credentials.user_id == "bound-peer"
    assert not list(tmp_path.iterdir())

@pytest.mark.asyncio
async def test_verify_code_is_forwarded_once_and_not_retained():
    await adapter.poll_link(challenge, verification_code="123456")
    fake_api.poll_qr_status.assert_awaited_once_with(..., "123456")
    assert "123456" not in repr(adapter)
```

增加 `wait`、`scaned`、`need_verifycode`、`scaned_but_redirect`、`expired`、
`verify_code_blocked`、`binded_redirect` 和 malformed confirmed 响应的用例。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_wechat_link_adapter.py -q`

Expected: FAIL because the WeChat adapter does not exist.

**Step 3: Write minimal implementation**

用 `wechatbot.protocol.ILinkApi` 直接实现 `begin_link` 与 `poll_link`：

- `begin_link()` 调用 `get_qr_code(FIXED_QR_BASE_URL, [])`，仅返回 `qrcode_img_content`
  和加密所需的 qrcode 值；二维码显示 URL 不是凭证，但不能在日志中打印。
- `poll_link()` 处理 SDK 已知状态，IDC redirect 只更新本次 challenge 的 poll base URL；
  `confirmed` 必须得到 `bot_token`、`ilink_bot_id`、`ilink_user_id` 和 base URL 才能
  生成 `BindingCredentials`。
- 绝不调用 `wechatbot.auth.save_credentials/load_credentials`，不构造
  `WeChatBot.run()`，也不让 Adapter 写文件或访问数据库。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_wechat_link_adapter.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels/adapters/wechat_ilink.py tests/unit/server/channels/test_wechat_link_adapter.py
git commit -m "feat: add wechat link adapter"
```

### Task 6: 实现微信入站规范化、图片下载校验和文本发送

**Files:**
- Modify: `src/server/channels/adapters/wechat_ilink.py`
- Test: `tests/unit/server/channels/test_wechat_message_adapter.py`

**Step 1: Write the failing test**

覆盖协议转换而不是 SDK 私有实现：

```python
def test_only_bound_sender_text_and_image_become_processable_inbound():
    inbound = adapter.normalize(raw_text_and_image, binding_view)
    assert inbound.text == "请解释这题"
    assert inbound.images[0].cdn_reference is not None

def test_file_voice_and_video_are_ignored_without_a_download():
    inbound = adapter.normalize(raw_voice, binding_view)
    assert inbound.kind is InboundKind.IGNORED

@pytest.mark.asyncio
async def test_delivery_uses_inbound_reply_context_and_stable_client_id():
    await adapter.deliver(credentials, ReplyContext(peer_id="p", token="t"), message)
    assert fake_api.sent[0]["context_token"] == "t"
    assert fake_api.sent[0]["client_id"] == message.client_id
```

另加拒绝非绑定 sender、空/机器人消息、`-14`、超大/伪造 MIME/过大像素图片、以及
超过 iLink 字符限制的安全文本分片用例。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_wechat_message_adapter.py -q`

Expected: FAIL because normalize/download/deliver behavior is missing.

**Step 3: Write minimal implementation**

- 只接受 `message_type=USER` 且 `from_user_id` 等于 binding 的加密 bound peer；其他
  sender 返回可审计但不可处理的 `REJECTED`，不生成平台回复。
- 使用 `MessageItemType` 逐项解析文本和图片；语音/文件/视频在下载前直接返回
  `IGNORED`。不依赖 `WeChatBot._parse_message()` 或 `_chunk_text()` 私有方法。
- 对 processable image，保存加密 CDN reference，领取后用 SDK 公共 crypto helpers
  (`decode_aes_key`、`decrypt_aes_ecb`) 从固定 iLink CDN 下载；用 Pillow `verify()` 和
  reopen 检查真实格式、文件字节和像素上限，再生成 `data:image/<mime>;base64,...`。
  不把图片字节写入数据库或日志，worker 崩溃后可按同一加密引用重取。
- `deliver()` 用 SDK `ILinkApi.build_text_message`/`send_message` 构造文本；Gateway
  在事务中预先按限制拆成多条 outbox，每段携带 UUIDv5 形式的稳定 client id，Adapter
  不自行随机化 id。
- 将 `ApiError.errcode == -14` 转成 domain `BindingExpiredError`，让 Runner 停止而
  不是无限重试。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_wechat_message_adapter.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels/adapters/wechat_ilink.py tests/unit/server/channels/test_wechat_message_adapter.py
git commit -m "feat: handle wechat text and image messages"
```

### Task 7: 实现用户所有权受控的通道设置 API

**Files:**
- Create: `src/server/models/channels.py`
- Create: `src/server/services/channels/linking.py`
- Create: `src/server/app/channels.py`
- Modify: `src/server/app/setup.py`
- Test: `tests/unit/server/app/test_channels_api.py`
- Test: `tests/unit/server/services/channels/test_linking.py`

**Step 1: Write the failing test**

用 FastAPI dependency overrides 与 fake repository/adapter 测试：

```python
async def test_student_can_create_own_wechat_link_attempt(client, student_auth):
    response = await client.post("/api/v1/channels/wechat/link-attempts")
    assert response.status_code == 201
    assert fake_repo.created_for_user_id == student_auth.user_id

async def test_link_attempt_cannot_be_polled_or_cancelled_by_another_user(client):
    assert (await client.post(OTHER_USERS_ATTEMPT)).status_code == 404

async def test_idle_timeout_is_bounded_and_disconnect_scrubs_credentials(client): ...
```

验证 `need_verifycode` 不出现在 response，且 poll request body 只允许符合长度/字符
限制的 verification code。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/app/test_channels_api.py tests/unit/server/services/channels/test_linking.py -q`

Expected: FAIL because route、models 与 service 均不存在。

**Step 3: Write minimal implementation**

- 在 `models/channels.py` 定义不含秘密的 response models：binding state、idle timeout、
  last error code、attempt id、二维码 URL、attempt state、expires at、
  `verification_required`。request model 只接受 `idle_timeout_seconds` 或临时
  `verification_code`。
- `services/channels/linking.py` 调用 ChannelAdapter 和 repository，获得 attempt owner
  lock 后物化/轮询/确认 binding。`confirmed` 事务要么产生一个 active binding，要么
  幂等返回当前 binding；`verify_code_blocked` 与 expired 结束 attempt。
- `app/channels.py` 以 `CurrentUserId` 验证用户，路径 type 仅从 adapter registry 解析；
  从 response 排除 token、cursor、bound peer、reply context 和完整 iLink errors。
- 在 `app/setup.py` 注册 `channels_router`，但不要从 lifespan 启动 poller。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/app/test_channels_api.py tests/unit/server/services/channels/test_linking.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/models/channels.py src/server/services/channels/linking.py src/server/app/channels.py src/server/app/setup.py tests/unit/server/app/test_channels_api.py tests/unit/server/services/channels/test_linking.py
git commit -m "feat: add channel binding settings api"
```

### Task 8: 用正式内部 Chat API 实现 Flash AgentAdapter

**Files:**
- Create: `src/server/channels/agent_adapters/langalpha_flash.py`
- Test: `tests/unit/server/channels/test_langalpha_flash_adapter.py`

**Step 1: Write the failing test**

mock `httpx.AsyncClient.stream`，验证 request 和 SSE 汇总：

```python
@pytest.mark.asyncio
async def test_flash_adapter_sends_image_context_and_collects_final_text():
    result = await adapter.run_turn(session, AgentTurn(text="解释", images=[image], request_key="key-1"))
    assert posted_json["agent_mode"] == "flash"
    assert posted_json["platform"] == "wechat"
    assert posted_json["additional_context"][0]["data"].startswith("data:image/")
    assert result.text == "完整回复"

@pytest.mark.asyncio
async def test_duplicate_request_reconnects_to_the_existing_run(): ...
```

覆盖首个 `metadata` 中 thread id、`message_chunk` 文本累积、terminal stream、`error`
事件、HTTP 409 `duplicate_request` 后请求既有 run 的 `/messages/stream?run_id=...`。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_langalpha_flash_adapter.py -q`

Expected: FAIL because `LangAlphaFlashAdapter` does not exist.

**Step 3: Write minimal implementation**

- 使用 `GINLIXFLOW_BASE_URL`（与现有 report-back 相同）和 `INTERNAL_SERVICE_TOKEN`，
  请求头包含 `X-Service-Token`、`X-User-Id`、`X-Dispatch: background`；在 platform mode
  缺少内部 token 时拒绝启动并记录无敏感配置错误。
- 首次 turn 调用 `POST /api/v1/threads/messages`，固定 body：

```python
{
    "agent_mode": "flash",
    "platform": "wechat",
    "external_thread_id": external_thread_id,
    "request_key": request_key,
    "messages": [{"role": "user", "content": text}],
    "additional_context": image_contexts_or_none,
}
```

后续 turn 调用 `/api/v1/threads/{thread_id}/messages`。读取 `metadata.thread_id` 作为
不透明 `AgentSession.ref`，只汇总 `message_chunk` 的文本内容，不向微信透传工具、思考、
artifact 或内部 error payload。
- 409 duplicate 必须用返回的 `thread_id/run_id` 连接现有 stream；stream 断开时用同一
request key reconnect，绝不启动第二个 turn。terminal error 返回可重试的 domain error，
由 inbound queue 控制重试。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_langalpha_flash_adapter.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels/agent_adapters/langalpha_flash.py tests/unit/server/channels/test_langalpha_flash_adapter.py
git commit -m "feat: bridge channel turns to flash"
```

### Task 9: 实现入站编排、会话轮换和恢复

**Files:**
- Create: `src/server/services/channels/__init__.py`
- Create: `src/server/services/channels/gateway_runner.py`
- Test: `tests/unit/server/services/channels/test_gateway_runner.py`

**Step 1: Write the failing test**

使用 fake ChannelAdapter、AgentAdapter 与 repository，验证 Runner 的关键状态机：

```python
@pytest.mark.asyncio
async def test_idle_gap_creates_new_session_without_using_thread_updated_at():
    await runner.handle_claim(claim_after_six_hours)
    assert repo.new_session_calls == 1
    assert agent.opened_external_ids == ["wechat:<opaque-new-session>"]

@pytest.mark.asyncio
async def test_same_session_is_serial_and_different_sessions_can_progress(): ...

@pytest.mark.asyncio
async def test_agent_success_writes_outbox_before_inbound_is_acked(): ...
```

覆盖入站 cursor 先持久化、重复 provider id 不重复调用 Agent、ignored 不下载、绑定外
sender rejected、crash 后 duplicate request reconnect、Flash 失败 nack/backoff、以及
`BindingExpiredError` 使绑定进入 `reauth_required`。

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/channels/test_gateway_runner.py -q`

Expected: FAIL because `GatewayRunner` does not exist.

**Step 3: Write minimal implementation**

实现四个清晰的 worker tick：

```python
class GatewayRunner:
    async def poll_bindings_once(self) -> None: ...
    async def ingest_binding(self, lease: BindingLease) -> None: ...
    async def process_inbound_once(self) -> None: ...
    async def deliver_once(self) -> None: ...
```

`poll_bindings_once()` 只领取有效 binding lease；`ingest_binding()` 在同一 DB transaction
写新 cursor 与去重 inbound rows，然后立即释放 poll 操作，不等待 Flash。处理 inbound
时根据该 peer 的 `last_inbound_at` 和 binding timeout 原子选择或轮换 session；
`external_thread_id` 使用 binding UUID、不可逆 peer hash、session UUID 的派生值，绝不
直接使用微信 user id。每条 session 的 claim query/head ordering 是串行保证，而非
`asyncio.Lock`。

成功路径必须是 `AgentAdapter.run_turn` -> 一个事务内保存 agent ref、outbox rows、ack
inbound；先写发件箱，后交给发送 loop。失败/lease 丢失不吞异常；nack 由 attempts fence
保证陈旧 worker 不能改写后继 owner。`-14` 清除不可用 ciphertext/cursor，状态变
`reauth_required`，不删除 channel session 或 LangAlpha thread。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/channels/test_gateway_runner.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/channels/gateway_runner.py tests/unit/server/services/channels/test_gateway_runner.py
git commit -m "feat: orchestrate durable channel turns"
```

### Task 10: 实现可靠发件箱、重试和发送上下文约束

**Files:**
- Modify: `src/server/database/channels.py`
- Modify: `src/server/services/channels/gateway_runner.py`
- Test: `tests/unit/server/services/channels/test_channel_delivery.py`
- Test: `tests/unit/server/database/test_channels.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_delivery_reads_context_from_referenced_inbound_not_latest_peer_context():
    await runner.deliver_once()
    adapter.deliver.assert_awaited_once_with(..., ReplyContext(token="old-message-token"), ...)

@pytest.mark.asyncio
async def test_lost_ack_reuses_same_client_id_after_lease_expiry(): ...

@pytest.mark.asyncio
async def test_text_chunks_stay_ordered_and_retry_only_the_unacked_chunk(): ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/channels/test_channel_delivery.py tests/unit/server/database/test_channels.py -q`

Expected: FAIL because delivery behavior is not implemented.

**Step 3: Write minimal implementation**

实现 `claim_due_deliveries`、`ack_delivery`、`nack_delivery`，所有状态更新都按
`delivery_id + attempts` fence。claim SQL 按 `session_id, sequence_no` 保序，避免回复
第 2 段先于第 1 段发送。发送 adapter 只收到 repository join 出的该 inbound `reply_context`；
不能从 binding/session 读取“最新 context token”。网络错误以指数退避保留 row；不可
恢复错误达到上限才 `dead`，保留脱敏分类码。若发送已成功但 ack 丢失，lease 到期的
重发使用同一 `client_id`，由 iLink 去重机会降低可见重复。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/channels/test_channel_delivery.py tests/unit/server/database/test_channels.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/database/channels.py src/server/services/channels/gateway_runner.py tests/unit/server/database/test_channels.py tests/unit/server/services/channels/test_channel_delivery.py
git commit -m "feat: deliver channel replies from durable outbox"
```

### Task 11: 提供独立 worker 命令与部署编排

**Files:**
- Create: `src/server/services/channels/worker.py`
- Modify: `Makefile`
- Modify: `docker-compose.yml`
- Modify: `deploy/docker-compose-dev.yml`
- Modify: `deploy/docker-compose-middleware.yml`
- Modify: `deploy/docker-compose-nas.example.yml`
- Modify: `.env.example`
- Modify: `deploy/.env.example`
- Test: `tests/unit/server/services/channels/test_worker.py`

**Step 1: Write the failing test**

测试 worker 在不 import FastAPI lifespan 或 Flash graph 的情况下，打开 app-data pool、
启动 runner、收到 cancellation 后停止 loops 并关闭 pool：

```python
@pytest.mark.asyncio
async def test_worker_owns_gateway_loops_but_not_fastapi_lifespan(monkeypatch):
    await run_worker_until_cancelled()
    runner.stop.assert_awaited_once()
    assert "src.server.app.setup" not in imported_modules
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/channels/test_worker.py -q`

Expected: FAIL because worker entrypoint does not exist.

**Step 3: Write minimal implementation**

- `python -m src.server.services.channels.worker` 配置日志、打开 `get_or_create_pool()`，
  构造 adapter registry、Flash adapter 和 `GatewayRunner`，运行 polling/inbound/delivery
  task group，SIGTERM/SIGINT 时停止领取新项、等待有界 grace、关闭 pool。
- 不能调用 `src.server.app.setup.lifespan`，不能作为 FastAPI background task，不能保留
  进程内 binding registry。多实例通过 Task 3 的 binding/message leases 竞争。
- 在 Makefile 增加 `dev-gateway`。在所有包含 `backend` 服务的 compose 清单增加
  `channel-gateway`，与 backend 同镜像/环境/源码卷，命令为 worker module，`depends_on`
  backend health，容器内 `GINLIXFLOW_BASE_URL=http://backend:8000`。不复制任何秘密；
  example env 只说明已有内部 token 和加密 key 是必需的，不能打印具体值。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/channels/test_worker.py -q && docker compose config >/dev/null && docker compose -f deploy/docker-compose-dev.yml config >/dev/null`

Expected: PASS and both compose files render without schema errors. Run equivalent config checks for
the middleware and NAS manifests.

**Step 5: Commit**

```bash
git add src/server/services/channels/worker.py Makefile docker-compose.yml deploy/docker-compose-dev.yml deploy/docker-compose-middleware.yml deploy/docker-compose-nas.example.yml .env.example deploy/.env.example tests/unit/server/services/channels/test_worker.py
git commit -m "feat: run channel gateway as worker"
```

### Task 12: 接入设置页 API、查询键和本地化

**Files:**
- Modify: `web/src/pages/Settings/api.ts`
- Modify: `web/src/pages/Settings/queries.ts`
- Modify: `web/src/lib/queryKeys.ts`
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`
- Test: `web/src/pages/Settings/__tests__/channelsApi.test.ts`
- Test: `web/src/lib/__tests__/queryKeys.test.ts`
- Test: `web/src/locales/__tests__/keys.test.ts`

**Step 1: Write the failing test**

```ts
it('uses the generic wechat channel endpoints without exposing credentials', async () => {
  await startWechatLinkAttempt();
  expect(api.post).toHaveBeenCalledWith('/api/v1/channels/wechat/link-attempts');
});

it('keeps all channel states under the settings query-key namespace', () => {
  expect(queryKeys.settings.channels.wechat()).toEqual(['settings', 'channels', 'wechat']);
});
```

**Step 2: Run test to verify it fails**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/channelsApi.test.ts src/lib/__tests__/queryKeys.test.ts src/locales/__tests__/keys.test.ts`

Expected: FAIL because the API client and keys do not exist.

**Step 3: Write minimal implementation**

在 Settings API layer 定义严格的 TypeScript interfaces（`ChannelStatus`、`LinkAttempt`、
`LinkPollResult`），提供 get/start/poll/cancel/update/disconnect 函数。`poll` 的
verification code 只存在函数参数中，不写到 localStorage。queries 增加 React Query
status hook 和 mutations；每次成功 mutation 失效 `queryKeys.settings.channels.wechat()`。
在两套 locale 加入“通道”“微信”“配置微信”“等待扫码”“已连接”“重新连接”“断开连接”、
空闲时长和配对码所需的可见文案，并通过 existing locale key tests。

**Step 4: Run test to verify it passes**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/channelsApi.test.ts src/lib/__tests__/queryKeys.test.ts src/locales/__tests__/keys.test.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/pages/Settings/api.ts web/src/pages/Settings/queries.ts web/src/lib/queryKeys.ts web/src/locales/en-US.json web/src/locales/zh-CN.json web/src/pages/Settings/__tests__/channelsApi.test.ts web/src/lib/__tests__/queryKeys.test.ts web/src/locales/__tests__/keys.test.ts
git commit -m "feat: add channel settings client"
```

### Task 13: 构建微信绑定设置页与完整 Dialog 状态

**Files:**
- Create: `web/src/pages/Settings/panels/ChannelsTab.tsx`
- Modify: `web/src/pages/Settings/Settings.tsx`
- Modify: `web/src/pages/Settings/Settings.css`
- Test: `web/src/pages/Settings/__tests__/ChannelsTab.test.tsx`
- Test: `web/src/pages/Settings/__tests__/Settings.channels.test.tsx`

**Step 1: Write the failing test**

使用 MSW/API mocks 验证核心用户流：

```tsx
it('shows the QR after Configure WeChat and polls until confirmed', async () => {
  render(<ChannelsTab />);
  await user.click(screen.getByRole('button', { name: /configure wechat/i }));
  expect(await screen.findByRole('img', { name: /wechat qr code/i })).toHaveAttribute('src', QR_URL);
  await advanceTimersByTimeAsync(2_000);
  expect(await screen.findByText(/connected/i)).toBeVisible();
});

it('cancels an unfinished link attempt when the dialog closes', async () => { ... });
it('shows a one-time verification-code input only when requested', async () => { ... });
it('allows every authenticated member including a student to see the Channels tab', async () => { ... });
```

**Step 2: Run test to verify it fails**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/ChannelsTab.test.tsx src/pages/Settings/__tests__/Settings.channels.test.tsx`

Expected: FAIL because the Channels tab does not exist.

**Step 3: Write minimal implementation**

- 在 `Settings.tsx` 增加所有登录成员可见的 `channels` tab，保留学生只隐藏模型页的现有
  规则；不要把通道放进家庭账户或模型页。
- `ChannelsTab` 展示一个微信卡片：未连接时仅有“配置微信”命令；active 状态显示连接、
  idle timeout input（分钟/小时与 API 秒数互转，校验后保存）和破坏性“断开连接”确认；
  `reauth_required` 显示重新连接。
- 配置命令打开 Radix Dialog：创建 attempt 后呈现实际 `img` QR；以稳定 2 秒计时轮询
  `poll`，处理 waiting/scanned/verification required/confirmed/expired/failed。配对码
  input 只在 `verification_required` 时出现，提交后清空值；Dialog close/unmount 清除
  timer 并 cancel 未结束 attempt。不要把二维码装进新卡片，也不要在 UI 显示 token、微信
  ID、context token 或技术说明文字。
- 使用现有 tokens、lucide `QrCode`/`CheckCircle2`/`RefreshCw`/`Unlink`，固定图像容器
  尺寸和 responsive 约束；不用渐变或新色板。不要让长状态文本挤出移动端宽度。

**Step 4: Run test to verify it passes**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/ChannelsTab.test.tsx src/pages/Settings/__tests__/Settings.channels.test.tsx`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/pages/Settings/panels/ChannelsTab.tsx web/src/pages/Settings/Settings.tsx web/src/pages/Settings/Settings.css web/src/pages/Settings/__tests__/ChannelsTab.test.tsx web/src/pages/Settings/__tests__/Settings.channels.test.tsx
git commit -m "feat: add wechat channel settings"
```

### Task 14: 执行跨层验证并记录交付结果

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/plans/2026-08-28-wechat-ilink-channel-gateway-design.md`（仅在实现发现与已确认设计有差异时）

**Step 1: Write the failing test**

没有为已实现行为补写“汇总测试”。列出验收矩阵并逐一运行既有聚焦测试；任何失败先按
`superpowers:systematic-debugging` 追踪根因，再新增最小回归测试，禁止通过删断言获得绿灯。

**Step 2: Run verification commands**

```bash
uv run pytest tests/unit/server/channels tests/unit/server/database/test_channels.py tests/unit/server/services/channels tests/unit/server/app/test_channels_api.py tests/unit/migrations -q
uv run ruff check src/server/channels src/server/database/channels.py src/server/services/channels src/server/app/channels.py src/server/models/channels.py
cd web && pnpm vitest run src/pages/Settings/__tests__/channelsApi.test.ts src/pages/Settings/__tests__/ChannelsTab.test.tsx src/pages/Settings/__tests__/Settings.channels.test.tsx src/lib/__tests__/queryKeys.test.ts src/locales/__tests__/keys.test.ts
cd web && pnpm typecheck && pnpm build
docker compose config >/dev/null
docker compose -f deploy/docker-compose-dev.yml config >/dev/null
docker compose -f deploy/docker-compose-middleware.yml config >/dev/null
docker compose -f deploy/docker-compose-nas.example.yml config >/dev/null
```

Expected: all targeted test groups, Ruff, typecheck/build and compose config commands exit 0.

**Step 3: Perform controlled runtime checks**

在先检查精确容器与端口后，仅启动项目作用域的依赖和服务。使用这个 worktree 已有的
`.env` 运行 migration、`uv run python server.py --host 0.0.0.0 --port 8010`、
`GINLIXFLOW_BASE_URL=http://127.0.0.1:8010 uv run python -m src.server.services.channels.worker`
和 `cd web && VITE_PROXY_BACKEND=http://127.0.0.1:8010 pnpm dev --host 0.0.0.0 --port 5187`。
不得占用另一个 Codex 会话正在使用的 `8000` 与 `5177`。用 mock iLink adapter 或 test
binding 验证：cursor 持久化、文本入站、图片入站、ignored 媒体、6 小时轮换、outbox
retry 和 `-14` 重新认证。不得使用真实微信 token，也不得打印敏感值。通过浏览器确认
`http://<LAN-IP>:5187/settings?tab=channels` 可达，QR dialog 在桌面和手机宽度下没有重叠。

**Step 4: Record verified result**

在 `CHANGELOG.md` 写中文完成记录，包含功能、可靠性/安全边界及实际运行的验证命令。
若实际 SDK/协议与设计存在已确认差异，只更新设计文档的对应决策和引用，不重写历史。

**Step 5: Commit**

```bash
git add CHANGELOG.md docs/plans/2026-08-28-wechat-ilink-channel-gateway-design.md
git commit -m "docs: record wechat channel gateway verification"
```

## 最终人工验收清单

- 在普通用户和学生账号下均能看到设置中的“通道”页签，且各自只能看到、修改和解绑自己的微信绑定。
- 扫码 -> 已扫描 -> 手机确认 -> 已连接能完成；扫码过期、需要短配对码、配对码受阻、取消 Dialog、解绑和 `-14` 都给出可恢复状态，不泄漏 token。
- 从绑定微信发送文本会在用户自己的 Flash thread 中得到最终文本回复；连续消息 6 小时内复用 thread，超过 6 小时新建 thread。
- 图片可作为 Flash 的 `additional_context` 输入；语音、文件/PDF、视频不下载、不调用 Flash、不回复。
- 关闭或重启 gateway worker 后，已有 cursor、inbound、in-flight agent turn 和 delivery outbox 可由租约/稳定 request key 恢复；不会因同一 provider message 或同一 outbox part 创建重复模型 turn。
- 发送失败会重试；发送成功但 ack 丢失的重试保留相同 iLink client id；每条发送严格取其引用 inbound 的 `context_token`。
- `git diff --check`、后端聚焦测试、Ruff、前端 typecheck/build、compose config 和 LAN 前端可达检查都有本次运行的成功证据。
