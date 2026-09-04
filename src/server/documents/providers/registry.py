"""Explicit provider registry for format-based inspector resolution."""

from __future__ import annotations

from collections.abc import Iterable

from src.server.documents.providers.base import DocumentInspector


class InspectorNotFoundError(LookupError):
    """Raised when no inspector supports a requested document format."""


class DocumentProviderRegistry:
    """Own provider instances without making process memory durable state."""

    def __init__(self, *, inspectors: Iterable[DocumentInspector] = ()) -> None:
        self._inspectors_by_format: dict[str, DocumentInspector] = {}
        inspector_ids: set[str] = set()

        for inspector in inspectors:
            descriptor = inspector.descriptor
            if descriptor.inspector_id in inspector_ids:
                raise ValueError(
                    f"Duplicate inspector ID: {descriptor.inspector_id}"
                )
            inspector_ids.add(descriptor.inspector_id)

            for document_format in descriptor.supported_formats:
                normalized = _normalize_format(document_format)
                if normalized in self._inspectors_by_format:
                    raise ValueError(
                        f"Multiple inspectors registered for format: {normalized}"
                    )
                self._inspectors_by_format[normalized] = inspector

    def inspector_for_format(self, document_format: str) -> DocumentInspector:
        normalized = _normalize_format(document_format)
        try:
            return self._inspectors_by_format[normalized]
        except KeyError as error:
            raise InspectorNotFoundError(
                f"No inspector is registered for format: {normalized}"
            ) from error


def _normalize_format(document_format: str) -> str:
    normalized = document_format.strip().lower().lstrip(".")
    if not normalized:
        raise ValueError("Document format cannot be empty")
    return normalized
