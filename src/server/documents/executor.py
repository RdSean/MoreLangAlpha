"""Fenced execution and exact-key publication of document parser bundles."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from src.config.settings import get_document_parsing_config
from src.server.database import document_jobs as job_repository
from src.server.database.document_jobs import ArtifactPublication
from src.server.documents.contracts import (
    ArtifactBundle,
    DocumentDomainError,
    InspectionResult,
    InvalidParserOutputError,
    ParseRequest,
    PdfClassification,
    SourceDocument,
    is_safe_artifact_path,
)
from src.server.documents.ids import new_public_id
from src.server.documents.process_runner import (
    IsolatedProcessTimeoutError,
    SpawnProcessRunner,
)
from src.server.database import document_usage as usage_repository
from src.server.documents.providers.base import DocumentParser, IsolatedProcessRunner
from src.server.documents.providers.registry import (
    DocumentProviderRegistry,
    build_default_provider_registry,
)
from src.server.documents.storage import DocumentObjectStore


logger = logging.getLogger(__name__)

_DEFAULT_MAX_ARTIFACTS = 256

UpdateNotifier = Callable[[str, int], Awaitable[None]]

UsageRecorder = Callable[..., Awaitable[object]]


class JobRepository(Protocol):
    async def update_progress(self, **kwargs: object) -> dict[str, Any] | None: ...

    async def publish_artifacts(self, **kwargs: object) -> dict[str, Any] | None: ...

    async def fail_job(self, **kwargs: object) -> dict[str, Any] | None: ...


class JobClaimLostError(RuntimeError):
    """The durable claim changed or cancellation won a stage boundary."""


@dataclass(slots=True)
class ClaimedDocumentJob:
    row: dict[str, Any]
    claimed_by: str
    attempt_count: int
    status_version: int
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @classmethod
    def from_row(
        cls,
        row: dict[str, Any] | dict[str, object],
        *,
        claimed_by: str,
    ) -> ClaimedDocumentJob:
        return cls(
            row=dict(row),
            claimed_by=claimed_by,
            attempt_count=int(row["attempt_count"]),
            status_version=int(row["status_version"]),
        )

    @property
    def job_id(self) -> str:
        return str(self.row["job_id"])


class DocumentJobExecutor:
    """Execute one claimed job while PostgreSQL continues to own its state."""

    def __init__(
        self,
        *,
        object_store: DocumentObjectStore,
        repository: JobRepository = job_repository,
        provider_registry: DocumentProviderRegistry | None = None,
        process_runner: IsolatedProcessRunner | None = None,
        parse_timeout_seconds: float | None = None,
        max_artifacts: int = _DEFAULT_MAX_ARTIFACTS,
        max_bundle_bytes: int | None = None,
        max_image_bytes: int | None = None,
        id_factory: Callable[[str], str] = new_public_id,
        usage_recorder: UsageRecorder = usage_repository.record_usage,
    ) -> None:
        config = get_document_parsing_config()
        if max_artifacts <= 0:
            raise ValueError("max_artifacts must be positive")
        self._repository = repository
        self._object_store = object_store
        self._provider_registry = provider_registry or build_default_provider_registry()
        self._process_runner = process_runner or SpawnProcessRunner()
        self._parse_timeout_seconds = (
            float(config.parse_timeout_seconds)
            if parse_timeout_seconds is None
            else parse_timeout_seconds
        )
        self._max_artifacts = max_artifacts
        self._max_bundle_bytes = (
            config.max_upload_bytes if max_bundle_bytes is None else max_bundle_bytes
        )
        # Images get their own ceiling. Counting them into the text's budget
        # would fail a picture-heavy scan that has ample room for the words.
        self._max_image_bytes = (
            config.max_image_bytes if max_image_bytes is None else max_image_bytes
        )
        if (
            self._parse_timeout_seconds <= 0
            or self._max_bundle_bytes <= 0
            or self._max_image_bytes <= 0
        ):
            raise ValueError("executor limits must be positive")
        self._id_factory = id_factory
        self._usage_recorder = usage_recorder
        self._update_notifier: UpdateNotifier | None = None

    def set_update_notifier(self, notifier: UpdateNotifier | None) -> None:
        """Attach best-effort wake delivery without coupling to Redis."""
        self._update_notifier = notifier

    async def execute(
        self,
        claim: ClaimedDocumentJob,
    ) -> dict[str, Any] | None:
        uploaded_keys: list[str] = []
        try:
            with tempfile.TemporaryDirectory(
                prefix=f"langalpha-document-job-{claim.job_id}-"
            ) as temp_name:
                root = Path(temp_name)
                source_path = root / "source" / "document.pdf"
                output_dir = root / "output"
                source_path.parent.mkdir(mode=0o700)
                output_dir.mkdir(mode=0o700)

                await self._advance(claim, stage="preparing", percentage=10)
                await self._object_store.get_file(
                    str(claim.row["source_storage_key"]),
                    source_path,
                    max_bytes=int(claim.row["source_size_bytes"]),
                )

                await self._advance(claim, stage="parsing", percentage=30)
                parser = self._provider_registry.parser_for_selection(
                    parser_id=str(claim.row["parser_id"]),
                    document_format=str(claim.row["document_format"]),
                    classification=str(claim.row["classification"]),
                )
                request = _parse_request(claim.row, source_path, output_dir)
                bundle = await self._process_runner.run(
                    _run_parser,
                    (parser, request),
                    timeout_seconds=self._parse_timeout_seconds,
                )
                publications = self._validate_bundle(
                    claim=claim,
                    output_dir=output_dir,
                    bundle=bundle,
                )

                await self._advance(claim, stage="storing", percentage=80)
                for publication in publications:
                    await self._object_store.put_file(
                        publication.storage_key,
                        output_dir / publication.relative_path,
                        content_type=publication.media_type,
                    )
                    uploaded_keys.append(publication.storage_key)

                primary_id = _primary_artifact_id(bundle, publications)
                async with claim.lock:
                    completed = await self._repository.publish_artifacts(
                        job_id=claim.job_id,
                        claimed_by=claim.claimed_by,
                        attempt_count=claim.attempt_count,
                        expected_status_version=claim.status_version,
                        artifacts=publications,
                        primary_artifact_id=primary_id,
                    )
                    if completed is None:
                        raise JobClaimLostError
                    claim.status_version = int(completed["status_version"])
                # After publication, never before: a bundle the executor
                # rejects below would otherwise leave a spend record for a
                # document that produced nothing, and over-stating usage is
                # worse than omitting it.
                await self._record_usage(claim, bundle)
                await self._notify(claim)
                return completed
        except JobClaimLostError:
            await self._delete_uploaded(uploaded_keys)
            return None
        except asyncio.CancelledError:
            await self._delete_uploaded(uploaded_keys)
            raise
        except Exception as error:
            await self._delete_uploaded(uploaded_keys)
            return await self._record_failure(claim, error)

    async def _record_usage(self, claim: ClaimedDocumentJob, bundle: object) -> None:
        """Persist what the parse cost, if the provider reported it.

        Providers stay pure: they declare usage in the artifact metadata and the
        executor — the only party that knows the job published successfully —
        writes it. A local parser simply declares nothing and no row appears.

        Failures here are logged and swallowed. The document is already
        published by this point, so raising would turn a successful parse into a
        failed job over bookkeeping; under-reporting spend is the acceptable
        direction.
        """
        usage = _usage_from_bundle(bundle)
        if usage is None:
            return
        try:
            await self._usage_recorder(
                job_id=claim.job_id,
                owner_user_id=str(claim.row.get("owner_user_id") or ""),
                provider_id=str(usage["provider_id"]),
                pages=int(usage["pages"]),
                list_cost_cents=usage.get("list_cost_cents"),
                final_cost_cents=int(usage["final_cost_cents"]),
            )
        except Exception:  # noqa: BLE001 - bookkeeping must not fail a good parse
            logger.warning(
                "[documents] could not record usage for job %s",
                claim.job_id,
                exc_info=True,
            )

    async def _advance(
        self,
        claim: ClaimedDocumentJob,
        *,
        stage: str,
        percentage: int,
    ) -> None:
        async with claim.lock:
            updated = await self._repository.update_progress(
                job_id=claim.job_id,
                claimed_by=claim.claimed_by,
                attempt_count=claim.attempt_count,
                expected_status_version=claim.status_version,
                stage=stage,
                percentage=percentage,
            )
            if updated is None:
                raise JobClaimLostError
            claim.status_version = int(updated["status_version"])
        await self._notify(claim)

    def _validate_bundle(
        self,
        *,
        claim: ClaimedDocumentJob,
        output_dir: Path,
        bundle: object,
    ) -> tuple[ArtifactPublication, ...]:
        if not isinstance(bundle, ArtifactBundle):
            raise InvalidParserOutputError("Parser returned an invalid artifact bundle")
        if not bundle.artifacts or len(bundle.artifacts) > self._max_artifacts:
            raise InvalidParserOutputError("Parser returned an invalid artifact count")

        relative_paths: set[str] = set()
        publications: list[ArtifactPublication] = []
        total_bytes = 0
        image_bytes = 0
        for spec in bundle.artifacts:
            if spec.relative_path in relative_paths or not is_safe_artifact_path(
                output_dir,
                spec.relative_path,
            ):
                raise InvalidParserOutputError(
                    "Parser returned an unsafe artifact path"
                )
            artifact_path = output_dir / spec.relative_path
            if (
                not artifact_path.is_file()
                or artifact_path.is_symlink()
                or _has_symlink_parent(artifact_path, output_dir)
            ):
                raise InvalidParserOutputError(
                    "Parser returned an invalid artifact file"
                )
            relative_paths.add(spec.relative_path)
            size = artifact_path.stat().st_size
            # Two budgets, on purpose: the text must fit the upload-sized
            # allowance, the pictures have their own.
            if spec.artifact_kind == "embedded_image":
                image_bytes += size
            else:
                total_bytes += size
            if total_bytes > self._max_bundle_bytes:
                raise InvalidParserOutputError("Parser artifact bundle is too large")
            if image_bytes > self._max_image_bytes:
                raise InvalidParserOutputError(
                    "Parser image artifacts are too large"
                )

            artifact_id = self._id_factory("artifact")
            storage_key = (
                f"documents/{claim.row['document_id']}/artifacts/"
                f"{claim.job_id}/{spec.relative_path}"
            )
            publications.append(
                ArtifactPublication(
                    artifact_id=artifact_id,
                    artifact_kind=spec.artifact_kind,
                    format=spec.format,
                    media_type=spec.media_type,
                    relative_path=spec.relative_path,
                    storage_key=storage_key,
                    schema_name=spec.schema_name,
                    schema_version=spec.schema_version,
                    locator=spec.locator,
                    metadata=spec.metadata,
                )
            )

        if (
            bundle.primary_relative_path is not None
            and bundle.primary_relative_path not in relative_paths
        ):
            raise InvalidParserOutputError("Primary artifact is not in the bundle")
        return tuple(publications)

    async def _record_failure(
        self,
        claim: ClaimedDocumentJob,
        error: Exception,
    ) -> dict[str, Any] | None:
        error_code, error_message = _safe_error(error)
        # A described failure is one the caller can act on and needs no log
        # line. Anything else reached the executor unexplained — a parser child
        # that died, an unwrapped provider error — and only the server log can
        # carry the reason, because the job's message stays deliberately vague.
        if isinstance(error, DocumentDomainError):
            logger.info(
                "Document job %s failed: %s (%s)",
                claim.job_id,
                error_message,
                error_code,
            )
        else:
            logger.warning(
                "Document job %s failed (%s): %r",
                claim.job_id,
                error_code,
                error,
                exc_info=error,
            )
        async with claim.lock:
            failed = await self._repository.fail_job(
                job_id=claim.job_id,
                claimed_by=claim.claimed_by,
                attempt_count=claim.attempt_count,
                expected_status_version=claim.status_version,
                error_code=error_code,
                error_message=error_message,
            )
            if failed is not None:
                claim.status_version = int(failed["status_version"])
        if failed is not None:
            await self._notify(claim)
        return failed

    async def _notify(self, claim: ClaimedDocumentJob) -> None:
        if self._update_notifier is None:
            return
        try:
            await self._update_notifier(claim.job_id, claim.status_version)
        except Exception:
            logger.debug(
                "Document job wake hint failed for %s",
                claim.job_id,
                exc_info=True,
            )

    async def _delete_uploaded(self, keys: list[str]) -> None:
        for key in reversed(keys):
            try:
                await self._object_store.delete(key)
            except Exception:
                logger.exception("Failed to compensate document artifact %s", key)


def _run_parser(parser: DocumentParser, request: ParseRequest) -> ArtifactBundle:
    return parser.parse(request)


def _usage_from_bundle(bundle: object) -> dict[str, Any] | None:
    """Find the documented ``usage`` sub-object in a bundle's metadata.

    Scanned across every artifact rather than read off the primary one, so a
    provider that returns a non-document first is not silently ignored, and
    validated enough that a malformed blob is skipped instead of raising inside
    the publish path.
    """
    if not isinstance(bundle, ArtifactBundle):
        return None
    for artifact in bundle.artifacts:
        usage = (artifact.metadata or {}).get("usage")
        if not isinstance(usage, dict):
            continue
        if not {"provider_id", "pages", "final_cost_cents"} <= set(usage):
            continue
        return usage
    return None


def _parse_request(
    row: dict[str, Any],
    source_path: Path,
    output_dir: Path,
) -> ParseRequest:
    classification = cast(PdfClassification, str(row["classification"]))
    return ParseRequest(
        source=SourceDocument(
            document_id=str(row["document_id"]),
            source_path=source_path,
            original_filename=str(row["original_filename"]),
            media_type=str(row["media_type"]),
            document_format=str(row["document_format"]),
        ),
        inspection=InspectionResult(
            inspector_id=str(row["inspector_id"]),
            inspector_name=str(row["inspector_name"]),
            inspector_version=(
                str(row["inspector_version"])
                if row.get("inspector_version") is not None
                else None
            ),
            status="completed",
            detected_format=str(row["detected_format"]),
            classification=classification,
            summary=dict(row.get("inspection_summary") or {}),
            details=dict(row.get("inspection_details") or {}),
        ),
        parser_id=str(row["parser_id"]),
        output_dir=output_dir,
        options=dict(row.get("parser_options") or {}),
    )


def _primary_artifact_id(
    bundle: object,
    publications: tuple[ArtifactPublication, ...],
) -> str | None:
    if not isinstance(bundle, ArtifactBundle) or bundle.primary_relative_path is None:
        return None
    return next(
        publication.artifact_id
        for publication in publications
        if publication.relative_path == bundle.primary_relative_path
    )


def _has_symlink_parent(path: Path, root: Path) -> bool:
    current = path.parent
    while current != root:
        if current.is_symlink():
            return True
        current = current.parent
    return False


def _safe_error(error: Exception) -> tuple[str, str]:
    if isinstance(error, IsolatedProcessTimeoutError):
        return "parse_timeout", "Document parsing timed out"
    if isinstance(error, DocumentDomainError):
        return error.code, error.safe_message
    return "parse_failed", "Document parsing failed"
