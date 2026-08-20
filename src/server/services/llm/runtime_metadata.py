"""Safe LLM runtime provenance shared by chat persistence paths."""

from __future__ import annotations

from typing import Any


_RUNTIME_KEYS = (
    "credential_source",
    "household_id",
    "family_endpoint_id",
    "display_name",
    "provider",
    "model_id",
)


def safe_llm_runtime_metadata(metadata: Any) -> dict[str, str]:
    """Return only non-secret runtime provenance suitable for persistence."""
    if not isinstance(metadata, dict):
        return {}
    return {
        key: value.strip()
        for key in _RUNTIME_KEYS
        if isinstance((value := metadata.get(key)), str) and value.strip()
    }
