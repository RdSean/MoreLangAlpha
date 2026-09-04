"""Best-effort local PDF text provider using the shared legacy extractor."""

from __future__ import annotations

from src.server.documents.contracts import (
    ArtifactBundle,
    ArtifactSpec,
    JsonValue,
    ParseRequest,
    ParserDescriptor,
)
from src.server.documents.providers.base import validate_parse_request
from src.utils.pdf_text import extract_pdf_text


QUALITY_WARNING = "Pages without a usable text layer may be missing or empty."


class LegacyPdfExtractor:
    """Publish whatever local PDF text is available, including empty output."""

    descriptor = ParserDescriptor(
        parser_id="legacy-pdf-text",
        display_name="Legacy PDF Text",
        version=None,
        supported_formats=frozenset({"pdf"}),
        supported_classifications=frozenset(
            {"text_based", "mixed", "scanned", "image_based", "unknown"}
        ),
        available=True,
        reason="Extracts available PDF text locally without OCR.",
        warning=QUALITY_WARNING,
    )

    def parse(self, request: ParseRequest) -> ArtifactBundle:
        validate_parse_request(request, self.descriptor)
        result = extract_pdf_text(request.source.source_path, max_pages=None)
        metadata: dict[str, JsonValue] = {
            "backend": result.backend,
            "extracted_pages": list(result.extracted_pages),
            "total_pages": result.total_pages,
        }
        if request.inspection.classification != "text_based":
            metadata["warning"] = QUALITY_WARNING

        request.output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        relative_path = "document.md"
        request.output_dir.joinpath(relative_path).write_text(
            result.markdown,
            encoding="utf-8",
        )
        return ArtifactBundle(
            artifacts=(
                ArtifactSpec(
                    artifact_kind="primary_document",
                    format="gfm",
                    media_type="text/markdown",
                    relative_path=relative_path,
                    metadata=metadata,
                ),
            ),
            primary_relative_path=relative_path,
        )
