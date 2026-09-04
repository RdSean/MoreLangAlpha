"""Format-neutral provider protocols and descriptors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.server.documents.contracts import (
    ArtifactBundle,
    InspectionResult,
    ParseRequest,
    ParserDescriptor,
    ParserIncompatibleError,
    ParserUnavailableError,
)


@dataclass(frozen=True, slots=True)
class InspectorDescriptor:
    inspector_id: str
    display_name: str
    version: str | None
    supported_formats: frozenset[str]
    available: bool
    reason: str


class DocumentInspector(Protocol):
    descriptor: InspectorDescriptor

    async def inspect(self, source_path: Path) -> InspectionResult: ...


class DocumentParser(Protocol):
    descriptor: ParserDescriptor

    def parse(self, request: ParseRequest) -> ArtifactBundle: ...


class IsolatedProcessRunner(Protocol):
    async def run(
        self,
        target: Callable[..., object],
        args: tuple[object, ...],
        *,
        timeout_seconds: float,
    ) -> object: ...


def validate_parse_request(
    request: ParseRequest,
    descriptor: ParserDescriptor,
) -> None:
    """Reject unavailable or incompatible selections before native execution."""
    if not descriptor.available:
        raise ParserUnavailableError("The selected parser is not available")
    if request.parser_id != descriptor.parser_id:
        raise ParserIncompatibleError("The parse request selected another parser")
    if request.inspection.status != "completed":
        raise ParserIncompatibleError("A completed inspection is required")
    if (
        request.source.document_format not in descriptor.supported_formats
        or request.inspection.classification
        not in descriptor.supported_classifications
    ):
        raise ParserIncompatibleError(
            "The selected parser is not compatible with this document"
        )
