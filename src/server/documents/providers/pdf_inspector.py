"""Isolated adapter for the pinned pdf-inspector Python package."""

from __future__ import annotations

import importlib.util
import math
from importlib import metadata
from pathlib import Path
from typing import cast

from src.config.settings import get_document_parsing_config
from src.server.documents.contracts import InspectionResult, JsonValue, PdfClassification
from src.server.documents.process_runner import SpawnProcessRunner
from src.server.documents.providers.base import (
    InspectorDescriptor,
    IsolatedProcessRunner,
)


_SUPPORTED_CLASSIFICATIONS: frozenset[str] = frozenset(
    {"text_based", "mixed", "scanned", "image_based"}
)


class PdfInspectorDetector:
    """Normalize pdf-inspector output without exposing its runtime types."""

    def __init__(
        self,
        *,
        runner: IsolatedProcessRunner | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        version = _package_version()
        self.descriptor = InspectorDescriptor(
            inspector_id="pdf-inspector",
            display_name="PDF Inspector",
            version=version,
            supported_formats=frozenset({"pdf"}),
            available=importlib.util.find_spec("pdf_inspector") is not None,
            reason="Detects the extraction needs of PDF documents.",
        )
        self._runner = runner or SpawnProcessRunner()
        self._timeout_seconds = (
            float(get_document_parsing_config().parse_timeout_seconds)
            if timeout_seconds is None
            else timeout_seconds
        )

    async def inspect(self, source_path: Path) -> InspectionResult:
        try:
            payload = await self._runner.run(
                _inspect_pdf_in_child,
                (str(source_path),),
                timeout_seconds=self._timeout_seconds,
            )
            return self._normalize_payload(payload)
        except Exception:
            return InspectionResult(
                inspector_id=self.descriptor.inspector_id,
                inspector_name=self.descriptor.display_name,
                inspector_version=self.descriptor.version,
                status="failed",
                detected_format="pdf",
                classification="unknown",
                error_code="inspection_failed",
                error_message="PDF inspection failed",
            )

    def _normalize_payload(self, payload: object) -> InspectionResult:
        if not isinstance(payload, dict):
            raise ValueError("Invalid inspector payload")

        page_count = payload.get("page_count")
        confidence = payload.get("confidence")
        if not _is_int(page_count) or page_count < 0:
            raise ValueError("Invalid page count")
        if (
            not isinstance(confidence, int | float)
            or isinstance(confidence, bool)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("Invalid confidence")

        raw_classification = str(payload.get("pdf_type", "unknown"))
        normalized = raw_classification.strip().lower().replace("-", "_")
        classification: PdfClassification = cast(
            PdfClassification,
            normalized if normalized in _SUPPORTED_CLASSIFICATIONS else "unknown",
        )
        page_dimensions = _normalize_page_dimensions(
            payload.get("page_dimensions"),
            page_count=page_count,
        )
        summary: dict[str, JsonValue] = {
            "page_count": page_count,
            "page_dimensions": page_dimensions,
        }
        details: dict[str, JsonValue] = {
            "pages_needing_ocr": _normalize_page_numbers(
                payload.get("pages_needing_ocr"),
                page_count=page_count,
            ),
            "confidence": float(confidence),
            "processing_time_ms": _normalize_nonnegative_int(
                payload.get("processing_time_ms"),
                field="processing_time_ms",
            ),
            "ocr_reasons_by_page": _normalize_ocr_reasons(
                payload.get("ocr_reasons_by_page"),
                page_count=page_count,
            ),
            "title": _normalize_optional_string(payload.get("title"), field="title"),
            "is_complex_layout": _normalize_bool(
                payload.get("is_complex_layout"),
                field="is_complex_layout",
            ),
            "pages_with_tables": _normalize_page_numbers(
                payload.get("pages_with_tables"),
                page_count=page_count,
            ),
            "pages_with_columns": _normalize_page_numbers(
                payload.get("pages_with_columns"),
                page_count=page_count,
            ),
            "has_encoding_issues": _normalize_bool(
                payload.get("has_encoding_issues"),
                field="has_encoding_issues",
            ),
        }

        return InspectionResult(
            inspector_id=self.descriptor.inspector_id,
            inspector_name=self.descriptor.display_name,
            inspector_version=self.descriptor.version,
            status="completed",
            detected_format="pdf",
            classification=classification,
            summary=summary,
            details=details,
        )


def _package_version() -> str | None:
    try:
        return metadata.version("pdf-inspector")
    except metadata.PackageNotFoundError:
        return None


def _inspect_pdf_in_child(source_path: str) -> dict[str, object]:
    from pdf_inspector import detect_pdf
    from pypdf import PdfReader

    result = detect_pdf(source_path)
    reader = PdfReader(source_path)
    dimensions: list[dict[str, float | int]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if page.rotation % 180:
            width, height = height, width
        dimensions.append(
            {
                "page": page_number,
                "width_points": width,
                "height_points": height,
            }
        )

    return {
        "pdf_type": result.pdf_type,
        "page_count": result.page_count,
        "page_dimensions": dimensions,
        "pages_needing_ocr": list(result.pages_needing_ocr),
        "confidence": result.confidence,
        "processing_time_ms": result.processing_time_ms,
        "ocr_reasons_by_page": [
            {"page": item.page, "reasons": list(item.reasons)}
            for item in result.ocr_reasons_by_page
        ],
        "title": result.title,
        "is_complex_layout": result.is_complex_layout,
        "pages_with_tables": list(result.pages_with_tables),
        "pages_with_columns": list(result.pages_with_columns),
        "has_encoding_issues": result.has_encoding_issues,
    }


def _normalize_page_dimensions(
    value: object,
    *,
    page_count: int,
) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list) or len(value) != page_count:
        raise ValueError("Invalid page dimensions")

    dimensions: list[dict[str, JsonValue]] = []
    for expected_page, item in enumerate(value, start=1):
        if not isinstance(item, dict) or item.get("page") != expected_page:
            raise ValueError("Invalid page dimensions")
        width = item.get("width_points")
        height = item.get("height_points")
        if not _is_positive_finite_number(width) or not _is_positive_finite_number(
            height
        ):
            raise ValueError("Invalid page dimensions")
        dimensions.append(
            {
                "page": expected_page,
                "width_points": float(width),
                "height_points": float(height),
            }
        )
    return dimensions


def _normalize_page_numbers(value: object, *, page_count: int) -> list[int]:
    if not isinstance(value, list):
        raise ValueError("Invalid page list")
    if any(not _is_int(page) or not 1 <= page <= page_count for page in value):
        raise ValueError("Invalid page list")
    if len(value) != len(set(value)):
        raise ValueError("Invalid page list")
    return list(value)


def _normalize_ocr_reasons(
    value: object,
    *,
    page_count: int,
) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        raise ValueError("Invalid OCR reasons")

    normalized: list[dict[str, JsonValue]] = []
    seen_pages: set[int] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Invalid OCR reasons")
        page = item.get("page")
        reasons = item.get("reasons")
        if (
            not _is_int(page)
            or not 1 <= page <= page_count
            or page in seen_pages
            or not isinstance(reasons, list)
            or any(not isinstance(reason, str) for reason in reasons)
        ):
            raise ValueError("Invalid OCR reasons")
        seen_pages.add(page)
        normalized.append({"page": page, "reasons": list(reasons)})
    return normalized


def _normalize_nonnegative_int(value: object, *, field: str) -> int:
    if not _is_int(value) or value < 0:
        raise ValueError(f"Invalid {field}")
    return value


def _normalize_optional_string(value: object, *, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Invalid {field}")
    return value


def _normalize_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Invalid {field}")
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_positive_finite_number(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )
