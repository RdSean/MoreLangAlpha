# Artifact Proxy Download Design

## Goal

Keep artifact downloads on the LangAlpha origin. The browser must never be
redirected to a MinIO/S3 endpoint, while existing ownership checks and the
public download route remain unchanged.

## Decision

`GET /api/v1/document-artifacts/{artifact_id}/download` will authorize the
request through the existing owner-scoped artifact lookup, open the private
object through the document object-store adapter, and return a FastAPI
`StreamingResponse`.

The object-store boundary will expose an opened download containing a bounded
chunk iterator and optional content length. Opening the object happens before
response headers are sent so storage failures can still become a normal API
error. The iterator closes the S3 response body in a `finally` block, including
client disconnects.

## Response Contract

- Keep the existing LangAlpha route and authentication behavior.
- Return the artifact's stored `media_type` as `Content-Type`.
- Return `Content-Disposition: attachment` using the shared RFC 6266 helper so
  Unicode filenames are safe.
- Return `Content-Length` when the object store supplies it.
- Do not expose a presigned URL or MinIO host to the client.
- Do not add HTTP Range support in this change; a future Nginx/X-Accel delivery
  implementation can preserve this public route.

## Error Handling

Missing or foreign-owner artifacts remain `404`; student access remains `403`.
Object-store failures are wrapped in the existing safe `DocumentStorageError`
contract. No backend exception or object key is returned to the browser.

## Verification

Unit tests will prove chunked iteration, body cleanup, safe storage errors,
owner-scoped lookup, headers, and absence of redirects. The real MinIO test
will verify that response bytes travel through LangAlpha without a `Location`
header. Existing frontend code needs no behavior change because it already
links to the LangAlpha artifact route.
