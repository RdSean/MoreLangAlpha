"""Contracts for the complete managed textbook teaching-asset bundle."""

from __future__ import annotations

import copy
import json

import pytest

from src.server.services.education_teaching_assets import (
    TeachingAssetValidationError,
    expected_teaching_asset_paths,
    validate_teaching_assets,
)


CHAPTER_ONE = "f5761267-11d1-4977-8107-e2671c99a2f0"
CHAPTER_TWO = "c0887dfa-9bd8-4a38-849f-30713bd31758"
FROZEN_INPUT = {
    "chapters": [
        {
            "content_chapter_id": CHAPTER_ONE,
            "position": 1,
            "slug": "01-overview",
            "content_sha256": "a" * 64,
        },
        {
            "content_chapter_id": CHAPTER_TWO,
            "position": 2,
            "slug": "02-practice",
            "content_sha256": "b" * 64,
        },
    ]
}


def _question(position: int, knowledge_point: str, concept_id: str) -> dict[str, object]:
    return {
        "position": position,
        "prompt": "选择正确答案",
        "options": {"A": "正确", "B": "错误"},
        "correct_option": "A",
        "explanation": "解释",
        "knowledge_point": knowledge_point,
        "concept_id": concept_id,
    }


def _chapter_assets(chapter_id: str, content_sha256: str, concept_id: str, knowledge_point: str) -> dict[str, object]:
    return {
        "knowledge": {
            "format": "langalpha-managed-chapter-knowledge/v1",
            "content_chapter_id": chapter_id,
            "content_sha256": content_sha256,
            "knowledge_points": [knowledge_point],
            "concepts": [
                {
                    "concept_id": concept_id,
                    "name": knowledge_point,
                    "evidence": [{"start": 0, "end": 12}],
                }
            ],
            "relations": [],
            "prerequisite_concept_ids": [],
        },
        "toolkit": f"# {knowledge_point}\n\n中文解释、例子、易错点和复习提示。",
        "practice": {
            "format": "langalpha-managed-chapter-practice/v1",
            "content_chapter_id": chapter_id,
            "content_sha256": content_sha256,
            "questions": [_question(1, knowledge_point, concept_id)],
        },
    }


def _package() -> dict[str, object]:
    chapters = []
    for chapter, concept_id, knowledge_point in (
        (FROZEN_INPUT["chapters"][0], "concept-1", "核心概念一"),
        (FROZEN_INPUT["chapters"][1], "concept-2", "核心概念二"),
    ):
        chapters.append(
            {
                "content_chapter_id": chapter["content_chapter_id"],
                "content_sha256": chapter["content_sha256"],
                "learning_objectives": ["掌握内容"],
                "knowledge_points": [knowledge_point],
                "key_difficulties": ["难点"],
                "prerequisites": [],
                "teaching_material": "# 导读\n\n面向中国学生的教学材料",
                "questions": [_question(1, knowledge_point, concept_id)],
            }
        )
    return {"format": "langalpha-managed-teaching-package/v1", "chapters": chapters}


def _bundle() -> dict[str, bytes]:
    paths = expected_teaching_asset_paths(FROZEN_INPUT)
    chapter_assets = {
        CHAPTER_ONE: _chapter_assets(CHAPTER_ONE, "a" * 64, "concept-1", "核心概念一"),
        CHAPTER_TWO: _chapter_assets(CHAPTER_TWO, "b" * 64, "concept-2", "核心概念二"),
    }
    bundle = {
        paths.concept_index: {
            "format": "langalpha-managed-concept-index/v1",
            "concepts": [
                {"concept_id": "concept-1", "name": "核心概念一", "content_chapter_ids": [CHAPTER_ONE]},
                {"concept_id": "concept-2", "name": "核心概念二", "content_chapter_ids": [CHAPTER_TWO]},
            ],
            "relations": [],
        },
        paths.coverage_audit: {
            "format": "langalpha-managed-coverage-audit/v1",
            "chapters": [
                {"content_chapter_id": CHAPTER_ONE, "content_sha256": "a" * 64, "status": "complete", "missing": [], "asset_kinds": ["knowledge", "toolkit", "practice", "teaching"]},
                {"content_chapter_id": CHAPTER_TWO, "content_sha256": "b" * 64, "status": "complete", "missing": [], "asset_kinds": ["knowledge", "toolkit", "practice", "teaching"]},
            ],
        },
        paths.teaching_package: _package(),
    }
    encoded = {path: json.dumps(value, ensure_ascii=False).encode("utf-8") for path, value in bundle.items()}
    for chapter in FROZEN_INPUT["chapters"]:
        assets = chapter_assets[chapter["content_chapter_id"]]
        expected = paths.for_chapter(chapter["content_chapter_id"])
        encoded[expected.knowledge] = json.dumps(assets["knowledge"], ensure_ascii=False).encode("utf-8")
        encoded[expected.toolkit] = str(assets["toolkit"]).encode("utf-8")
        encoded[expected.practice] = json.dumps(assets["practice"], ensure_ascii=False).encode("utf-8")
    return encoded


def test_validates_exact_complete_bundle_and_returns_safe_manifest():
    bundle = _bundle()

    validated = validate_teaching_assets(bundle, FROZEN_INPUT)

    assert validated["format"] == "langalpha-family-teaching-assets/v2"
    assert [chapter["content_chapter_id"] for chapter in validated["chapters"]] == [CHAPTER_ONE, CHAPTER_TWO]
    assert validated["concept_index"]["concept_count"] == 2
    assert all("education/" not in json.dumps(chapter) for chapter in validated["chapters"])
    assert all(len(entry["sha256"]) == 64 for chapter in validated["chapters"] for entry in chapter["assets"])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda bundle, paths: bundle.pop(paths.for_chapter(CHAPTER_TWO).toolkit), "missing"),
        (lambda bundle, paths: bundle.__setitem__(paths.for_chapter(CHAPTER_TWO).knowledge, json.dumps({**json.loads(bundle[paths.for_chapter(CHAPTER_TWO).knowledge]), "content_sha256": "a" * 64}).encode("utf-8")), "hash"),
        (lambda bundle, paths: bundle.__setitem__(paths.coverage_audit, json.dumps({"format": "langalpha-managed-coverage-audit/v1", "chapters": []}).encode("utf-8")), "(?i)coverage"),
        (lambda bundle, paths: bundle.__setitem__(paths.for_chapter(CHAPTER_ONE).practice, json.dumps({**json.loads(bundle[paths.for_chapter(CHAPTER_ONE).practice]), "questions": [_question(1, "核心概念一", "unknown-concept")]}).encode("utf-8")), "concept"),
        (lambda bundle, paths: bundle.__setitem__(paths.teaching_package, json.dumps({**_package(), "chapters": [{**_package()["chapters"][0], "questions": [_question(1, "不匹配知识点", "concept-1")]}, _package()["chapters"][1]]}).encode("utf-8")), "knowledge point"),
    ],
)
def test_rejects_missing_or_inconsistent_complete_assets(mutate, message):
    bundle = copy.deepcopy(_bundle())
    paths = expected_teaching_asset_paths(FROZEN_INPUT)
    mutate(bundle, paths)

    with pytest.raises(TeachingAssetValidationError, match=message):
        validate_teaching_assets(bundle, FROZEN_INPUT)


def test_expected_paths_are_service_derived_and_stable():
    paths = expected_teaching_asset_paths(FROZEN_INPUT)

    assert paths.concept_index == "outputs/knowledge/concept-index.json"
    assert paths.coverage_audit == "outputs/knowledge/coverage-audit.json"
    assert paths.for_chapter(CHAPTER_ONE).toolkit == "outputs/chapters/01-01-overview-toolkit.md"
    assert paths.for_chapter(CHAPTER_TWO).practice == "outputs/chapters/02-02-practice-practice.json"
