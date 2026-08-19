# Student Flash Route Design

## Context

Student accounts are restricted to their deterministic private Flash workspace.
The chat route wrapper currently creates that workspace and replaces the URL,
but it continues to return the loading surface after the replacement. The
Flash workspace has already been created successfully, while the chat UI never
mounts.

## Decision

Keep the existing deterministic Flash workspace API and route shape. The
student wrapper will only redirect a student from the root `/chat` route to
their Flash workspace. It will render its child chat route when the URL already
identifies a workspace or a thread.

The existing server-side ownership checks remain the authorization boundary for
workspace and thread data. This change does not expose model configuration,
BYOK credentials, PTC workspaces, sandbox features, or parent-only settings to
students.

## Alternatives Considered

1. Keep the wrapper on every chat route but add client-side Flash workspace ID
   comparison. This would add an extra request to every student deep link and
   still complicate permitted thread playback.
2. Remove the wrapper entirely. This would make `/chat` show a generic gallery
   before a Flash workspace is created.
3. Redirect only the root `/chat` route, then render existing chat routes.
   This is the selected minimal fix: it preserves the automatic Flash entry
   point and delegates deep-link authorization to the existing API checks.

## Verification

Add a focused component test proving that a student first sees the loading
state on `/chat`, is redirected after the Flash workspace resolves, and then
receives the child chat content at `/chat/:workspaceId`. Also cover a student
thread deep link rendering its child directly. Run the focused Vitest file,
frontend typecheck and production build.
