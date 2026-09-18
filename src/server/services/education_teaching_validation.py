"""Validation for untrusted managed-PTC teaching-package candidates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID


_PACKAGE_FORMAT = "langalpha-managed-teaching-package/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT_LENGTH = 30_000
_MAX_LIST_ITEMS = 64
_MAX_QUESTIONS_PER_CHAPTER = 24


class TeachingPackageValidationError(ValueError):
    """A managed agent candidate cannot become an education teaching package."""


def _require_string(value: object, *, field: str, limit: int = _MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TeachingPackageValidationError(f"{field} must be a non-empty string")
    if len(value) > limit:
        raise TeachingPackageValidationError(f"{field} exceeds its maximum length")
    return value.strip()


def _require_string_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > _MAX_LIST_ITEMS:
        raise TeachingPackageValidationError(f"{field} must be a non-empty bounded list")
    items = [_require_string(item, field=field, limit=500) for item in value]
    if len(set(items)) != len(items):
        raise TeachingPackageValidationError(f"{field} must not contain duplicates")
    return items


def _optional_string_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_LIST_ITEMS:
        raise TeachingPackageValidationError(f"{field} must be a bounded list")
    items = [_require_string(item, field=field, limit=500) for item in value]
    if len(set(items)) != len(items):
        raise TeachingPackageValidationError(f"{field} must not contain duplicates")
    return items


def _frozen_chapters(frozen_input: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    chapters = frozen_input.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise TeachingPackageValidationError("Frozen input must contain chapters")
    result: dict[str, Mapping[str, Any]] = {}
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            raise TeachingPackageValidationError("Frozen chapter must be an object")
        chapter_id = str(chapter.get("content_chapter_id", ""))
        try:
            UUID(chapter_id)
        except ValueError as exc:
            raise TeachingPackageValidationError("Frozen content chapter id is invalid") from exc
        content_sha256 = str(chapter.get("content_sha256", ""))
        if not _SHA256_RE.fullmatch(content_sha256):
            raise TeachingPackageValidationError("Frozen content hash is invalid")
        if chapter_id in result:
            raise TeachingPackageValidationError("Frozen content chapter ids must be unique")
        result[chapter_id] = chapter
    return result


def _validate_questions(value: object, *, knowledge_points: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > _MAX_QUESTIONS_PER_CHAPTER:
        raise TeachingPackageValidationError("questions must be a non-empty bounded list")
    questions: list[dict[str, Any]] = []
    positions: set[int] = set()
    for question in value:
        if not isinstance(question, Mapping):
            raise TeachingPackageValidationError("question must be an object")
        position = question.get("position")
        if not isinstance(position, int) or isinstance(position, bool) or position <= 0:
            raise TeachingPackageValidationError("question position is invalid")
        if position in positions:
            raise TeachingPackageValidationError("question positions must be unique")
        positions.add(position)
        options = question.get("options")
        if not isinstance(options, Mapping) or not 2 <= len(options) <= 6:
            raise TeachingPackageValidationError("question must have 2 to 6 options")
        validated_options: dict[str, str] = {}
        for option, label in options.items():
            option_key = _require_string(option, field="option key", limit=32)
            if option_key in validated_options:
                raise TeachingPackageValidationError("question options must be unique")
            validated_options[option_key] = _require_string(
                label, field="option label", limit=1_000
            )
        correct_option = _require_string(
            question.get("correct_option"), field="correct option", limit=32
        )
        if correct_option not in validated_options:
            raise TeachingPackageValidationError("correct option must be one of the options")
        knowledge_point = _require_string(
            question.get("knowledge_point"), field="knowledge point", limit=500
        )
        if knowledge_point not in knowledge_points:
            raise TeachingPackageValidationError(
                "question knowledge point must reference a chapter knowledge point"
            )
        questions.append(
            {
                "position": position,
                "prompt": _require_string(question.get("prompt"), field="question prompt"),
                "options": validated_options,
                "correct_option": correct_option,
                "explanation": _require_string(
                    question.get("explanation"), field="question explanation"
                ),
                "knowledge_point": knowledge_point,
            }
        )
    return sorted(questions, key=lambda question: question["position"])


def validate_teaching_package(
    candidate: object, frozen_input: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a safe normalized candidate or reject it before archival.

    The managed model controls prose only. Chapter identity, object paths and
    package identity are verified or generated by the service.
    """
    if not isinstance(candidate, Mapping):
        raise TeachingPackageValidationError("Teaching package must be an object")
    if candidate.get("format") != _PACKAGE_FORMAT:
        raise TeachingPackageValidationError("Teaching package format is invalid")
    frozen = _frozen_chapters(frozen_input)
    raw_chapters = candidate.get("chapters")
    if not isinstance(raw_chapters, list):
        raise TeachingPackageValidationError("Teaching package chapters must be a list")
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for chapter in raw_chapters:
        if not isinstance(chapter, Mapping):
            raise TeachingPackageValidationError("Teaching chapter must be an object")
        chapter_id = str(chapter.get("content_chapter_id", ""))
        if chapter_id not in frozen or chapter_id in seen_ids:
            raise TeachingPackageValidationError("Teaching package must cover every frozen chapter exactly once")
        seen_ids.add(chapter_id)
        content_sha256 = str(chapter.get("content_sha256", ""))
        if content_sha256 != frozen[chapter_id]["content_sha256"]:
            raise TeachingPackageValidationError("Teaching chapter content hash does not match frozen input")
        knowledge_points = _require_string_list(
            chapter.get("knowledge_points"), field="knowledge_points"
        )
        validated.append(
            {
                "content_chapter_id": chapter_id,
                "content_sha256": content_sha256,
                "learning_objectives": _require_string_list(
                    chapter.get("learning_objectives"), field="learning_objectives"
                ),
                "knowledge_points": knowledge_points,
                "key_difficulties": _require_string_list(
                    chapter.get("key_difficulties"), field="key_difficulties"
                ),
                "prerequisites": _optional_string_list(
                    chapter.get("prerequisites"), field="prerequisites"
                ),
                "teaching_material": _require_string(
                    chapter.get("teaching_material"), field="teaching_material"
                ),
                "questions": _validate_questions(
                    chapter.get("questions"), knowledge_points=set(knowledge_points)
                ),
            }
        )
    if set(frozen) != seen_ids:
        raise TeachingPackageValidationError(
            "Teaching package must cover every frozen chapter exactly once"
        )
    positions = {
        str(chapter["content_chapter_id"]): int(chapter.get("position", 0))
        for chapter in frozen.values()
    }
    return {
        "format": _PACKAGE_FORMAT,
        "chapters": sorted(validated, key=lambda chapter: positions[chapter["content_chapter_id"]]),
    }
