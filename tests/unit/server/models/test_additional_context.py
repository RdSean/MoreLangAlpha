"""Tests for the generic AdditionalContext discriminated union."""

import pytest
from pydantic import TypeAdapter, ValidationError

from src.server.models.additional_context import (
    AdditionalContext,
    DirectiveContext,
    MultimodalContext,
    SkillContext,
    WidgetContext,
)


_adapter = TypeAdapter(AdditionalContext)


def test_skill_context_routes_to_skill_model():
    context = _adapter.validate_python({"type": "skills", "name": "pdf"})

    assert isinstance(context, SkillContext)
    assert context.name == "pdf"


def test_file_context_routes_to_multimodal_model():
    context = _adapter.validate_python(
        {"type": "file", "data": "data:text/plain;base64,eA=="}
    )

    assert isinstance(context, MultimodalContext)
    assert context.type == "file"


def test_directive_context_routes_to_directive_model():
    context = _adapter.validate_python({"type": "directive", "content": "Focus on clarity."})

    assert isinstance(context, DirectiveContext)
    assert context.content == "Focus on clarity."


def test_widget_context_requires_display_metadata():
    with pytest.raises(ValidationError):
        _adapter.validate_python(
            {"type": "widget", "widget_id": "widget-1", "text": "summary"}
        )


def test_widget_context_routes_to_widget_model():
    context = _adapter.validate_python(
        {
            "type": "widget",
            "widget_type": "progress.summary",
            "widget_id": "widget-1",
            "label": "Progress",
            "text": "<widget-context>Ready</widget-context>",
        }
    )

    assert isinstance(context, WidgetContext)
    assert context.data == {}
