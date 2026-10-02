"""Fixed semantic-stage contracts for managed textbook items."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("item_kind", "expected_stages"),
    (
        (
            "structure",
            [
                "structure_reading",
                "structure_organizing",
                "structure_splitting",
                "structure_validating",
            ],
        ),
        (
            "material",
            [
                "material_reading",
                "material_organizing",
                "material_writing",
                "material_validating",
            ],
        ),
        (
            "supplementary",
            [
                "supplementary_reading",
                "supplementary_organizing",
                "supplementary_validating",
            ],
        ),
    ),
)
def test_progress_contract_exposes_only_the_item_stage_catalog(
    item_kind, expected_stages
):
    from src.server.services.education_book_progress import progress_contract

    contract = progress_contract({"kind": item_kind})

    assert contract["tool"] == "report_progress"
    assert contract["allowed_stages"] == expected_stages
    assert len(contract["allowed_actions"]) == (8 if item_kind == "material" else 0)


def test_material_actions_are_scoped_optional_and_return_deep_copies():
    from src.server.services.education_book_progress import (
        progress_contract,
        progress_message,
    )

    actions = progress_contract({"kind": "material"})["allowed_actions"]
    assert actions["clarifying_concepts"]["message"] == "正在澄清概念与术语"
    assert "原文" in actions["explaining_source_examples"]["when"]
    assert "原有" in actions["creating_examples"]["when"]
    assert (
        progress_message(
            "material_writing", item_kind="material", action="clarifying_concepts"
        )
        == "正在澄清概念与术语"
    )
    assert (
        progress_message(
            "material_reading", item_kind="material", action="clarifying_concepts"
        )
        is None
    )
    assert (
        progress_message(
            "structure_reading", item_kind="structure", action="reading_context"
        )
        is None
    )
    assert (
        progress_message("material_writing", item_kind="material", action="unknown")
        is None
    )
    actions["clarifying_concepts"]["stages"].append("invented")
    actions["clarifying_concepts"]["message"] = "invented"
    fresh = progress_contract({"kind": "material"})["allowed_actions"]
    assert "invented" not in fresh["clarifying_concepts"]["stages"]
    assert fresh["clarifying_concepts"]["message"] == "正在澄清概念与术语"


def test_progress_contract_returns_a_fresh_stage_list():
    from src.server.services.education_book_progress import progress_contract

    contract = progress_contract({"kind": "structure"})
    contract["allowed_stages"].append("invented")

    assert "invented" not in progress_contract({"kind": "structure"})["allowed_stages"]


def test_progress_message_is_scoped_to_the_item_kind():
    from src.server.services.education_book_progress import progress_message

    assert (
        progress_message("structure_organizing", item_kind="structure")
        == "正在整理章节层级"
    )
    assert progress_message("material_writing", item_kind="structure") is None
    assert progress_message("unknown", item_kind="material") is None


def test_progress_contract_rejects_unknown_item_kind():
    from src.server.services.education_book_progress import progress_contract

    with pytest.raises(ValueError, match="item kind"):
        progress_contract({"kind": "unknown"})
