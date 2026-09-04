# Document Knowledge Library and Parsing Pipeline Design

**Date:** 2026-09-05

## Goal

Add a user-private document knowledge library that can accept a PDF, inspect it,
recommend a parsing method, wait for the user to choose that method, and produce
Markdown through a durable synchronous or asynchronous job. The same foundation
must later support OCR, extracted images, structured JSON, additional document
formats, education assets, workspace copies, and Agent tool calls without making
the core document domain depend on any of those consumers.

The first release includes a top-level web entry named `知识库`, served at
`/documents`, and a backend API that can also be called directly by future
Agents.

## Non-goals

- Automatically parse a document immediately after upload.
- Implement OCR, a hosted parser, vector indexing, retrieval, or knowledge
  graphs.
- Add Markdown edit history or artifact revisions. A future editor will update
  the current artifact in place.
- Add nested Dataset folders or inherited Dataset permissions.
- Couple document ownership to a workspace, education household, or PTC
  sandbox.
- Install or invoke Agent Skills for parsing. The first integration calls the
  Python packages through explicit provider code.

## Selected Architecture

Create a `documents` domain inside the existing FastAPI application. PostgreSQL
stores documents, inspection reports, Dataset and tag membership, parse jobs,
and artifact metadata. The existing S3-compatible storage configuration stores
source files and parser output; MinIO is the current development implementation.

The web application, future education adapters, workspace copy operations, and
Agent tools consume the document service API. They do not import parser
providers or access storage keys directly.

PostgreSQL is the source of truth for asynchronous work. Per-process state may
only hold the execution context for a job already claimed through a database
lease. Redis can wake progress subscribers, but a missing Redis notification
must degrade to a PostgreSQL reread.

This modular-monolith design deliberately preserves a later move to a dedicated
parser service: providers and job execution sit behind contracts, while the
asset, API, and UI contracts remain unchanged.

## Public Identifiers

New document-domain entities use compact, globally unique identifiers with a
three-letter type prefix, a hyphen, and a 12-character Base62 random suffix:

```text
dts-k7N3pQ8x2AbM  Dataset
doc-f4T9wK2c7PqR  Document
ins-t3Q8jM6p2VzK  Inspection
job-m8R2vX6n3LdQ  Parse job
art-b5H9sC4y7WkN  Artifact
tag-c2L7rP4n8XsQ  Tag
```

These IDs are the database primary keys; there is no parallel UUID. A unique
constraint detects a collision and the ID factory retries. IDs are opaque and
never replace ownership checks. Parser IDs are stable readable identifiers such
as `anydoc-local`, not random entity IDs.

## Data Model

### Documents

`documents` owns the immutable uploaded source:

- `document_id`
- `owner_user_id`
- `original_filename`
- `media_type`
- `document_format`
- `source_storage_key`
- `source_size_bytes`
- `source_sha256`
- `created_at`
- `updated_at`

The source size and SHA-256 apply only to the uploaded source. Derived artifacts
do not store size or hashes because their content may be edited in place later.

### Datasets and tags

`document_datasets` contains `dataset_id`, `owner_user_id`, `name`, optional
`description`, and timestamps. `document_dataset_items` is a many-to-many join
between a Dataset and a Document. A document may belong to no Dataset or several
Datasets.

`document_tags` contains `tag_id`, `owner_user_id`, `name`, and
`normalized_name`, unique per owner. `document_tag_assignments` is the
many-to-many join between Documents and tags.

Datasets are logical collections, not object-store directories. Dataset rename,
membership changes, and multi-Dataset membership never move or copy objects.
The first UI presents Datasets like folders but does not support nesting.

### Inspections

`document_inspections` records each inspection independently:

- `inspection_id`
- `document_id`
- `inspector_id`, `inspector_name`, and `inspector_version`
- `status`
- `detected_format`
- `classification`
- `summary JSONB`
- `details JSONB`
- safe `error_code` and `error_message`
- timestamps

`summary` holds generic display data such as page count and page dimensions.
Format-specific values, including PDF pages that need OCR, remain in `details`
and do not shape the general document table or wizard.

### Parse jobs

`document_parse_jobs` has a many-to-one relationship with Documents. There is
no uniqueness constraint on Document and parser: a user may run the same parser
repeatedly or compare different parsers without replacing an earlier result.

Each job stores:

- `job_id`, `document_id`, and the inspection used for the decision
- stable `parser_id`
- parser display-name and version snapshots
- requested parser options
- execution request mode (`sync` or `async`)
- status, stage, percentage, and a monotonic status version
- attempt count, claimant, lease expiry, and cancellation request time
- safe error code and message
- creation, start, completion, and update timestamps
- the primary artifact reference once publication succeeds

Terminal statuses are `completed`, `failed`, and `cancelled`. The common stage
vocabulary is `queued`, `preparing`, `parsing`, `storing`, then a terminal
status. Progress is intentionally coarse and format-neutral.

### Artifacts

One parse job produces an ArtifactBundle with one or more rows in
`document_artifacts`:

- `artifact_id`
- `document_id`
- `producer_job_id`
- `artifact_kind`: `primary_document`, `embedded_image`, `structured_data`, or
  `manifest`
- `format`: for example `gfm`, `png`, `jpeg`, or `document_json`
- `media_type`
- optional `schema_name` and `schema_version` for structured JSON
- bundle-relative path and S3-compatible `storage_key`
- optional `locator JSONB` for page, slide, sheet, or content-region provenance
- extensible `metadata JSONB`
- `created_at` and `updated_at`

The artifact's `producer_job_id` leads to the exact parser ID, name, version,
options, and inspection. Artifacts do not duplicate parser provenance columns.
They also do not store size, SHA-256, or revisions. A future Markdown editor
updates the existing object and `updated_at` in place.

## Object Storage

Define a small `DocumentObjectStore` service contract for put, get, exact-key
delete, and signed download URL operations. The initial
`S3CompatibleDocumentStore` reuses LangAlpha's current S3-compatible/MinIO
configuration and client helpers. Document services never depend directly on a
MinIO-specific SDK.

Objects use stable, private keys that do not include the user-controlled
filename:

```text
documents/doc-f4T9wK2c7PqR/source
documents/doc-f4T9wK2c7PqR/artifacts/job-m8R2vX6n3LdQ/document.md
documents/doc-f4T9wK2c7PqR/artifacts/job-m8R2vX6n3LdQ/document.json
documents/doc-f4T9wK2c7PqR/artifacts/job-m8R2vX6n3LdQ/images/page-003-01.png
documents/doc-f4T9wK2c7PqR/artifacts/job-m8R2vX6n3LdQ/manifest.json
```

The original filename stays in PostgreSQL and Content-Disposition metadata.
The bucket remains private. Every download authorizes through Document ownership
before issuing a short-lived signed URL.

Parsers write into a per-job temporary directory. The parent validates every
relative output path, builds or validates the manifest, and uploads the bundle
under the final unique job prefix. Artifact rows and job completion are then
published in one database transaction. If upload or publication fails, cleanup
deletes only the exact keys created by that job; it never enumerates or removes
unrelated MinIO objects.

## Inspector and Parser Contracts

Keep inspection and parsing as distinct public decisions:

```text
DocumentInspector.inspect(source) -> InspectionResult
DocumentParser.parse(source, options, progress) -> ArtifactBundle
```

A provider registry exposes descriptors separately from provider execution.
Descriptors include stable ID, display name, supported formats and
classifications, availability, a short reason, and whether a method is
recommended. Routes and UI code do not import third-party parsers or hard-code
classification routing tables.

Initial providers are:

- `PdfInspectorDetector`: calls `pdf-inspector` in detection mode and records
  `text_based`, `scanned`, `image_based`, `mixed`, or `unknown`, plus generic
  summary information and detailed OCR-routing data.
- `AnydocExtractor` (`anydoc-local`): the recommended local extractor only for
  text-based PDFs. The pinned anydoc release raises `NeedsOcr` instead of
  returning partial Markdown when a PDF contains scanned pages, so it is marked
  incompatible with mixed, scanned, and image-based classifications.
- `LegacyPdfExtractor` (`legacy-pdf-text`): reuses the existing
  pdfplumber-primary/pypdf-fallback behavior as a best-effort compatibility
  path. It is the available recommendation for mixed, scanned, and image-based
  PDFs. Mixed files may yield only pages with a text layer; scanned and
  image-based files may yield empty output because this provider is not OCR.
- `ocr-document`: an unavailable descriptor shown as a future option. It has no
  executing provider in the first release. `scanned` is an input classification;
  `ocr-document` is a future parser method that can act on scanned, image-based,
  or mixed inputs.

The method selection UI shows only a few simple cards: name, recommendation,
one-sentence reason, availability, and quality warning. The user must explicitly
choose a method and start parsing. Upload and inspection never trigger a parser.

The initial implementation pins and directly invokes the Python packages:

```text
pdf-inspector==1.17.0
firecrawl-anydoc==0.2.4
```

Both releases publish ABI3 wheels for Python 3.13 on macOS Intel/ARM and Linux
x86_64/ARM, so supported development and Docker targets do not need a Rust
compiler. Imports stay inside providers and are lazy so availability can be
reported cleanly.

Native parsing runs in a spawned, bounded child process rather than the FastAPI
event loop. The parent downloads the source from MinIO, owns the temporary
directory, enforces the deadline, validates output, and terminates the child on
timeout. A native crash therefore fails one job rather than the serving worker.

## Upload, Inspection, and Parse Flow

1. Stream and validate the upload while enforcing the configured 50 MB limit
   and calculating the source SHA-256.
2. Persist the source under its Document key and insert the user-owned metadata,
   optional Dataset membership, and optional tags. Compensate the exact source
   object if database insertion fails.
3. Run the PDF inspection under a bounded deadline and return the saved
   Document, inspection summary, and available parse options. If inspection
   fails, keep the source and expose a retry action.
4. Wait for the user or API caller to submit a parser ID. Validate that the
   parser is available and compatible with the selected inspection.
5. Create a new durable parse job every time. Do not overwrite or reuse a prior
   job based on Document or parser ID.
6. Execute and publish the ArtifactBundle. The original Document and previous
   jobs remain intact on failure.

Synchronous and asynchronous requests use the same durable job and executor:

- `async` returns `202` and the job immediately.
- `sync` waits for the job for at most the configured synchronous wait period.
- A synchronous job completed within that period returns `200` and artifacts.
- A job still running returns `202`; it continues asynchronously and the caller
  follows the same status API.
- Client disconnect never cancels the durable job.

## Durable Job Execution and Progress

Application workers claim queued jobs with PostgreSQL leases and guarded
updates. Claims include a worker identity, attempt counter, and lease expiry.
The executor renews its lease while active. An expired lease makes a job
eligible for recovery after a worker crash. Artifact publication is idempotent
for the job ID.

Every status write increases `status_version`; progress cannot move backwards
within an attempt. An SSE connection first reads and emits the current database
snapshot. Redis notifications prompt a reread, while periodic PostgreSQL reads
recover missed notifications. A regular job GET endpoint is the polling
fallback. The existing chat SSE/replay state is not reused or extended for
document jobs.

Cancellation is cooperative between pipeline stages. When a parser child is
active, the owning executor may terminate that child after observing the
durable cancellation request. A request handled by another Web worker only
changes PostgreSQL and sends a best-effort wake; correctness does not depend on
the wake.

## API Surface

Documents and parsing:

```http
POST   /api/v1/documents
GET    /api/v1/documents
GET    /api/v1/documents/{document_id}
PATCH  /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}

POST /api/v1/documents/{document_id}/inspections
GET  /api/v1/documents/{document_id}/parse-options
POST /api/v1/documents/{document_id}/parse-jobs

GET  /api/v1/document-jobs/{job_id}
GET  /api/v1/document-jobs/{job_id}/events
POST /api/v1/document-jobs/{job_id}/cancel

GET /api/v1/documents/{document_id}/artifacts
GET /api/v1/document-artifacts/{artifact_id}/download
```

Dataset and tag resources have separate CRUD/list endpoints. The multipart
upload accepts optional Dataset and tag inputs; creating a Dataset remains an
explicit Dataset API call that the upload wizard can compose.

The Document list supports server-side filename search and filters for Dataset,
tags, media type, inspection classification, and parse status. It follows the
existing `limit`, `offset`, and `total` pagination convention. Every query
enforces `owner_user_id` in the database access layer.

Stable public error codes include `unsupported_media_type`, `file_too_large`,
`inspection_failed`, `parser_unavailable`, `parser_incompatible`,
`parse_timeout`, `invalid_parser_output`, and `storage_failed`. Raw native,
filesystem, object-store, or database exception text never reaches the client.

## Web Experience

The sidebar label is `知识库`; its route is `/documents`. The page has two
independent tabs:

```text
/documents
  Dataset
    Dataset card list
      Dataset detail -> paginated table scoped to that Dataset
  All documents
    paginated table for every Document owned by the user
```

The Dataset tab supports creation and search. Cards show name, description,
document count, and recent update time. A Dataset detail view supports filename
search and tag, format, classification, and parse-status filters. Uploading from
that view preselects the current Dataset.

The All Documents tab provides the same table and filters, plus a Dataset
filter. Common columns are filename, Datasets, tags, format, source size, parse
status, update time, and actions. All filtering and pagination are server-side.

The upload experience follows the existing model-setup wizard's visual and
interaction conventions:

```text
File and classification -> Inspection summary -> Method -> Progress -> Result
```

The summary shows only filename, file size, page count, page dimensions,
classification, and a short recommendation. The first release always parses
the complete document; it does not expose page-range selection. The result view
provides Markdown preview, individual artifact downloads, bundle contents, and
the list of prior parse jobs. Starting again always creates another job.

The UI uses the existing Quiet Workspace tokens, shared liveness glyph, React
Query key hierarchy, API-layer convention, localization catalogs, and lazy
route loading. It does not make the page a marketing surface or nest cards
inside cards.

## Configuration and Deployment

The operational defaults are environment-configurable through centralized,
typed settings accessors rather than direct environment reads in business code:

```text
DOCUMENT_MAX_UPLOAD_BYTES=52428800
DOCUMENT_SYNC_WAIT_SECONDS=30
DOCUMENT_PARSE_TIMEOUT_SECONDS=600
```

The 50 MB limit applies to all uploads. There is no separate synchronous file
size or global page-count limit: synchronous mode falls back to the durable
asynchronous response after its wait period, while an individual provider may
declare and report its own resource constraint.

Docker and local dependency files include the pinned native wheels. The MinIO
development configuration remains the storage backend and uses the existing S3
API endpoint, not the MinIO console endpoint. No code reads or logs storage
credentials, and tests operate only below a generated `documents/` test prefix.

## Security and Failure Handling

- Validate declared media type, filename, PDF signature, and streaming size.
- Keep source and artifact buckets private and authorize every signed URL.
- Use a mode-restricted temporary directory per execution and never execute PDF
  embedded content.
- Reject absolute, parent-relative, symlinked, or escaping parser output paths.
- Bound inspection, parse execution, output count, and individual output size.
- Preserve the original Document and every prior completed job when a new job
  fails.
- Do not expose local paths, storage endpoints, credentials, or raw provider
  errors.
- Do not treat a compact public ID as authorization.

Virus scanning is a future provider/gate and is not part of the first release.

## Verification

Backend unit tests cover compact ID generation and collision retry, ownership,
Dataset and multi-tag filters, recommendation mapping, provider registration,
state transitions, monotonic progress, lease recovery, sync-to-async behavior,
stable errors, output validation, publication, and exact-key compensation.

Provider contract tests use small text-based, scanned, image-based, and mixed
PDF fixtures. They exercise the real pinned Python bindings and assert
classification, expected warnings, and Markdown behavior without accepting OCR
quality as implemented.

Integration tests cover PostgreSQL competing claims and expired-lease recovery,
plus a MinIO round trip contained under a generated `documents/` test prefix.
They verify multi-artifact publication and cleanup without enumerating unrelated
objects.

Frontend tests cover both tabs, Dataset navigation, server-side filters and
pagination, Dataset creation in the upload flow, the inspection gate, explicit
method selection, progress reconnect, terminal errors, artifact presentation,
and multiple parse jobs for one Document.

Before handoff, run focused backend tests, Ruff, frontend tests, type checking,
and the production frontend build. Start the development frontend on
`0.0.0.0:5177` and verify the complete workflow through the LAN-accessible URL.

## Alternatives Rejected

- **Workspace-owned files:** there is no unambiguous default workspace, and
  reusable source assets should not live inside a PTC sandbox.
- **Education-owned assets:** household and parent/student semantics would make
  a general parser depend on one product module.
- **Immediate automatic routing:** it removes the explicit decision boundary
  required for user choice and future Agent planning.
- **Dedicated parsing microservice now:** it provides stronger independent
  scaling but adds premature service discovery, authentication, deployment,
  queueing, and recovery work. The provider boundary keeps this migration open.
- **Browser-only WASM inspection:** it cannot be the trusted report used by APIs
  and Agents and would duplicate server-side detection logic.
- **Dataset-only or tag-only organization:** Datasets provide actionable
  collections while tags provide orthogonal filtering; either alone constrains
  the intended reuse.
