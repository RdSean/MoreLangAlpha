"""Validation contracts for one knowledge-point Markdown lesson."""

import pytest

from src.server.services.education_lesson_validation import (
    KnowledgePointLessonValidationError,
    validate_kp_lesson_outputs,
)


VALID_PRACTICE = {
    "format": "langalpha-managed-chapter-practice/v1",
    "questions": [
        {
            "position": 1,
            "prompt": "Which statement is true?",
            "options": {"A": "True", "B": "False"},
            "correct_option": "A",
            "explanation": "True is correct.",
        }
    ],
}


def test_accepts_plain_markdown_lesson_without_structured_vocabulary() -> None:
    validated = validate_kp_lesson_outputs(
        markdown="# 世界运动\n\n## 词汇\n\n| 单词 | 释义 |\n| --- | --- |\n".encode(),
        practice=None,
        auto_grading=False,
    )

    assert validated["markdown"].startswith("# 世界运动")
    assert validated["practice"] is None
    assert validated["size_bytes"] > 0


def test_rejects_empty_or_oversized_markdown() -> None:
    with pytest.raises(
        KnowledgePointLessonValidationError,
        match="must not be empty",
    ):
        validate_kp_lesson_outputs(
            markdown=b"   ",
            practice=None,
            auto_grading=False,
        )

    with pytest.raises(
        KnowledgePointLessonValidationError,
        match="too large",
    ):
        validate_kp_lesson_outputs(
            markdown=b"# lesson\n" + b"x" * 200_001,
            practice=None,
            auto_grading=False,
        )


def test_requires_practice_only_when_auto_grading_is_enabled() -> None:
    with pytest.raises(
        KnowledgePointLessonValidationError,
        match="practice.json",
    ):
        validate_kp_lesson_outputs(
            markdown=b"# lesson\n",
            practice=None,
            auto_grading=True,
        )

    with pytest.raises(
        KnowledgePointLessonValidationError,
        match="not requested",
    ):
        validate_kp_lesson_outputs(
            markdown=b"# lesson\n",
            practice=b"{}",
            auto_grading=False,
        )


def test_accepts_structured_practice_for_auto_grading() -> None:
    validated = validate_kp_lesson_outputs(
        markdown="# lesson\n\nContent.\n".encode(),
        practice=(
            '{"format":"langalpha-managed-chapter-practice/v1",'
            '"questions":[{"position":1,"prompt":"?","options":{"A":"yes",'
            '"B":"no"},"correct_option":"A","explanation":"because"}]}'
        ).encode(),
        auto_grading=True,
    )

    assert validated["practice"]["questions"][0]["correct_option"] == "A"
