# Same-secret reassignment implementation plan

> Execute task-by-task using subagent-driven-development; this OpenSpec change is the repository SSOT and plan location.

**Goal:** Reassign a used key without changing credentials or moving historical consumption.
**Architecture:** Immutable attribution snapshots; explicit request capture; attribution-aware permanent rollups.
**Tech Stack:** Existing Python/FastAPI/SQLAlchemy/Alembic, SQLite/PostgreSQL, React/TypeScript.
**Spec:** design.md and specs/team-consumption/spec.md in this change.

## Global constraints
No production changes. No credential rotation. Preserve key ID, limits and counters. No historical reassignment or raw-only reconstruction. Existing administrative permissions apply. Keep existing team's reservations stable during an in-flight change.

## Tasks
- [x] 1. Storage and history: add immutable snapshot model and request/hourly attribution columns, safe upgrade/backfill and guarded downgrade; implement deterministic snapshot-ID helper. Add migration round-trip/pruned-history tests; update hourly folds and lifecycle mirrors, snapshot-based team report and identity retention guards. Verify existing time-rollup/report suites.
- [x] 2. Assignment and admission: remove used-key edit prohibition; ensure snapshots for created/reassigned keys, validate membership and preserve counters/secret. Capture immutable ID in ApiKeyData and verify current assignment at admission. Pass the admitted snapshot through every logging/forwarding/turn path, including unlimited requests. Add tests for unchanged secret, cached race, in-flight settlement and all supported surfaces. Do not use late current-key lookup for admitted traffic.
- [x] 3. Dashboard: enable editing after use, add concise explanatory copy/localization, exercise used-key editing and membership selection in focused tests. Verify types, lint and build.
- [x] 4. Integrate and review: A -> B -> A mid-hour raw/folded/retained reports; protected historical identities; new team exhaustion; schema/migration checks; real-copy rehearsal with no upstream traffic; current-head independent review and fixes. Update OpenSpec and docs to final behavior. Do not deploy or push until implementation verification is complete.

## Review focus
Admission racing reassignment; same-hour split and raw retention; old reservation settlement against old limits; stale cached scopes; unchanged keys and counters. Each must have regression coverage rather than helper-only tests.

## Verification evidence (2026-11-09)
- PostgreSQL shared-budget/history/report regressions: 27 passed.
- Legacy migration replay/round-trip and new SQLite migrations: 3 passed.
- New attribution migration SQLite + PostgreSQL backfill/round-trip and downgrade guard: 3 passed.
- Offline real-copy rehearsal: 169094 raw rows, 5632 hourly rows, 4 keys preserved; all key records and budget counters unchanged, folded usage totals unchanged, keyed raw attribution complete; schema drift none.
- OpenSpec strict validation, backend Ruff and formatting checks passed. Focused frontend tests (27), types, lint and build passed during implementation.
- Independent review completed after tracing origin reservation, signed forwarding, owner rejection and origin cleanup; no blocking findings remain. Added an integration regression covering real origin admission, reassignment during forwarding, HTTP 409 at owner/origin, no upstream dispatch and complete original-reservation release. Full external WebSocket transcript not exercised. Existing frontend flow test stalls before the edited dialog; full frontend suite is not claimed passing.
- No EC2 deployment, credential change, commit or push performed for this change.

## Delivery preparation
- Combined regression selection: 146 passed, 1 PostgreSQL-only skip; PostgreSQL-specific selection already passed separately.
- Architecture, cancellation safety, timing seams, settings tiers and migration topology passed.
- App and changed regression tests pass type checking. Full repository type checking on Windows is limited by Linux-specific APIs and unavailable uvloop.
- Deployment/rollback procedure and remaining release checks: [delivery.md](delivery.md). Do not run the previous EC2 switch scripts unchanged for this revision.

## Linux preparation gate (2026-11-10)
- Targeted regression and migration selection: 150 passed, 2 PostgreSQL-only skips (separately covered during implementation).
- Full repository ty check in Linux: passed. Repository Ruff check and format check: passed.
- User authorized commit/push and image/script preparation, without starting deployment. Exact revision/image and remote preflight are recorded in the private EC2 preparation receipt.
