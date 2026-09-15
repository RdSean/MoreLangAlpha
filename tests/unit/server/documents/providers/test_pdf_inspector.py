from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from src.server.documents.process_runner import (
    IsolatedProcessError,
    IsolatedProcessTimeoutError,
    SpawnProcessRunner,
)
from src.server.documents.providers.pdf_inspector import PdfInspectorDetector


FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "documents"


class _ResultRunner:
    def __init__(self, result: object) -> None:
        self.result = result

    async def run(
        self,
        target: Callable[..., object],
        args: tuple[object, ...],
        *,
        timeout_seconds: float,
    ) -> object:
        return self.result


class _CrashRunner:
    async def run(
        self,
        target: Callable[..., object],
        args: tuple[object, ...],
        *,
        timeout_seconds: float,
    ) -> object:
        return await SpawnProcessRunner().run(
            _crash_process,
            (),
            timeout_seconds=timeout_seconds,
        )


def _crash_process() -> None:
    os._exit(17)


def _write_after_delay(pid_path: str, output_path: str) -> None:
    Path(pid_path).write_text(str(os.getpid()), encoding="ascii")
    time.sleep(10)
    Path(output_path).write_text("child survived", encoding="ascii")


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _upstream_result() -> dict[str, object]:
    return {
        "pdf_type": "mixed",
        "page_count": 2,
        "page_dimensions": [
            {"page": 1, "width_points": 612.0, "height_points": 792.0},
            {"page": 2, "width_points": 612.0, "height_points": 792.0},
        ],
        "pages_needing_ocr": [2],
        "confidence": 0.65,
        "processing_time_ms": 7,
        "ocr_reasons_by_page": [{"page": 2, "reasons": ["scanned"]}],
        "title": "Algebra notes",
        "is_complex_layout": False,
        "pages_with_tables": [],
        "pages_with_columns": [],
        "has_encoding_issues": False,
    }


@pytest.mark.asyncio
async def test_pdf_inspector_maps_upstream_fields_to_generic_result(
    tmp_path: Path,
) -> None:
    result = await PdfInspectorDetector(
        runner=_ResultRunner(_upstream_result()),
    ).inspect(tmp_path / "source.pdf")

    assert result.status == "completed"
    assert result.detected_format == "pdf"
    assert result.classification == "mixed"
    assert result.summary == {
        "page_count": 2,
        "page_dimensions": [
            {"page": 1, "width_points": 612.0, "height_points": 792.0},
            {"page": 2, "width_points": 612.0, "height_points": 792.0},
        ],
    }
    assert result.error_code is None


@pytest.mark.asyncio
async def test_pdf_inspector_preserves_ocr_pages_and_supported_diagnostics(
    tmp_path: Path,
) -> None:
    result = await PdfInspectorDetector(
        runner=_ResultRunner(_upstream_result()),
    ).inspect(tmp_path / "source.pdf")

    assert result.details == {
        "pages_needing_ocr": [2],
        "confidence": 0.65,
        "processing_time_ms": 7,
        "ocr_reasons_by_page": [{"page": 2, "reasons": ["scanned"]}],
        "title": "Algebra notes",
        "is_complex_layout": False,
        "pages_with_tables": [],
        "pages_with_columns": [],
        "has_encoding_issues": False,
    }


@pytest.mark.asyncio
async def test_pdf_inspector_rejects_non_json_safe_upstream_payload(
    tmp_path: Path,
) -> None:
    payload = _upstream_result()
    payload["page_dimensions"] = [
        {"page": 1, "width_points": float("nan"), "height_points": 792.0},
        {"page": 2, "width_points": 612.0, "height_points": 792.0},
    ]

    result = await PdfInspectorDetector(
        runner=_ResultRunner(payload),
    ).inspect(tmp_path / "source.pdf")

    assert result.status == "failed"
    assert result.error_code == "inspection_failed"
    assert result.summary == {}
    assert result.details == {}


@pytest.mark.asyncio
async def test_pdf_inspector_reports_safe_error_when_child_crashes(
    tmp_path: Path,
) -> None:
    secret_path = tmp_path / "private" / "source.pdf"

    result = await PdfInspectorDetector(
        runner=_CrashRunner(),
        timeout_seconds=5,
    ).inspect(secret_path)

    assert result.status == "failed"
    assert result.classification == "unknown"
    assert result.error_code == "inspection_failed"
    assert result.error_message == "PDF inspection failed"
    assert str(secret_path) not in repr(result)


@pytest.mark.asyncio
async def test_process_runner_terminates_child_at_deadline(tmp_path: Path) -> None:
    pid_path = tmp_path / "child.pid"
    output_path = tmp_path / "too-late.txt"

    with pytest.raises(
        IsolatedProcessTimeoutError,
        match="timed out",
    ):
        await SpawnProcessRunner().run(
            _write_after_delay,
            (str(pid_path), str(output_path)),
            timeout_seconds=1,
        )

    assert pid_path.exists()
    assert not _pid_exists(int(pid_path.read_text(encoding="ascii")))
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_process_runner_converts_child_crash_to_safe_error() -> None:
    with pytest.raises(IsolatedProcessError) as error:
        await SpawnProcessRunner().run(
            _crash_process,
            (),
            timeout_seconds=5,
        )

    assert str(error.value) == "The isolated process failed"


@pytest.mark.asyncio
async def test_process_runner_drains_large_result_before_joining_child() -> None:
    result = await SpawnProcessRunner().run(
        bytes,
        (1_000_000,),
        timeout_seconds=2,
    )

    assert isinstance(result, bytes)
    assert len(result) == 1_000_000


@pytest.mark.integration
@pytest.mark.parametrize(
    ("filename", "classification", "ocr_pages"),
    [
        ("text.pdf", "text_based", []),
        ("scanned.pdf", "scanned", [1]),
        ("image-based.pdf", "image_based", [1]),
        ("mixed.pdf", "mixed", [2]),
    ],
)
@pytest.mark.asyncio
async def test_real_pdf_inspector_binding_classifies_fixtures(
    filename: str,
    classification: str,
    ocr_pages: list[int],
) -> None:
    result = await PdfInspectorDetector(timeout_seconds=10).inspect(
        FIXTURES / filename
    )

    assert result.status == "completed"
    assert result.classification == classification
    assert result.details["pages_needing_ocr"] == ocr_pages
    assert result.summary["page_count"] >= 1
    assert len(result.summary["page_dimensions"]) == result.summary["page_count"]
