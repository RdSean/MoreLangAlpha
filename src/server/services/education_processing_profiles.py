"""Validated textbook processing profiles and prompt composition."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from src.server.database.education_textbooks import (
    create_processing_profile,
    get_processing_profile_for_parent,
)
from src.server.services.education_textbooks import TextbookTransitionError


DEFAULT_PROFILE = {
    "subject": "other",
    "grade_band": "middle",
    "language": "zh-CN",
    "depth": "standard",
    "question_types": ["choice", "mixed"],
    "prompt_fragment": "",
    "allowed_skills": ["book-to-skill"],
}
_SUBJECTS = {"english", "math", "chinese", "science", "other"}
_GRADE_BANDS = {"primary", "middle", "high", "adult"}
_LANGUAGES = {"zh-CN", "en", "bilingual"}
_DEPTHS = {"overview", "standard", "deep"}
_QUESTION_TYPES = {"choice", "fill", "short_answer", "mixed"}


def normalize_processing_profile(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = {**DEFAULT_PROFILE, **dict(value or {})}
    subject = str(raw.get("subject") or "")
    grade_band = str(raw.get("grade_band") or "")
    language = str(raw.get("language") or "")
    depth = str(raw.get("depth") or "")
    question_types = raw.get("question_types")
    allowed_skills = raw.get("allowed_skills")
    prompt_fragment = str(raw.get("prompt_fragment") or "").strip()
    if subject not in _SUBJECTS:
        raise TextbookTransitionError("Processing profile subject is invalid")
    if grade_band not in _GRADE_BANDS:
        raise TextbookTransitionError("Processing profile grade band is invalid")
    if language not in _LANGUAGES:
        raise TextbookTransitionError("Processing profile language is invalid")
    if depth not in _DEPTHS:
        raise TextbookTransitionError("Processing profile depth is invalid")
    if (
        not isinstance(question_types, list)
        or not question_types
        or len(question_types) > 4
        or any(item not in _QUESTION_TYPES for item in question_types)
    ):
        raise TextbookTransitionError("Processing profile question types are invalid")
    if (
        not isinstance(allowed_skills, list)
        or len(allowed_skills) > 8
        or any(not isinstance(item, str) or not item for item in allowed_skills)
    ):
        raise TextbookTransitionError("Processing profile allowed skills are invalid")
    if len(prompt_fragment) > 2_000:
        raise TextbookTransitionError("Processing profile prompt is too long")
    return {
        "subject": subject,
        "grade_band": grade_band,
        "language": language,
        "depth": depth,
        "question_types": list(dict.fromkeys(question_types)),
        "prompt_fragment": prompt_fragment,
        "allowed_skills": list(dict.fromkeys(allowed_skills)),
    }


def processing_profile_sha256(profile: Mapping[str, Any]) -> str:
    normalized = normalize_processing_profile(profile)
    return hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


async def resolve_processing_profile(
    *,
    parent_user_id: str,
    version_id: str,
    profile_input: Mapping[str, Any] | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    if profile_id:
        profile = await get_processing_profile_for_parent(
            parent_user_id=parent_user_id,
            profile_id=profile_id,
        )
        if not profile or str(profile["version_id"]) != version_id:
            raise TextbookTransitionError("Processing profile is unavailable")
        return profile
    normalized = normalize_processing_profile(profile_input)
    profile = await create_processing_profile(
        parent_user_id=parent_user_id,
        version_id=version_id,
        **normalized,
        profile_sha256=processing_profile_sha256(normalized),
    )
    if not profile:
        raise TextbookTransitionError("Textbook version is unavailable")
    return profile


def processing_profile_prompt(profile: Mapping[str, Any] | None) -> str:
    if not profile:
        return ""
    fragment = str(profile.get("prompt_fragment") or "").strip()
    lines = [
        "教材处理配置：",
        f"- 学科：{profile.get('subject')}",
        f"- 学段：{profile.get('grade_band')}",
        f"- 语言：{profile.get('language')}",
        f"- 深度：{profile.get('depth')}",
        f"- 题型：{', '.join(profile.get('question_types') or [])}",
    ]
    if fragment:
        lines.append(f"- 额外要求：{fragment}")
    return "\n".join(lines)
