from __future__ import annotations

import pytest

from src.server.documents.contracts import (
    ArtifactBundle,
    ArtifactSpec,
    ParseRequest,
    ParserDescriptor,
)
from src.server.documents.executor import ClaimedDocumentJob, DocumentJobExecutor
from src.server.documents.process_runner import (
    IsolatedProcessError,
    IsolatedProcessTimeoutError,
)
from src.server.documents.providers.registry import DocumentProviderRegistry


class _Repository:
    def __init__(self) -> None:
        self.progress: list[tuple[str, int]] = []
        self.published = None
        self.failed = None
        self.cancel_at_stage: str | None = None

    async def update_progress(self, **kwargs):
        self.progress.append((kwargs["stage"], kwargs["percentage"]))
        if kwargs["stage"] == self.cancel_at_stage:
            return None
        return {
            "status_version": kwargs["expected_status_version"] + 1,
            "status": "running",
        }

    async def publish_artifacts(self, **kwargs):
        self.published = kwargs
        return {
            "job_id": kwargs["job_id"],
            "status": "completed",
            "status_version": kwargs["expected_status_version"] + 1,
        }

    async def fail_job(self, **kwargs):
        self.failed = kwargs
        return {
            "job_id": kwargs["job_id"],
            "status": "failed",
            "status_version": kwargs["expected_status_version"] + 1,
        }


class _ObjectStore:
    def __init__(self, *, fail_put_number: int | None = None) -> None:
        self.fail_put_number = fail_put_number
        self.puts: list[tuple[str, bytes, str]] = []
        self.deletes: list[str] = []

    async def get_file(self, key, destination, *, max_bytes):
        destination.write_bytes(b"%PDF-1.4 source")
        return 16

    async def put_file(self, key, source, *, content_type):
        if self.fail_put_number == len(self.puts) + 1:
            raise RuntimeError("upload failed")
        self.puts.append((key, source.read_bytes(), content_type))

    async def delete(self, key):
        self.deletes.append(key)


class _Parser:
    descriptor = ParserDescriptor(
        parser_id="test-parser",
        display_name="Test Parser",
        version="1",
        supported_formats=frozenset({"pdf"}),
        supported_classifications=frozenset({"text_based"}),
        available=True,
        reason="Used by executor tests.",
    )

    def __init__(self, specs: tuple[ArtifactSpec, ...] | None = None) -> None:
        self.specs = specs or (
            ArtifactSpec(
                artifact_kind="primary_document",
                format="gfm",
                media_type="text/markdown",
                relative_path="document.md",
            ),
        )

    def parse(self, request: ParseRequest) -> ArtifactBundle:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        for spec in self.specs:
            if spec.relative_path.startswith(("/", "..")):
                continue
            target = request.output_dir / spec.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"content:{spec.relative_path}", encoding="utf-8")
        return ArtifactBundle(
            artifacts=self.specs,
            primary_relative_path=self.specs[0].relative_path,
        )


class _SizedParser(_Parser):
    """Writes files of an exact size, so the arithmetic is what is under test."""

    def __init__(self, specs: tuple[ArtifactSpec, ...], sizes: dict[str, int]) -> None:
        super().__init__(specs)
        self.sizes = sizes

    def parse(self, request: ParseRequest) -> ArtifactBundle:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        for spec in self.specs:
            target = request.output_dir / spec.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x" * self.sizes.get(spec.relative_path, 1))
        return ArtifactBundle(
            artifacts=self.specs,
            primary_relative_path=self.specs[0].relative_path,
        )


class _SymlinkParser(_Parser):
    def parse(self, request: ParseRequest) -> ArtifactBundle:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        outside = request.output_dir.parent / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        (request.output_dir / "document.md").symlink_to(outside)
        return ArtifactBundle(
            artifacts=self.specs,
            primary_relative_path="document.md",
        )


class _UsageParser(_Parser):
    """A parser that declares what the parse cost, the way Datalab does."""

    def __init__(self, usage: dict[str, object] | None) -> None:
        super().__init__()
        metadata = {"usage": usage} if usage is not None else None
        self.specs = (
            ArtifactSpec(
                artifact_kind="primary_document",
                format="gfm",
                media_type="text/markdown",
                relative_path="document.md",
                metadata=metadata,
            ),
        )


class _Runner:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.timeouts: list[float] = []

    async def run(self, target, args, *, timeout_seconds):
        self.timeouts.append(timeout_seconds)
        if self.error:
            raise self.error
        return target(*args)


def _job() -> dict[str, object]:
    return {
        "job_id": "job-A1b2C3d4E5f6",
        # The claim query carries the owner so a provider's reported usage can
        # be attributed without a second lookup.
        "owner_user_id": "owner-1",
        "document_id": "doc-A1b2C3d4E5f6",
        "inspection_id": "ins-A1b2C3d4E5f6",
        "parser_id": "test-parser",
        "parser_options": {},
        "status": "running",
        "attempt_count": 1,
        "status_version": 1,
        "source_storage_key": "documents/doc-A1b2C3d4E5f6/source",
        "source_size_bytes": 16,
        "original_filename": "source.pdf",
        "media_type": "application/pdf",
        "document_format": "pdf",
        "inspector_id": "pdf-inspector",
        "inspector_name": "PDF Inspector",
        "inspector_version": "1.17.0",
        "inspection_status": "completed",
        "detected_format": "pdf",
        "classification": "text_based",
        "inspection_summary": {"page_count": 1},
        "inspection_details": {},
    }


def _executor(
    repository: _Repository,
    store: _ObjectStore,
    parser: _Parser,
    *,
    runner: _Runner | None = None,
    ids: tuple[str, ...] = ("art-A1b2C3d4E5f6",),
    usage_recorder=None,
    max_bundle_bytes: int = 1024,
    max_image_bytes: int | None = None,
) -> DocumentJobExecutor:
    artifact_ids = iter(ids)
    return DocumentJobExecutor(
        repository=repository,
        object_store=store,
        provider_registry=DocumentProviderRegistry(parsers=(parser,)),
        process_runner=runner or _Runner(),
        parse_timeout_seconds=12,
        max_artifacts=10,
        max_bundle_bytes=max_bundle_bytes,
        id_factory=lambda kind: next(artifact_ids),
        **({"usage_recorder": usage_recorder} if usage_recorder else {}),
        **({"max_image_bytes": max_image_bytes} if max_image_bytes else {}),
    )


@pytest.mark.asyncio
async def test_executor_runs_all_stages_and_publishes_artifacts() -> None:
    repository = _Repository()
    store = _ObjectStore()
    claim = ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1")

    result = await _executor(repository, store, _Parser()).execute(claim)

    assert result is not None
    assert [stage for stage, _ in repository.progress] == [
        "preparing",
        "parsing",
        "storing",
    ]
    assert repository.published is not None
    assert repository.published["expected_status_version"] == 4
    assert repository.failed is None


@pytest.mark.asyncio
async def test_executor_uses_unique_job_prefix_for_every_artifact() -> None:
    specs = (
        ArtifactSpec("primary_document", "gfm", "text/markdown", "document.md"),
        ArtifactSpec("embedded_image", "png", "image/png", "images/page-1.png"),
    )
    repository = _Repository()
    store = _ObjectStore()
    executor = _executor(
        repository,
        store,
        _Parser(specs),
        ids=("art-A1b2C3d4E5f6", "art-G7h8I9j0K1l2"),
    )

    await executor.execute(ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1"))

    assert [key for key, _, _ in store.puts] == [
        "documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/document.md",
        ("documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/images/page-1.png"),
    ]


@pytest.mark.parametrize(
    "parser",
    [
        _Parser(
            (ArtifactSpec("primary_document", "gfm", "text/markdown", "../escape.md"),)
        ),
        _Parser(
            (
                ArtifactSpec(
                    "primary_document", "gfm", "text/markdown", "/tmp/escape.md"
                ),
            )
        ),
        _SymlinkParser(),
    ],
)
@pytest.mark.asyncio
async def test_executor_rejects_parent_absolute_and_symlink_outputs(
    parser: _Parser,
) -> None:
    repository = _Repository()
    store = _ObjectStore()

    result = await _executor(repository, store, parser).execute(
        ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1")
    )

    assert result is not None and result["status"] == "failed"
    assert repository.failed["error_code"] == "invalid_parser_output"
    assert store.puts == []


def _image_spec(name: str) -> ArtifactSpec:
    return ArtifactSpec("embedded_image", "jpeg", "image/jpeg", name)


@pytest.mark.asyncio
async def test_image_bytes_do_not_consume_the_markdown_budget() -> None:
    """A picture-heavy scan must not fail on a budget meant for the text."""
    repository = _Repository()
    specs = (
        ArtifactSpec("primary_document", "gfm", "text/markdown", "document.md"),
        _image_spec("big.jpg"),
    )
    parser = _SizedParser(specs, {"document.md": 10, "big.jpg": 4096})

    result = await _executor(
        repository,
        _ObjectStore(),
        parser,
        ids=("art-A1b2C3d4E5f6", "art-A1b2C3d4E5f7"),
        max_bundle_bytes=1024,
        max_image_bytes=10_000,
    ).execute(ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1"))

    assert result is not None and result["status"] == "completed"
    assert repository.failed is None


@pytest.mark.asyncio
async def test_images_have_their_own_ceiling() -> None:
    repository = _Repository()
    specs = (
        ArtifactSpec("primary_document", "gfm", "text/markdown", "document.md"),
        _image_spec("big.jpg"),
    )
    parser = _SizedParser(specs, {"document.md": 10, "big.jpg": 4096})

    result = await _executor(
        repository,
        _ObjectStore(),
        parser,
        ids=("art-A1b2C3d4E5f6", "art-A1b2C3d4E5f7"),
        max_image_bytes=1024,
    ).execute(ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1"))

    assert result is not None and result["status"] == "failed"
    assert repository.failed["error_code"] == "invalid_parser_output"
    # Distinct from the text message: an operator reading the job should not
    # have to guess which budget was actually exceeded.
    assert "image" in repository.failed["error_message"].lower()


@pytest.mark.asyncio
async def test_markdown_bytes_still_count_against_the_bundle_budget() -> None:
    repository = _Repository()
    parser = _SizedParser(
        (ArtifactSpec("primary_document", "gfm", "text/markdown", "document.md"),),
        {"document.md": 4096},
    )

    result = await _executor(repository, _ObjectStore(), parser).execute(
        ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1")
    )

    assert result is not None and result["status"] == "failed"
    assert repository.failed["error_code"] == "invalid_parser_output"
    assert "too large" in repository.failed["error_message"]


@pytest.mark.asyncio
async def test_partial_upload_failure_deletes_only_uploaded_job_keys() -> None:
    specs = (
        ArtifactSpec("primary_document", "gfm", "text/markdown", "document.md"),
        ArtifactSpec("structured_data", "json", "application/json", "data.json"),
    )
    repository = _Repository()
    store = _ObjectStore(fail_put_number=2)

    result = await _executor(
        repository,
        store,
        _Parser(specs),
        ids=("art-A1b2C3d4E5f6", "art-G7h8I9j0K1l2"),
    ).execute(ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1"))

    first_key = "documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/document.md"
    assert result is not None and result["status"] == "failed"
    assert store.deletes == [first_key]
    assert repository.published is None


@pytest.mark.asyncio
async def test_parser_timeout_fails_job_with_stable_error() -> None:
    repository = _Repository()
    runner = _Runner(IsolatedProcessTimeoutError("internal timeout"))

    result = await _executor(
        repository,
        _ObjectStore(),
        _Parser(),
        runner=runner,
    ).execute(ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1"))

    assert result is not None and result["status"] == "failed"
    assert repository.failed["error_code"] == "parse_timeout"
    assert repository.failed["error_message"] == "Document parsing timed out"
    assert runner.timeouts == [12]


@pytest.mark.asyncio
async def test_an_opaque_parser_failure_is_logged_but_not_shown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The user gets the generic message; the operator gets the reason.

    A parser child can die for reasons we cannot describe to a parent — a
    revoked key, a provider outage. The job's message stays deliberately
    vague, so the diagnosis has to reach the server log instead of the screen.
    """
    repository = _Repository()
    runner = _Runner(
        IsolatedProcessError(
            "The isolated process failed: DatalabAPIError: Request failed: boom"
        )
    )

    with caplog.at_level("WARNING", logger="src.server.documents.executor"):
        result = await _executor(
            repository,
            _ObjectStore(),
            _Parser(),
            runner=runner,
        ).execute(ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1"))

    assert result is not None and result["status"] == "failed"
    assert repository.failed["error_message"] == "Document parsing failed"
    assert "job-A1b2C3d4E5f6" in caplog.text
    assert "Request failed: boom" in caplog.text


@pytest.mark.asyncio
async def test_cancel_between_stages_never_publishes_artifacts() -> None:
    repository = _Repository()
    repository.cancel_at_stage = "storing"
    store = _ObjectStore()

    result = await _executor(repository, store, _Parser()).execute(
        ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1")
    )

    assert result is None
    assert store.puts == []
    assert repository.published is None
    assert repository.failed is None


@pytest.mark.asyncio
async def test_executor_publishes_only_compact_wake_hints_after_db_updates() -> None:
    repository = _Repository()
    hints: list[tuple[str, int]] = []

    async def notify(job_id: str, status_version: int) -> None:
        hints.append((job_id, status_version))

    executor = _executor(repository, _ObjectStore(), _Parser())
    executor.set_update_notifier(notify)

    await executor.execute(ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1"))

    assert hints == [
        ("job-A1b2C3d4E5f6", 2),
        ("job-A1b2C3d4E5f6", 3),
        ("job-A1b2C3d4E5f6", 4),
        ("job-A1b2C3d4E5f6", 5),
    ]


class TestUsageRecording:
    """Where a provider's reported cost becomes a row."""

    @pytest.mark.asyncio
    async def test_records_usage_a_parser_declared(self) -> None:
        calls: list[dict[str, object]] = []

        async def record(**kwargs: object) -> None:
            calls.append(kwargs)

        parser = _UsageParser(
            {
                "provider_id": "datalab-online",
                "pages": 12,
                "list_cost_cents": 24,
                "final_cost_cents": 24,
            }
        )
        executor = _executor(
            _Repository(), _ObjectStore(), parser, usage_recorder=record
        )

        await executor.execute(
            ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1")
        )

        assert calls == [
            {
                "job_id": "job-A1b2C3d4E5f6",
                "owner_user_id": "owner-1",
                "provider_id": "datalab-online",
                "pages": 12,
                "list_cost_cents": 24,
                "final_cost_cents": 24,
            }
        ]

    @pytest.mark.asyncio
    async def test_a_local_parser_records_nothing(self) -> None:
        """No declared usage, no row — the local parsers cost nothing."""
        calls: list[dict[str, object]] = []

        async def record(**kwargs: object) -> None:
            calls.append(kwargs)

        executor = _executor(
            _Repository(), _ObjectStore(), _Parser(), usage_recorder=record
        )
        await executor.execute(
            ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1")
        )

        assert calls == []

    @pytest.mark.asyncio
    async def test_bookkeeping_failure_does_not_fail_a_published_parse(self) -> None:
        """The document is already stored; losing it over a cost row is worse."""
        repository = _Repository()

        async def explode(**kwargs: object) -> None:
            raise RuntimeError("usage table is on fire")

        parser = _UsageParser(
            {"provider_id": "datalab-online", "pages": 1, "final_cost_cents": 2}
        )
        executor = _executor(repository, _ObjectStore(), parser, usage_recorder=explode)

        result = await executor.execute(
            ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1")
        )

        assert result is not None
        assert repository.failed is None

    @pytest.mark.asyncio
    async def test_a_malformed_usage_blob_is_skipped(self) -> None:
        """Missing required keys means "no usable declaration", not a crash."""
        calls: list[dict[str, object]] = []

        async def record(**kwargs: object) -> None:
            calls.append(kwargs)

        parser = _UsageParser({"pages": 3})
        executor = _executor(
            _Repository(), _ObjectStore(), parser, usage_recorder=record
        )

        await executor.execute(
            ClaimedDocumentJob.from_row(_job(), claimed_by="worker-1")
        )

        assert calls == []
