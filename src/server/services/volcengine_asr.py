"""Small protocol helpers for the Volcengine one-sentence ASR WebSocket."""

from __future__ import annotations

import gzip
import json
import struct

from src.config.settings import VolcengineAsrConfig

FULL_CLIENT_REQUEST = 0x1
AUDIO_ONLY_REQUEST = 0x2
FULL_SERVER_RESPONSE = 0x9
SERVER_ERROR = 0xF
LAST_AUDIO_PACKET = 0x2
def _pack_frame(message_type: int, payload: bytes, *, flags: int = 0, json_payload: bool = False) -> bytes:
    serialization = 0x1 if json_payload else 0x0
    header = bytes((0x11, (message_type << 4) | flags, (serialization << 4) | 0x1, 0x0))
    return header + struct.pack("!I", len(payload)) + payload


def build_full_request(config: VolcengineAsrConfig, *, request_id: str, user_id: str) -> bytes:
    body = {
        "app": {"appid": config.app_id, "token": config.access_token, "cluster": config.cluster},
        "user": {"uid": user_id},
        "audio": {"format": "raw", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
        "request": {
            "reqid": request_id,
            "sequence": 1,
            "nbest": 1,
            "show_utterances": True,
            "result_type": "single",
        },
    }
    return _pack_frame(
        FULL_CLIENT_REQUEST,
        gzip.compress(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()),
        json_payload=True,
    )


def build_audio_request(pcm: bytes, *, is_last: bool = False) -> bytes:
    return _pack_frame(
        AUDIO_ONLY_REQUEST,
        gzip.compress(pcm),
        flags=LAST_AUDIO_PACKET if is_last else 0,
    )


def build_authorization_header(config: VolcengineAsrConfig) -> str:
    """Use the provider's documented token-authentication default."""
    return f"Bearer; {config.access_token}"


def decode_server_frame(frame: bytes) -> dict[str, object]:
    if len(frame) < 8:
        raise ValueError("short ASR frame")
    header_size = (frame[0] & 0x0F) * 4
    if header_size < 4 or len(frame) < header_size:
        raise ValueError("invalid ASR header")
    message_type = frame[1] >> 4
    payload = frame[header_size:]
    if message_type == SERVER_ERROR:
        if len(payload) < 8:
            raise ValueError("short ASR error frame")
        error_code, message_size = struct.unpack("!II", payload[:8])
        if len(payload[8:]) != message_size:
            raise ValueError("truncated ASR error frame")
        return map_upstream_error(error_code)

    if len(payload) < 4:
        raise ValueError("short ASR response payload")
    payload_size = struct.unpack("!I", payload[:4])[0]
    payload = payload[4 : 4 + payload_size]
    if len(payload) != payload_size:
        raise ValueError("truncated ASR frame")
    if message_type != FULL_SERVER_RESPONSE:
        raise ValueError("unsupported ASR response")

    body = json.loads(gzip.decompress(payload))
    if body.get("code") != 1000:
        return map_upstream_error(body.get("code"), body.get("message"))
    result = (body.get("result") or [{}])[0]
    utterances = result.get("utterances") or []
    utterance = utterances[-1] if utterances else result
    return {
        "type": "final" if utterance.get("definite", True) else "partial",
        "text": utterance.get("text", result.get("text", "")),
        "definite": bool(utterance.get("definite", True)),
    }


def map_upstream_error(code: object, _message: object = None) -> dict[str, str]:
    if code == 45000030:
        safe_code = "resource_not_granted"
    elif code in (1002, 1005, 1099):
        safe_code = "service_unavailable"
    elif code in (1003, 1004):
        safe_code = "rate_limited"
    elif code in (1010, 1011, 1012):
        safe_code = "invalid_audio"
    elif code == 1013:
        safe_code = "no_speech"
    elif code in (1020, 1021):
        safe_code = "timed_out"
    else:
        safe_code = "protocol_error"
    return {"type": "error", "code": safe_code}
