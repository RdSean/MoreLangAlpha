# Same-Origin Artifact Download Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stream document artifacts through the authenticated LangAlpha API instead of redirecting browsers to private MinIO/S3 URLs.

**Architecture:** Open each object through the existing document storage adapter after an owner-scoped artifact lookup, then return its chunk iterator through FastAPI `StreamingResponse`. Preserve the public route, media type, Unicode filename, and optional content length so a later Nginx/X-Accel implementation can replace delivery without changing clients.

**Tech Stack:** Python 3.13, FastAPI/Starlette, boto3 `StreamingBody`, pytest, httpx, MinIO

---

### Task 1: Replace the artifact redirect with an authenticated byte stream

**Files:**

- Modify: `src/utils/storage/s3_compatible.py`
- Modify: `src/server/documents/storage.py`
- Modify: `src/server/documents/jobs.py`
- Modify: `src/server/app/documents.py`
- Modify: `tests/unit/utils/storage/test_s3_compatible.py`
- Modify: `tests/unit/server/documents/test_storage.py`
- Modify: `tests/unit/server/documents/test_jobs.py`
- Modify: `tests/unit/server/app/test_documents_api.py`
- Modify: `tests/integration/test_document_storage_minio.py`
- Modify: `tests/integration/test_document_library_api.py`
- Modify: `CHANGELOG.md`

**Step 1: Write the failing storage tests**

Add tests that request an opened object stream and assert:

```python
download = open_download_stream("documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/document.md")
assert download.content_length == len(payload)
assert b"".join(download.chunks) == payload
assert body.closed
```

Also cover a missing body, non-integer content length, fixed-size chunk reads,
and exception-safe body closure. At the document adapter boundary, assert that
invalid keys are rejected before storage is called and backend failures become
`DocumentStorageError`.

**Step 2: Write the failing service and route tests**

Change the download expectations from `307 Location: https://minio...` to:

```python
assert response.status_code == 200
assert response.content == b"# Lesson\n"
assert "location" not in response.headers
assert response.headers["content-type"].startswith("text/markdown")
assert "filename*=UTF-8''" in response.headers["content-disposition"]
```

Verify the service still performs an owner-scoped artifact lookup and passes
only the stored key to the object store. Keep the existing `404` and `403`
tests.

**Step 3: Run the focused tests and verify RED**

Run:

```bash
uv run pytest \
  tests/unit/utils/storage/test_s3_compatible.py \
  tests/unit/server/documents/test_storage.py \
  tests/unit/server/documents/test_jobs.py \
  tests/unit/server/app/test_documents_api.py -q
```

Expected: FAIL because the storage boundary has no opened stream contract and
the route still returns a redirect.

**Step 4: Implement the minimal stream boundary**

Add an immutable opened-download value carrying `chunks` and
`content_length`. The boto3 adapter must call `get_object` before returning,
read only fixed-size chunks, and close the body from the iterator's `finally`
block. Expose this through `DocumentObjectStore.open_download(key)` using
`asyncio.to_thread`.

Replace `DocumentParseJobService.create_artifact_download()` with an operation
that returns the opened object plus the artifact's safe filename and media
type. Remove the document domain's presigned-URL dependency; leave the generic
S3 presigning helper available for unrelated consumers.

**Step 5: Implement the FastAPI response**

Return `StreamingResponse` from the existing artifact route with:

```python
headers = {
    "Content-Disposition": content_disposition(filename),
    **({"Content-Length": str(content_length)} if content_length is not None else {}),
}
```

Use the artifact `media_type` and never set a `Location` header.

**Step 6: Verify GREEN and real MinIO behavior**

Run the focused unit command from Step 3, then:

```bash
uv run pytest tests/integration/test_document_storage_minio.py -q
uv run pytest tests/integration/test_document_library_api.py -q
```

Expected: all pass. The real MinIO assertion must confirm response bytes,
headers, and absence of redirects.

**Step 7: Update the changelog and run regression checks**

Add a Chinese `知识库文档解析基础` bullet describing same-origin artifact
downloads. Run:

```bash
uv run pytest tests/unit/server/documents tests/unit/server/app/test_documents_api.py -q
cd web && pnpm test -- src/pages/Documents && pnpm typecheck
git diff --check
```

Expected: all pass with no diff-check errors.

**Step 8: Commit atomically**

```bash
git add src/utils/storage/s3_compatible.py src/server/documents/storage.py \
  src/server/documents/jobs.py src/server/app/documents.py \
  tests/unit/utils/storage/test_s3_compatible.py \
  tests/unit/server/documents/test_storage.py \
  tests/unit/server/documents/test_jobs.py \
  tests/unit/server/app/test_documents_api.py \
  tests/integration/test_document_storage_minio.py \
  tests/integration/test_document_library_api.py CHANGELOG.md
git commit -m "fix: proxy document artifact downloads"
```
