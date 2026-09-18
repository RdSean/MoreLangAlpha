"""Validation for one knowledge-point Markdown lesson candidate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


_PRACTICE_FORMAT = "langalpha-managed-chapter-practice/v1"
_MAX_LESSON_BYTES = 200_000
_MAX_PRACTICE_BYTES = 200_000
_MAX_QUESTIONS = 48


class KnowledgePointLessonValidationError(ValueError):
    """A lesson candidate cannot become an immutable lesson revision."""


def _decode_json_object(content: bytes, *, field: str) -> Mapping[str, Any]:
    try:
        decoded = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgePointLessonValidationError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(decoded, Mapping):
        raise KnowledgePointLessonValidationError(
            f"{field} must be a JSON object"
        )
    return decoded


def _validate_practice(content: bytes) -> dict[str, Any]:
    if len(content) > _MAX_PRACTICE_BYTES:
        raise KnowledgePointLessonValidationError("practice.json is too large")
    decoded = _decode_json_object(content, field="practice.json")
    if decoded.get("format") != _PRACTICE_FORMAT:
        raise KnowledgePointLessonValidationError("practice.json format is invalid")
    questions = decoded.get("questions")
    if (
        not isinstance(questions, list)
        or not questions
        or len(questions) > _MAX_QUESTIONS
    ):
        raise KnowledgePointLessonValidationError(
            "practice.json questions must be a non-empty bounded list"
        )
    positions: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for question in questions:
        if not isinstance(question, Mapping):
            raise KnowledgePointLessonValidationError("practice question is invalid")
        position = question.get("position")
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position <= 0
            or position in positions
        ):
            raise KnowledgePointLessonValidationError(
                "practice question positions must be unique and positive"
            )
        positions.add(position)
        options = question.get("options")
        if not isinstance(options, Mapping) or not 2 <= len(options) <= 6:
            raise KnowledgePointLessonValidationError(
                "practice question requires 2 to 6 options"
            )
        correct_option = question.get("correct_option")
        if not isinstance(correct_option, str) or correct_option not in options:
            raise KnowledgePointLessonValidationError(
                "practice correct_option must be one of its options"
            )
        normalized.append(
            {
                "position": position,
                "prompt": str(question.get("prompt") or "").strip(),
                "options": {str(key): str(value) for key, value in options.items()},
                "correct_option": correct_option,
                "explanation": str(question.get("explanation") or "").strip(),
            }
        )
        if not normalized[-1]["prompt"]:
            raise KnowledgePointLessonValidationError(
                "practice question prompt must not be empty"
            )
        if not normalized[-1]["explanation"]:
            raise KnowledgePointLessonValidationError(
                "practice question explanation must not be empty"
            )
    return {
        "format": _PRACTICE_FORMAT,
        "questions": sorted(normalized, key=lambda item: item["position"]),
    }


def validate_kp_lesson_outputs(
    *,
    markdown: bytes,
    practice: bytes | None,
    auto_grading: bool,
) -> dict[str, Any]:
    """Return normalized lesson content or reject the candidate."""
    if not isinstance(markdown, bytes):
        raise KnowledgePointLessonValidationError("lesson.md must be bytes")
    if not markdown.strip():
        raise KnowledgePointLessonValidationError("lesson.md must not be empty")
    if len(markdown) > _MAX_LESSON_BYTES:
        raise KnowledgePointLessonValidationError("lesson.md is too large")
    try:
        decoded_markdown = markdown.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise KnowledgePointLessonValidationError(
            "lesson.md must be valid UTF-8"
        ) from exc
    if not auto_grading and practice is not None:
        raise KnowledgePointLessonValidationError(
            "practice.json was provided but auto-grading was not requested"
        )
    if auto_grading and practice is None:
        raise KnowledgePointLessonValidationError(
            "practice.json is required when auto-grading is requested"
        )
    normalized_practice = _validate_practice(practice) if practice is not None else None
    return {
        "markdown": decoded_markdown,
        "markdown_sha256": hashlib.sha256(markdown).hexdigest(),
        "size_bytes": len(markdown),
        "practice": normalized_practice,
    }
