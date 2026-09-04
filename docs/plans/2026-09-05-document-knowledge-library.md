# Document Knowledge Library Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a user-private `知识库` at `/documents` where a user uploads a PDF, reviews its inspection and recommended methods, explicitly starts a parser, follows durable progress, and receives Markdown plus extensible artifacts in S3-compatible storage.

**Architecture:** Add a self-contained document domain to the FastAPI modular monolith. PostgreSQL owns Documents, Datasets, tags, inspections, parse jobs, leases, and artifact metadata; MinIO/S3 owns source and derived objects; provider registries isolate `pdf-inspector`, AnyDoc, the shared legacy PDF text extractor, and future OCR/hosted parsers. The React route calls only stable REST/SSE contracts and never imports parser-specific routing logic.

**Tech Stack:** Python 3.13, FastAPI, async psycopg, Alembic raw SQL, PostgreSQL, Redis pub/sub hints, boto3-compatible MinIO/S3, `pdf-inspector==1.17.0`, `firecrawl-anydoc==0.2.4`, `pdfplumber`, `pypdf`, React 19, TypeScript, React Query, Vitest, Playwright.

---

Implementation notes:

- Work only in `/Users/seanlee/.config/superpowers/worktrees/langalpha/wechat-ilink-bot` on `feature/wechat-ilink-bot`.
- Apply @superpowers:test-driven-development to every behavior change and @superpowers:verification-before-completion before each completion claim.
- After every substantial verified task, update `CHANGELOG.md` in Chinese and create the listed atomic commit. Do not combine unrelated tasks.
- Keep the generic document domain independent of education, workspace, PTC, Flash, Skills, and MCP modules. Routes may reuse the existing student-access guard.
- `scanned`, `image_based`, and `mixed` are inspection classifications. `ocr-document` is a future parser descriptor, not a classification and not an implemented OCR engine.

### Task 1: Pin native packages and expose typed runtime limits

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/config/env.py`
- Modify: `src/config/settings.py`
- Create: `tests/unit/config/test_document_parsing_config.py`
- Modify: `CHANGELOG.md`

**Step 1: Write the failing configuration tests**

Add tests that reload `src.config.env` and `src.config.settings` under controlled environment values and assert:

```python
def test_document_parsing_defaults(monkeypatch):
    monkeypatch.delenv("DOCUMENT_MAX_UPLOAD_BYTES", raising=False)
    monkeypatch.delenv("DOCUMENT_SYNC_WAIT_SECONDS", raising=False)
    monkeypatch.delenv("DOCUMENT_PARSE_TIMEOUT_SECONDS", raising=False)
    config = reload_document_config()
    assert config.max_upload_bytes == 52_428_800
    assert config.sync_wait_seconds == 30
    assert config.parse_timeout_seconds == 600


def test_document_parsing_config_rejects_non_positive_values(monkeypatch):
    monkeypatch.setenv("DOCUMENT_MAX_UPLOAD_BYTES", "0")
    with pytest.raises(ValueError, match="DOCUMENT_MAX_UPLOAD_BYTES"):
        reload_document_config()
```

The helper must restore both modules after each test so import-time environment constants do not leak across the suite.

**Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/unit/config/test_document_parsing_config.py -q`

Expected: FAIL because `DocumentParsingConfig` and its accessor do not exist.

**Step 3: Add the minimal typed configuration and dependencies**

Pin these exact main dependencies and refresh the lock:

```toml
"pdf-inspector==1.17.0",
"firecrawl-anydoc==0.2.4",
```

Add validated integer constants to `src/config/env.py`, then expose one immutable typed object from `src/config/settings.py`:

```python
@dataclass(frozen=True, slots=True)
class DocumentParsingConfig:
    max_upload_bytes: int
    sync_wait_seconds: int
    parse_timeout_seconds: int


def get_document_parsing_config() -> DocumentParsingConfig:
    return DocumentParsingConfig(
        max_upload_bytes=env.DOCUMENT_MAX_UPLOAD_BYTES,
        sync_wait_seconds=env.DOCUMENT_SYNC_WAIT_SECONDS,
        parse_timeout_seconds=env.DOCUMENT_PARSE_TIMEOUT_SECONDS,
    )
```

Business modules added later must call this accessor and must not read the environment directly. Run `uv lock` after editing `pyproject.toml`.

**Step 4: Verify imports and tests**

Run: `uv sync --extra test && uv run pytest tests/unit/config/test_document_parsing_config.py -q`

Expected: PASS, and both native packages install on the current Python 3.13 platform without a Rust build.

**Step 5: Update changelog and commit**

Add a Chinese `知识库文档解析基础` bullet describing the pinned packages and configured limits.

```bash
git add pyproject.toml uv.lock src/config/env.py src/config/settings.py tests/unit/config/test_document_parsing_config.py CHANGELOG.md
git commit -m "build: add document parsing dependencies"
```

### Task 2: Define compact IDs and format-neutral domain contracts

**Files:**

- Create: `src/server/documents/__init__.py`
- Create: `src/server/documents/ids.py`
- Create: `src/server/documents/contracts.py`
- Create: `tests/unit/server/documents/test_ids.py`
- Create: `tests/unit/server/documents/test_contracts.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing ID and contract tests**

Cover each public prefix, Base62 shape, collision retry, invalid prefix rejection, artifact path validation, and progress monotonicity:

```python
@pytest.mark.parametrize("kind,prefix", [
    ("dataset", "dts"), ("document", "doc"), ("inspection", "ins"),
    ("job", "job"), ("artifact", "art"), ("tag", "tag"),
])
def test_new_public_id_has_typed_base62_shape(kind, prefix):
    value = new_public_id(kind)
    assert re.fullmatch(rf"{prefix}-[0-9A-Za-z]{{12}}", value)


def test_progress_rejects_regression():
    previous = JobProgress(stage="parsing", percentage=60, status_version=4)
    with pytest.raises(ValueError):
        validate_progress_transition(previous, stage="parsing", percentage=59)


@pytest.mark.parametrize("path", ["/tmp/a.md", "../a.md", "images/../../a", "link.md"])
def test_artifact_relative_path_must_stay_in_bundle(path, tmp_path):
    assert not is_safe_artifact_path(tmp_path, path)
```

For the symlink case, create `tmp_path / "link.md"` pointing outside the bundle before calling the validator.

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/documents/test_ids.py tests/unit/server/documents/test_contracts.py -q`

Expected: FAIL because the document domain does not exist.

**Step 3: Implement the contracts**

Use `secrets.choice` over ASCII Base62 and retry only when the caller-provided uniqueness callback reports a collision. Define enums/dataclasses for:

```python
PdfClassification = Literal["text_based", "mixed", "scanned", "image_based", "unknown"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
JobStage = Literal["queued", "preparing", "parsing", "storing", "completed", "failed", "cancelled"]
ArtifactKind = Literal["primary_document", "embedded_image", "structured_data", "manifest"]

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
class ArtifactSpec:
    artifact_kind: ArtifactKind
    format: str
    media_type: str
    relative_path: str
    schema_name: str | None = None
    schema_version: str | None = None
    locator: dict[str, object] | None = None
    metadata: dict[str, object] | None = None
```

Also define `SourceDocument`, `InspectionResult`, `ParseRequest`, `ArtifactBundle`, `ProgressUpdate`, and stable domain exceptions carrying public error codes. Do not add artifact size, artifact hash, edit revision, workspace ID, or education ID.

**Step 4: Run focused tests**

Run: `uv run pytest tests/unit/server/documents/test_ids.py tests/unit/server/documents/test_contracts.py -q`

Expected: PASS.

**Step 5: Update changelog and commit**

```bash
git add src/server/documents tests/unit/server/documents CHANGELOG.md
git commit -m "feat: define document domain contracts"
```

### Task 3: Add the document-library PostgreSQL schema

**Files:**

- Create: `migrations/versions/045_add_document_library.py`
- Create: `tests/unit/migrations/test_document_library_migration.py`
- Create: `tests/integration/test_document_library_schema_db.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing migration tests**

The unit test loads revision `045` with `runpy` and asserts `down_revision == "044"`. The PostgreSQL integration test upgrades to head and verifies:

- `document_datasets`, `documents`, `document_dataset_items`, `document_tags`, `document_tag_assignments`, `document_inspections`, `document_parse_jobs`, and `document_artifacts` exist.
- IDs are `VARCHAR(16)` primary keys with prefix/length checks.
- `documents`, `document_datasets`, and `document_tags` carry `owner_user_id`; dependent inspections, jobs, and artifacts authorize through their Document, and membership writes cannot cross owners.
- a Document accepts multiple jobs with the same parser ID.
- `document_artifacts` includes format/media/schema/locator/metadata fields and excludes size/hash/revision fields.
- job status, stage, percentage, status version, lease, attempts, cancellation, parser snapshot, and primary artifact columns exist.
- expected owner/filter/claim indexes exist.

**Step 2: Run the migration tests and verify failure**

Run: `uv run pytest tests/unit/migrations/test_document_library_migration.py -q`

Expected: FAIL because revision `045` is absent.

**Step 3: Implement revision 045 with raw SQL**

Use `op.execute()` only. Add explicit checks such as:

```sql
CHECK (document_id ~ '^doc-[0-9A-Za-z]{12}$'),
CHECK (source_size_bytes >= 0),
CHECK (percentage BETWEEN 0 AND 100),
CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
CHECK (artifact_kind IN ('primary_document', 'embedded_image', 'structured_data', 'manifest'))
```

Keep Datasets flat and model Dataset membership and tags as many-to-many joins. Add `ON DELETE CASCADE` only for metadata rows and join rows; object deletion remains service-managed. Downgrade tables in reverse dependency order.

**Step 4: Run unit and real-PostgreSQL migration tests**

Run: `uv run pytest tests/unit/migrations/test_document_library_migration.py -q`

Run: `uv run pytest tests/integration/test_document_library_schema_db.py -q`

Expected: PASS against a project-scoped temporary PostgreSQL instance, including upgrade to head and downgrade of revision `045` back to `044`.

**Step 5: Update changelog and commit**

```bash
git add migrations/versions/045_add_document_library.py tests/unit/migrations/test_document_library_migration.py tests/integration/test_document_library_schema_db.py CHANGELOG.md
git commit -m "feat: add document library schema"
```

### Task 4: Add bounded streaming object-store operations

**Files:**

- Modify: `src/utils/storage/s3_compatible.py`
- Create: `src/server/documents/storage.py`
- Modify: `tests/unit/utils/storage/test_s3_compatible.py`
- Create: `tests/unit/server/documents/test_storage.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing streaming tests**

Use fake boto3 bodies/files and assert:

```python
def test_download_to_file_stops_before_limit_is_exceeded(...): ...
def test_upload_file_accepts_an_explicit_cap_larger_than_global_default(...): ...
def test_document_store_rejects_keys_outside_documents_prefix(...): ...
def test_document_store_deletes_only_the_exact_supplied_key(...): ...
def test_signed_download_uses_private_bucket_and_short_ttl(...): ...
```

Also assert downloads stream in chunks rather than calling `Body.read()` without a size.

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/utils/storage/test_s3_compatible.py tests/unit/server/documents/test_storage.py -q`

Expected: FAIL because explicit caps and file streaming are unavailable.

**Step 3: Implement storage primitives and the domain adapter**

Extend the shared module without changing existing callers:

```python
def upload_file(
    key: str,
    file_path: str,
    content_type: str | None = None,
    *,
    max_bytes: int | None = None,
) -> bool: ...

def download_to_file(key: str, destination: Path, *, max_bytes: int) -> int: ...

def create_presigned_download_url(
    key: str, *, expires_seconds: int, download_name: str
) -> str: ...
```

Implement `DocumentObjectStore` as a protocol and `S3CompatibleDocumentStore` as its first adapter. It must validate `documents/{doc-id}/...`, support put/get/exact delete/signed URL, use the Document parsing upload cap, and never expose bucket credentials or endpoint details.

**Step 4: Run tests**

Run: `uv run pytest tests/unit/utils/storage/test_s3_compatible.py tests/unit/server/documents/test_storage.py -q`

Expected: PASS and all pre-existing storage tests remain green.

**Step 5: Update changelog and commit**

```bash
git add src/utils/storage/s3_compatible.py src/server/documents/storage.py tests/unit/utils/storage/test_s3_compatible.py tests/unit/server/documents/test_storage.py CHANGELOG.md
git commit -m "feat: stream document objects with bounded storage"
```

### Task 5: Implement ownership-safe Dataset, tag, and Document queries

**Files:**

- Create: `src/server/database/documents.py`
- Create: `tests/unit/server/database/test_documents.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing SQL contract tests**

Use the repository's fake async cursor/pool patterns and test:

```python
async def test_document_lookup_always_scopes_owner(...): ...
async def test_dataset_membership_rejects_cross_owner_document(...): ...
async def test_list_documents_combines_dataset_tags_classification_and_status(...): ...
async def test_list_documents_returns_total_before_limit_offset(...): ...
async def test_same_document_can_have_multiple_datasets_and_tags(...): ...
async def test_tag_normalized_name_is_unique_per_owner(...): ...
```

Inspect bound parameters, not just returned rows, so an omitted owner predicate cannot pass accidentally.

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/database/test_documents.py -q`

Expected: FAIL because the repository module is absent.

**Step 3: Implement async psycopg repository functions**

Add explicit functions for Dataset CRUD/list/count, tag CRUD/list, Document create/get/update/delete/list, membership replacement, inspection create/get/list, artifact list/get, and parse-job history. `list_documents` accepts one immutable filter object containing `query`, `dataset_id`, tag IDs, media type, classification, parse status, `limit`, and `offset`.

Use CTEs or `EXISTS` predicates so multi-tag and multi-Dataset joins do not duplicate rows or inflate `total`. Require `owner_user_id` in every public repository function; never authorize from compact ID shape.

**Step 4: Run focused repository tests**

Run: `uv run pytest tests/unit/server/database/test_documents.py -q`

Expected: PASS.

**Step 5: Update changelog and commit**

```bash
git add src/server/database/documents.py tests/unit/server/database/test_documents.py CHANGELOG.md
git commit -m "feat: add document library persistence"
```

### Task 6: Build upload and library services with exact-key compensation

**Files:**

- Create: `src/server/documents/library.py`
- Create: `tests/unit/server/documents/test_library.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing service tests**

Drive the service with an async chunk iterator, fake repository, and fake object store:

```python
async def test_upload_streams_to_temp_file_hashes_and_persists_pdf(...): ...
async def test_upload_rejects_declared_length_over_limit_before_reading(...): ...
async def test_upload_rejects_stream_that_crosses_limit(...): ...
async def test_upload_rejects_non_pdf_signature_and_media_type(...): ...
async def test_database_failure_deletes_only_the_new_source_key(...): ...
async def test_dataset_and_tags_are_attached_after_owner_validation(...): ...
async def test_delete_removes_only_keys_loaded_from_owned_rows(...): ...
```

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/documents/test_library.py -q`

Expected: FAIL because `DocumentLibraryService` is absent.

**Step 3: Implement the minimal service**

The upload algorithm must:

1. allocate `doc-...` and a mode-restricted temporary file;
2. reject anything except PDF for v1 using declared media type, normalized filename, and `%PDF-` signature;
3. stream once while enforcing `get_document_parsing_config().max_upload_bytes` and computing SHA-256;
4. upload to `documents/{document_id}/source` with a private content type;
5. insert source metadata and validated Dataset/tag relationships;
6. delete that exact source key if database publication fails; and
7. always remove the local temporary file.

Document source size/hash live only on the Document. Keep `create_dataset`, `list_datasets`, `list_documents`, tag mutation, metadata patch, and owned delete behind this service rather than routes calling SQL/storage directly.

**Step 4: Run service tests**

Run: `uv run pytest tests/unit/server/documents/test_library.py -q`

Expected: PASS.

**Step 5: Update changelog and commit**

```bash
git add src/server/documents/library.py tests/unit/server/documents/test_library.py CHANGELOG.md
git commit -m "feat: add document upload service"
```

### Task 7: Register inspectors and isolate `pdf-inspector`

**Files:**

- Create: `src/server/documents/providers/__init__.py`
- Create: `src/server/documents/providers/base.py`
- Create: `src/server/documents/providers/registry.py`
- Create: `src/server/documents/providers/pdf_inspector.py`
- Create: `src/server/documents/process_runner.py`
- Create: `tests/unit/server/documents/providers/test_registry.py`
- Create: `tests/unit/server/documents/providers/test_pdf_inspector.py`
- Create: `tests/fixtures/documents/text.pdf`
- Create: `tests/fixtures/documents/scanned.pdf`
- Create: `tests/fixtures/documents/image-based.pdf`
- Create: `tests/fixtures/documents/mixed.pdf`
- Modify: `CHANGELOG.md`

**Step 1: Write failing provider and isolation tests**

Generate and commit only small deterministic, non-sensitive fixtures. Assert:

```python
def test_registry_resolves_inspector_by_format(): ...
def test_pdf_inspector_maps_upstream_fields_to_generic_result(): ...
def test_pdf_inspector_preserves_page_count_dimensions_and_ocr_pages(): ...
def test_pdf_inspector_reports_safe_error_when_child_crashes(): ...
def test_process_runner_terminates_child_at_deadline(): ...
```

Add a real binding contract test, marked `integration`, that runs `detect_pdf(path)` against all four fixtures and asserts the expected normalized classifications. Do not mock the upstream package in that test.

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/documents/providers/test_registry.py tests/unit/server/documents/providers/test_pdf_inspector.py -q`

Expected: FAIL because providers and the runner are absent.

**Step 3: Implement the inspector boundary**

Define protocols:

```python
class DocumentInspector(Protocol):
    descriptor: InspectorDescriptor
    def inspect(self, source_path: Path) -> InspectionResult: ...


class IsolatedProcessRunner(Protocol):
    async def run(
        self,
        target: Callable[..., object],
        args: tuple[object, ...],
        *,
        timeout_seconds: int,
    ) -> object: ...
```

Use multiprocessing's `spawn` context, a bounded result channel, deadline termination, and explicit child join. `PdfInspectorDetector` lazily imports `pdf_inspector.detect_pdf`, normalizes upstream values to `text_based|mixed|scanned|image_based|unknown`, puts page count/page dimensions in `summary`, and pages-needing-OCR/confidence/raw supported fields in `details`. Convert exceptions to `inspection_failed` without paths or upstream stack traces.

**Step 4: Run unit and binding tests**

Run: `uv run pytest tests/unit/server/documents/providers/test_registry.py tests/unit/server/documents/providers/test_pdf_inspector.py -q`

Run: `uv run pytest tests/unit/server/documents/providers/test_pdf_inspector.py -m integration -q`

Expected: PASS; the real fixtures map consistently on the pinned version.

**Step 5: Update changelog and commit**

```bash
git add src/server/documents/providers src/server/documents/process_runner.py tests/unit/server/documents/providers tests/fixtures/documents CHANGELOG.md
git commit -m "feat: inspect PDF document classifications"
```

### Task 8: Extract one shared legacy PDF text implementation

**Files:**

- Create: `src/utils/pdf_text.py`
- Modify: `src/ptc_agent/agent/memo/pdf.py`
- Modify: `src/tools/web/inhouse/extractors/pdf.py`
- Create: `tests/unit/utils/test_pdf_text.py`
- Modify: existing focused memo and web extractor tests discovered with `rg -n "pdfplumber|pypdf" tests/unit`
- Modify: `CHANGELOG.md`

**Step 1: Write failing shared-extractor tests**

Preserve current behavior while making it reusable:

```python
def test_pdfplumber_is_primary_and_pypdf_is_fallback(...): ...
def test_each_page_has_stable_markdown_heading(...): ...
def test_empty_text_layer_returns_no_usable_text(...): ...
def test_page_cap_is_checked_by_both_backends(...): ...
```

Add regression assertions that memo and web extraction delegate to the shared module and retain their existing public errors/results.

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/utils/test_pdf_text.py -q`

Expected: FAIL because `src.utils.pdf_text` does not exist.

**Step 3: Move the pure synchronous core**

Expose a dependency-free contract from the shared utility:

```python
@dataclass(frozen=True, slots=True)
class PdfTextResult:
    markdown: str
    backend: Literal["pdfplumber", "pypdf"]
    extracted_pages: tuple[int, ...]
    total_pages: int


def extract_pdf_text(path_or_bytes: Path | bytes, *, max_pages: int | None) -> PdfTextResult: ...
```

Keep timeouts, concurrency limits, HTTP concerns, and document-domain exceptions in their callers. Remove duplicate extraction loops from the memo and web implementations only after parity tests pass.

**Step 4: Run all affected tests**

Run: `uv run pytest tests/unit/utils/test_pdf_text.py tests/unit/ptc_agent tests/unit/tools -q`

Expected: PASS with no change to current memo/web behavior.

**Step 5: Update changelog and commit**

```bash
git add src/utils/pdf_text.py src/ptc_agent/agent/memo/pdf.py src/tools/web/inhouse/extractors/pdf.py tests/unit/utils/test_pdf_text.py tests/unit/ptc_agent tests/unit/tools CHANGELOG.md
git commit -m "refactor: share legacy PDF text extraction"
```

### Task 9: Implement AnyDoc, legacy, and future OCR parser descriptors

**Files:**

- Create: `src/server/documents/providers/anydoc.py`
- Create: `src/server/documents/providers/legacy_pdf.py`
- Modify: `src/server/documents/providers/registry.py`
- Create: `tests/unit/server/documents/providers/test_anydoc.py`
- Create: `tests/unit/server/documents/providers/test_legacy_pdf.py`
- Create: `tests/unit/server/documents/providers/test_recommendations.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing routing and provider tests**

Encode the approved matrix exactly:

| Classification | Recommended available parser | Other visible choice |
|---|---|---|
| `text_based` | `anydoc-local` | `legacy-pdf-text` |
| `mixed` | `legacy-pdf-text` | unavailable `ocr-document` |
| `scanned` | `legacy-pdf-text` with quality warning | unavailable `ocr-document` |
| `image_based` | `legacy-pdf-text` with quality warning | unavailable `ocr-document` |
| `unknown` | `legacy-pdf-text` with warning | unavailable `ocr-document` |

Add these specific assertions:

```python
def test_anydoc_rejects_mixed_before_execution(): ...
def test_anydoc_maps_needs_ocr_to_parser_incompatible(): ...
def test_legacy_parser_can_return_empty_markdown_with_warning_for_scan(): ...
def test_ocr_document_is_visible_but_cannot_create_a_job(): ...
def test_every_option_has_one_sentence_reason_and_availability(): ...
```

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/documents/providers/test_anydoc.py tests/unit/server/documents/providers/test_legacy_pdf.py tests/unit/server/documents/providers/test_recommendations.py -q`

Expected: FAIL because parser providers and the recommendation resolver are absent.

**Step 3: Implement providers and recommendation policy**

`AnydocExtractor` lazily calls `anydoc.to_markdown(source_path)` and publishes `document.md`; catch the package's `NeedsOcr` and expose `parser_incompatible`. `LegacyPdfExtractor` calls `extract_pdf_text`, publishes Markdown even when the result is partial/empty, and includes a quality warning in artifact metadata/job result.

Register `ocr-document` as `available=False` with reason `OCR parser is not configured yet`; do not add placeholder execution code. Keep all classification routing inside the registry/recommendation policy so API and React code render descriptors returned by the server.

**Step 4: Run unit and real provider tests**

Run: `uv run pytest tests/unit/server/documents/providers -q`

Run: `uv run pytest tests/unit/server/documents/providers/test_anydoc.py -m integration -q`

Expected: PASS. AnyDoc succeeds on `text.pdf` and refuses mixed/scanned/image fixtures without producing partial Markdown.

**Step 5: Update changelog and commit**

```bash
git add src/server/documents/providers tests/unit/server/documents/providers CHANGELOG.md
git commit -m "feat: add document parser providers"
```

### Task 10: Persist and orchestrate repeatable inspections

**Files:**

- Create: `src/server/documents/inspection.py`
- Modify: `src/server/database/documents.py`
- Create: `tests/unit/server/documents/test_inspection.py`
- Modify: `tests/unit/server/database/test_documents.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing orchestration tests**

```python
async def test_inspection_downloads_owned_source_to_job_temp_dir(...): ...
async def test_every_retry_creates_a_new_inspection_row(...): ...
async def test_success_persists_generic_summary_and_pdf_details(...): ...
async def test_failure_keeps_document_and_records_safe_error(...): ...
async def test_parse_options_are_derived_from_selected_inspection(...): ...
```

Assert temp files disappear on success, provider error, and timeout.

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/documents/test_inspection.py tests/unit/server/database/test_documents.py -q`

Expected: FAIL because inspection orchestration is missing.

**Step 3: Implement inspection service and SQL**

`DocumentInspectionService.inspect(owner_user_id, document_id)` must authorize the Document, create `ins-...`, stream its source into a private temporary directory, call the registered inspector through the bounded process runner, persist success or a stable failure code, and return saved data plus parser descriptors.

Do not auto-create a parse job. A failed inspection remains retryable and does not delete the source. Permit a caller to request parse options for a specific owned inspection, defaulting to the latest successful inspection only when explicitly omitted.

**Step 4: Run focused tests**

Run: `uv run pytest tests/unit/server/documents/test_inspection.py tests/unit/server/database/test_documents.py -q`

Expected: PASS.

**Step 5: Update changelog and commit**

```bash
git add src/server/documents/inspection.py src/server/database/documents.py tests/unit/server/documents/test_inspection.py tests/unit/server/database/test_documents.py CHANGELOG.md
git commit -m "feat: orchestrate PDF document inspection"
```

### Task 11: Add durable parse-job claim and transition SQL

**Files:**

- Create: `src/server/database/document_jobs.py`
- Create: `tests/unit/server/database/test_document_jobs.py`
- Create: `tests/integration/test_document_job_claims_db.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing state-machine tests**

Cover:

```python
async def test_create_job_always_inserts_even_for_same_document_and_parser(...): ...
async def test_two_workers_cannot_claim_the_same_job(...): ...
async def test_expired_lease_is_recoverable_and_increments_attempt(...): ...
async def test_wrong_claimant_cannot_update_progress_or_complete(...): ...
async def test_progress_and_status_version_never_move_backwards(...): ...
async def test_cancel_terminal_job_is_idempotent(...): ...
async def test_publish_artifacts_and_completion_is_one_transaction(...): ...
```

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/database/test_document_jobs.py -q`

Expected: FAIL because parse-job persistence is absent.

**Step 3: Implement guarded SQL operations**

Use `FOR UPDATE SKIP LOCKED` to claim one queued or expired-running row. Every mutation must bind `job_id`, `claimed_by`, current attempt, and expected status version. Lease renewal may only extend a live claim. Completion inserts artifact rows and updates `primary_artifact_id` in one transaction.

Keep public operations explicit: `create_job`, `get_owned_job`, `claim_next_job`, `renew_lease`, `update_progress`, `request_cancel`, `publish_artifacts`, `fail_job`, and `recover_expired_jobs`. Do not use process-local queues as truth.

**Step 4: Run unit and PostgreSQL concurrency tests**

Run: `uv run pytest tests/unit/server/database/test_document_jobs.py -q`

Run: `uv run pytest tests/integration/test_document_job_claims_db.py -q`

Expected: PASS, including two real database connections racing for one job and recovery after forced lease expiry.

**Step 5: Update changelog and commit**

```bash
git add src/server/database/document_jobs.py tests/unit/server/database/test_document_jobs.py tests/integration/test_document_job_claims_db.py CHANGELOG.md
git commit -m "feat: persist durable document parse jobs"
```

### Task 12: Execute parse jobs and publish artifact bundles

**Files:**

- Create: `src/server/documents/executor.py`
- Create: `src/server/services/document_job_worker.py`
- Create: `tests/unit/server/documents/test_executor.py`
- Create: `tests/unit/server/services/test_document_job_worker.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing executor tests**

```python
async def test_executor_runs_preparing_parsing_storing_completed_stages(...): ...
async def test_executor_rejects_absolute_parent_and_symlink_outputs(...): ...
async def test_executor_uploads_each_artifact_under_unique_job_prefix(...): ...
async def test_partial_upload_failure_deletes_only_uploaded_job_keys(...): ...
async def test_parser_timeout_terminates_child_and_fails_job(...): ...
async def test_cancel_between_stages_never_publishes_artifacts(...): ...
async def test_worker_renews_lease_until_terminal(...): ...
async def test_worker_restart_recovers_expired_claim(...): ...
```

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/documents/test_executor.py tests/unit/server/services/test_document_job_worker.py -q`

Expected: FAIL because the executor and worker are absent.

**Step 3: Implement executor and per-worker claimant**

The executor must create a private per-job temporary directory, stream the source into it, invoke only the parser selected on the job, enforce `parse_timeout_seconds`, validate a bounded manifest and every output path, upload to `documents/{document_id}/artifacts/{job_id}/...`, then transactionally publish artifact rows.

The worker starts once per FastAPI process but claims work through PostgreSQL. Give each process a unique claimant ID, use a bounded concurrency semaphore, renew leases, inspect durable cancellation between stages, and clean exact uploaded keys on failed publication. A child crash or malformed output fails one job with a stable public error.

**Step 4: Run executor and worker tests**

Run: `uv run pytest tests/unit/server/documents/test_executor.py tests/unit/server/services/test_document_job_worker.py -q`

Expected: PASS with no orphan child process in timeout/cancellation tests.

**Step 5: Update changelog and commit**

```bash
git add src/server/documents/executor.py src/server/services/document_job_worker.py tests/unit/server/documents/test_executor.py tests/unit/server/services/test_document_job_worker.py CHANGELOG.md
git commit -m "feat: execute document parse jobs"
```

### Task 13: Add Redis wake hints, SSE snapshots, and bounded sync waiting

**Files:**

- Create: `src/server/services/document_job_events.py`
- Create: `tests/unit/server/services/test_document_job_events.py`
- Modify: `src/server/documents/executor.py`
- Modify: `tests/unit/server/documents/test_executor.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing event delivery tests**

Reuse the shared Redis subscription helper and assert:

```python
async def test_sse_emits_database_snapshot_before_subscribing(...): ...
async def test_redis_hint_causes_database_reread_not_payload_trust(...): ...
async def test_sse_poll_fallback_observes_update_when_hint_is_lost(...): ...
async def test_sync_wait_returns_completed_snapshot_inside_deadline(...): ...
async def test_sync_wait_returns_pending_after_30_seconds_without_cancelling(...): ...
async def test_disconnect_does_not_cancel_durable_job(...): ...
```

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/services/test_document_job_events.py tests/unit/server/documents/test_executor.py -q`

Expected: FAIL because document job event coordination is absent.

**Step 3: Implement DB-authoritative notifications**

Publish only a compact wake hint such as `{"job_id": "job-...", "status_version": 3}`. Use `subscribe_to_channel` from `src/server/services/workspace_status_pubsub.py`; do not create another Redis pool. On connection, read and emit the owned PostgreSQL snapshot immediately. On hint or paced timer, reread the database and emit only a newer version. End after one terminal snapshot.

Implement `wait_for_terminal_job` using the same snapshots and `get_document_parsing_config().sync_wait_seconds`. Timeout returns the current non-terminal job for a `202` response and never changes or cancels it.

**Step 4: Run tests**

Run: `uv run pytest tests/unit/server/services/test_document_job_events.py tests/unit/server/documents/test_executor.py -q`

Expected: PASS even when Redis is unavailable or drops a hint.

**Step 5: Update changelog and commit**

```bash
git add src/server/services/document_job_events.py src/server/documents/executor.py tests/unit/server/services/test_document_job_events.py tests/unit/server/documents/test_executor.py CHANGELOG.md
git commit -m "feat: stream durable document job progress"
```

### Task 14: Expose authenticated REST, download, and SSE APIs

**Files:**

- Create: `src/server/models/documents.py`
- Create: `src/server/app/documents.py`
- Modify: `src/server/app/setup.py`
- Create: `tests/unit/server/app/test_documents_api.py`
- Modify: `tests/unit/server/app/test_generic_router_registration.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing API contract tests**

Cover every route and ownership boundary:

```text
POST   /api/v1/document-datasets
GET    /api/v1/document-datasets
GET    /api/v1/document-datasets/{dataset_id}
PATCH  /api/v1/document-datasets/{dataset_id}
DELETE /api/v1/document-datasets/{dataset_id}
GET    /api/v1/document-tags
POST   /api/v1/document-tags
DELETE /api/v1/document-tags/{tag_id}
POST   /api/v1/documents
GET    /api/v1/documents
GET    /api/v1/documents/{document_id}
PATCH  /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}
POST   /api/v1/documents/{document_id}/inspections
GET    /api/v1/documents/{document_id}/parse-options
POST   /api/v1/documents/{document_id}/parse-jobs
GET    /api/v1/documents/{document_id}/parse-jobs
GET    /api/v1/documents/{document_id}/artifacts
GET    /api/v1/document-jobs/{job_id}
GET    /api/v1/document-jobs/{job_id}/events
POST   /api/v1/document-jobs/{job_id}/cancel
GET    /api/v1/document-artifacts/{artifact_id}/download
```

Assert multipart upload, size error `413`, PDF validation `415/422`, server-side filters/pagination, same-user ownership, student `403`, unavailable/incompatible parser `409`, async `202`, sync-complete `200`, sync-fallback `202`, SSE content type, and authorized short-lived download redirects.

**Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/server/app/test_documents_api.py tests/unit/server/app/test_generic_router_registration.py -q`

Expected: FAIL because models/router/registration are absent.

**Step 3: Implement thin routes and Pydantic response models**

Routes must derive the caller from the existing authenticated user dependency, call `require_nonstudent_agent_features`, validate query limits, and delegate to document services. They must not import provider implementations or construct storage keys.

Use the repository's `limit`, `offset`, `total` response convention. Multipart upload accepts the file plus optional repeated `dataset_ids` and tags. `POST .../parse-jobs` accepts:

```python
class CreateParseJobRequest(BaseModel):
    inspection_id: str
    parser_id: str
    mode: Literal["sync", "async"] = "async"
    options: dict[str, JsonValue] = Field(default_factory=dict)
```

Register the router and start/stop `DocumentJobWorker` in the FastAPI lifespan with the same defensive cleanup pattern as other workers. Do not add document job state to chat SSE/checkpoints.

**Step 4: Run API and registration tests**

Run: `uv run pytest tests/unit/server/app/test_documents_api.py tests/unit/server/app/test_generic_router_registration.py tests/unit/server/app/test_tokenizer_startup.py -q`

Expected: PASS; existing lifecycle tests prove startup failure cleanup still works.

**Step 5: Update changelog and commit**

```bash
git add src/server/models/documents.py src/server/app/documents.py src/server/app/setup.py tests/unit/server/app/test_documents_api.py tests/unit/server/app/test_generic_router_registration.py CHANGELOG.md
git commit -m "feat: expose document library API"
```

### Task 15: Add frontend document API types and React Query keys

**Files:**

- Create: `web/src/pages/Documents/types.ts`
- Create: `web/src/pages/Documents/api.ts`
- Create: `web/src/pages/Documents/hooks.ts`
- Create: `web/src/pages/Documents/__tests__/api.test.ts`
- Modify: `web/src/lib/queryKeys.ts`
- Modify: `web/src/lib/__tests__/queryKeys.test.ts`
- Modify: `CHANGELOG.md`

**Step 1: Write failing API and cache-key tests**

Test multipart serialization, repeated Dataset/tag fields, list query parameters, 200/202 parse-job responses, cancellation, artifact download URL handling, and hierarchical invalidation:

```typescript
expect(queryKeys.documents.list({ offset: 0 })).toEqual([
  'documents', 'list', { offset: 0 },
]);
expect(queryKeys.documents.job('job-abc')).toEqual([
  'documents', 'jobs', 'job-abc',
]);
```

Ensure the types model generic artifact format/media/schema metadata rather than assuming every artifact is Markdown.

**Step 2: Run tests and verify failure**

Run: `cd web && pnpm test -- src/pages/Documents/__tests__/api.test.ts src/lib/__tests__/queryKeys.test.ts`

Expected: FAIL because the Documents client and key hierarchy are absent.

**Step 3: Implement the typed client and hooks**

Define `DocumentSummary`, `DatasetSummary`, `Tag`, `Inspection`, `ParserOption`, `ParseJob`, `Artifact`, `Paginated<T>`, and filter types. Add API functions for all routes used by the web experience and React Query hooks/mutations that invalidate the narrowest correct prefix after Dataset, tag, Document, inspection, job, and deletion changes.

The event-stream helper must reconnect with the last seen `status_version`, accept database snapshots only, and fall back to periodic job GET calls after repeated SSE errors.

**Step 4: Run frontend unit tests**

Run: `cd web && pnpm test -- src/pages/Documents/__tests__/api.test.ts src/lib/__tests__/queryKeys.test.ts`

Expected: PASS.

**Step 5: Update changelog and commit**

```bash
git add web/src/pages/Documents web/src/lib/queryKeys.ts web/src/lib/__tests__/queryKeys.test.ts CHANGELOG.md
git commit -m "feat: add document library web client"
```

### Task 16: Register `/documents`, navigation, translations, and the two-tab shell

**Files:**

- Create: `web/src/pages/Documents/DocumentsPage.tsx`
- Create: `web/src/pages/Documents/DocumentsPage.css`
- Create: `web/src/pages/Documents/__tests__/DocumentsPage.test.tsx`
- Modify: `web/src/components/Main/Main.tsx`
- Modify: `web/src/components/nav/navItems.ts`
- Modify: `web/src/components/Sidebar/AppSidebar.tsx`
- Modify: `web/src/components/Sidebar/__tests__/AppSidebar.navigation.test.ts`
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`
- Modify: `web/src/locales/__tests__/keys.test.ts`
- Modify: `CHANGELOG.md`

**Step 1: Write failing route and shell tests**

Assert:

```typescript
it('shows 知识库 in desktop and mobile navigation for an eligible user', ...);
it('hides the documents entry for a student account', ...);
it('lazy-loads /documents and preloads its chunk', ...);
it('opens with Dataset and All Documents tabs', ...);
it('preserves independent search and page state when switching tabs', ...);
```

**Step 2: Run tests and verify failure**

Run: `cd web && pnpm test -- src/pages/Documents/__tests__/DocumentsPage.test.tsx src/components/Sidebar/__tests__/AppSidebar.navigation.test.ts src/locales/__tests__/keys.test.ts`

Expected: FAIL because `/documents` and its navigation metadata are absent.

**Step 3: Implement the quiet workspace shell**

Add `routeChunks.documents`, a lazy route, and a `Library` or `Files` Lucide icon. Render `知识库` as a first-level work surface with compact title/actions and a proper tab control, not a marketing hero or nested cards. Filter NAV items from the authenticated user role so students cannot see the entry; the backend remains authoritative.

Use existing color tokens from `DESIGN.md`, radius no greater than 8px, stable toolbar dimensions, responsive overflow, and translated accessible labels. Dataset-tab state and all-documents-tab state must remain independent in the URL search parameters.

**Step 4: Run focused frontend tests**

Run: `cd web && pnpm test -- src/pages/Documents/__tests__/DocumentsPage.test.tsx src/components/Sidebar/__tests__/AppSidebar.navigation.test.ts src/locales/__tests__/keys.test.ts`

Expected: PASS.

**Step 5: Update changelog and commit**

```bash
git add web/src/pages/Documents web/src/components/Main/Main.tsx web/src/components/nav/navItems.ts web/src/components/Sidebar/AppSidebar.tsx web/src/components/Sidebar/__tests__/AppSidebar.navigation.test.ts web/src/locales CHANGELOG.md
git commit -m "feat: add knowledge library navigation"
```

### Task 17: Build Dataset cards and server-paginated document tables

**Files:**

- Create: `web/src/pages/Documents/components/DatasetGrid.tsx`
- Create: `web/src/pages/Documents/components/DatasetDialog.tsx`
- Create: `web/src/pages/Documents/components/DocumentTable.tsx`
- Create: `web/src/pages/Documents/components/DocumentFilters.tsx`
- Create: `web/src/pages/Documents/components/Pagination.tsx`
- Create: `web/src/pages/Documents/__tests__/DatasetGrid.test.tsx`
- Create: `web/src/pages/Documents/__tests__/DocumentTable.test.tsx`
- Modify: `web/src/pages/Documents/DocumentsPage.tsx`
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`
- Modify: `CHANGELOG.md`

**Step 1: Write failing interaction tests**

Cover Dataset create/search/open/rename/delete, scoped table loading, all-documents loading, filename debounce, Dataset/tag/format/classification/status filters, pagination, empty/loading/error states, row actions, and query parameter reset when filters change.

Use API mocks that fail if the client performs local filtering or requests an unbounded list. Assert Dataset cards show only name, description, document count, and updated time. Assert the all-documents table shows filename, Datasets, tags, format, source size, parse status, updated time, and actions.

**Step 2: Run tests and verify failure**

Run: `cd web && pnpm test -- src/pages/Documents/__tests__/DatasetGrid.test.tsx src/pages/Documents/__tests__/DocumentTable.test.tsx`

Expected: FAIL because collection views are absent.

**Step 3: Implement collection views**

Use cards only for repeated Datasets; Dataset detail and All Documents are unframed table work surfaces. Use menus for row action sets, icons for familiar actions, tooltips for icon-only actions, and a compact select/popover for option filters. Keep page size fixed and request `limit`/`offset` from the server.

Opening upload from a Dataset passes that Dataset as the preselected logical membership; it must not modify an object-storage path.

**Step 4: Run interaction tests**

Run: `cd web && pnpm test -- src/pages/Documents/__tests__/DatasetGrid.test.tsx src/pages/Documents/__tests__/DocumentTable.test.tsx`

Expected: PASS at desktop and narrow jsdom container widths without text overlap.

**Step 5: Update changelog and commit**

```bash
git add web/src/pages/Documents web/src/locales/en-US.json web/src/locales/zh-CN.json CHANGELOG.md
git commit -m "feat: browse document datasets and files"
```

### Task 18: Build the upload, inspection, method, progress, and result wizard

**Files:**

- Create: `web/src/pages/Documents/components/DocumentWizard.tsx`
- Create: `web/src/pages/Documents/components/steps/FileStep.tsx`
- Create: `web/src/pages/Documents/components/steps/InspectionStep.tsx`
- Create: `web/src/pages/Documents/components/steps/MethodStep.tsx`
- Create: `web/src/pages/Documents/components/steps/ProgressStep.tsx`
- Create: `web/src/pages/Documents/components/steps/ResultStep.tsx`
- Create: `web/src/pages/Documents/__tests__/DocumentWizard.test.tsx`
- Modify: `web/src/pages/Documents/DocumentsPage.tsx`
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`
- Modify: `CHANGELOG.md`

**Step 1: Write failing end-to-end component tests**

Test the exact decision boundary:

```typescript
it('uploads and inspects but does not start parsing', ...);
it('shows filename size page count dimensions classification and recommendation', ...);
it('requires an explicit available parser selection before starting', ...);
it('marks AnyDoc incompatible for mixed scanned and image-based PDFs', ...);
it('shows legacy quality warnings for scanned and image-based PDFs', ...);
it('shows OCR document as visible but unavailable', ...);
it('retries a failed inspection without reuploading', ...);
it('follows SSE and polling fallback to a terminal result', ...);
it('shows Markdown preview and every generic bundle artifact', ...);
it('starts another job without replacing prior job history', ...);
```

**Step 2: Run tests and verify failure**

Run: `cd web && pnpm test -- src/pages/Documents/__tests__/DocumentWizard.test.tsx`

Expected: FAIL because the wizard is absent.

**Step 3: Implement the five-stage wizard**

Follow `SetupWizard.tsx` for stepper spacing, transitions, responsive layout, and design tokens, while fitting inside the normal application shell. Stages are `File and classification`, `Inspection summary`, `Method`, `Progress`, and `Result`.

The summary is intentionally generic: filename, source size, page count, page dimensions, classification, and one short recommendation. Render parser option groups directly from server descriptors. Disable unavailable/incompatible methods with their shortest reason. Do not expose page-range controls or automatically click the recommended method.

Reuse `web/src/pages/ChatAgent/components/Markdown.tsx` for the primary Markdown preview. Also list image, JSON, manifest, and future formats using `artifact_kind`, `format`, and `media_type`, with per-artifact download controls and prior parse-job history.

**Step 4: Run wizard and surrounding tests**

Run: `cd web && pnpm test -- src/pages/Documents/__tests__`

Expected: PASS, including disconnect/reconnect, failure, cancel, and rerun states.

**Step 5: Update changelog and commit**

```bash
git add web/src/pages/Documents web/src/locales/en-US.json web/src/locales/zh-CN.json CHANGELOG.md
git commit -m "feat: add guided PDF parsing workflow"
```

### Task 19: Prove PostgreSQL, MinIO, and full API behavior

**Files:**

- Create: `tests/integration/test_document_storage_minio.py`
- Create: `tests/integration/test_document_library_api.py`
- Create: `scripts/smoke_document_library.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing integration tests and smoke assertions**

The MinIO test must generate a unique key root under `documents/test-{random}/`, upload one source and a Markdown/JSON/image/manifest bundle, download them, verify exact content, issue an authorized URL, and remove only keys it created in `finally`. It must never list or delete unrelated objects.

The API test must execute:

1. create Dataset and tags;
2. upload and inspect a text PDF;
3. verify no parse job exists before user choice;
4. choose AnyDoc asynchronously and follow to completion;
5. choose AnyDoc synchronously on another run and accept either `200` or durable `202`;
6. inspect mixed/scanned/image fixtures and verify legacy/OCR warnings;
7. run the legacy parser twice on one Document and preserve both jobs/artifacts;
8. filter/paginate both global and Dataset document lists; and
9. prove a second user and a student cannot read source, jobs, or artifacts.

**Step 2: Run tests and verify the initial failure**

Run: `uv run pytest tests/integration/test_document_storage_minio.py tests/integration/test_document_library_api.py -q`

Expected: FAIL until environment fixtures and the complete integrated behavior are wired.

**Step 3: Complete only integration wiring and add a repeatable smoke client**

Reuse repository integration fixtures for PostgreSQL/auth/application startup. Read MinIO connection values through existing storage configuration; never read or print `密码.md` from tests or scripts. The smoke script accepts server URL, auth input, and a fixture path through arguments/environment and prints only IDs, classifications, statuses, and artifact names.

The script must not delete user data. Test cleanup may delete only exact generated test keys/rows.

**Step 4: Run integration coverage**

Run: `uv run pytest tests/integration/test_document_storage_minio.py tests/integration/test_document_library_api.py -q`

Expected: PASS against project-scoped PostgreSQL and the configured MinIO S3 API at port `9000`, never console port `9001`.

**Step 5: Update changelog and commit**

```bash
git add tests/integration/test_document_storage_minio.py tests/integration/test_document_library_api.py scripts/smoke_document_library.py CHANGELOG.md
git commit -m "test: cover document library integration"
```

### Task 20: Run full verification and LAN visual QA

**Files:**

- Create: `web/e2e/documents.spec.js`
- Modify: `CHANGELOG.md`

**Step 1: Write the browser acceptance test**

Mock only deterministic API state for the browser suite and assert both tabs, Dataset navigation, upload/inspection gate, explicit method choice, progress reconnect, Markdown preview, generic artifact downloads, prior jobs, responsive table behavior, and hidden student navigation. Include desktop and mobile projects.

**Step 2: Run the browser test and fix only observed regressions**

Run: `cd web && pnpm test:e2e -- documents.spec.js`

Expected: PASS in desktop and mobile projects with no console errors, clipped controls, or incoherent overlap.

**Step 3: Run the complete static and unit verification set**

Run:

```bash
make lint
uv run pytest tests/unit -q
cd web && pnpm test && pnpm typecheck && pnpm build
```

Expected: every command exits `0`. Do not claim completion from focused tests alone.

**Step 4: Run real integration verification**

Run: `uv run pytest -m integration`

Expected: PASS, or document an existing unrelated environmental failure with its exact command and output before proceeding. Do not weaken or skip the new document integration tests.

**Step 5: Start services and verify the real workflow over LAN**

Inspect existing Docker names/ports before `make up`; do not remove unknown resources. Start the backend using the repository command and the frontend exactly as required:

```bash
uv run python server.py --reload
cd web && pnpm dev --host 0.0.0.0 --port 5177
```

Use the browser at both desktop and mobile viewports to upload each fixture, inspect it, confirm parsing does not start before selection, run the suggested available method, reconnect to progress, inspect Markdown/artifacts/history, and exercise filters/pagination. Verify the frontend is reachable at `http://<LAN-IP>:5177/documents` as well as localhost. Capture screenshots for QA but do not commit generated screenshots.

**Step 6: Request review and resolve findings**

Apply @superpowers:requesting-code-review to the complete diff. Fix correctness, security, ownership, durability, and UX findings with focused regression tests. Re-run the affected focused tests and then the full commands from Steps 3-5.

**Step 7: Update changelog, verify the final diff, and commit**

Record the completed Web workflow and full verification in Chinese. Then run:

```bash
git diff --check
git status --short
git diff --stat HEAD
```

Expected: no whitespace errors or untracked generated files; only intended final QA/test files remain.

```bash
git add web/e2e/documents.spec.js CHANGELOG.md
git commit -m "test: verify knowledge library workflow"
```

Finally apply @superpowers:finishing-a-development-branch and present merge/PR/keep-worktree options only after every required verification is green.
