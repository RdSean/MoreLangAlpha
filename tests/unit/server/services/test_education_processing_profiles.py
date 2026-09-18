"""Processing profile validation and prompt composition."""

from unittest.mock import AsyncMock

import pytest

from src.server.services import education_processing_profiles


def test_normalizes_default_profile_and_hashes_canonically():
    normalized = education_processing_profiles.normalize_processing_profile(None)
    first = education_processing_profiles.processing_profile_sha256(normalized)
    second = education_processing_profiles.processing_profile_sha256(
        education_processing_profiles.normalize_processing_profile(None)
    )

    assert normalized["subject"] == "other"
    assert first == second
    assert len(first) == 64


@pytest.mark.asyncio
async def test_resolve_profile_creates_versioned_default(monkeypatch):
    create = AsyncMock(
        return_value={
            "profile_id": "profile-1",
            "version_id": "version-1",
            "version": 1,
            "profile_sha256": "a" * 64,
        }
    )
    monkeypatch.setattr(
        education_processing_profiles,
        "create_processing_profile",
        create,
    )

    profile = await education_processing_profiles.resolve_processing_profile(
        parent_user_id="parent-1",
        version_id="version-1",
    )

    assert profile["profile_id"] == "profile-1"
    assert create.await_args.kwargs["subject"] == "other"


def test_prompt_contains_only_bounded_profile_fields():
    prompt = education_processing_profiles.processing_profile_prompt(
        {
            "subject": "english",
            "grade_band": "middle",
            "language": "zh-CN",
            "depth": "deep",
            "question_types": ["choice", "fill"],
            "prompt_fragment": "强调阅读策略",
        }
    )

    assert "学科：english" in prompt
    assert "题型：choice, fill" in prompt
    assert "强调阅读策略" in prompt
