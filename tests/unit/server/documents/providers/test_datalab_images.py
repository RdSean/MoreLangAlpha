"""Extracted images become artifacts of their own.

Datalab returns images as ``{filename: base64}`` inside the response and writes
markdown that references them by bare filename, so the file that lands in the
object store has to be named exactly what the markdown says — otherwise the
reference resolves to nothing (which is why extraction used to be off).

The SDK client is replaced throughout; none of this reaches the network.
"""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.config.settings import DocumentParsingConfig, DatalabConfig
from src.server.documents.contracts import (
    InspectionResult,
    ParseRequest,
    SourceDocument,
)
from src.server.documents.providers import datalab


JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body" * 8
PNG = b"\x89PNG\r\n\x1a\n" + b"png-body" * 8


def _b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def _config() -> DatalabConfig:
    return DatalabConfig(
        api_key="dl-test-key",
        mode="balanced",
        poll_budget_seconds=540,
        parse_timeout_seconds=600,
    )


def _limits(
    *, images: int = 200, image_bytes: int = 32 * 1024 * 1024
) -> DocumentParsingConfig:
    return DocumentParsingConfig(
        max_upload_bytes=50 * 1024 * 1024,
        sync_wait_seconds=30,
        parse_timeout_seconds=600,
        max_image_artifacts=images,
        max_image_bytes=image_bytes,
    )


def _request(tmp_path: Path) -> ParseRequest:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4 test")
    return ParseRequest(
        source=SourceDocument(
            document_id="doc-A1b2C3d4E5f6",
            source_path=source,
            original_filename="homework.pdf",
            media_type="application/pdf",
            document_format="pdf",
        ),
        inspection=InspectionResult(
            inspector_id="pdf-inspector",
            inspector_name="PDF Inspector",
            inspector_version="1",
            status="completed",
            detected_format="pdf",
            classification="mixed",
            summary={},
            details={},
        ),
        parser_id="datalab-online",
        output_dir=tmp_path / "out",
        options={"disable_image_extraction": False},
    )


def _result(**overrides: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "success": True,
        "markdown": "![A picture](a_img.jpg)\n\nbody",
        "error": None,
        "page_count": 1,
        "parse_quality_score": None,
        "cost_breakdown": {"final_cost_cents": 1},
        "metadata": {"failed_pages": []},
        "images": {"a_img.jpg": _b64(JPEG)},
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.fixture
def stub_client(monkeypatch):
    captured: dict[str, Any] = {"calls": []}

    class FakeClient:
        def convert(self, path: str, **kwargs: Any) -> Any:
            captured["calls"].append({"path": path, **kwargs})
            return captured["result"]

    monkeypatch.setattr(datalab, "_client", lambda config: FakeClient())
    monkeypatch.setattr(datalab, "_convert_options", lambda options: options)
    monkeypatch.setattr(datalab, "get_document_parsing_config", _limits)
    captured["result"] = _result()
    return captured


def _images(bundle) -> list[Any]:
    return [a for a in bundle.artifacts if a.artifact_kind == "embedded_image"]


class TestWritingImages:
    def test_an_image_is_written_beside_the_markdown(
        self, tmp_path: Path, stub_client
    ) -> None:
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        images = _images(bundle)
        assert [spec.relative_path for spec in images] == ["a_img.jpg"]
        # The name is the reference: anything else and the markdown points at a
        # file that is not there.
        assert (tmp_path / "out" / "a_img.jpg").read_bytes() == JPEG
        assert images[0].media_type == "image/jpeg"
        assert images[0].format == "jpeg"
        assert (images[0].metadata or {})["referenced"] is True

    def test_the_type_comes_from_the_bytes_not_the_name(
        self, tmp_path: Path, stub_client
    ) -> None:
        stub_client["result"] = _result(
            markdown="![a](a_img.jpg)\n\n![b](b_img.jpg)\n\n![c](c_img.jpg)",
            images={
                "a_img.jpg": _b64(PNG),
                # A .jpg that is really a PNG: the extension lies, the magic
                # number does not, and the browser needs the truth.
                "b_img.jpg": _b64(PNG),
                "c_img.jpg": _b64(JPEG),
            },
        )
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        types = {spec.relative_path: spec.media_type for spec in _images(bundle)}
        assert types["a_img.jpg"] == "image/png"
        assert types["b_img.jpg"] == "image/png"
        assert types["c_img.jpg"] == "image/jpeg"

    def test_a_data_uri_prefix_is_tolerated(self, tmp_path: Path, stub_client) -> None:
        """The SDK has shipped both shapes; neither should cost us an image."""
        stub_client["result"] = _result(
            images={"a_img.jpg": f"data:image/jpeg;base64,{_b64(JPEG)}"}
        )
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        assert (tmp_path / "out" / "a_img.jpg").read_bytes() == JPEG

    def test_a_hostile_name_is_reduced_to_its_basename(
        self, tmp_path: Path, stub_client
    ) -> None:
        stub_client["result"] = _result(
            markdown="![a](passwd.jpg)",
            images={"../../etc/passwd.jpg": _b64(JPEG)},
        )
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        assert [spec.relative_path for spec in _images(bundle)] == ["passwd.jpg"]
        # And nothing was written outside the bundle directory.
        assert not (tmp_path / "etc").exists()

    def test_two_names_that_collapse_to_one_keep_the_first(
        self, tmp_path: Path, stub_client
    ) -> None:
        stub_client["result"] = _result(
            markdown="![a](a_img.jpg)",
            images={"a_img.jpg": _b64(JPEG), "nested/a_img.jpg": _b64(PNG)},
        )
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        assert [spec.relative_path for spec in _images(bundle)] == ["a_img.jpg"]
        assert (tmp_path / "out" / "a_img.jpg").read_bytes() == JPEG

    def test_undecodable_base64_is_dropped_rather_than_failing_the_document(
        self, tmp_path: Path, stub_client
    ) -> None:
        stub_client["result"] = _result(
            markdown="![a](a_img.jpg)",
            images={"a_img.jpg": "not base64 at all !!"},
        )
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        assert _images(bundle) == []
        metadata = bundle.artifacts[0].metadata or {}
        assert metadata["images_kept"] == 0
        assert metadata["images_dropped"] == 1

    def test_no_images_leaves_the_bundle_as_it_was(
        self, tmp_path: Path, stub_client
    ) -> None:
        stub_client["result"] = _result(images={})
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        assert len(bundle.artifacts) == 1
        assert bundle.primary_relative_path == "document.md"
        metadata = bundle.artifacts[0].metadata or {}
        assert metadata["images_kept"] == 0
        assert metadata["image_bytes"] == 0
        assert "warning" not in metadata


class TestImageLimits:
    def test_the_count_limit_drops_and_accounts(
        self, tmp_path: Path, stub_client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            datalab, "get_document_parsing_config", lambda: _limits(images=1)
        )
        stub_client["result"] = _result(
            markdown="![a](a_img.jpg)\n\n![b](b_img.jpg)",
            images={"a_img.jpg": _b64(JPEG), "b_img.jpg": _b64(JPEG)},
        )
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        assert [spec.relative_path for spec in _images(bundle)] == ["a_img.jpg"]
        metadata = bundle.artifacts[0].metadata or {}
        assert metadata["images_kept"] == 1
        assert metadata["images_dropped"] == 1
        assert "1 image" in str(metadata["warning"])

    def test_a_referenced_image_beats_an_unreferenced_one(
        self, tmp_path: Path, stub_client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Keep what the document actually points at.

        The response can carry an image the markdown never mentions; when the
        budget only stretches to one, the referenced one is the useful one.
        """
        monkeypatch.setattr(
            datalab, "get_document_parsing_config", lambda: _limits(images=1)
        )
        stub_client["result"] = _result(
            markdown="![b](b_img.jpg)",
            images={"a_cover.jpg": _b64(JPEG), "b_img.jpg": _b64(PNG)},
        )
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        assert [spec.relative_path for spec in _images(bundle)] == ["b_img.jpg"]

    def test_the_byte_limit_drops_and_accounts(
        self, tmp_path: Path, stub_client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            datalab, "get_document_parsing_config", lambda: _limits(image_bytes=16)
        )
        stub_client["result"] = _result(
            markdown="![a](a_img.jpg)",
            images={"a_img.jpg": _b64(JPEG)},
        )
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        assert _images(bundle) == []
        assert (bundle.artifacts[0].metadata or {})["images_dropped"] == 1
