# Textbook Start Learning Implementation Plan

**Goal:** Show a Mentrix-style learning prompt for knowledge points without a lecture, with summary, standard, deep and custom modes.

**Architecture:** Add a scoped learning-start component to the shared book reader. Keep the existing generation API and parent permission gate. Custom mode expands depth and requirements controls below the split button; presets submit immediately. Existing lecture replacement retains its confirmation flow. Source directories remain readable.

**Tech Stack:** React, existing Radix dropdown primitives, lucide, CSS theme tokens, Vitest.

## Steps

1. Add failing coverage for the empty lecture screen, all preset payloads, custom inline controls, disabled/student controls, and knowledge navigation without a source fetch.
2. Add the centered icon, ready status, guidance and split start/mode button, with inline custom controls and pending handling. Compose it in BookReader and bypass source fallback for knowledge learning.
3. Disable unnecessary source fetching on empty knowledge selections. Keep parent and student permissions, existing lectures and explicit source navigation intact.
4. Run focused tests, typecheck and ESLint. Verify desktop and mobile, menu, custom expansion and navigation in the browser without starting real generation. Update the Chinese changelog and make an atomic commit.
