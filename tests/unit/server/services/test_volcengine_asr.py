"""Pure protocol helpers for the Volcengine ASR relay."""

from __future__ import annotations

import gzip
import json
import struct

from src.config.settings import VolcengineAsrConfig
from src.server.services.volcengine_asr import (
    AUDIO_ONLY_REQUEST,
    FULL_CLIENT_REQUEST,
    LAST_AUDIO_PACKET,
    build_audio_request,
    build_authorization_header,
    build_full_request,
    decode_server_frame,
    map_upstream_error,
)

CONFIG = VolcengineAsrConfig(
    app_id="test-app",
    access_token="test-token",
    access_secret="test-secret",
    cluster="test-cluster",
    ws_url="wss://asr.example.test/api/v2/asr",
)


def _decode_frame(frame: bytes) -> tuple[bytes, bytes]:
    return frame[:4], frame[8:]


def test_full_request_uses_raw_pcm_16khz_mono_and_gzip() -> None:
    frame = build_full_request(CONFIG, request_id="request-1", user_id="user-1")
    header, payload = _decode_frame(frame)
    body = json.loads(gzip.decompress(payload))

    assert header[1] >> 4 == FULL_CLIENT_REQUEST
    assert body["audio"] == {
        "format": "raw",
        "codec": "raw",
        "rate": 16000,
        "bits": 16,
        "channel": 1,
    }


def test_last_audio_packet_has_last_packet_flag() -> None:
    frame = build_audio_request(b"pcm", is_last=True)
    header, payload = _decode_frame(frame)

    assert header[1] >> 4 == AUDIO_ONLY_REQUEST
    assert header[1] & 0x0F == LAST_AUDIO_PACKET
    assert gzip.decompress(payload) == b"pcm"


def test_hmac_header_never_contains_access_secret() -> None:
    header = build_authorization_header(CONFIG)

    assert header.startswith('HMAC256; access_token="test-token";')
    assert "test-secret" not in header


def test_decode_server_result_and_map_error_without_provider_text() -> None:
    result = {"code": 1000, "message": "Success", "result": [{"text": "你好", "utterances": [{"text": "你好", "definite": False}]}]}
    payload = gzip.compress(json.dumps(result).encode())
    frame = bytes((0x10, 0x90, 0x11, 0)) + struct.pack("!I", len(payload)) + payload

    assert decode_server_frame(frame) == {"type": "partial", "text": "你好", "definite": False}
    assert map_upstream_error(1002, "token=test-token") == {
        "type": "error",
        "code": "service_unavailable",
    }
