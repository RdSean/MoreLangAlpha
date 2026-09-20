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
    assert "/managed/textbook-job/<job>/inputs/sources/" in managed
    assert "/managed/textbook-job/<job>/inputs/assets/" in managed
    assert "/managed/textbook-job/<job>/inputs/chapters/" in managed
    assert "AskUserQuestion" not in managed
    assert "PDF" not in managed
    assert "artifacts/" not in managed
    assert "complete source" in managed.lower()
    assert "Unit/TOC" in managed
    assert "Markdown image" in managed


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
    for contract in (book_contract, knowledge_contract):
        assert "complete source" in contract.lower()
        assert "does not guarantee" in contract
        assert "Unit/TOC" in contract
        assert "inputs/assets/" in contract
        assert "asset_paths" in contract


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


def test_book_to_skill_managed_structure_mode_is_non_interactive_and_source_grounded():
    text = (SKILLS_ROOT / "book-to-skill/SKILL.md").read_text()
    contract = (
        SKILLS_ROOT / "book-to-skill/reference/managed-textbook-contract.md"
    ).read_text()

    assert "--managed-textbook-structure" in text
    assert "outputs/structure.json" in text
    assert "langalpha-managed-textbook-structure/v1" in contract
    assert "non-teaching Unit" in contract
    assert "must not invent knowledge points" in contract


def test_book_to_skill_structure_contract_uses_service_owned_identity_fields():
    text = (SKILLS_ROOT / "book-to-skill/SKILL.md").read_text()
    contract = (
        SKILLS_ROOT / "book-to-skill/reference/managed-textbook-contract.md"
    ).read_text()

    assert "Do not calculate `position`" in contract
    assert '"quote": "short source excerpt"' in contract
    assert '"knowledge_points": [{' in contract
    assert "the service derives those values" in text
    assert '"start": 0' not in contract.split("## Frozen inputs", 1)[0]


def test_book_to_skill_managed_lesson_mode_uses_markdown_as_primary_output():
    text = (SKILLS_ROOT / "book-to-skill/SKILL.md").read_text()
    contract = (
        SKILLS_ROOT / "book-to-skill/reference/managed-textbook-contract.md"
    ).read_text()

    assert "--managed-textbook-lesson" in text
    assert "outputs/lesson.md" in text
    assert "outputs/practice.json" in text
    assert "Mentrix-style" in contract
    assert "Markdown" in contract
    assert "--managed-textbook-lesson" not in (
        SKILLS_ROOT / "the-knowledge-guy/SKILL.md"
    ).read_text()


def test_book_to_skill_managed_asset_mode_defines_reusable_chapter_files():
    text = (SKILLS_ROOT / "book-to-skill/SKILL.md").read_text()
    contract = (
        SKILLS_ROOT / "book-to-skill/reference/managed-textbook-contract.md"
    ).read_text()

    assert "--managed-textbook-assets" in text
    assert "outputs/chapters_manifest.json" in text
    assert "outputs/chapters/*.md" in text
    assert "glossary.md" in text
    assert "patterns.md" in text
    assert "cheatsheet.md" in text
    assert "nutshell.md" in text
    assert "langalpha-managed-book-assets/v1" in contract
