"""Strict service-side validation for managed teaching-package candidates."""

import copy

import pytest

from src.server.services.education_teaching_validation import (
    TeachingPackageValidationError,
    validate_teaching_package,
)


FROZEN_INPUT = {
    "chapters": [
        {
            "content_chapter_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
            "position": 1,
            "slug": "01-overview",
            "content_sha256": "a" * 64,
        }
    ]
}


VALID_PACKAGE = {
    "format": "langalpha-managed-teaching-package/v1",
    "chapters": [
        {
            "content_chapter_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
            "content_sha256": "a" * 64,
            "learning_objectives": ["掌握内容"],
            "knowledge_points": ["核心概念"],
            "key_difficulties": ["难点"],
            "prerequisites": [],
            "teaching_material": "# 导读\n\n中文教学材料",
            "questions": [
                {
                    "position": 1,
                    "prompt": "选择正确答案",
                    "options": {"A": "正确", "B": "错误"},
                    "correct_option": "A",
                    "explanation": "解释",
                    "knowledge_point": "核心概念",
                }
            ],
        }
    ],
}


def test_accepts_complete_hashed_teaching_package():
    validated = validate_teaching_package(VALID_PACKAGE, FROZEN_INPUT)

    assert validated["chapters"][0]["knowledge_points"] == ["核心概念"]


def test_accepts_a_realistic_chapter_with_more_than_24_knowledge_points():
    package = copy.deepcopy(VALID_PACKAGE)
    knowledge_points = [f"知识点 {index}" for index in range(25)]
    package["chapters"][0]["knowledge_points"] = knowledge_points
    package["chapters"][0]["questions"][0]["knowledge_point"] = knowledge_points[0]

    validated = validate_teaching_package(package, FROZEN_INPUT)

    assert len(validated["chapters"][0]["knowledge_points"]) == 25


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda package: package.__setitem__("chapters", []), "cover every frozen chapter"),
        (
            lambda package: package["chapters"][0].__setitem__("content_sha256", "b" * 64),
            "hash",
        ),
        (
            lambda package: package["chapters"][0]["questions"][0].__setitem__("correct_option", "C"),
            "correct option",
        ),
        (
            lambda package: package["chapters"][0]["questions"][0].__setitem__("knowledge_point", "未关联"),
            "knowledge point",
        ),
    ],
)
def test_rejects_missing_or_invalid_managed_candidate(mutation, message):
    package = copy.deepcopy(VALID_PACKAGE)
    mutation(package)

    with pytest.raises(TeachingPackageValidationError, match=message):
        validate_teaching_package(package, FROZEN_INPUT)
