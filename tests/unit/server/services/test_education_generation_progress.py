"""Semantic progress-event normalization and safety contracts."""

from __future__ import annotations

import json
import math

import pytest

from src.server.services import education_generation_progress


@pytest.mark.parametrize("stage", sorted(education_generation_progress.PROGRESS_STAGES))
@pytest.mark.parametrize(
    "status",
    sorted(education_generation_progress.PROGRESS_STATUSES),
)
def test_parse_progress_event_accepts_the_stable_stage_status_matrix(
    stage: str,
    status: str,
) -> None:
    metadata = {"reason": "checkpoint_review"} if status == "skipped" else None
    parsed = education_generation_progress.parse_progress_event(
        {
            "event_key": f"{stage}:{status}:job-1",
            "stage": stage,
            "status": status,
            "label": "处理进度",
            **({"metadata": metadata} if metadata else {}),
        }
    )

    assert parsed["event_key"] == f"{stage}:{status}:job-1"
    assert parsed["stage"] == stage
    assert parsed["status"] == status
    assert parsed["label"] == "处理进度"


def test_parse_progress_event_normalizes_safe_optional_fields() -> None:
    parsed = education_generation_progress.parse_progress_event(
        {
            "event_key": "chapter_analysis:completed:chapter-1",
            "stage": "chapter_analysis",
            "substage": " Chapter Boundary ",
            "status": "completed",
            "label": "Chapter 1\tcomplete",
            "detail": "Scanned 12\npages",
            "node_key": "unit-1.reading-a",
            "current": 12,
            "total": 12,
            "timestamp": "2026-09-22T10:30:00+09:00",
            "metadata": {"page_count": 12, "nested": {"safe": True}},
        }
    )

    assert parsed == {
        "event_key": "chapter_analysis:completed:chapter-1",
        "stage": "chapter_analysis",
        "substage": "chapter_boundary",
        "status": "completed",
        "label": "Chapter 1 complete",
        "detail": "Scanned 12 pages",
        "node_key": "unit-1.reading-a",
        "current_value": 12,
        "total_value": 12,
        "timestamp": "2026-09-22T10:30:00+09:00",
        "metadata": {"page_count": 12, "nested": {"safe": True}},
    }


def test_parse_progress_event_derives_a_safe_label_and_accepts_stdin_shape() -> None:
    parsed = education_generation_progress.parse_progress_event(
        {
            "event_key": "content_processing:running:content",
            "stage": "content_processing",
            "status": "running",
        }
    )

    assert parsed["label"] == "content_processing running"


def test_parse_progress_event_truncates_text_after_normalization() -> None:
    parsed = education_generation_progress.parse_progress_event(
        {
            "event_key": "knowledge_point_generation:running:knowledge",
            "stage": "knowledge_point_generation",
            "status": "running",
            "label": "题" * (education_generation_progress.MAX_LABEL_LENGTH + 20),
            "detail": "文" * (education_generation_progress.MAX_DETAIL_LENGTH + 20),
        }
    )

    assert len(parsed["label"]) == education_generation_progress.MAX_LABEL_LENGTH
    assert len(parsed["detail"]) == education_generation_progress.MAX_DETAIL_LENGTH


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_key", ""),
        ("stage", "unknown"),
        ("status", "waiting"),
        ("substage", "../unsafe"),
    ],
)
def test_parse_progress_event_rejects_invalid_required_or_enum_fields(
    field: str,
    value: object,
) -> None:
    raw = {
        "event_key": "chapter_analysis:running:valid",
        "stage": "chapter_analysis",
        "status": "running",
        "label": "Valid",
    }
    raw[field] = value

    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(raw)


@pytest.mark.parametrize(
    "event_key",
    (
        "probe:noop:job-1",
        "diagnostic:test:job-1",
        "test:run:job-1",
        "debug:trace:job-1",
    ),
)
def test_parse_progress_event_rejects_diagnostic_event_keys(event_key: str) -> None:
    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(
            {
                "event_key": event_key,
                "stage": "chapter_analysis",
                "status": "running",
            }
        )


def test_skipped_events_require_checkpoint_review_reason() -> None:
    raw = {
        "event_key": "chapter_analysis:skipped:job-1",
        "stage": "chapter_analysis",
        "status": "skipped",
    }
    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(raw)

    parsed = education_generation_progress.parse_progress_event(
        {
            **raw,
            "metadata": {"reason": "checkpoint_review"},
        }
    )

    assert parsed["status"] == "skipped"
    assert parsed["metadata"] == {"reason": "checkpoint_review"}


def test_parse_progress_event_enforces_event_key_length() -> None:
    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(
            {
                "event_key": (
                    "chapter_analysis:completed:"
                    + "x" * education_generation_progress.MAX_EVENT_KEY_LENGTH
                ),
                "stage": "chapter_analysis",
                "status": "completed",
            }
        )


@pytest.mark.parametrize(
    "raw",
    [
        [],
        "not an object",
        42,
        None,
    ],
)
def test_parse_progress_event_rejects_non_objects(raw: object) -> None:
    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(raw)


UNSAFE_PROGRESS_TEXT_CASES = (
    "OPENAI_API_KEY=opaque-value",
    "ANTHROPIC_ACCESS_TOKEN: opaque-value",
    "GITHUB_TOKEN opaque-value",
    "prefix_api_key=opaque-value",
    "access_key_id: opaque-value",
    "secret_key=opaque-value",
    "PASSWORD=opaque-value",
    "passwd_suffix: opaque-value",
    "TOKEN=opaque-value",
    "client_secret: opaque-value",
    '{"token":"opaque-value"}',
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
    "ghp_abcdefghijklmnopqrstuvwxyz1234",
    "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz",
    "AKIA1234567890ABCDEF",
    "ASIA1234567890ABCDEF",
    "/etc/passwd",
    "/foo",
    "path /foo",
    "见 /foo",
    "path: /foo",
    "path=/etc/passwd",
    "参见 /notes.md",
    "打开 /content/chapter.md",
    "/managed/textbook-job/secret",
    "/home/parent/book.md",
    "/tmp/progress.jsonl",
    r"C:\Users\parent\book.md",
    "C:/Users/parent/book.md",
    r"\\server\share\book.md",
    "s3://bucket/private",
    "file:///tmp/private",
    "https://user:password@example.com/book",
)

SAFE_PROGRESS_TEXT_CASES = (
    "private_key",
    "public_key",
    "token",
    "client_secret",
    "已完成 1 / 3 个文件",
    "Reading A / B",
    "TCP /IP",
    "1 /3",
    "Reading A /B",
)


@pytest.mark.parametrize("value", UNSAFE_PROGRESS_TEXT_CASES)
@pytest.mark.parametrize("field", ["label", "detail"])
def test_parse_progress_event_rejects_paths_and_secret_like_text(
    field: str,
    value: str,
) -> None:
    raw = {
        "event_key": "chapter_analysis:running:safe",
        "stage": "chapter_analysis",
        "status": "running",
        "label": "Safe",
    }
    raw[field] = value

    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(raw)


@pytest.mark.parametrize("value", SAFE_PROGRESS_TEXT_CASES)
@pytest.mark.parametrize("field", ["label", "detail"])
def test_parse_progress_event_accepts_safe_domain_text(
    field: str,
    value: str,
) -> None:
    raw = {
        "event_key": "chapter_analysis:running:safe",
        "stage": "chapter_analysis",
        "status": "running",
        "label": "Safe",
    }
    raw[field] = value

    parsed = education_generation_progress.parse_progress_event(raw)

    assert parsed[field] == value


@pytest.mark.parametrize(
    "raw",
    [
        {
            "event_key": "chapter_analysis:running:safe",
            "stage": "chapter_analysis",
            "status": "running",
            "reasoning": "hidden",
        },
        {
            "event_key": "chapter_analysis:running:safe",
            "stage": "chapter_analysis",
            "status": "running",
            "metadata": {"outer": {"tool_args": {"query": "hidden"}}},
        },
        {
            "event_key": "chapter_analysis:running:safe",
            "stage": "chapter_analysis",
            "status": "running",
            "metadata": {"sandbox_path": "/managed/root"},
        },
    ],
)
def test_parse_progress_event_rejects_forbidden_nested_fields(raw: dict) -> None:
    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(raw)


@pytest.mark.parametrize(
    "metadata",
    [
        {"bad": math.nan},
        {"bad": math.inf},
        {"bad": -math.inf},
    ],
)
def test_parse_progress_event_rejects_non_json_numbers(metadata: dict) -> None:
    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(
            {
                "event_key": "chapter_analysis:running:safe",
                "stage": "chapter_analysis",
                "status": "running",
                "metadata": metadata,
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("current", -1),
        ("total", -1),
        ("current", education_generation_progress.MAX_COUNT_VALUE + 1),
        ("total", education_generation_progress.MAX_COUNT_VALUE + 1),
    ],
)
def test_parse_progress_event_rejects_invalid_counts(
    field: str,
    value: int,
) -> None:
    raw = {
        "event_key": "chapter_analysis:running:safe",
        "stage": "chapter_analysis",
        "status": "running",
        "total": 4,
        "current": 4,
    }
    raw[field] = value

    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(raw)


def test_parse_progress_event_preserves_zero_total_counts() -> None:
    parsed = education_generation_progress.parse_progress_event(
        {
            "event_key": "chapter_analysis:running:safe",
            "stage": "chapter_analysis",
            "status": "skipped",
            "current_value": 0,
            "total_value": 0,
            "metadata": {"reason": "checkpoint_review"},
        }
    )

    assert parsed["current_value"] == 0
    assert parsed["total_value"] == 0


@pytest.mark.parametrize("field", ["current_value", "total_value"])
def test_parse_progress_event_accepts_individual_optional_counts(field: str) -> None:
    parsed = education_generation_progress.parse_progress_event(
        {
            "event_key": "chapter_analysis:running:safe",
            "stage": "chapter_analysis",
            "status": "running",
            field: 7,
        }
    )

    assert parsed[field] == 7


@pytest.mark.parametrize(
    "value",
    [
        "zero\u200bwidth",
        "bidi\u202eoverride",
        "bom\ufeffmarker",
    ],
)
def test_parse_progress_event_rejects_unicode_format_controls(value: str) -> None:
    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(
            {
                "event_key": "chapter_analysis:running:safe",
                "stage": "chapter_analysis",
                "status": "running",
                "label": value,
            }
        )


def test_parse_progress_event_rejects_oversized_string_before_regex() -> None:
    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_event(
            {
                "event_key": "chapter_analysis:running:safe",
                "stage": "chapter_analysis",
                "status": "running",
                "label": "x"
                * (education_generation_progress.MAX_PROGRESS_STRING_BYTES + 1),
            }
        )


def test_parse_progress_json_line_rejects_oversized_raw_line() -> None:
    payload = " " * (education_generation_progress.MAX_PROGRESS_EVENT_BYTES + 1)
    payload += json.dumps(
        {
            "event_key": "chapter_analysis:running:safe",
            "stage": "chapter_analysis",
            "status": "running",
        }
    )

    with pytest.raises(education_generation_progress.ProgressEventValidationError):
        education_generation_progress.parse_progress_json_line(payload)
