# 火山引擎后端语音识别 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为聊天输入框增加火山引擎豆包语音后端流式识别，优先使用受 Cookie 保护的后端 WebSocket，并在该路径无法启动时保留浏览器 Web Speech API 降级。

**Architecture:** 浏览器将麦克风音频转换为 16 kHz、16-bit、单声道 PCM 并通过同源 WebSocket 连续发送。FastAPI 路由完成会话 Cookie 鉴权后委托 ASR relay service；service 使用火山二进制协议和后端凭据连接上游，向前端发送脱敏的 `partial`、`final`、`error`、`done` 事件。前端 hook 保持一个后端采集路径和现有 Web Speech 降级路径，二者共用文本合并和停止清理。

**Tech Stack:** Python 3.13+、FastAPI、`websockets` 15、pytest/pytest-asyncio；React 19、TypeScript、Web Audio API、Vitest、Testing Library、Lucide。

---

### Task 1: 部署级 ASR 配置

**Files:**
- Modify: `.env.example`
- Modify: `src/config/env.py`
- Modify: `src/config/settings.py`
- Create: `tests/unit/config/test_volcengine_asr.py`

**Step 1: Write the failing test**

```python
from src.config.settings import get_volcengine_asr_config


def test_returns_none_when_required_asr_values_are_missing(monkeypatch):
    monkeypatch.delenv("VOLCENGINE_ASR_APP_ID", raising=False)
    assert get_volcengine_asr_config() is None


def test_reads_deployment_asr_config_without_exposing_secret(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_ASR_APP_ID", "test-app")
    monkeypatch.setenv("VOLCENGINE_ASR_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("VOLCENGINE_ASR_ACCESS_SECRET", "test-secret")
    monkeypatch.setenv("VOLCENGINE_ASR_CLUSTER", "test-cluster")

    config = get_volcengine_asr_config()

    assert config is not None
    assert config.app_id == "test-app"
    assert config.cluster == "test-cluster"
    assert "test-secret" not in repr(config)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/config/test_volcengine_asr.py -q`

Expected: FAIL because `get_volcengine_asr_config` does not exist.

**Step 3: Write minimal implementation**

Add empty-value environment constants in `src/config/env.py`, a frozen/slotted configuration value object in `src/config/settings.py`, and one accessor. Read env values inside the accessor so tests can use `monkeypatch`; return `None` unless app id, access token and cluster are non-empty. Set `repr=False` on token and secret fields. Keep the default WSS URL as `wss://openspeech.bytedance.com/api/v2/asr` and accept an optional `VOLCENGINE_ASR_WS_URL` override.

Add an `.env.example` section with only blank values and comments explaining that all four values stay backend-only. Do not reference, parse or commit `temp_pwd.txt`.

```python
@dataclass(frozen=True, slots=True)
class VolcengineAsrConfig:
    app_id: str
    access_token: str = field(repr=False)
    cluster: str
    access_secret: str = field(default="", repr=False)
    ws_url: str = "wss://openspeech.bytedance.com/api/v2/asr"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/config/test_volcengine_asr.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add .env.example src/config/env.py src/config/settings.py tests/unit/config/test_volcengine_asr.py
git commit -m "feat: add volcengine asr configuration"
```

### Task 2: 火山二进制协议与安全鉴权

**Files:**
- Create: `src/server/services/volcengine_asr.py`
- Create: `tests/unit/server/services/test_volcengine_asr.py`

**Step 1: Write the failing tests**

```python
def test_full_request_uses_raw_pcm_16khz_mono_and_gzip():
    frame = build_full_request(config=CONFIG, request_id="request-1", user_id="user-1")
    header, payload = decode_frame(frame)

    assert header.message_type is MessageType.FULL_CLIENT_REQUEST
    body = gzip.decompress(payload)
    assert json.loads(body)["audio"] == {
        "format": "raw", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1,
    }


def test_last_audio_packet_has_last_packet_flag():
    header, payload = decode_frame(build_audio_request(b"pcm", is_last=True))
    assert header.message_type is MessageType.AUDIO_ONLY_REQUEST
    assert header.flags == LAST_AUDIO_PACKET_FLAG
    assert gzip.decompress(payload) == b"pcm"


def test_hmac_header_never_contains_the_access_secret():
    header = build_authorization_header(CONFIG)
    assert header.startswith('HMAC256; access_token="test-token";')
    assert "test-secret" not in header


def test_upstream_error_is_mapped_to_a_safe_client_event():
    assert map_upstream_error(code=1002, message="token=test-token") == {
        "type": "error", "code": "service_unavailable",
    }
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/services/test_volcengine_asr.py -q`

Expected: FAIL because the module does not exist.

**Step 3: Write minimal implementation**

Implement protocol code as pure functions and values before adding network I/O:

- Build four-byte version-1 headers, big-endian payload sizes, gzip JSON full requests, gzip PCM audio requests, and a final-audio flag.
- Parse full server response and error frames; only parse explicitly supported message/serialization/compression combinations.
- Build `Authorization` as HMAC256 when `access_secret` exists. Use a deterministic `User-Agent` header and sign the exact WebSocket request line and signed header value using HMAC-SHA256 plus URL-safe base64. When no secret exists, use `Bearer; <token>`.
- Generate the request JSON with `show_utterances=true` and `result_type=single`; never accept app id, cluster, token, audio configuration or request sequence from the browser.
- Convert successful utterances into a provider-neutral structure. Maintain final text in the relay, not the browser; map every provider error to a small fixed event. Send only generic `service_unavailable`, `invalid_audio`, `rate_limited`, `timed_out`, or `protocol_error` codes.

```python
def build_audio_request(pcm: bytes, *, is_last: bool) -> bytes:
    flags = LAST_AUDIO_PACKET_FLAG if is_last else 0
    payload = gzip.compress(pcm)
    return _pack_frame(
        message_type=MessageType.AUDIO_ONLY_REQUEST,
        flags=flags,
        serialization=Serialization.NONE,
        compression=Compression.GZIP,
        payload=payload,
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/services/test_volcengine_asr.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/volcengine_asr.py tests/unit/server/services/test_volcengine_asr.py
git commit -m "feat: add volcengine asr protocol client"
```

### Task 3: 受鉴权保护的 ASR WebSocket relay

**Files:**
- Create: `src/server/app/speech.py`
- Modify: `src/server/app/setup.py`
- Create: `tests/unit/server/app/test_speech.py`
- Modify: `tests/unit/server/app/test_generic_router_registration.py`

**Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_relay_authenticates_before_accepting(monkeypatch):
    websocket = FakeWebSocket()
    monkeypatch.setattr("src.server.app.speech.authenticate_websocket", AsyncMock(return_value="user-1"))
    monkeypatch.setattr("src.server.app.speech.get_volcengine_asr_config", lambda: CONFIG)

    await transcribe_stream(websocket)

    assert websocket.accepted is True


@pytest.mark.asyncio
async def test_relay_rejects_text_before_start_and_closes_both_sides():
    websocket = FakeWebSocket(messages=[{"type": "websocket.receive", "text": "not-json"}])

    await transcribe_stream(websocket)

    assert websocket.close_code == 1003
    assert websocket.sent_json[-1] == {"type": "error", "code": "protocol_error"}


def test_speech_route_is_registered():
    assert "/ws/v1/speech/transcribe" in {route.path for route in app.routes}
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/app/test_speech.py tests/unit/server/app/test_generic_router_registration.py -q`

Expected: FAIL because the speech router and handler do not exist.

**Step 3: Write minimal implementation**

Create `speech_router = APIRouter(prefix="/ws/v1", tags=["Speech"])`. The handler must:

1. Call `authenticate_websocket(websocket)` before `accept()`.
2. Resolve config before accepting; when missing, accept only long enough to send `{ "type": "error", "code": "service_unavailable" }`, then close with `1013`.
3. Require one JSON `{ "type": "start" }` frame, then accept only binary PCM frames and one JSON `{ "type": "stop" }` frame.
4. Enforce a conservative packet ceiling (for example 64 KiB), idle timeout and maximum session duration as named module constants.
5. Delegate all vendor I/O to `VolcengineAsrRelay`, which opens `websockets.connect` with the internally generated `Authorization` header, forwards requests, reads upstream responses concurrently, and owns final text composition.
6. On browser disconnect, stop, timeout, malformed messages or upstream failure, send the final packet when appropriate, close the provider socket in `finally`, and never log raw packet bytes or credentials.

Use explicit dependency-free helper functions for client frame validation so they can be unit tested with fake sockets. Do not add process-global session registries: each relay is request scoped.

Register `speech_router` in `setup.py` alongside the other routers. Extend the generic router registration test with the expected route instead of adding a duplicate app bootstrap.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/app/test_speech.py tests/unit/server/app/test_generic_router_registration.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/app/speech.py src/server/app/setup.py tests/unit/server/app/test_speech.py tests/unit/server/app/test_generic_router_registration.py
git commit -m "feat: relay speech recognition through backend"
```

### Task 4: 前端 PCM 转换与分包工具

**Files:**
- Create: `web/src/components/ui/voice-input.pcm.ts`
- Create: `web/src/components/ui/__tests__/voice-input.pcm.test.ts`

**Step 1: Write the failing tests**

```ts
it('converts float samples to little-endian signed PCM16', () => {
  expect(float32ToPcm16(new Float32Array([-1, 0, 1]))).toEqual(
    new Uint8Array([0x00, 0x80, 0x00, 0x00, 0xff, 0x7f]),
  );
});

it('resamples 48 kHz mono audio to 16 kHz and emits 100 ms packets', () => {
  const packetizer = new PcmPacketizer({ sourceRate: 48_000, targetRate: 16_000, packetMs: 100 });
  const packets = packetizer.push(new Float32Array(4_800));

  expect(packets).toHaveLength(1);
  expect(packets[0]).toHaveLength(3_200);
});

it('keeps an incomplete tail for the next audio callback', () => {
  const packetizer = new PcmPacketizer({ sourceRate: 16_000, targetRate: 16_000, packetMs: 100 });
  expect(packetizer.push(new Float32Array(800))).toEqual([]);
  expect(packetizer.push(new Float32Array(800))).toHaveLength(1);
});
```

**Step 2: Run tests to verify they fail**

Run: `cd web && pnpm vitest run src/components/ui/__tests__/voice-input.pcm.test.ts`

Expected: FAIL because the PCM module does not exist.

**Step 3: Write minimal implementation**

Implement pure, browser-independent functions:

- Clamp Float32 samples to `[-1, 1]` and encode signed PCM16 in little-endian order.
- Downsample with a windowed averaging/linear method that maintains fractional source position and tail samples across callback boundaries; no external audio package.
- Buffer resampled PCM until it has 1600 samples, emit fixed 3200-byte packet `ArrayBuffer`s, and retain the tail.
- Expose `flush()` for a bounded final tail so the hook can send the last audio packet before `stop`.

Keep microphone permissions and WebSocket concerns out of this module so it remains deterministic under Vitest.

**Step 4: Run tests to verify they pass**

Run: `cd web && pnpm vitest run src/components/ui/__tests__/voice-input.pcm.test.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/components/ui/voice-input.pcm.ts web/src/components/ui/__tests__/voice-input.pcm.test.ts
git commit -m "feat: add pcm packetizer for speech input"
```

### Task 5: 后端优先语音输入 hook 与浏览器降级

**Files:**
- Modify: `web/src/components/ui/chat-input.useVoiceInput.ts`
- Modify: `web/src/components/ui/chat-input.tsx`
- Create: `web/src/components/ui/__tests__/chat-input.useVoiceInput.test.tsx`
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`

**Step 1: Write the failing tests**

```tsx
it('opens the backend speech WebSocket before creating browser recognition', async () => {
  renderHook(() => useVoiceInput({ message: '', setMessage, isLoading: false }));
  await act(() => result.current.toggleListening());

  expect(MockWebSocket).toHaveBeenCalledWith(expect.stringMatching(/\/ws\/v1\/speech\/transcribe$/));
  expect(MockSpeechRecognition).not.toHaveBeenCalled();
});

it('uses the browser recognizer after backend startup fails', async () => {
  mockSocketOpenFailure();
  renderHook(() => useVoiceInput({ message: '', setMessage, isLoading: false }));

  await act(() => result.current.toggleListening());

  expect(MockSpeechRecognition).toHaveBeenCalledOnce();
});

it('combines final and partial backend transcripts without duplication', async () => {
  // receive final "hello" then partial "world"
  expect(setMessage).toHaveBeenLastCalledWith('hello world');
});

it('releases tracks, closes AudioContext, and sends stop when stopped', async () => {
  await act(() => result.current.stopListening());
  expect(track.stop).toHaveBeenCalledOnce();
  expect(audioContext.close).toHaveBeenCalledOnce();
  expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: 'stop' }));
});
```

**Step 2: Run tests to verify they fail**

Run: `cd web && pnpm vitest run src/components/ui/__tests__/chat-input.useVoiceInput.test.tsx`

Expected: FAIL because the hook still instantiates `SpeechRecognition` immediately.

**Step 3: Write minimal implementation**

Refactor the existing hook into narrowly scoped helpers:

- `backendSpeechSupported` checks WebSocket, `navigator.mediaDevices.getUserMedia`, AudioContext and the current origin; `browserSpeechSupported` keeps the current `SpeechRecognition` detection. `speechSupported` becomes their logical OR so the button remains visible when only backend capture is available.
- `startBackendSpeech()` opens a same-origin `ws:`/`wss:` URL at `/ws/v1/speech/transcribe`, waits for the open/ready sequence, sends `{ type: 'start' }`, requests mono microphone input, and pipes source node callbacks through `PcmPacketizer`.
- Prefer AudioWorklet when `audioWorklet` is available. Retain a ScriptProcessor fallback only for older browsers. Pass the actual source sample rate into `PcmPacketizer`; do not assume browser hardware runs at 16 kHz.
- Treat a backend failure before the first successful recognition event as a fallback trigger. Start existing `SpeechRecognition` and append to the same base/final/interim transcript state. A failure after backend text exists displays a generic service toast and preserves text; it must not expose upstream details.
- On `partial`, replace only the current partial segment; on `final`, append once and clear the current partial segment. On `done`, stop cleanly without losing text.
- Reuse stop logic for send, typing/IME interrupts, loading changes and unmount. It must close the socket, stop tracks, disconnect nodes, close AudioContext and stop/abort browser recognition idempotently.

In `chat-input.tsx`, replace the recording-state `MicOff` import/render with `Square`. Preserve class names, `title`, `aria-label`, animation and `voice_input_enabled` gate. Add only necessary locale strings for backend service failure; reuse existing keys otherwise.

**Step 4: Run tests to verify they pass**

Run: `cd web && pnpm vitest run src/components/ui/__tests__/chat-input.useVoiceInput.test.tsx`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/components/ui/chat-input.useVoiceInput.ts web/src/components/ui/chat-input.tsx web/src/components/ui/__tests__/chat-input.useVoiceInput.test.tsx web/src/locales/en-US.json web/src/locales/zh-CN.json
git commit -m "feat: stream voice input through backend stt"
```

### Task 6: 端到端回归验证与变更记录

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add the release-note test target**

No production test is added in this task. First run the complete focused suite from Tasks 1-5 to establish the final behavior before changing the changelog.

**Step 2: Run verification before the changelog change**

Run:

```bash
uv run pytest \
  tests/unit/config/test_volcengine_asr.py \
  tests/unit/server/services/test_volcengine_asr.py \
  tests/unit/server/app/test_speech.py \
  tests/unit/server/app/test_generic_router_registration.py -q
cd web && pnpm typecheck
cd web && pnpm vitest run \
  src/components/ui/__tests__/voice-input.pcm.test.ts \
  src/components/ui/__tests__/chat-input.useVoiceInput.test.tsx
```

Expected: all tests pass and typecheck succeeds.

**Step 3: Record the user-visible change**

Add a concise Chinese `CHANGELOG.md` entry describing the backend relay, 16 kHz PCM streaming, no-browser-secret boundary, browser recognition fallback, and the recording stop icon. Do not mention or include local credential paths or values.

**Step 4: Run final verification**

Run:

```bash
uv run pytest \
  tests/unit/config/test_volcengine_asr.py \
  tests/unit/server/services/test_volcengine_asr.py \
  tests/unit/server/app/test_speech.py \
  tests/unit/server/app/test_generic_router_registration.py -q
cd web && pnpm typecheck
cd web && pnpm vitest run \
  src/components/ui/__tests__/voice-input.pcm.test.ts \
  src/components/ui/__tests__/chat-input.useVoiceInput.test.tsx
cd web && pnpm dev --host 0.0.0.0 --port 5177
```

Expected: automated checks pass; the dev server listens on `0.0.0.0:5177`. Open the chat page in a browser to verify the existing recording animation is unchanged and the recording control renders a square stop icon. Do not attempt a live provider call until deployment variables are set locally.

**Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: record backend speech recognition"
```
