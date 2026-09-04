"""Format-neutral inspector, parser, job, and artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal, TypeAlias


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

PdfClassification: TypeAlias = Literal[
    "text_based",
    "mixed",
    "scanned",
    "image_based",
    "unknown",
]
InspectionStatus: TypeAlias = Literal["pending", "completed", "failed"]
JobStatus: TypeAlias = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]
JobStage: TypeAlias = Literal[
    "queued",
    "preparing",
    "parsing",
    "storing",
    "completed",
    "failed",
    "cancelled",
]
ArtifactKind: TypeAlias = Literal[
    "primary_document",
    "embedded_image",
    "structured_data",
    "manifest",
]


@dataclass(frozen=True, slots=True)
class ParserDescriptor:
    parser_id: str
    display_name: str
    version: str | None
    supported_formats: frozenset[str]
    supported_classifications: frozenset[str]
    available: bool
    reason: str
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class SourceDocument:
    document_id: str
    source_path: Path
    original_filename: str
    media_type: str
    document_format: str


@dataclass(frozen=True, slots=True)
class InspectionResult:
    inspector_id: str
    inspector_name: str
    inspector_version: str | None
    status: InspectionStatus
    detected_format: str
    classification: PdfClassification
    summary: dict[str, JsonValue] = field(default_factory=dict)
    details: dict[str, JsonValue] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    artifact_kind: ArtifactKind
    format: str
    media_type: str
    relative_path: str
    schema_name: str | None = None
    schema_version: str | None = None
    locator: dict[str, JsonValue] | None = None
    metadata: dict[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    artifacts: tuple[ArtifactSpec, ...]
    primary_relative_path: str | None = None


@dataclass(frozen=True, slots=True)
class ParseRequest:
    source: SourceDocument
    inspection: InspectionResult
    parser_id: str
    output_dir: Path
    options: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    stage: JobStage
    percentage: int
    message: str | None = None


@dataclass(frozen=True, slots=True)
class JobProgress:
    stage: JobStage
    percentage: int
    status_version: int


class DocumentDomainError(Exception):
    """Base exception whose stable code and safe message may cross the API."""

    default_code = "document_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.safe_message = message


class UnsupportedMediaTypeError(DocumentDomainError):
    default_code = "unsupported_media_type"


class FileTooLargeError(DocumentDomainError):
    default_code = "file_too_large"


class InspectionFailedError(DocumentDomainError):
    default_code = "inspection_failed"


class ParserUnavailableError(DocumentDomainError):
    default_code = "parser_unavailable"


class ParserIncompatibleError(DocumentDomainError):
    default_code = "parser_incompatible"


class ParseTimeoutError(DocumentDomainError):
    default_code = "parse_timeout"


class InvalidParserOutputError(DocumentDomainError):
    default_code = "invalid_parser_output"


class DocumentStorageError(DocumentDomainError):
    default_code = "storage_failed"


_STAGE_ORDER: dict[JobStage, int] = {
    "queued": 0,
    "preparing": 1,
    "parsing": 2,
    "storing": 3,
    "completed": 4,
    "failed": 4,
    "cancelled": 4,
}
_TERMINAL_STAGES: frozenset[JobStage] = frozenset(
    {"completed", "failed", "cancelled"}
)


def validate_progress_transition(
    previous: JobProgress,
    *,
    stage: JobStage,
    percentage: int,
    status_version: int,
) -> JobProgress:
    """Validate and construct one monotonic, versioned progress snapshot."""
    if not 0 <= percentage <= 100:
        raise ValueError("percentage must be between 0 and 100")
    if status_version <= previous.status_version:
        raise ValueError("status_version must increase")
    if previous.stage in _TERMINAL_STAGES:
        raise ValueError("stage cannot change after a terminal stage")
    if _STAGE_ORDER[stage] < _STAGE_ORDER[previous.stage]:
        raise ValueError("stage cannot move backwards")
    if percentage < previous.percentage:
        raise ValueError("percentage cannot move backwards")

    return JobProgress(
        stage=stage,
        percentage=percentage,
        status_version=status_version,
    )


def is_safe_artifact_path(bundle_root: Path, relative_path: str) -> bool:
    """Return whether a POSIX bundle path resolves below the bundle root."""
    if not relative_path or "\\" in relative_path:
        return False

    path = PurePosixPath(relative_path)
    if path.is_absolute() or path == PurePosixPath("."):
        return False
    if any(part in {"", ".", ".."} for part in path.parts):
        return False

    root = bundle_root.resolve()
    candidate = root.joinpath(*path.parts).resolve(strict=False)
    return candidate != root and candidate.is_relative_to(root)
