"""Explicit provider registry and parser recommendation policy."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from src.server.documents.contracts import (
    ParserDescriptor,
    ParserIncompatibleError,
    ParserUnavailableError,
)
from src.server.documents.providers.base import DocumentInspector, DocumentParser


class InspectorNotFoundError(LookupError):
    """Raised when no inspector supports a requested document format."""


class DocumentProviderRegistry:
    """Own provider instances without making process memory durable state."""

    def __init__(
        self,
        *,
        inspectors: Iterable[DocumentInspector] = (),
        parsers: Iterable[DocumentParser] = (),
        unavailable_parsers: Iterable[ParserDescriptor] = (),
    ) -> None:
        self._inspectors_by_format: dict[str, DocumentInspector] = {}
        self._parsers_by_id: dict[str, DocumentParser] = {}
        self._parser_descriptors: list[ParserDescriptor] = []
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

        for parser in parsers:
            self._register_parser_descriptor(parser.descriptor)
            self._parsers_by_id[parser.descriptor.parser_id] = parser
        for descriptor in unavailable_parsers:
            self._register_parser_descriptor(descriptor)

    def inspector_for_format(self, document_format: str) -> DocumentInspector:
        normalized = _normalize_format(document_format)
        try:
            return self._inspectors_by_format[normalized]
        except KeyError as error:
            raise InspectorNotFoundError(
                f"No inspector is registered for format: {normalized}"
            ) from error

    def parser_options(
        self,
        *,
        document_format: str,
        classification: str,
    ) -> tuple[ParserDescriptor, ...]:
        normalized_format = _normalize_format(document_format)
        compatible = [
            descriptor
            for descriptor in self._parser_descriptors
            if normalized_format in descriptor.supported_formats
            and classification in descriptor.supported_classifications
        ]
        recommended_id = _recommended_parser_id(classification, compatible)
        options = [
            replace(
                descriptor,
                recommended=descriptor.parser_id == recommended_id,
                warning=(
                    None
                    if descriptor.parser_id == "legacy-pdf-text"
                    and classification == "text_based"
                    else descriptor.warning
                ),
            )
            for descriptor in compatible
        ]
        options.sort(key=lambda option: not option.recommended)
        return tuple(options)

    def parser_for_selection(
        self,
        *,
        parser_id: str,
        document_format: str,
        classification: str,
    ) -> DocumentParser:
        descriptor = next(
            (
                item
                for item in self._parser_descriptors
                if item.parser_id == parser_id
            ),
            None,
        )
        if descriptor is None or not descriptor.available:
            raise ParserUnavailableError("The selected parser is not available")
        if (
            _normalize_format(document_format) not in descriptor.supported_formats
            or classification not in descriptor.supported_classifications
        ):
            raise ParserIncompatibleError(
                "The selected parser is not compatible with this document"
            )
        try:
            return self._parsers_by_id[parser_id]
        except KeyError as error:
            raise ParserUnavailableError(
                "The selected parser is not available"
            ) from error

    def _register_parser_descriptor(self, descriptor: ParserDescriptor) -> None:
        if any(
            existing.parser_id == descriptor.parser_id
            for existing in self._parser_descriptors
        ):
            raise ValueError(f"Duplicate parser ID: {descriptor.parser_id}")
        self._parser_descriptors.append(descriptor)


def build_default_provider_registry() -> DocumentProviderRegistry:
    from src.server.documents.providers.anydoc import AnydocExtractor
    from src.server.documents.providers.legacy_pdf import LegacyPdfExtractor
    from src.server.documents.providers.pdf_inspector import PdfInspectorDetector

    return DocumentProviderRegistry(
        inspectors=(PdfInspectorDetector(),),
        parsers=(AnydocExtractor(), LegacyPdfExtractor()),
        unavailable_parsers=(
            ParserDescriptor(
                parser_id="ocr-document",
                display_name="OCR Document",
                version=None,
                supported_formats=frozenset({"pdf"}),
                supported_classifications=frozenset(
                    {"mixed", "scanned", "image_based", "unknown"}
                ),
                available=False,
                reason="OCR parser is not configured yet.",
            ),
        ),
    )


def _recommended_parser_id(
    classification: str,
    descriptors: list[ParserDescriptor],
) -> str | None:
    preferred_id = "anydoc-local" if classification == "text_based" else "legacy-pdf-text"
    available_ids = {
        descriptor.parser_id for descriptor in descriptors if descriptor.available
    }
    if preferred_id in available_ids:
        return preferred_id
    return next(
        (
            descriptor.parser_id
            for descriptor in descriptors
            if descriptor.available
        ),
        None,
    )


def _normalize_format(document_format: str) -> str:
    normalized = document_format.strip().lower().lstrip(".")
    if not normalized:
        raise ValueError("Document format cannot be empty")
    return normalized
