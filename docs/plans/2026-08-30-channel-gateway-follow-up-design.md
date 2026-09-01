# Channel Gateway Follow-up Design

## Goal

Close the four review findings without expanding the first release beyond its
text-and-image WeChat scope. The result must keep the gateway reusable for a
future channel while retaining PostgreSQL as the sole source of durable state.

## Constraints

- Reuse the public `wechatbot-sdk` protocol and crypto primitives. Do not use
  its file-backed credential store, in-memory cursor, or `WeChatBot.run()`.
- Keep iLink credentials, reply context, cursors, and QR poll state encrypted
  in PostgreSQL only.
- The initial AgentAdapter remains LangAlpha Flash. It must not know that its
  caller is specifically WeChat.
- Do not add a provider registry, an event bus, or a large abstract base class.

## Selected Design

### 1. Small explicit ChannelAdapter capabilities

The existing `ChannelAdapter` protocol gains only the operations the generic
runner already needs:

- `begin_link(previous_credentials)` lets a provider use encrypted existing
  credentials without giving database access to the adapter. WeChat sends its
  one known iLink token as `local_token_list`.
- `max_outbound_text_length` lets the gateway create durable, provider-sized
  outbox rows without a `channel_type == "wechat"` branch.
- `resolve_images(...)` turns normalized provider image references into
  validated `ResolvedImage` values. The gateway no longer probes concrete
  methods with `hasattr`.

`ChannelBindingExpiredError` becomes a provider-neutral contract exception.
Every provider with a revoked binding raises it; the gateway retains the one
reauthentication path.

The adapter owns iLink details such as the 2,000-character limit, natural text
breaks, CDN download, and AES decryption. The gateway owns durable outbox IDs,
ordering, and transactions.

### 2. Safe iLink reconfiguration

When a user starts a new QR attempt while an active binding exists, the linking
service passes its decrypted `BindingCredentials` to the adapter for this one
request. The adapter passes the token to `get_qr_code(local_token_list=...)`.

`binded_redirect` is represented as a successful `LinkPollResult` that marks
`reuse_existing_binding=True`; it deliberately contains no credentials. In the
same finalization transaction, the repository verifies the existing active
binding and marks the QR attempt linked without retiring its epoch, session,
or credentials. A scan for a different account still returns `confirmed` and
uses the existing fenced replacement path.

This supports a future or visible "reconfigure" action without exposing the
token to the browser, logs, or the adapter's persisted challenge state.

### 3. QR poll timeout recovery

The 10-second API deadline remains bounded. A local `asyncio.TimeoutError` is
not a terminal QR result: the service finalizes the attempt as `waiting`,
releases its short lease, and returns the current attempt state. The browser's
two-second poll continues normally instead of receiving a 500 and waiting for
lease expiry. Provider-declared terminal statuses remain unchanged.

### 4. Channel provenance reaches Flash

`AgentTurn` carries `channel_type`, populated from the claimed inbound row.
`LangAlphaFlashAdapter` puts that value into the existing internal chat API's
`platform` field. No platform-specific import or conditional remains in
`GatewayRunner`.

## Non-goals

- iLink typing and notify-start/notify-stop lifecycle calls.
- Voice, file, video, or native outbound image support.
- A generic cross-provider configuration UI or plugin registry.
- Changing existing 6-hour session, inbox/outbox, lease, or epoch semantics.

## Validation

- Write red tests for reused bindings, timeout lease release, natural 2,000
  character splitting, generic expiry propagation, generic image resolution,
  and Flash platform propagation.
- Run the focused backend channel tests, Settings tests, Ruff, and the existing
  production build checks. Live WeChat QR scanning remains a manual provider
  verification step.
