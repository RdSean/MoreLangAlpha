# Real Service Textbook Workflow Repair Design

## Context

Against the current `feature/family-textbook-learning` worktree, the real
parent flow successfully creates a textbook through `POST
/api/v1/education/textbooks`. The client then invalidates the library query and
leaves the parent at `/education/textbooks`. A newly created textbook has no
version, so its detail view maps an empty `versions` array to no `VersionPanel`.
The only parent source-upload and processing controls live inside that panel.

This makes the backend-created draft visible in the library but leaves no
reachable next action on the first detail screen. The real service evidence
shows the API and household authorization are not the failing boundary.

## Options Considered

1. Navigate only after create. This removes the extra click but leaves a new
   detail page without controls because no version exists yet.
2. Add source selection and processing to the library. This would duplicate
   detail workflow state and conflicts with the established one-textbook
   management route.
3. Navigate after create and render a detail-level draft workflow when there
   is no version. This keeps all source selection and lifecycle work on the
   canonical textbook page and makes the existing version-state controls
   reachable after a job is created.

The implementation uses option 3.

## Design

`TextbooksPage` will use the current React Router navigation API. After
`createTextbook` returns its existing safe response ID, the modal closes and
the browser moves directly to `/education/textbooks/:textbookId`.

`TextbookDetailPage` will render a compact draft action panel when
`textbook.versions.length === 0`. It presents the existing `StartProcessingDialog`,
which already supports selecting parent-owned candidate assets or submitting a
new upload through the authorized API. Its explicit submission creates a frozen
processing version. Once that version exists, the existing `VersionPanel`
continues to offer the next valid operation: run, retry, review, publish, and
assign. The action labels make the full sequence visible without allowing an
invalid transition.

The backend contract remains unchanged. Asset selection, upload, processing,
publication, and assignment continue to pass through the existing FastAPI
services, household authorization joins, and `education/` storage prefix.
The client never receives a storage key.

## Tests

Add focused UI regressions proving that creation navigates to the returned
detail ID and that an empty-version draft has the source-processing entry
point. Existing mutation, API, and browser acceptance tests continue to cover
later lifecycle states. Real browser verification must use the current
worktree's `5177`/`8000` services and a real parent session; mock Playwright
results are reported separately.
