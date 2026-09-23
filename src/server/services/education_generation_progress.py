"""Normalize and stage safe semantic progress events for managed generation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import json
import math
import re
from typing import Any
import unicodedata


PROGRESS_STAGES = frozenset(
    {
        "chapter_analysis",
        "content_processing",
        "knowledge_point_generation",
        "lesson_preparation",
    }
)
PROGRESS_STATUSES = frozenset(
    {
        "queued",
        "running",
        "completed",
        "failed",
        "skipped",
    }
)
MAX_LABEL_LENGTH = 200
MAX_DETAIL_LENGTH = 1_000
MAX_EVENT_KEY_LENGTH = 255
MAX_SUBSTAGE_LENGTH = 64
MAX_NODE_KEY_LENGTH = 255
MAX_COUNT_VALUE = 2_147_483_647
MAX_METADATA_DEPTH = 3
MAX_METADATA_ITEMS = 50
MAX_METADATA_STRING_LENGTH = 500
MAX_METADATA_INTEGER = 9_223_372_036_854_775_807
MAX_PROGRESS_EVENT_BYTES = 64 * 1024
MAX_PROGRESS_STRING_BYTES = 8 * 1024

_ALLOWED_FIELDS = frozenset(
    {
        "event_key",
        "stage",
        "substage",
        "status",
        "label",
        "detail",
        "node_key",
        "current",
        "total",
        "current_value",
        "total_value",
        "timestamp",
        "metadata",
    }
)
_FORBIDDEN_FIELD_KEYS = frozenset(
    {
        "reasoning",
        "chain_of_thought",
        "prompt",
        "prompts",
        "tool_args",
        "tool_arguments",
        "tool_result",
        "tool_results",
        "credential",
        "credentials",
        "secret",
        "secrets",
        "sandbox_path",
        "api_key",
        "access_token",
        "authorization",
        "password",
    }
)
_LINE_BREAK_RE = re.compile(r"\r\n|[\t\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_SUBSTAGE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_EVENT_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}:"
    r"(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,63}:){1,4}"
    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,126}$"
)
_REJECTED_EVENT_KEY_PREFIXES = frozenset(
    {"probe", "diagnostic", "test", "debug"}
)
_NODE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_UNSAFE_TEXT_PATTERN_STRINGS = (
    r"^/(?!/)[^\s]+",
    r"['\"=(\[{:,;]/(?!/)[^\s]+",
    r"(?i)(?<![:/])/(?:managed|home|tmp|etc|users|private|var|workspace)(?:/|$)",
    r"(?<![:/])/(?!/)[^\s/]+/[^\s]*",
    r"/(?!/)[^\s/]+\.[0-9A-Za-z]{1,8}(?![0-9A-Za-z])",
    r"\s/(?!/)[a-z][a-z0-9._-]*(?![A-Za-z0-9])",
    r"(?i)(?:^|[\s='\"(:;,])(?:[A-Za-z]:[\\/]|\\\\)[^\s]*",
    r"(?i)(?:file|s3)://",
    r"(?i)https?://[^/\s:@]+:[^/\s@]+@",
    (
        r"(?i)[\"']?(?:api|access|secret|private|public|client)[_-]?"
        r"(?:key|token|secret)(?:[_-]?id)?[\"']?\s*[:=]\s*"
        r"[\"']?[^\s\"'},]+"
    ),
    (
        r"(?i)[\"']?(?:password|passwd|credential|credentials|token)"
        r"[a-z0-9_-]*[\"']?"
        r"\s*[:=]\s*[\"']?[^\s\"'},]+"
    ),
    (
        r"(?i)(?:openai|anthropic|github)[a-z0-9_-]*"
        r"(?:api[_-]?key|access[_-]?token|secret[_-]?key|token|secret|key)"
        r"(?:\s*[:=]\s*|\s+)[\"']?[^\s\"'},]+"
    ),
    r"(?i)(?:sk-|ghp_|github_pat_|glpat-|xox[baprs]-)[a-z0-9_-]{12,}",
    r"(?i)(?:AKIA|ASIA)[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)bearer\s+[a-z0-9._~+/-]{16,}",
)
_UNSAFE_TEXT_PATTERNS = tuple(
    re.compile(pattern) for pattern in _UNSAFE_TEXT_PATTERN_STRINGS
)


class ProgressEventValidationError(ValueError):
    """A managed progress event violates the semantic safety contract."""


def _validate_string_budget(value: object, *, label: str) -> None:
    if not isinstance(value, str):
        return
    if len(value.encode("utf-8")) > MAX_PROGRESS_STRING_BYTES:
        raise ProgressEventValidationError(f"{label} exceeds the string size limit")
    if any(unicodedata.category(character) == "Cf" for character in value):
        raise ProgressEventValidationError(f"{label} contains format controls")


def _validate_raw_string_budgets(raw: object) -> None:
    stack = [raw]
    while stack:
        value = stack.pop()
        if isinstance(value, str):
            _validate_string_budget(value, label="progress string")
        elif isinstance(value, Mapping):
            for key, nested in value.items():
                if not isinstance(key, str):
                    raise ProgressEventValidationError(
                        "progress metadata keys must be strings"
                    )
                _validate_string_budget(key, label="progress metadata key")
                stack.append(nested)
        elif isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray),
        ):
            stack.extend(value)


def _normalize_text(value: object, *, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ProgressEventValidationError(f"{label} must be a string")
    _validate_string_budget(value, label=label)
    normalized = _LINE_BREAK_RE.sub(" ", value)
    if _CONTROL_RE.search(normalized):
        raise ProgressEventValidationError(f"{label} contains control characters")
    normalized = " ".join(normalized.split())
    _reject_unsafe_text(normalized, label=label)
    return normalized[:limit]


def _normalize_substage(value: object) -> str | None:
    normalized = _normalize_text(
        value,
        label="progress substage",
        limit=MAX_SUBSTAGE_LENGTH,
    )
    if not normalized:
        return None
    normalized = re.sub(r"[\s-]+", "_", normalized.lower())
    if not _SUBSTAGE_RE.fullmatch(normalized):
        raise ProgressEventValidationError("progress substage is invalid")
    return normalized


def _reject_unsafe_text(value: str, *, label: str) -> None:
    if any(pattern.search(value) for pattern in _UNSAFE_TEXT_PATTERNS):
        raise ProgressEventValidationError(f"{label} contains unsafe content")


def _normalize_key(value: object, *, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str):
        raise ProgressEventValidationError(f"{label} must be a string")
    _validate_string_budget(value, label=label)
    normalized = value.strip()
    if not normalized or not pattern.fullmatch(normalized):
        raise ProgressEventValidationError(f"{label} is invalid")
    _reject_unsafe_text(normalized, label=label)
    return normalized


def _normalized_field_key(key: object) -> str:
    if not isinstance(key, str):
        raise ProgressEventValidationError("metadata keys must be strings")
    _validate_string_budget(key, label="progress metadata key")
    normalized = re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
    return normalized


def _reject_forbidden_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if _normalized_field_key(key) in _FORBIDDEN_FIELD_KEYS:
                raise ProgressEventValidationError(
                    "progress event contains a forbidden field"
                )
            _reject_forbidden_fields(nested)
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for nested in value:
            _reject_forbidden_fields(nested)


def _normalize_metadata_value(value: object, *, depth: int) -> object:
    if depth > MAX_METADATA_DEPTH:
        raise ProgressEventValidationError("progress metadata is too deeply nested")
    if isinstance(value, str):
        return _normalize_text(
            value,
            label="progress metadata text",
            limit=MAX_METADATA_STRING_LENGTH,
        )
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_METADATA_INTEGER:
            raise ProgressEventValidationError("progress metadata integer is unsafe")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProgressEventValidationError("progress metadata number is invalid")
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_METADATA_ITEMS:
            raise ProgressEventValidationError("progress metadata has too many fields")
        normalized: dict[str, object] = {}
        for key, nested in value.items():
            normalized_key = _normalized_field_key(key)
            if not normalized_key or len(normalized_key) > 100:
                raise ProgressEventValidationError("progress metadata key is invalid")
            normalized[normalized_key] = _normalize_metadata_value(
                nested,
                depth=depth + 1,
            )
        return normalized
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        if len(value) > MAX_METADATA_ITEMS:
            raise ProgressEventValidationError("progress metadata has too many items")
        return [_normalize_metadata_value(nested, depth=depth + 1) for nested in value]
    raise ProgressEventValidationError("progress metadata value is unsupported")


def _normalize_count(raw: object, *, label: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ProgressEventValidationError(f"{label} must be an integer")
    if raw < 0 or raw > MAX_COUNT_VALUE:
        raise ProgressEventValidationError(f"{label} is outside the allowed range")
    return raw


def _count_field(
    event: Mapping[str, object],
    *,
    primary: str,
    alias: str,
    label: str,
) -> int | None:
    if primary in event and alias in event and event[primary] != event[alias]:
        raise ProgressEventValidationError(f"{label} fields disagree")
    value = event[primary] if primary in event else event.get(alias)
    return _normalize_count(value, label=label)


def _normalize_timestamp(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ProgressEventValidationError("progress timestamp must be a string")
    _validate_string_budget(raw, label="progress timestamp")
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProgressEventValidationError("progress timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ProgressEventValidationError("progress timestamp must include a timezone")
    return raw.strip()


def parse_progress_event(raw: object) -> dict[str, Any]:
    """Return the bounded, non-secret projection persisted from one progress event."""
    if not isinstance(raw, Mapping):
        raise ProgressEventValidationError("progress event must be an object")
    _validate_raw_string_budgets(raw)
    unknown_fields = set(raw) - _ALLOWED_FIELDS
    if unknown_fields:
        raise ProgressEventValidationError("progress event contains unknown fields")
    _reject_forbidden_fields(raw)

    event_key = _normalize_key(
        raw.get("event_key"),
        label="progress event_key",
        pattern=_EVENT_KEY_RE,
    )
    if len(event_key) > MAX_EVENT_KEY_LENGTH:
        raise ProgressEventValidationError("progress event_key is too long")
    if event_key.split(":", 1)[0].lower() in _REJECTED_EVENT_KEY_PREFIXES:
        raise ProgressEventValidationError("progress event_key prefix is reserved")
    stage_raw = raw.get("stage")
    if not isinstance(stage_raw, str):
        raise ProgressEventValidationError("progress stage must be a string")
    stage = stage_raw.strip().lower()
    if stage not in PROGRESS_STAGES:
        raise ProgressEventValidationError("progress stage is invalid")

    status_raw = raw.get("status")
    if not isinstance(status_raw, str):
        raise ProgressEventValidationError("progress status must be a string")
    status = status_raw.strip().lower()
    if status not in PROGRESS_STATUSES:
        raise ProgressEventValidationError("progress status is invalid")

    metadata = None
    if raw.get("metadata") is not None:
        metadata = _normalize_metadata_value(raw["metadata"], depth=0)
        if not isinstance(metadata, dict):
            raise ProgressEventValidationError("progress metadata must be an object")
    if status == "skipped" and (
        not isinstance(metadata, dict)
        or metadata.get("reason") != "checkpoint_review"
    ):
        raise ProgressEventValidationError(
            "progress skipped status requires checkpoint_review reason"
        )

    substage = (
        _normalize_substage(raw["substage"])
        if raw.get("substage") is not None
        else None
    )
    label_raw = raw.get("label")
    if label_raw is None or (isinstance(label_raw, str) and not label_raw.strip()):
        label = f"{stage} {status}"
    else:
        label = _normalize_text(
            label_raw,
            label="progress label",
            limit=MAX_LABEL_LENGTH,
        )
        if not label:
            label = f"{stage} {status}"

    normalized: dict[str, Any] = {
        "event_key": event_key,
        "stage": stage,
        "status": status,
        "label": label,
    }
    if substage is not None:
        normalized["substage"] = substage
    if raw.get("detail") is not None:
        detail = _normalize_text(
            raw["detail"],
            label="progress detail",
            limit=MAX_DETAIL_LENGTH,
        )
        if detail:
            normalized["detail"] = detail
    if raw.get("node_key") is not None:
        normalized["node_key"] = _normalize_key(
            raw["node_key"],
            label="progress node_key",
            pattern=_NODE_KEY_RE,
        )

    current_value = _count_field(
        raw,
        primary="current_value",
        alias="current",
        label="progress current count",
    )
    total_value = _count_field(
        raw,
        primary="total_value",
        alias="total",
        label="progress total count",
    )
    if current_value is not None and total_value is not None:
        if current_value > total_value:
            raise ProgressEventValidationError(
                "progress current count exceeds total count"
            )
    if current_value is not None:
        normalized["current_value"] = current_value
    if total_value is not None:
        normalized["total_value"] = total_value

    timestamp = _normalize_timestamp(raw.get("timestamp"))
    if timestamp is not None:
        normalized["timestamp"] = timestamp
    if metadata is not None:
        normalized["metadata"] = metadata
    return normalized


def _reject_json_constant(value: str) -> None:
    raise ProgressEventValidationError(f"non-standard JSON constant: {value}")


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    decoded: dict[str, object] = {}
    for key, value in pairs:
        if key in decoded:
            raise ProgressEventValidationError("duplicate JSON key")
        decoded[key] = value
    return decoded


def _parse_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ProgressEventValidationError("non-finite JSON number")
    return parsed


def parse_progress_json_line(raw_line: str | bytes) -> dict[str, Any]:
    """Parse one bounded JSONL event and return its normalized projection."""
    if isinstance(raw_line, bytes):
        try:
            line = raw_line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProgressEventValidationError(
                "progress line must be UTF-8"
            ) from exc
    elif isinstance(raw_line, str):
        line = raw_line
    else:
        raise ProgressEventValidationError("progress line must be text or bytes")
    if len(line.encode("utf-8")) > MAX_PROGRESS_EVENT_BYTES:
        raise ProgressEventValidationError("progress line exceeds the event size limit")
    try:
        decoded = json.loads(
            line,
            parse_constant=_reject_json_constant,
            parse_float=_parse_json_float,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, ProgressEventValidationError):
            raise
        raise ProgressEventValidationError("progress line is invalid JSON") from exc
    return parse_progress_event(decoded)


def is_accepted_progress_event(raw: object) -> bool:
    """Whether one persisted row still satisfies the authoritative parser contract."""
    if not isinstance(raw, Mapping):
        return False
    candidate = {key: value for key, value in raw.items() if key in _ALLOWED_FIELDS}
    try:
        parse_progress_event(candidate)
    except ProgressEventValidationError:
        return False
    return True


_PROGRESS_HELPER_TEMPLATE = '''\
#!/usr/bin/env python3
"""Append one validated semantic progress event for the managed pipeline."""

from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys
import unicodedata


STAGES = __STAGES__
STATUSES = __STATUSES__
FORBIDDEN_FIELDS = __FORBIDDEN_FIELDS__
ALLOWED_FIELDS = __ALLOWED_FIELDS__
MAX_LABEL_LENGTH = __MAX_LABEL_LENGTH__
MAX_DETAIL_LENGTH = __MAX_DETAIL_LENGTH__
MAX_COUNT_VALUE = __MAX_COUNT_VALUE__
MAX_METADATA_DEPTH = __MAX_METADATA_DEPTH__
MAX_METADATA_ITEMS = __MAX_METADATA_ITEMS__
MAX_METADATA_STRING_LENGTH = __MAX_METADATA_STRING_LENGTH__
MAX_METADATA_INTEGER = __MAX_METADATA_INTEGER__
MAX_PROGRESS_EVENT_BYTES = __MAX_PROGRESS_EVENT_BYTES__
MAX_PROGRESS_STRING_BYTES = __MAX_PROGRESS_STRING_BYTES__
LINE_BREAK_RE = re.compile(r"\\r\\n|[\\t\\n\\r\\v\\f\\x1c-\\x1e\\x85\\u2028\\u2029]")
CONTROL_RE = re.compile(r"[\\x00-\\x1f\\x7f-\\x9f]")
SUBSTAGE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
EVENT_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}:"
    r"(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,63}:){1,4}"
    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,126}$"
)
REJECTED_EVENT_KEY_PREFIXES = __REJECTED_EVENT_KEY_PREFIXES__
NODE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
UNSAFE_TEXT_PATTERNS = tuple(
    re.compile(pattern) for pattern in __UNSAFE_TEXT_PATTERNS__
)


class InvalidProgress(ValueError):
    pass


def validate_string_budget(value: str) -> None:
    if len(value.encode("utf-8")) > MAX_PROGRESS_STRING_BYTES:
        raise InvalidProgress("string size limit")
    if any(unicodedata.category(character) == "Cf" for character in value):
        raise InvalidProgress("format control")


def validate_string_budgets(raw: object) -> None:
    stack = [raw]
    while stack:
        value = stack.pop()
        if isinstance(value, str):
            validate_string_budget(value)
        elif isinstance(value, dict):
            for key, nested in value.items():
                if not isinstance(key, str):
                    raise InvalidProgress("metadata key must be a string")
                validate_string_budget(key)
                stack.append(nested)
        elif isinstance(value, list):
            stack.extend(value)


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    output = {}
    for key, value in pairs:
        if key in output:
            raise InvalidProgress("duplicate JSON key")
        output[key] = value
    return output


def reject_unsafe_text(value: str) -> None:
    if any(pattern.search(value) for pattern in UNSAFE_TEXT_PATTERNS):
        raise InvalidProgress("unsafe progress text")


def clean_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        raise InvalidProgress("text field must be a string")
    validate_string_budget(value)
    normalized = LINE_BREAK_RE.sub(" ", value)
    if CONTROL_RE.search(normalized):
        raise InvalidProgress("control character")
    normalized = " ".join(normalized.split())
    reject_unsafe_text(normalized)
    return normalized[:limit]


def reject_forbidden(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise InvalidProgress("metadata key must be a string")
            normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            if normalized in FORBIDDEN_FIELDS:
                raise InvalidProgress("forbidden field")
            reject_forbidden(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_forbidden(nested)


def metadata_value(value: object, depth: int) -> object:
    if depth > MAX_METADATA_DEPTH:
        raise InvalidProgress("metadata too deep")
    if isinstance(value, str):
        return clean_text(value, MAX_METADATA_STRING_LENGTH)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_METADATA_INTEGER:
            raise InvalidProgress("metadata integer")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidProgress("metadata number")
        return value
    if isinstance(value, dict):
        if len(value) > MAX_METADATA_ITEMS:
            raise InvalidProgress("metadata size")
        output = {}
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            if not normalized or len(normalized) > 100:
                raise InvalidProgress("metadata key")
            output[normalized] = metadata_value(nested, depth + 1)
        return output
    if isinstance(value, list):
        if len(value) > MAX_METADATA_ITEMS:
            raise InvalidProgress("metadata size")
        return [metadata_value(nested, depth + 1) for nested in value]
    raise InvalidProgress("metadata value")


def count_field(event: dict, primary: str, alias: str) -> int | None:
    if primary in event and alias in event and event[primary] != event[alias]:
        raise InvalidProgress("count fields disagree")
    value = event[primary] if primary in event else event.get(alias)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidProgress("count must be an integer")
    if value < 0 or value > MAX_COUNT_VALUE:
        raise InvalidProgress("count range")
    return value


def timestamp_value(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidProgress("timestamp must be a string")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise InvalidProgress("timestamp timezone")
    return value.strip()


def parse_event(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise InvalidProgress("progress event must be an object")
    validate_string_budgets(raw)
    if set(raw) - set(ALLOWED_FIELDS):
        raise InvalidProgress("unknown field")
    reject_forbidden(raw)
    event_key = raw.get("event_key")
    if not isinstance(event_key, str) or not EVENT_KEY_RE.fullmatch(event_key.strip()):
        raise InvalidProgress("event_key")
    event_key = event_key.strip()
    if len(event_key) > MAX_EVENT_KEY_LENGTH:
        raise InvalidProgress("event_key length")
    if event_key.split(":", 1)[0].lower() in REJECTED_EVENT_KEY_PREFIXES:
        raise InvalidProgress("event_key prefix")
    reject_unsafe_text(event_key)
    stage = raw.get("stage")
    status = raw.get("status")
    if not isinstance(stage, str) or stage.strip().lower() not in STAGES:
        raise InvalidProgress("stage")
    if not isinstance(status, str) or status.strip().lower() not in STATUSES:
        raise InvalidProgress("status")
    stage = stage.strip().lower()
    status = status.strip().lower()
    metadata = None
    if raw.get("metadata") is not None:
        metadata = metadata_value(raw["metadata"], 0)
        if not isinstance(metadata, dict):
            raise InvalidProgress("metadata object")
    if status == "skipped" and (
        not isinstance(metadata, dict)
        or metadata.get("reason") != "checkpoint_review"
    ):
        raise InvalidProgress("skipped reason")
    output = {"event_key": event_key, "stage": stage, "status": status}

    substage = raw.get("substage")
    if substage is not None:
        normalized = clean_text(substage, 64).lower()
        normalized = re.sub(r"[\\s-]+", "_", normalized)
        if not SUBSTAGE_RE.fullmatch(normalized):
            raise InvalidProgress("substage")
        output["substage"] = normalized

    label = raw.get("label")
    if label is None or (isinstance(label, str) and not label.strip()):
        label = f"{stage} {status}"
    else:
        label = clean_text(label, MAX_LABEL_LENGTH) or f"{stage} {status}"
    output["label"] = label

    detail = raw.get("detail")
    if detail is not None:
        normalized = clean_text(detail, MAX_DETAIL_LENGTH)
        if normalized:
            output["detail"] = normalized
    node_key = raw.get("node_key")
    if node_key is not None:
        if not isinstance(node_key, str) or not NODE_KEY_RE.fullmatch(node_key.strip()):
            raise InvalidProgress("node_key")
        node_key = node_key.strip()
        reject_unsafe_text(node_key)
        output["node_key"] = node_key

    current = count_field(raw, "current_value", "current")
    total = count_field(raw, "total_value", "total")
    if current is not None and total is not None and current > total:
        raise InvalidProgress("count order")
    if current is not None:
        output["current_value"] = current
    if total is not None:
        output["total_value"] = total

    timestamp = timestamp_value(raw.get("timestamp"))
    if timestamp is not None:
        output["timestamp"] = timestamp
    if metadata is not None:
        output["metadata"] = metadata
    return output


def main() -> int:
    if len(sys.argv) > 2:
        raise InvalidProgress("provide one JSON object")
    raw_text = (
        sys.argv[1]
        if len(sys.argv) == 2
        else sys.stdin.read(MAX_PROGRESS_EVENT_BYTES + 1)
    )
    try:
        if len(raw_text.encode("utf-8")) > MAX_PROGRESS_EVENT_BYTES:
            raise InvalidProgress("event size limit")
        raw = json.loads(raw_text, object_pairs_hook=reject_duplicate_keys)
        event = parse_event(raw)
    except (InvalidProgress, ValueError, TypeError) as exc:
        print(f"invalid progress event: {exc}", file=sys.stderr)
        return 2
    target = Path(__file__).resolve().parent / "progress.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        handle.write("\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def progress_helper_source() -> bytes:
    """Return the fixed, standalone sandbox helper staged for managed runs."""
    source = (
        _PROGRESS_HELPER_TEMPLATE.replace(
            "__STAGES__",
            repr(sorted(PROGRESS_STAGES)),
        )
        .replace("__STATUSES__", repr(sorted(PROGRESS_STATUSES)))
        .replace("__FORBIDDEN_FIELDS__", repr(sorted(_FORBIDDEN_FIELD_KEYS)))
        .replace("__ALLOWED_FIELDS__", repr(sorted(_ALLOWED_FIELDS)))
        .replace(
            "__REJECTED_EVENT_KEY_PREFIXES__",
            repr(sorted(_REJECTED_EVENT_KEY_PREFIXES)),
        )
        .replace(
            "__UNSAFE_TEXT_PATTERNS__",
            repr(_UNSAFE_TEXT_PATTERN_STRINGS),
        )
        .replace("__MAX_LABEL_LENGTH__", str(MAX_LABEL_LENGTH))
        .replace("__MAX_DETAIL_LENGTH__", str(MAX_DETAIL_LENGTH))
        .replace("__MAX_COUNT_VALUE__", str(MAX_COUNT_VALUE))
        .replace("__MAX_METADATA_DEPTH__", str(MAX_METADATA_DEPTH))
        .replace("__MAX_METADATA_ITEMS__", str(MAX_METADATA_ITEMS))
        .replace("__MAX_METADATA_INTEGER__", str(MAX_METADATA_INTEGER))
        .replace("__MAX_PROGRESS_EVENT_BYTES__", str(MAX_PROGRESS_EVENT_BYTES))
        .replace("__MAX_PROGRESS_STRING_BYTES__", str(MAX_PROGRESS_STRING_BYTES))
        .replace(
            "__MAX_METADATA_STRING_LENGTH__",
            str(MAX_METADATA_STRING_LENGTH),
        )
    )
    return source.encode("utf-8")
