"""The Datalab provider.

The SDK client is replaced throughout: these tests are about how we interpret
its results, and none of them should reach the network or spend money. The two
behaviours with their own cases are the ones the vendor's own documentation
warns about — a completed request that failed without raising, and partial page
failures that are still a success.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.config.settings import DatalabConfig
from src.server.documents.contracts import (
    InspectionResult,
    InvalidParserOutputError,
    ParseRequest,
    ParseTimeoutError,
    ParserUnavailableError,
    SourceDocument,
)
from src.server.documents.providers import datalab


def _config() -> DatalabConfig:
    return DatalabConfig(
        api_key="dl-test-key",
        mode="balanced",
        poll_budget_seconds=540,
        parse_timeout_seconds=600,
    )


def _request(tmp_path: Path, *, options: dict[str, Any] | None = None) -> ParseRequest:
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
            classification="scanned",
            summary={},
            details={},
        ),
        parser_id="datalab-online",
        output_dir=tmp_path / "out",
        options=options or {},
    )


def _result(**overrides: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "success": True,
        "markdown": "# homework\n\nbody",
        "error": None,
        "page_count": 3,
        "parse_quality_score": 4.5,
        "cost_breakdown": {"list_cost_cents": 6, "final_cost_cents": 6},
        "metadata": {"failed_pages": []},
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.fixture
def stub_client(monkeypatch):
    """Replace the SDK client and capture how it was called."""
    captured: dict[str, Any] = {"calls": []}

    class FakeClient:
        def convert(self, path: str, **kwargs: Any) -> Any:
            captured["calls"].append({"path": path, **kwargs})
            result = captured["result"]
            if isinstance(result, BaseException):
                raise result
            return result

    monkeypatch.setattr(datalab, "_client", lambda config: FakeClient())
    monkeypatch.setattr(datalab, "_convert_options", lambda options: options)
    captured["result"] = _result()
    return captured


class TestDescriptor:
    def test_reports_unavailable_without_configuration(self) -> None:
        extractor = datalab.DatalabExtractor(config_loader=lambda: None)
        assert extractor.descriptor.available is False
        # The reason has to say what to set, or the picker just says "no".
        assert "DATALAB_API_KEY" in extractor.descriptor.reason

    def test_reports_available_with_configuration(self) -> None:
        extractor = datalab.DatalabExtractor(config_loader=_config)
        assert extractor.descriptor.available is True

    def test_supports_every_classification(self) -> None:
        """The point of a hosted parser: the local ones cannot read scans."""
        extractor = datalab.DatalabExtractor(config_loader=_config)
        assert extractor.descriptor.supported_classifications == frozenset(
            {"text_based", "mixed", "scanned", "image_based", "unknown"}
        )

    def test_parsing_without_configuration_raises(self, tmp_path: Path) -> None:
        extractor = datalab.DatalabExtractor(config_loader=lambda: None)
        with pytest.raises(ParserUnavailableError):
            extractor.parse(_request(tmp_path))


class TestSuccessfulConversion:
    def test_writes_markdown_and_publishes_it_as_the_primary_artifact(
        self, tmp_path: Path, stub_client
    ) -> None:
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        written = tmp_path / "out" / "document.md"
        assert written.read_text(encoding="utf-8") == "# homework\n\nbody"

        artifact = bundle.artifacts[0]
        assert artifact.artifact_kind == "primary_document"
        assert artifact.format == "gfm"
        assert artifact.media_type == "text/markdown"
        assert artifact.relative_path == bundle.primary_relative_path

    def test_records_the_cost_and_quality_in_metadata(
        self, tmp_path: Path, stub_client
    ) -> None:
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )
        metadata = bundle.artifacts[0].metadata or {}

        assert metadata["page_count"] == 3
        assert metadata["parse_quality_score"] == 4.5
        # The shape the executor records usage from.
        assert metadata["usage"] == {
            "provider_id": "datalab-online",
            "pages": 3,
            "list_cost_cents": 6,
            "final_cost_cents": 6,
        }

    def test_passes_the_poll_budget_from_configuration(
        self, tmp_path: Path, stub_client
    ) -> None:
        """The ordering the config validated has to survive to the call.

        Without this assertion a refactor could hard-code a budget above our
        subprocess timeout and orphan billable work with nothing failing.
        """
        datalab.DatalabExtractor(config_loader=_config).parse(_request(tmp_path))
        call = stub_client["calls"][0]
        assert call["max_polls"] == 540

    def test_stored_options_reach_the_client(self, tmp_path: Path, stub_client) -> None:
        request = _request(tmp_path, options={"mode": "accurate", "page_range": "0-5"})
        datalab.DatalabExtractor(config_loader=_config).parse(request)

        forwarded = stub_client["calls"][0]["options"]
        assert forwarded.mode == "accurate"
        assert forwarded.page_range == "0-5"

    def test_nonsense_stored_options_do_not_fail_the_job(
        self, tmp_path: Path, stub_client
    ) -> None:
        """A stale wizard must still get a document, on defaults."""
        request = _request(tmp_path, options={"mode": "turbo"})
        bundle = datalab.DatalabExtractor(config_loader=_config).parse(request)

        assert stub_client["calls"][0]["options"].mode == "balanced"
        assert bundle.primary_relative_path == "document.md"


class TestFailureHandling:
    def test_a_completed_but_failed_request_raises(
        self, tmp_path: Path, stub_client
    ) -> None:
        """The vendor's documented trap: success=False without an exception."""
        stub_client["result"] = _result(success=False, error="unsupported encoding")

        with pytest.raises(InvalidParserOutputError, match="unsupported encoding"):
            datalab.DatalabExtractor(config_loader=_config).parse(_request(tmp_path))

        # And nothing was written for it to be published by mistake.
        assert not (tmp_path / "out" / "document.md").exists()

    def test_empty_output_raises_rather_than_publishing_an_empty_document(
        self, tmp_path: Path, stub_client
    ) -> None:
        stub_client["result"] = _result(markdown="   ")
        with pytest.raises(InvalidParserOutputError):
            datalab.DatalabExtractor(config_loader=_config).parse(_request(tmp_path))

    def test_partial_page_failures_are_still_a_success(
        self, tmp_path: Path, stub_client
    ) -> None:
        """`metadata.failed_pages` is a warning, not a failure.

        Failing the whole job over one unreadable page would throw away the
        pages that did convert, which is the more useful outcome.
        """
        stub_client["result"] = _result(metadata={"failed_pages": [4, 5]})

        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        metadata = bundle.artifacts[0].metadata or {}
        assert metadata["failed_pages"] == [4, 5]
        assert "2 page" in str(metadata["warning"])

    def test_a_missing_cost_breakdown_does_not_crash_the_metadata(
        self, tmp_path: Path, stub_client
    ) -> None:
        """Be forgiving about what we record, strict about what we publish."""
        stub_client["result"] = _result(cost_breakdown=None, page_count=None)

        bundle = datalab.DatalabExtractor(config_loader=_config).parse(
            _request(tmp_path)
        )

        usage = (bundle.artifacts[0].metadata or {})["usage"]
        assert usage["pages"] == 0
        assert usage["final_cost_cents"] == 0


class TestSdkFailures:
    """What the caller is told when the SDK itself gives up.

    The SDK wraps HTTP failures, including connection errors, in
    ``DatalabAPIError`` and raises ``DatalabTimeoutError`` when polling runs
    dry. Letting those escape makes the job end at the executor's generic
    "Document parsing failed" with no way to tell a wrong key from a network
    outage — a real run against a deliberately invalid key produced exactly
    that, which is why these cases are pinned here rather than left to the
    executor.
    """

    def test_rejected_credentials_name_the_missing_setting(
        self, tmp_path: Path, stub_client
    ) -> None:
        from datalab_sdk.exceptions import DatalabAPIError

        stub_client["result"] = DatalabAPIError("Unauthorized", status_code=401)

        with pytest.raises(ParserUnavailableError) as error:
            datalab.DatalabExtractor(config_loader=_config).parse(_request(tmp_path))

        assert "DATALAB_API_KEY" in error.value.safe_message
        assert "401" in error.value.safe_message
        # The cause survives so the operator log keeps the provider's words.
        assert isinstance(error.value.__cause__, DatalabAPIError)

    def test_an_unreachable_api_is_a_conversion_failure_not_a_crash(
        self, tmp_path: Path, stub_client
    ) -> None:
        from datalab_sdk.exceptions import DatalabAPIError

        # The shape the SDK uses for a transport error: no status code at all.
        stub_client["result"] = DatalabAPIError("Request failed: boom")

        with pytest.raises(InvalidParserOutputError, match="Request failed: boom"):
            datalab.DatalabExtractor(config_loader=_config).parse(_request(tmp_path))

    def test_exhausted_polling_is_reported_as_a_timeout(
        self, tmp_path: Path, stub_client
    ) -> None:
        from datalab_sdk.exceptions import DatalabTimeoutError

        stub_client["result"] = DatalabTimeoutError("Polling timed out after 540 seconds")

        with pytest.raises(ParseTimeoutError) as error:
            datalab.DatalabExtractor(config_loader=_config).parse(_request(tmp_path))

        assert error.value.code == "parse_timeout"
