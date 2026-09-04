from __future__ import annotations

from pathlib import Path

from src.server.documents.contracts import InspectionResult
from src.server.documents.providers.base import InspectorDescriptor
from src.server.documents.providers.registry import DocumentProviderRegistry


class _PdfInspector:
    descriptor = InspectorDescriptor(
        inspector_id="pdf-inspector",
        display_name="PDF Inspector",
        version="1.17.0",
        supported_formats=frozenset({"pdf"}),
        available=True,
        reason="Detects the extraction needs of PDF documents.",
    )

    async def inspect(self, source_path: Path) -> InspectionResult:
        raise AssertionError("registry lookup must not execute the inspector")


def test_registry_resolves_inspector_by_format() -> None:
    inspector = _PdfInspector()
    registry = DocumentProviderRegistry(inspectors=(inspector,))

    assert registry.inspector_for_format(".PDF") is inspector
