"""Local AnyDoc provider for digital documents with usable text layers."""

from __future__ import annotations

import importlib.util
from importlib import metadata

from src.server.documents.contracts import (
    ArtifactBundle,
    ArtifactSpec,
    ParseRequest,
    ParserDescriptor,
    ParserIncompatibleError,
)
from src.server.documents.providers.base import validate_parse_request


class AnydocExtractor:
    """Convert a text-based PDF to local Markdown without hosted fallback."""

    def __init__(self) -> None:
        self.descriptor = ParserDescriptor(
            parser_id="anydoc-local",
            display_name="AnyDoc Local",
            version=_package_version(),
            supported_formats=frozenset({"pdf"}),
            supported_classifications=frozenset({"text_based"}),
            available=importlib.util.find_spec("anydoc") is not None,
            reason="Best for PDFs with a usable text layer.",
        )

    def parse(self, request: ParseRequest) -> ArtifactBundle:
        validate_parse_request(request, self.descriptor)

        import anydoc

        try:
            markdown = anydoc.to_markdown(
                request.source.source_path,
                ocr="reject",
            )
        except anydoc.NeedsOcrError as error:
            raise ParserIncompatibleError(
                "AnyDoc cannot parse pages that require OCR"
            ) from error
        if not markdown.strip():
            raise ParserIncompatibleError(
                "AnyDoc returned no Markdown; use a mixed-document parser"
            )

        request.output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        relative_path = "document.md"
        request.output_dir.joinpath(relative_path).write_text(
            markdown,
            encoding="utf-8",
        )
        return ArtifactBundle(
            artifacts=(
                ArtifactSpec(
                    artifact_kind="primary_document",
                    format="gfm",
                    media_type="text/markdown",
                    relative_path=relative_path,
                ),
            ),
            primary_relative_path=relative_path,
        )


def _package_version() -> str | None:
    try:
        return metadata.version("firecrawl-anydoc")
    except metadata.PackageNotFoundError:
        return None
