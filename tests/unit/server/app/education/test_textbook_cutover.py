"""The textbook HTTP surface has no legacy processing or review entrypoints."""

import ast
from pathlib import Path

from src.server.app.education.textbooks import router

ROOT = Path(__file__).resolve().parents[5]
RETIRED_SERVICES = {
    "education_structure_jobs",
    "education_book_pipeline_jobs",
    "education_book_asset_jobs",
    "education_lesson_jobs",
    "education_book_package",
    "education_structure_validation",
    "education_structure_scope_validation",
    "education_lesson_validation",
    "education_structure_review",
    "education_candidate_review",
    "education_lesson_review",
    "education_progress_collector",
    "education_generation_progress",
    "education_structure_progress",
    "education_teaching_storage",
    "education_textbook_storage",
    "education_book_assets",
    "education_reading_assets",
    "education_source_refs",
    "education_processing_profiles",
}


def test_legacy_pipeline_modules_are_retired_not_wrapped():
    remaining = [
        name
        for name in sorted(RETIRED_SERVICES)
        if (ROOT / "src/server/services" / f"{name}.py").exists()
    ]
    assert remaining == []
    assert not (ROOT / "src/server/database/education_textbooks.py").exists()


def test_retired_skill_is_not_shipped_or_registered():
    from ptc_agent.agent.middleware.skills.registry import SKILL_REGISTRY

    assert not (ROOT / "plugins/langalpha_local/skills/book-to-skill/SKILL.md").exists()
    assert "book-to-skill" not in SKILL_REGISTRY
    assert "more-to-skills" in SKILL_REGISTRY


def test_only_workbench_jobs_assignments_and_learning_routes_remain():
    paths = {route.path.removeprefix("/api/v1/education") for route in router.routes}
    assert paths == {
        "/textbook-sources",
        "/textbooks",
        "/textbooks/{textbook_id}",
        "/textbooks/{textbook_id}/structure",
        "/textbooks/{textbook_id}/source",
        "/textbooks/{textbook_id}/knowledge-points/{knowledge_point_id}/material",
        "/textbooks/{textbook_id}/assets/{asset_id}",
        "/textbooks/{textbook_id}/jobs",
        "/textbooks/{textbook_id}/assignments",
        "/book-jobs/{job_id}",
        "/book-jobs/{job_id}/events",
        "/book-jobs/{job_id}/cancel",
        "/book-jobs/{job_id}/retry",
        "/learning",
        "/learning/{assignment_id}/structure",
        "/learning/{assignment_id}/knowledge-points/{knowledge_point_id}",
        "/learning/{assignment_id}/knowledge-points/{knowledge_point_id}/progress",
        "/learning/{assignment_id}/items",
        "/learning/{assignment_id}/knowledge-points/{knowledge_point_id}/items",
        "/learning/{assignment_id}/items/{item_id}",
        "/learning/{assignment_id}/nodes/{skill_node_id}/summaries",
        "/learning/{assignment_id}/chat-space",
        "/learning/{assignment_id}/chat-transcript",
    }


def test_textbook_facade_does_not_import_the_legacy_database():
    from src.server.services import education_textbooks

    tree = ast.parse(Path(education_textbooks.__file__).read_text())
    assert not any(
        isinstance(node, ast.ImportFrom)
        and node.module == "src.server.database.education_textbooks"
        for node in ast.walk(tree)
    )
