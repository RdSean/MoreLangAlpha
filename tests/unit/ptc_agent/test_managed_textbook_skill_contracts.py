"""Managed textbook mode remains non-interactive and output-bounded."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _managed_block(text: str) -> str:
    start = text.index("## Managed textbook mode")
    next_heading = text.find("\n## ", start + 1)
    return text[start:] if next_heading == -1 else text[start:next_heading]


def test_book_to_skill_managed_mode_accepts_only_staged_markdown_manifest():
    text = (ROOT / "skills/book-to-skill/SKILL.md").read_text()
    managed = _managed_block(text)

    assert "--managed-textbook" in text
    assert "/managed/textbook-job/<job>/inputs/manifest.json" in managed
    assert "/managed/textbook-job/<job>/inputs/chapters/" in managed
    assert "AskUserQuestion" not in managed
    assert "PDF" not in managed
    assert "artifacts/" not in managed


def test_knowledge_guy_managed_mode_writes_only_schema_validated_outputs():
    text = (ROOT / "skills/the-knowledge-guy/SKILL.md").read_text()
    managed = _managed_block(text)

    assert "--managed-textbook" in text
    assert "outputs/teaching-package.json" in managed
    assert "EDUCATION_PROGRESS" in managed
    assert "AskUserQuestion" not in managed
    assert "artifacts/" not in managed
    assert "content_sha256" in managed
    assert "strict JSON" in managed
    assert "escape inner double quotes" in managed


def test_managed_contracts_define_the_same_output_schema():
    book_contract = (
        ROOT / "skills/book-to-skill/reference/managed-textbook-contract.md"
    ).read_text()
    knowledge_contract = (
        ROOT / "skills/the-knowledge-guy/reference/managed-textbook-contract.md"
    ).read_text()

    for required_field in (
        "content_chapter_id",
        "content_sha256",
        "learning_objectives",
        "knowledge_points",
        "teaching_material",
        "correct_option",
    ):
        assert required_field in book_contract
        assert required_field in knowledge_contract
