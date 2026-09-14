from __future__ import annotations

from pathlib import Path

from src.server.documents.contracts import InspectionResult
from src.server.documents.providers.base import InspectorDescriptor
from src.server.documents.providers.registry import (
    DocumentProviderRegistry,
    build_default_provider_registry,
)


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


class TestDefaultParserComposition:
    """The picker's menu: who is offered, and who is recommended.

    Asserted on the composition rather than on availability, because
    availability depends on whether the deployment set a Datalab key — the
    option list itself must not.
    """

    def _ids(self, registry, classification: str) -> set[str]:
        return {
            option.parser_id
            for option in registry.parser_options(
                document_format="pdf", classification=classification
            )
        }

    def _recommended(self, registry, classification: str) -> str | None:
        return next(
            (
                option.parser_id
                for option in registry.parser_options(
                    document_format="pdf", classification=classification
                )
                if option.recommended
            ),
            None,
        )

    def test_the_hosted_parser_is_offered_for_every_classification(self) -> None:
        """It is the only parser that can read a scan, so it must always show."""
        registry = build_default_provider_registry()
        for classification in (
            "text_based",
            "mixed",
            "scanned",
            "image_based",
            "unknown",
        ):
            assert "datalab-online" in self._ids(registry, classification), (
                classification
            )

    def test_the_retired_ocr_placeholder_is_gone(self) -> None:
        """Datalab does the job it was standing in for."""
        registry = build_default_provider_registry()
        for classification in ("scanned", "image_based", "unknown", "mixed"):
            assert "ocr-document" not in self._ids(registry, classification), (
                classification
            )

    def test_the_free_local_parser_stays_first_where_it_works(self) -> None:
        """Text-based PDFs should not be sent to a paid API by default."""
        registry = build_default_provider_registry()
        assert self._recommended(registry, "text_based") == "anydoc-local"

    def test_the_hosted_parser_is_recommended_where_the_locals_cannot_help(
        self,
    ) -> None:
        registry = build_default_provider_registry()
        for classification in ("scanned", "image_based", "mixed", "unknown"):
            assert self._recommended(registry, classification) != "legacy-pdf-text", (
                classification
            )


class TestRecommendationPolicy:
    """The policy itself, driven with explicit descriptors so it is deterministic."""

    _ALL_CLASSIFICATIONS = (
        "text_based",
        "mixed",
        "scanned",
        "image_based",
        "unknown",
    )

    @classmethod
    def _descriptor(cls, parser_id: str, *, available: bool):
        """Mirror the real declarations.

        AnyDoc only claims ``text_based``; the registry filters a classification's
        compatible parsers *before* asking this policy, so a fixture that gave
        AnyDoc scan support would be testing a list the production code never
        builds.
        """
        from src.server.documents.contracts import ParserDescriptor

        supported = (
            frozenset({"text_based"})
            if parser_id == "anydoc-local"
            else frozenset(cls._ALL_CLASSIFICATIONS)
        )
        return ParserDescriptor(
            parser_id=parser_id,
            display_name=parser_id,
            version=None,
            supported_formats=frozenset({"pdf"}),
            supported_classifications=supported,
            available=available,
            reason="test",
        )

    def test_prefers_the_local_parser_for_text_based(self) -> None:
        from src.server.documents.providers.registry import _recommended_parser_id

        descriptors = [
            self._descriptor("anydoc-local", available=True),
            self._descriptor("datalab-online", available=True),
            self._descriptor("legacy-pdf-text", available=True),
        ]
        assert _recommended_parser_id("text_based", descriptors) == "anydoc-local"

    def test_falls_back_to_the_hosted_parser_when_the_local_one_is_missing(
        self,
    ) -> None:
        from src.server.documents.providers.registry import _recommended_parser_id

        descriptors = [
            self._descriptor("anydoc-local", available=False),
            self._descriptor("datalab-online", available=True),
            self._descriptor("legacy-pdf-text", available=True),
        ]
        assert _recommended_parser_id("scanned", descriptors) == "datalab-online"

    def test_a_deployment_without_datalab_still_recommends_something(self) -> None:
        """No key configured must not leave the picker without a default."""
        from src.server.documents.providers.registry import _recommended_parser_id

        # Only the parsers that claim ``scanned`` reach the policy, which is
        # what the registry's own classification filter guarantees.
        descriptors = [
            self._descriptor("datalab-online", available=False),
            self._descriptor("legacy-pdf-text", available=True),
        ]
        assert _recommended_parser_id("scanned", descriptors) == "legacy-pdf-text"

    def test_prefers_the_hosted_parser_over_the_legacy_one_for_scans(self) -> None:
        """When both are available, the one that can actually read a scan wins."""
        from src.server.documents.providers.registry import _recommended_parser_id

        descriptors = [
            self._descriptor("datalab-online", available=True),
            self._descriptor("legacy-pdf-text", available=True),
        ]
        assert _recommended_parser_id("scanned", descriptors) == "datalab-online"
