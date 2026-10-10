# Household ICS Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Import household-shared ICS calendars from family settings and show their events in education.

**Architecture:** Persist validated ICS sources in an isolated education table. Authorize every request through household membership; parents manage and all members read. Expand recurring events within bounded date ranges in a cancellable process. React Query caches household sources and event ranges.

**Tech Stack:** FastAPI, async psycopg, Alembic raw SQL, icalendar, recurring-ical-events, React Query, React/TypeScript.

---

### Task 1: Parser and recurring events

- Create `tests/unit/server/services/test_education_calendar.py` for all-day end exclusion, timezone/floating dates, recurrence overrides/exclusions, invalid input and limits.
- Run `uv run pytest tests/unit/server/services/test_education_calendar.py -q` and confirm missing feature failure.
- Add dependencies with `uv add icalendar recurring-ical-events python-dateutil`.
- Create `src/server/services/education_calendar_parser.py` and verify focused tests.

### Task 2: Household persistence and APIs

- Create `tests/integration/test_education_calendar_db.py` and HTTP tests in `tests/unit/server/app/education/test_calendar.py` for shared reads, parent management, isolation, duplicate import/update, removal, and date boundaries.
- Create migration `migrations/versions/090_household_calendars.py`, database module `src/server/database/education_calendar.py`, service `src/server/services/education_calendar.py`, and router `src/server/app/education/calendar.py`; register in `src/server/app/setup.py`.
- Run focused unit tests and `uv run pytest tests/integration/test_education_calendar_db.py -m integration -q`.
- Verify Alembic upgrade, downgrade to 089, then upgrade on test database. Apply only the verified upgrade to local development database.

### Task 3: Settings and education UI

- Add frontend contracts, API calls, household/date query keys and hooks in education modules and `web/src/lib/queryKeys.ts`.
- Create `web/src/pages/Education/FamilyCalendarSettings.tsx`, mount in `web/src/pages/Settings/panels/FamilyAccountsTab.tsx`.
- Create shared day-event display and markers in `web/src/pages/Education/EducationNotebook.tsx`.
- Add meaningful frontend tests for import/update/remove/errors, events across child filters and day boundaries, and E2E mobile/desktop coverage.
- Run focused Vitest, Playwright and `pnpm build`.

### Task 4: Verification and delivery

- Run Ruff and focused backend/frontend regression tests; inspect screenshots.
- Verify dev server listens on `0.0.0.0:5177` and LAN HTTP responds.
- Update Chinese `CHANGELOG.md`, stage only feature files, create atomic feature commit; retain unrelated user changes and stay on the feature branch.

## Execution Results

- [x] Parser and recurring event contracts: 13 tests, including DST, floating time, exclusions, moved/cancelled occurrences and malformed rules.
- [x] Household persistence/API and Alembic 090: real PostgreSQL import/share/update/remove and cross-household isolation; downgrade/reupgrade preserves a seeded homework record. Local development database upgraded through Alembic.
- [x] Settings and education UI: 49 frontend tests; household/date cache reuse and invalidation, import errors and shared events across child filters.
- [x] Verification: 72 backend unit tests, 3 PostgreSQL integration tests, 8 browser regressions; 4 new calendar flows also checked in touch-enabled mobile and desktop contexts. Build, lint and LAN 5177 checks passed; screenshots inspected.
