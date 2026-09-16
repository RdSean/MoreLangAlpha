# Textbook and Library Formal Asset Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let the parent choose completed library parse jobs as textbook sources, freeze those sources into private textbook snapshots, and review the resulting formal teaching assets from both an independent library detail page and the textbook detail page without depending on a live PTC sandbox.

**Architecture:** Keep the document parser responsible only for high-fidelity Markdown and image extraction. Add a textbook-source binding from content versions to completed document parse jobs, copy the selected bundle into the private `education/` namespace, and continue staging only the frozen snapshot into the managed PTC run. Persist the teaching package and safe asset manifest as the single readable source for both library and textbook views.

**Tech Stack:** Python 3.13+, FastAPI, async psycopg3, Alembic raw SQL, Pydantic, private MinIO/S3-compatible storage, React 19, TypeScript, React Query, Vitest, Playwright.

---

## Task 1: Persist Parse Job Sources for Textbook Versions

**Files:**
- Create: `migrations/versions/062_add_textbook_artifact_sources.py`
- Modify: `src/server/database/education_textbooks.py:1561-1735`
- Create: `tests/unit/migrations/test_education_textbook_artifact_sources.py`
- Modify: `tests/unit/server/database/test_education_textbook_jobs.py`

**Step 1: Write the failing migration test**

Assert the new table has one row per frozen source bundle, rejects duplicate
positions, and keeps legacy `education_textbook_sources` intact.

```python
def test_artifact_source_migration_keeps_legacy_sources():
    sql = migration_module.upgrade_sql
    assert "CREATE TABLE education_textbook_artifact_sources" in sql
    assert "UNIQUE (version_id, position)" in sql
    assert "DROP TABLE IF EXISTS education_textbook_sources" not in sql
```

**Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/unit/migrations/test_education_textbook_artifact_sources.py -q
```

Expected: FAIL because the migration module does not exist.

**Step 3: Add the migration**

Create `education_textbook_artifact_sources`:

```sql
CREATE TABLE education_textbook_artifact_sources (
    version_id UUID NOT NULL
        REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT,
    document_id VARCHAR(16) NOT NULL
        REFERENCES documents(document_id) ON DELETE RESTRICT,
    producer_job_id VARCHAR(16) NOT NULL,
    primary_artifact_id VARCHAR(16) NOT NULL,
    position INTEGER NOT NULL CHECK (position > 0),
    primary_sha256 VARCHAR(64) NOT NULL
        CHECK (primary_sha256 ~ '^[0-9a-f]{64}$'),
    snapshot_prefix TEXT NOT NULL
        CHECK (snapshot_prefix LIKE 'education/%'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (version_id, producer_job_id),
    UNIQUE (version_id, position),
    FOREIGN KEY (producer_job_id, document_id)
        REFERENCES document_parse_jobs(job_id, document_id) ON DELETE RESTRICT,
    FOREIGN KEY (primary_artifact_id, producer_job_id)
        REFERENCES document_artifacts(artifact_id, producer_job_id)
        ON DELETE RESTRICT
);
```

Add `idx_education_textbook_artifact_sources_document` on
`(document_id, producer_job_id, version_id)`.

Do not remove, rewrite, or backfill legacy `education_textbook_sources`.

**Step 4: Add the database contract**

In `src/server/database/education_textbooks.py`, add:

```python
async def queue_textbook_processing_from_artifacts(
    *,
    parent_user_id: str,
    household_id: str,
    textbook_id: str,
    sources: list[dict[str, Any]],
    extractor_name: str,
    extractor_version: str,
) -> dict[str, Any] | None:
    ...
```

Each source item must contain `document_id`, `producer_job_id`,
`primary_artifact_id`, `primary_sha256`, and `snapshot_prefix`.

The transaction must:

- Lock and authorize the textbook by household.
- Calculate the next version sequence.
- Insert the version with `status = 'processing'`.
- Insert the new artifact sources in request order.
- Queue one `education_processing_jobs` row.

Make `claim_textbook_processing_job()` return the new source shape when
`education_textbook_artifact_sources` has rows for the version. Keep the legacy
query as a fallback for historical versions.

**Step 5: Add failing database tests**

Add tests in `tests/unit/server/database/test_education_textbook_jobs.py` for:

- A completed parse bundle becomes a `processing` version and queued job.
- Sources outside the parent's household are rejected.
- Duplicate source job IDs are deduplicated or rejected before insert.
- A legacy asset-backed version still claims and reads correctly.

Run:

```bash
uv run pytest tests/unit/server/database/test_education_textbook_jobs.py -q
```

Expected: FAIL before implementation, PASS after implementation.

**Step 6: Commit**

```bash
git add migrations/versions/062_add_textbook_artifact_sources.py \
  src/server/database/education_textbooks.py \
  tests/unit/migrations/test_education_textbook_artifact_sources.py \
  tests/unit/server/database/test_education_textbook_jobs.py \
  CHANGELOG.md
git commit -m "feat(education): bind textbook versions to parse job sources"
```

## Task 2: Freeze Completed Library Bundles into Education Storage

**Files:**
- Create: `src/server/services/education_textbook_source_snapshots.py`
- Modify: `src/server/services/education_textbooks.py:110-150`
- Modify: `src/server/services/education_textbook_storage.py:123-215`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py:186-215`
- Create: `tests/unit/server/services/test_education_textbook_source_snapshots.py`
- Modify: `tests/unit/server/services/test_education_textbooks.py`
- Modify: `tests/unit/server/app/education/test_textbooks.py`

**Step 1: Write failing service tests**

Cover:

- A completed parse job owned by the parent can be selected.
- A queued, failed, cancelled, missing, or foreign-owner parse job is rejected.
- The snapshot contains the primary Markdown and all referenced image
  artifacts with their relative paths preserved.
- The snapshot writes a service-generated manifest and SHA-256 values.
- Existing `education_assets` are not required for a new version.

```python
@pytest.mark.asyncio
async def test_snapshot_preserves_a_completed_parse_bundle(monkeypatch):
    source = await freeze_parse_job_source(
        owner_user_id="parent-1",
        document_id="doc-1",
        producer_job_id="job-1",
    )
    assert source["primary_artifact_id"] == "art-1"
    assert source["primary_sha256"] == "a" * 64
    assert source["snapshot_prefix"].startswith("education/")
```

**Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/unit/server/services/test_education_textbook_source_snapshots.py -q
```

Expected: FAIL because the snapshot service does not exist.

**Step 3: Implement the snapshot service**

Use `S3CompatibleDocumentStore` or the existing storage helpers to:

1. Read the owned parse job and all artifacts with its `producer_job_id`.
2. Require exactly one `primary_document` Markdown artifact.
3. Reject unsupported primary formats.
4. Copy the bundle to:

```text
education/<household>/<textbook-slug>/source-bundles/<version-id>/<position>/
```

5. Copy every source artifact under `artifacts/`; a source `manifest.json`
   therefore becomes `artifacts/manifest.json`, while the service-generated
   snapshot manifest remains at the bundle root.
6. Return the database-binding dictionary consumed by
   `queue_textbook_processing_from_artifacts()`.

The service must never return storage keys to the browser.

**Step 4: Add the request contract and service entry point**

Add a new optional field to the textbook processing request:

```python
source_parse_job_ids: list[str] = Field(default_factory=list)
```

Keep `source_asset_ids` temporarily for legacy compatibility. Reject requests
that mix both forms.

Add:

```python
async def start_processing_from_parse_jobs(
    *,
    parent_user_id: str,
    textbook_id: str,
    source_parse_job_ids: list[str],
) -> dict[str, Any]:
    ...
```

This method authorizes the parent, freezes all selected parse bundles, then
calls `queue_textbook_processing_from_artifacts()`.

**Snapshot cleanup invariant:** A known pre-commit
`TextbookQueueValidationError` or a `None` queue result may delete only the
exact keys written by this operation. The database queue call runs as an
explicitly referenced task and is awaited through `await_settled`, so caller
cancellation cannot cancel the database operation. Once that task settles, an
unknown exception or cancellation retains the snapshots because the durable
outcome is ambiguous; the log carries only `version_id` and `job_id` for later
orphan reconciliation. There is no post-cancellation `EXISTS` probe. A queued
job must never exist with missing snapshot objects. Cancellation of an
in-flight upload waits for the blocked worker to settle, then removes that
operation's exact destination key before re-raising.

**Step 5: Run focused tests**

```bash
uv run pytest \
  tests/unit/server/services/test_education_textbook_source_snapshots.py \
  tests/unit/server/services/test_education_textbooks.py \
  tests/unit/server/app/education/test_textbooks.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/server/services/education_textbook_source_snapshots.py \
  src/server/services/education_textbooks.py \
  src/server/services/education_textbook_storage.py \
  src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  tests/unit/server/services/test_education_textbook_source_snapshots.py \
  tests/unit/server/services/test_education_textbooks.py \
  tests/unit/server/app/education/test_textbooks.py \
  CHANGELOG.md
git commit -m "feat(education): freeze library parse bundles for textbooks"
```

## Task 3: Stage Multi-Source Frozen Content into Managed PTC

**Files:**
- Modify: `src/server/database/education_textbooks.py:1561-2050`
- Modify: `src/server/services/education_teaching_storage.py:100-215`
- Modify: `src/server/services/education_teaching_jobs.py:185-205`
- Modify: `skills/book-to-skill/reference/managed-textbook-contract.md`
- Modify: `skills/the-knowledge-guy/reference/managed-textbook-contract.md`
- Modify: `tests/unit/server/services/test_education_teaching_storage.py`
- Modify: `tests/unit/server/services/test_education_teaching_jobs.py`
- Modify: `tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py`

**Step 1: Write failing tests**

Assert:

- A version with two parse-job sources produces two frozen source entries.
- The PTC staging manifest contains ordered source IDs and SHA-256 values.
- No source contains a storage key, object URL, or sandbox path.
- One source may be the complete book; no Unit extraction is required.
- The managed prompt tells PTC to process the complete source bundle and does
  not require standard TOC or Unit names.

**Step 2: Run tests to verify they fail**

```bash
uv run pytest \
  tests/unit/server/services/test_education_teaching_storage.py \
  tests/unit/server/services/test_education_teaching_jobs.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q
```

Expected: FAIL because the managed input currently assumes pre-split chapters.

**Step 3: Extend the frozen teaching input**

Support this shape while keeping the current `chapters` shape for legacy
versions:

```python
{
    "format": "langalpha-managed-textbook-input/v2",
    "job_id": "...",
    "sources": [
        {
            "source_id": "job-1",
            "document_id": "doc-1",
            "position": 1,
            "title": "RE3 Part.pdf",
            "content_sha256": "...",
            "path": "sources/01-re3-part.md",
            "asset_paths": ["assets/01-re3-part/image-1.jpg"],
        }
    ],
}
```

Stage only service-derived paths. Copy source asset bytes under
`inputs/assets/<position>/` only when the Markdown references them.

**Step 4: Update the managed prompt and Skill contracts**

State that the source bundle may contain one or more complete documents, that
the parser does not guarantee Unit/TOC boundaries, and that PTC must generate
the final learning structure in its whitelisted outputs.

Do not introduce structure analysis as a separate phase in this task.

**Step 5: Run focused tests**

```bash
uv run pytest \
  tests/unit/server/services/test_education_teaching_storage.py \
  tests/unit/server/services/test_education_teaching_jobs.py \
  tests/unit/server/services/test_education_managed_ptc.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/server/database/education_textbooks.py \
  src/server/services/education_teaching_storage.py \
  src/server/services/education_teaching_jobs.py \
  skills/book-to-skill/reference/managed-textbook-contract.md \
  skills/the-knowledge-guy/reference/managed-textbook-contract.md \
  tests/unit/server/services/test_education_teaching_storage.py \
  tests/unit/server/services/test_education_teaching_jobs.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py \
  CHANGELOG.md
git commit -m "feat(education): stage complete library sources for teaching"
```

## Task 4: Expose Teaching Usage from the Library API

**Files:**
- Modify: `src/server/database/education_textbooks.py`
- Create: `src/server/services/document_teaching_usage.py`
- Modify: `src/server/models/documents.py`
- Modify: `src/server/app/documents.py`
- Create: `tests/unit/server/services/test_document_teaching_usage.py`
- Modify: `tests/unit/server/app/test_documents_api.py`

**Step 1: Write failing service tests**

Assert that the document owner can list teaching usages for a document:

```python
usage = await list_document_teaching_usages(
    owner_user_id="parent-1",
    document_id="doc-1",
)
assert usage[0]["textbook_title"] == "Reading Explorer 3"
assert usage[0]["content_version_sequence"] == 2
assert "storage_key" not in json.dumps(usage)
```

Also cover:

- A different user receives no rows.
- A legacy `education_assets` source is not reported by this endpoint.
- A failed package is reported without assets.
- A review or published package includes only safe package identifiers.

**Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/unit/server/services/test_document_teaching_usage.py -q
```

Expected: FAIL because the service does not exist.

**Step 3: Implement the read model**

Join:

```text
documents
  document_parse_jobs
  education_textbook_artifact_sources
  education_textbook_versions
  education_textbooks
  education_teaching_packages
  education_teaching_jobs
```

Return one item per content version and teaching package:

```python
{
    "document_id": "...",
    "producer_job_id": "...",
    "primary_artifact_id": "...",
    "textbook_id": "...",
    "textbook_title": "...",
    "content_version_id": "...",
    "content_version_sequence": 2,
    "teaching_package_id": "...",
    "teaching_package_sequence": 1,
    "status": "review",
    "has_asset_manifest": True,
}
```

Join through the document owner and household membership. Do not expose
`bundle_prefix`, object keys, or file URLs.

**Step 4: Add the API**

Add:

```http
GET /api/v1/documents/{document_id}/teaching-usage
```

Return:

```python
class DocumentTeachingUsageResponse(BaseModel):
    items: list[DocumentTeachingUsage]
```

The route must use the same non-student dependency as the rest of the document
API and return `404` for a missing or foreign-owned document.

**Step 5: Run focused tests**

```bash
uv run pytest \
  tests/unit/server/services/test_document_teaching_usage.py \
  tests/unit/server/app/test_documents_api.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/server/database/education_textbooks.py \
  src/server/services/document_teaching_usage.py \
  src/server/models/documents.py \
  src/server/app/documents.py \
  tests/unit/server/services/test_document_teaching_usage.py \
  tests/unit/server/app/test_documents_api.py \
  CHANGELOG.md
git commit -m "feat(documents): expose textbook usage for library assets"
```

## Task 5: Rename User-Facing Knowledge Library to Library

**Files:**
- Modify: `web/src/locales/zh-CN.json:103-148`
- Modify: `web/src/locales/zh-CN.json:206`
- Modify: `web/src/locales/zh-CN.json:294`
- Modify: `web/src/locales/en-US.json:103-148`
- Modify: `web/src/locales/en-US.json` for equivalent document copy
- Modify: `web/src/pages/Documents/__tests__/DocumentsPage.test.tsx`
- Modify: `web/src/components/Sidebar/__tests__/AppSidebar.navigation.test.ts`

**Step 1: Write the failing localization assertions**

Update tests to assert the sidebar and page title render `图书馆` in Chinese
and `Library` in English. Keep the route `/documents` and API paths unchanged.

**Step 2: Run the tests to verify they fail**

```bash
cd web && pnpm vitest run \
  src/pages/Documents/__tests__/DocumentsPage.test.tsx \
  src/components/Sidebar/__tests__/AppSidebar.navigation.test.ts
```

Expected: FAIL because the current copy still says Knowledge Library/知识库.

**Step 3: Update user-facing copy**

Change:

- `sidebar.documents`: `图书馆`.
- `documents.title`: `图书馆`.
- `documents.viewLabel`: `图书馆视图`.
- Dataset deletion and upload subtitles from `知识库` to `图书馆`.
- English equivalents to `Library`, not `Document Library` where space is
  constrained.

Do not rename `Document`, `documents` keys, `/documents`, database tables, or
API routes.

**Step 4: Run the focused tests**

```bash
cd web && pnpm vitest run \
  src/pages/Documents/__tests__/DocumentsPage.test.tsx \
  src/components/Sidebar/__tests__/AppSidebar.navigation.test.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/locales/zh-CN.json web/src/locales/en-US.json \
  web/src/pages/Documents/__tests__/DocumentsPage.test.tsx \
  web/src/components/Sidebar/__tests__/AppSidebar.navigation.test.ts \
  CHANGELOG.md
git commit -m "feat(web): rename knowledge library to library"
```

## Task 6: Add the Independent Library Document Detail Page

**Files:**
- Modify: `web/src/components/Main/routeChunks.ts`
- Modify: `web/src/components/Main/Main.tsx`
- Modify: `web/src/pages/Documents/types.ts`
- Modify: `web/src/pages/Documents/api.ts`
- Modify: `web/src/pages/Documents/hooks.ts`
- Create: `web/src/pages/Documents/DocumentDetailPage.tsx`
- Create: `web/src/pages/Documents/components/TeachingUsagePanel.tsx`
- Modify: `web/src/pages/Documents/components/DocumentPreviewDrawer.tsx`
- Create: `web/src/pages/Documents/__tests__/DocumentDetailPage.test.tsx`
- Modify: `web/src/pages/Documents/__tests__/DocumentPreviewDrawer.test.tsx`

**Step 1: Write failing page tests**

Assert:

- `/documents/:documentId` renders `原文 | 解析结果 | 教材资产`.
- The document name and parse state render.
- A completed parse result shows Markdown and image artifacts.
- A package in `review` shows official asset links.
- A failed package shows no asset links.
- Clicking the textbook link navigates to the textbook detail route.

**Step 2: Run the test to verify it fails**

```bash
cd web && pnpm vitest run \
  src/pages/Documents/__tests__/DocumentDetailPage.test.tsx
```

Expected: FAIL because the route and page do not exist.

**Step 3: Add the route**

Add a lazy route chunk:

```typescript
documentDetail: () => import('../../pages/Documents/DocumentDetailPage'),
```

Register:

```tsx
<Route path="/documents/:documentId" element={<DocumentDetail />} />
```

Keep `/documents` as the list route.

**Step 4: Implement the independent page**

Reuse viewer behavior from `DocumentPreviewDrawer` rather than duplicating PDF
or Markdown rendering. Extract the source and parsed tabs into a shared child
component if needed.

The third tab calls:

```typescript
getDocumentTeachingUsage(documentId)
```

Render one card per textbook/version/package. For `review` and `published`
packages, offer links to the existing textbook detail page. Do not fetch or
display object URLs.

Change `DocumentPreviewDrawer` into a quick preview with a visible
`查看详情` link to `/documents/:documentId`.

**Step 5: Run focused frontend tests**

```bash
cd web && pnpm vitest run \
  src/pages/Documents/__tests__/DocumentDetailPage.test.tsx \
  src/pages/Documents/__tests__/DocumentPreviewDrawer.test.tsx \
  src/pages/Documents/__tests__/DocumentsPage.test.tsx
```

Expected: PASS.

**Step 6: Commit**

```bash
git add web/src/components/Main/routeChunks.ts \
  web/src/components/Main/Main.tsx \
  web/src/pages/Documents/types.ts \
  web/src/pages/Documents/api.ts \
  web/src/pages/Documents/hooks.ts \
  web/src/pages/Documents/DocumentDetailPage.tsx \
  web/src/pages/Documents/components/TeachingUsagePanel.tsx \
  web/src/pages/Documents/components/DocumentPreviewDrawer.tsx \
  web/src/pages/Documents/__tests__/DocumentDetailPage.test.tsx \
  web/src/pages/Documents/__tests__/DocumentPreviewDrawer.test.tsx \
  CHANGELOG.md
git commit -m "feat(web): add independent library document detail"
```

## Task 7: Select Parse Jobs and Review Sources in Textbook Detail

**Files:**
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/Education/TextbookDetailPage.tsx`
- Modify: `web/src/pages/Education/__tests__/TextbookDetailPage.test.tsx`
- Modify: `web/src/pages/Education/__tests__/queries.test.tsx`

**Step 1: Write failing UI tests**

Assert:

- `开始加工` lists completed parse jobs, not `education_assets`.
- A user can select one or more complete parse results.
- Submitting sends `source_parse_job_ids`.
- The new `来源` tab shows source filename, parser, completed time, SHA-256
  prefix, and a link back to the library document.
- The `知识资产` tab appears only after package `review`.
- A sandbox/run failure does not remove the source list or library link.

**Step 2: Run the test to verify it fails**

```bash
cd web && pnpm vitest run \
  src/pages/Education/__tests__/TextbookDetailPage.test.tsx \
  src/pages/Education/__tests__/queries.test.tsx
```

Expected: FAIL because the textbook UI still selects `education_assets`.

**Step 3: Add typed APIs and hooks**

Add:

```typescript
export interface TextbookSource {
  document_id: string;
  producer_job_id: string;
  primary_artifact_id: string;
  filename: string;
  parser_id: string;
  parser_name: string;
  primary_sha256: string;
  created_at?: string | null;
  document_deleted: boolean;
}
```

Expose it from textbook detail through the existing detail query. Do not issue
one request per source.

Add a completed parse-job list hook for documents:

```typescript
export function useCompletedParseJobs(enabled: boolean) {
  return useQuery({
    queryKey: ['documents', 'parse-jobs', 'completed'],
    queryFn: educationApi.listCompletedParseJobs,
    enabled,
  });
}
```

**Step 4: Update the textbook UI**

Change `StartProcessingDialog` to select parse job bundles. The dialog should
show document filename, completed time, parser, and approximate artifact size.
Do not show raw storage keys.

Change the version tabs to:

```text
概览 | 来源 | 教学 | 知识资产 | 学生
```

The `来源` tab reads the frozen source projection and links to
`/documents/:documentId`.

**Step 5: Run focused frontend tests**

```bash
cd web && pnpm vitest run \
  src/pages/Education/__tests__/TextbookDetailPage.test.tsx \
  src/pages/Education/__tests__/queries.test.tsx \
  src/pages/Education/__tests__/TextbooksPage.test.tsx
```

Expected: PASS.

**Step 6: Commit**

```bash
git add web/src/pages/Education/types.ts \
  web/src/pages/Education/api.ts \
  web/src/pages/Education/queries.ts \
  web/src/pages/Education/TextbookDetailPage.tsx \
  web/src/pages/Education/__tests__/TextbookDetailPage.test.tsx \
  web/src/pages/Education/__tests__/queries.test.tsx \
  CHANGELOG.md
git commit -m "feat(web): select and review textbook library sources"
```

## Task 8: End-to-End Verification Without a Live Sandbox

**Files:**
- Modify: `web/e2e/documents.spec.js`
- Modify: `web/e2e/education.spec.js`
- Modify: `web/e2e/helpers/mockResponses.js`
- Modify: `CHANGELOG.md`

**Step 1: Add the failing browser flow**

Add a Playwright flow:

1. Upload a document and complete a mock parse job.
2. Open the independent library detail page and verify the parsed Markdown is
   visible.
3. Create a textbook and select the completed parse-job bundle.
4. Complete a mock teaching package and verify its formal assets.
5. Assert the library detail and textbook detail both show the same package.
6. Remove the runtime mock / mark the sandbox unavailable and verify both pages
   still load assets.
7. Publish and assign; assert the student sees only published content.

**Step 2: Run the new flow to verify it fails**

```bash
cd web && pnpm playwright test \
  e2e/documents.spec.js e2e/education.spec.js \
  --grep 'library textbook formal assets'
```

Expected: FAIL before frontend and mock integration are complete.

**Step 3: Complete mock contracts**

Add only safe fields:

- Document IDs and filenames.
- Parse job IDs, parser names, statuses, and timestamps.
- Textbook IDs, version sequences, package IDs, and statuses.
- Asset kinds and content summaries.

Never add `storage_key`, `bundle_prefix`, MinIO URLs, or sandbox paths to the
mock responses.

**Step 4: Run complete automated verification**

```bash
uv run pytest \
  tests/unit/migrations/test_education_textbook_artifact_sources.py \
  tests/unit/server/database/test_education_textbook_jobs.py \
  tests/unit/server/services/test_education_textbook_source_snapshots.py \
  tests/unit/server/services/test_education_textbooks.py \
  tests/unit/server/services/test_education_teaching_storage.py \
  tests/unit/server/services/test_education_teaching_jobs.py \
  tests/unit/server/services/test_document_teaching_usage.py \
  tests/unit/server/app/test_documents_api.py \
  tests/unit/server/app/education/test_textbooks.py -q
make lint
cd web && pnpm vitest run \
  src/pages/Documents/__tests__/DocumentDetailPage.test.tsx \
  src/pages/Documents/__tests__/DocumentPreviewDrawer.test.tsx \
  src/pages/Education/__tests__/TextbookDetailPage.test.tsx \
  src/pages/Education/__tests__/queries.test.tsx
cd web && pnpm typecheck
cd web && pnpm build
cd web && pnpm playwright test \
  e2e/documents.spec.js e2e/education.spec.js \
  --grep 'library textbook formal assets'
```

Expected: all commands exit `0`.

**Step 5: Run the real-service acceptance**

With the real backend and frontend running:

1. Upload and parse a PDF through the library.
2. Select that completed parse job from the textbook.
3. Complete the real managed PTC package.
4. Stop or let the sandbox expire.
5. Reload the library detail and textbook detail pages and verify the formal
   package remains readable.
6. Verify the browser network log contains no storage keys, object URLs, or
   sandbox paths.
7. Publish and assign; verify the student sees only the published package and
   no library/PTC controls.

Record mock and real-service results separately.

**Step 6: Commit**

```bash
git add web/e2e/documents.spec.js \
  web/e2e/education.spec.js \
  web/e2e/helpers/mockResponses.js \
  CHANGELOG.md
git commit -m "test(e2e): verify library and textbook formal assets"
```

## Completion Criteria

The work is complete only when:

- The user-visible name is `图书馆`.
- A textbook version can use completed parse-job bundles instead of
  `education_assets`.
- The selected bundle is copied into an immutable `education/` snapshot.
- PTC receives only the frozen source bundle and produces the existing
  whitelisted teaching assets.
- Library detail and textbook detail both read the same formal package.
- Formal assets remain readable after the PTC sandbox is unavailable.
- No structure analysis, Unit mapping, or exact cross-source fusion is
  presented as a first-phase guarantee.
- Student access remains limited to published assignments and Flash learning
  conversations.
