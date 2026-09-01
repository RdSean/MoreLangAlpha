# WeChat iLink Context Message Budget Design

**Date:** 2026-09-01

## Goal

Keep complete Flash answers deliverable through WeChat iLink while respecting
the provider's two independent limits: roughly 2000 characters per message and
at most 10 bot bubbles for one inbound `context_token`.

## Findings From Hermes and iLink

Hermes provides useful presentation primitives but does not implement the
iLink context budget. Its Weixin adapter sends each result of
`_split_text_for_weixin_delivery()` sequentially and uses a 4000-character
limit. Its delivery helper only truncates for adapters that do not advertise
native chunking. The copied `_split_delivery_units_for_weixin()` path also
turns short top-level units into independent messages; its packing helper is
only reached when one unit is already oversized. Hermes' low-level POST helper
checks HTTP status but does not inspect a successful HTTP response containing a
business-level `ret=-2` rate-limit result.

LangAlpha must therefore reuse the good parts (Markdown normalization, natural
boundaries, code-fence preservation, final-only delivery) while adding iLink
specific state and error handling.

## Design

### 1. Final text packing

`WeChatILinkAdapter.prepare_outbound_parts()` will normalize Markdown and feed
all ordinary text units to one greedy packer. Units are joined with a blank
line until the configured 2000-character limit is reached. An individual
oversized unit uses the existing natural newline/space splitter and preserves
fenced code blocks. Short units must never become one bubble each merely
because the model emitted separate headings or list lines.

The adapter's limit remains 2000 characters, which is conservative against the
provider's observed 2000-2400 range. The gateway performs no second semantic
split beyond the adapter's provider-sized parts.

### 2. Per-context message budget

The provider budget is represented explicitly as `10` messages per inbound
context. Normal responses with at most 10 packed parts are sent in order.
Responses requiring more than 10 parts reserve one slot for a continuation
notice, send at most nine content parts, and persist the remaining parts.

The notice instructs the user to send `继续`. A bot cannot obtain a fresh
context token itself; only the user's next inbound message supplies one. The
continuation therefore uses the next inbound `reply_context` and consumes a
fresh budget. A non-continuation message leaves the queued tail untouched;
explicit continuation is required so an unrelated question is not polluted.

Continuation state is durable, encrypted PostgreSQL state scoped to the
binding/session. It includes the remaining provider-neutral text parts, an
expiry aligned with the channel's idle timeout, and enough metadata to create
the next ordered outbox batch. No token or raw provider payload is logged.

### 3. Business error handling

The SDK's non-zero `ret`/`errcode` parsing remains the low-level source of
truth. An iLink `ret=-2` or equivalent rate-limit response becomes a typed
context-budget error. The delivery worker must stop retrying that response
under the exhausted token, persist the unsent tail, and avoid consuming all
eight generic retries. Raw error code and a redacted message are retained for
diagnostics; credentials, context tokens, and full payloads are not.

Transport failures and session expiry keep their existing retry/reauthorization
behavior. A context-budget error is not a session expiry and must not mark the
binding for reauthentication.

### 4. Stream and history guarantees

Structured stream events remain presentation-only. WeChat continues to hide
reasoning, tool chrome, and intermediate deltas; the complete main-agent text
is accumulated before the durable outbox write. The outbox remains the only
provider send path, so retries and worker restarts cannot duplicate an already
acknowledged part.

## Alternatives Rejected

- Sending all parts and hoping the provider accepts more than 10: loses the
  tail deterministically and creates misleading successful delivery state.
- Omitting or inventing `context_token`: violates iLink routing semantics and
  does not create a new quota.
- Hard truncating every answer to ten chunks: silently discards user-visible
  content instead of offering explicit continuation.
- Sending one token at a time: consumes the quota immediately and contradicts
  iLink's final-message model.

## References

- Hermes Weixin adapter:
  `docs/references/wechat-ilink/hermes/weixin-tutorial.py`
- Hermes base adapter and `truncate_message()`:
  `docs/references/wechat-ilink/hermes/base.py`
- Hermes delivery and stream dispatch:
  `docs/references/wechat-ilink/hermes/delivery.py`,
  `docs/references/wechat-ilink/hermes/stream_dispatch.py`
- Local iLink protocol reference:
  `docs/references/wechat-ilink/wechatbot/protocol.md`
- Upstream SDK implementation:
  `/Users/seanlee/DevelopCode/MoreAlpha/wechatbot/python/wechatbot/client.py`
  and `protocol.py`
