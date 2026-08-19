# Chat Session And Message Timestamps Design

## Scope

Add two presentation-only timestamps to the existing chat transcript:

1. Show the conversation's start time in the chat header.
2. Show each user and assistant message's send time beside its bubble.

Token accounting, agent think duration, and tool-call duration remain out of scope.

## Data Flow

The existing `GET /api/v1/threads/{thread_id}` response already exposes the
thread `created_at` value. `ChatView` will fetch that existing resource for the
resolved thread id and keep the value as local display state. No endpoint or
database change is needed. New-thread placeholders (`__default__`) simply omit
the header timestamp until the server-created thread can be resolved.

Message history and live events already normalize their timestamps to `Date`
objects before reaching `MessageBubble`. The bubble will render that existing
value directly, so replay and live messages use the same path.

## Presentation

- The header shows a compact localized date-and-time value with the existing
  `Clock` icon and a translated "started" label.
- Each message shows a localized date and time in a semantic `<time>` element
  above its content. User messages align the time to the right; assistant
  messages align it to the left.
- Invalid or missing timestamps render no time, preserving the current layout
  for legacy records.
- Existing CSS variables and responsive spacing are reused; no new API or
  database schema is introduced.

## Testing

- `ChatView.mount.test.tsx` mocks `getThread` and verifies the header renders a
  fetched `created_at` value.
- `MessageBubble.userQoL.test.tsx` verifies localized times for both roles and
  verifies a missing timestamp does not render a time element.
- Run the focused Vitest files, then the frontend lint/type/build checks.
