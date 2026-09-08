# Document Preview and Parse Status Design

## Goal

Keep document parsing as an explicit wizard while making normal document clicks open a preview drawer. Ensure completed parse jobs immediately refresh list status.

## Architecture

`DocumentsPage` owns URL state for the upload wizard and preview drawer independently. A new `DocumentPreviewDrawer` loads the owner-scoped source stream URL for the default Original tab and lazily loads the newest successful Markdown artifact for the Parsed tab. The existing PDF.js `PdfViewer` and Markdown renderer are reused. The wizard receives an optional completion callback; when artifacts are loaded it invalidates document detail and list queries.

The backend adds an owner-safe `GET /api/v1/documents/{document_id}/source` stream endpoint backed by the document library and S3-compatible object store. It never exposes a presigned localhost URL.

## Behavior and failure handling

- Closing the drawer removes only the `document` URL parameter.
- Closing the wizard removes only `upload` (and any legacy document parameter).
- Original preview remains available regardless of parse status.
- Parsed preview reports a clear empty state when no successful Markdown artifact exists and offers the parse wizard action.
- Source/artifact download failures are rendered inside the drawer, not as unhandled errors.

## Verification

Add focused frontend tests for drawer tabs, Markdown loading, and page URL behavior; extend wizard tests to assert completion refresh callback. Add backend route/service tests for owner-safe source streaming. Run document tests, typecheck, and backend focused tests.
