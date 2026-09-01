# Deterministic tiktoken Resource and Cache Design

**Date:** 2026-09-01

## Goal

Keep LangAlpha's `cl100k_base` token counting deterministic and available
without requiring a successful first-run network request. If the exact
vocabulary cannot be prepared, model calls must continue with approximate
counting while the model settings page clearly exposes the degraded state and
offers a bounded retry action.

## Current Failure

The compaction middleware calls `tiktoken.get_encoding("cl100k_base")` lazily.
On a cold process, tiktoken resolves that encoding through the public OpenAI
Blob Storage URL. Its default cache lives under the operating system's
temporary directory, so a backend restart can lose the cached vocabulary. A
network or TLS failure then escapes from token counting and can fail an entire
Flash run.

The current approximate encoder prevents that failure, but it does not provide
a deterministic exact resource, a stable cache location, startup repair, or a
user-visible degraded status.

## Selected Design

Use a repository-shipped vocabulary as a trusted seed and a fixed writable
cache as tiktoken's runtime input. This combines deterministic offline startup
with repair when either the cache or packaged resource is missing or corrupt.

### 1. Trusted bundled resource

Commit the official vocabulary at:

```text
src/ptc_agent/resources/tiktoken/cl100k_base.tiktoken
```

The resource is accepted only when its SHA-256 equals:

```text
223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7
```

The only download source is the official fixed URL:

```text
https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken
```

Neither the browser nor API callers may supply an alternative URL or digest.

### 2. Fixed writable cache

`TIKTOKEN_CACHE_DIR` remains the standard override. It is optional in `.env`.
When unset, LangAlpha resolves a stable repository-relative default:

```text
var/cache/tiktoken
```

Docker images set it explicitly to:

```text
/app/var/cache/tiktoken
```

The generated cache remains ignored by Git. Deployments only need an `.env`
override when they intentionally place the cache on a persistent volume or a
different writable filesystem.

### 3. Startup preparation

Application startup runs one non-fatal preparation operation before agent
requests are accepted:

1. Resolve and create the fixed cache directory.
2. Accept an existing cache entry only after SHA-256 verification.
3. Otherwise verify the bundled resource and atomically seed the cache from it.
4. If neither copy is valid, download the official resource to a unique
   temporary file, verify it, and atomically replace the cache entry.
5. If every exact path fails, log a sanitized error and mark the tokenizer as
   degraded without preventing application startup.

Temporary files are removed on failure. Concurrent process attempts remain
safe because only fully verified files are atomically renamed into place.

The same preparation function backs startup and the manual retry API. Exact
encoders may be cached in process. The approximate fallback must not be cached
permanently, allowing a successful later download to restore exact counting
without restarting the backend.

### 4. Runtime status and retry API

Add a small runtime-resource API with:

- a read endpoint returning the `cl100k_base` state;
- an authenticated retry endpoint that re-runs the fixed download and
  verification flow.

The public response reports only stable fields such as encoding name, status,
whether counting is exact, and a safe error code. It does not expose arbitrary
filesystem paths, temporary filenames, raw exception messages, or remote
content.

Expected stable states are `ready` and `approximate`. The frontend owns the
transient `downloading` presentation while the retry request is pending.

### 5. Model settings warning

The model settings page reads tokenizer status independently from model
preferences. When exact counting is unavailable, it renders a prominent error
banner above the model controls explaining that LangAlpha is using approximate
Token counting and that context compaction timing may be less precise.

The banner includes a `重新下载词表` / `Download vocabulary again` action.
During the request the action is disabled and displays a downloading state.
Success refreshes the status and removes the warning. Failure keeps the banner
visible and shows a localized retry failure message.

All user-visible tokenizer strings are defined in both:

```text
web/src/locales/zh-CN.json
web/src/locales/en-US.json
```

### 6. Docker images

Only `deploy/Dockerfile.backend` and `deploy/Dockerfile.dev` execute the
LangAlpha compaction runtime. They will:

- set `TIKTOKEN_CACHE_DIR=/app/var/cache/tiktoken`;
- create the directory before runtime;
- copy the bundled vocabulary into tiktoken's expected cache entry;
- verify the fixed SHA-256 during image creation;
- explicitly set ownership and writable permissions for the image's existing
  runtime user.

The current backend images run as root. This change keeps that user model to
avoid breaking Docker socket and browser dependencies, while making ownership
explicit. It does not change `deploy/Dockerfile.web` or `Dockerfile.sandbox`.
Dockerfile syntax will be reviewed and tested statically, but no image build is
run as part of this task.

## Error Handling

- Invalid cache files are never passed to tiktoken.
- Download responses are bounded by a timeout and maximum expected size.
- Hash mismatch, network failure, permission errors, and parse failure all
  preserve approximate counting.
- API errors expose a stable localized condition rather than raw host or TLS
  details.
- Approximate counting remains deliberately conservative and never blocks an
  Agent run.

## Verification

Focused tests cover:

- cache-path resolution and optional environment override;
- valid cache reuse;
- bundled-resource seeding;
- verified atomic download when both local copies are absent;
- corrupt downloads and offline fallback;
- automatic recovery from approximate to exact counting;
- runtime status and authenticated retry API contracts;
- model settings warning, retry state, and both locale catalogs;
- static Dockerfile cache configuration, hash verification, and ownership.

Backend unit tests, frontend targeted tests/type checking, Ruff, and source
resource digest verification are run. Docker images are not built per request.

## Alternatives Rejected

- **Fixed external cache only:** still makes a fresh deployment depend on
  external network access and does not satisfy the committed-resource goal.
- **Bundled resource only:** works offline but cannot repair an omitted or
  damaged deployment resource.
- **Place the resource in `.venv`:** virtual environments are regenerated by
  `uv`, are not committed, and are not a reliable shared location for
  worktrees or containers.

## References

- tiktoken `cl100k_base` registry constructor:
  `tiktoken_ext.openai_public.cl100k_base`
- tiktoken cache implementation: `tiktoken.load.read_file_cached`
- tiktoken BPE loader: `tiktoken.load.load_tiktoken_bpe`
- Official vocabulary URL:
  `https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken`
