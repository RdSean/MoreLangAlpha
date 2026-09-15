"""Managed textbook mode remains non-interactive and output-bounded."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
#: The two managed teaching skills ship in this deployment's own bundle.
SKILLS_ROOT = ROOT / "plugins/langalpha_local/skills"


def _managed_block(text: str) -> str:
    start = text.index("## Managed textbook mode")
    next_heading = text.find("\n## ", start + 1)
    return text[start:] if next_heading == -1 else text[start:next_heading]


def test_book_to_skill_managed_mode_accepts_only_staged_markdown_manifest():
    text = (SKILLS_ROOT / "book-to-skill/SKILL.md").read_text()
    managed = _managed_block(text)

    assert "--managed-textbook" in text
    assert "/managed/textbook-job/<job>/inputs/manifest.json" in managed
    assert "/managed/textbook-job/<job>/inputs/chapters/" in managed
    assert "AskUserQuestion" not in managed
    assert "PDF" not in managed
    assert "artifacts/" not in managed


def test_knowledge_guy_managed_mode_writes_only_schema_validated_outputs():
    text = (SKILLS_ROOT / "the-knowledge-guy/SKILL.md").read_text()
    managed = _managed_block(text)

    assert "--managed-textbook" in text
    assert "outputs/teaching-package.json" in managed
    assert "EDUCATION_PROGRESS" in managed
    assert "AskUserQuestion" not in managed
    assert "artifacts/" not in managed
    assert "content_sha256" in managed
    assert "strict JSON" in managed
    assert "escape inner double quotes" in managed
    assert "must exactly match" in managed


def test_managed_contracts_define_the_same_output_schema():
    book_contract = (
        SKILLS_ROOT / "book-to-skill/reference/managed-textbook-contract.md"
    ).read_text()
    knowledge_contract = (
        SKILLS_ROOT / "the-knowledge-guy/reference/managed-textbook-contract.md"
    ).read_text()

    for required_field in (
        "content_chapter_id",
        "content_sha256",
        '"chapters": [',
        '"asset_kinds": [',
        "from_concept_id",
        "to_concept_id",
        "learning_objectives",
        "knowledge_points",
        "teaching_material",
        "correct_option",
    ):
        assert required_field in book_contract
        assert required_field in knowledge_contract
    assert "must exactly match" in book_contract
    assert "must exactly match" in knowledge_contract


def test_managed_contracts_require_questions_for_each_practice_asset():
    for skill_name in ("book-to-skill", "the-knowledge-guy"):
        contract = (
            SKILLS_ROOT / f"{skill_name}/reference/managed-textbook-contract.md"
        ).read_text()

        assert re.search(
            r'"format": "langalpha-managed-chapter-practice/v1".{0,1000}"questions": \[',
            contract,
            re.DOTALL,
        )
        assert '"exercises"' not in contract


def test_managed_contracts_require_concept_index_to_copy_chapter_concepts_verbatim():
    for skill_name in ("book-to-skill", "the-knowledge-guy"):
        contract = (
            SKILLS_ROOT / f"{skill_name}/reference/managed-textbook-contract.md"
        ).read_text()

        assert re.search(
            r'"format": "langalpha-managed-concept-index/v1".{0,1000}'
            r'"concepts": \[\{.{0,1000}'
            r'"concept_id": "exact existing concept_id copied verbatim from a -knowledge\.json".{0,1000}'
            r'"content_chapter_ids": \["source content_chapter_id copied verbatim"\]',
            contract,
            re.DOTALL,
        )
        assert "Do not rename, merge, substitute or add concepts." in contract
