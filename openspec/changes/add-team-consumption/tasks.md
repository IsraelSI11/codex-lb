# Team Usage and Budgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Follow test-driven-development, with a fresh whole-branch review at completion.

**Goal:** Attribute proxy consumption to teams/developers and enforce shared team budgets while retaining existing clients and keys.

**Architecture:** Extend API-key attribution with teams and existing dashboard identities. Resolve team/key eligibility together, capture stable request attribution, and extend the existing reservation lifecycle to reserve and settle team counters in the same transaction as key counters. Keep administration central in the existing API dashboard area.

**Tech Stack:** Python >=3.13, FastAPI, SQLAlchemy, Alembic, SQLite/PostgreSQL, React, TypeScript, TanStack Query, Zod, pytest, Vitest, Bun.

**Spec:** [design.md](design.md), [team-consumption spec](specs/team-consumption/spec.md).

## Global Constraints

- Branch: `feature/team-usage-and-budgets`, based on upstream `main` at `72630bbfeee9e3b0d9acfb95e2b1e706b8b0188e`; upstream has no `develop`.
- Follow `.github/CONTRIBUTING.md`, `.agents/conventions/git-workflow.md`, project conventions, and OpenSpec-first.
- No new required configuration, credentials, environment settings, README sections, core-nav items, or runtime dependencies.
- Use typed schemas, dataclasses, request-scoped repositories, existing permission guards, and ISO datetime responses.
- Existing keys, clients, limits, scope semantics, missing-usage behavior, and error transport remain compatible.
- Key membership is validated on creation/reactivation; active keys block membership removal. Used key attribution cannot be reassigned.
- Use Conventional Commits; keep each concern reviewable. Do not open an upstream PR or merge branches.
- This is a coordinated feature branch; eventual upstream submission should be split into schema/management, enforcement/reporting, and dashboard PRs as appropriate. Intermediate stages are not the completed feature.

## Review Focus

1. Different keys racing for the same team's remaining budget, including multi-worker PostgreSQL execution.
2. Key deletion, identity deletion, or membership changes losing personal/team history after raw-log retention.
3. Cached key authorization, sticky sessions, files, retries, and alternate model sources escaping tightened team scope.
4. Period resets or administrator limit edits while reservations are in flight, including stale recovery and duplicate settlement.
5. Dashboard/API permissions accidentally exposing identity details or granting team membership administrative powers.

## Task 1: Persistence, Default migration, and administration

**Files:** Modify `app/db/models.py`, `app/dependencies.py`, `app/main.py`; create `app/modules/teams/{__init__,schemas,repository,service,api}.py`, a new Alembic revision, `tests/integration/test_teams_api.py`, and `tests/integration/test_team_consumption_migration.py`.

**Interfaces:** `Team` with protected Default identity, `TeamMembership(team_id, user_id)`, non-exclusive team account/source assignments, required `ApiKey.team_id` with Default default. API-key `owner_user_id` is the developer identity rather than a duplicate owner field. Team routes under `/api/teams` use existing API-key management/delegation rules and dashboard read constraints. Mutation responses use typed schemas.

- [x] Write service/API/migration tests: Default exists exactly once; existing key secret, limits and assignments survive; a user joins two teams; unknown users/resources fail; unauthorized management is rejected; referenced teams/identities cannot be destructively removed.
- [x] Run the new focused tests before implementation and confirm missing-feature failures.
- [x] Implement tables, forward migration at the freshly inspected Alembic head, central team/membership/resource routes, and request-scoped dependencies. Keep default team creation idempotent and historical upgrade work bounded.
- [x] Run `uv run pytest tests/integration/test_teams_api.py tests/integration/test_team_consumption_migration.py -q`; expect all passing. Run database upgrade/check and `python scripts/check_migration_topology.py` with the required script arguments from `make lint`; expect one valid head.
- [x] Review diff and make a scoped Conventional Commit only when authorized to commit.

## Task 2: Key attribution and effective eligibility

**Files:** Modify `app/modules/api_keys/{schemas,service,repository,api}.py`, `app/core/auth/api_key_cache.py`, existing proxy eligibility/selection entry points, and cache invalidation machinery. Extend key service/API and proxy eligibility tests; add `tests/integration/test_team_key_scopes.py`.

**Interfaces:** API-key create/response adds `team_id` and `owner_user_id`; omitted team means Default. The auth-side key snapshot includes effective account/source eligibility, without changing the stored explicit key assignments. `resolve_effective_scope(team_ids: Collection[str] | None, key_ids: Collection[str] | None) -> frozenset[str] | None` treats None as unrestricted and empty as deny-all.

- [x] Write tests for membership validation, service keys without owner, immutable used attribution, active-key membership removal rejection, reactivation after removal rejection, and backward-compatible omitted team.
- [x] Write scope tests: both unrestricted, team-only, key-only, intersection, explicit empty, shared account B, model sources, and cache invalidation after scope changes. Include sticky/file continuity and retries that previously selected a now-disallowed account.
- [x] Run tests to confirm failures; implement attribution validation and central effective-scope resolution through the canonical auth/selection paths rather than patching each protocol independently.
- [x] Run `uv run pytest tests/unit/test_api_keys_service.py tests/unit/test_api_keys_repository.py tests/integration/test_api_keys_api.py tests/unit/test_proxy_account_eligibility.py tests/integration/test_team_key_scopes.py -q`; expect all passing.
- [x] Review diff and make a scoped Conventional Commit only when authorized to commit.

## Task 3: Atomic shared budgets and complete reservation lifecycle

**Files:** Extend reservation models and add a new migration when needed; modify `app/modules/api_keys/{service,repository}.py`, reuse `limit_windows.py`, add focused team budget helpers under `app/modules/teams/`, and extend the existing reset/recovery scheduler. Add `tests/integration/test_team_budget_reservations.py` and `tests/unit/test_limit_windows.py`.

**Interfaces:** Team limit input/response reuses existing `LimitRuleCreate`/`LimitRuleResponse` semantics. Persist team reservation items linked to the same canonical request reservation. `enforce_limits_for_request` retains its public signature; settlement/release/recovery APIs operate on both scopes. Error message identifies team scope and reset time, keeping the existing HTTP/WebSocket envelopes.

- [x] Write tests for exhausted team with unexhausted key; unconfigured key plus configured team; unaffected other team; model-filtered rule; resets; simultaneous keys using independent sessions; key rejection rolling back team allocation and vice versa.
- [x] Write lifecycle tests for actual usage settlement, cancellation, failed upstream requests, repeated settlement, stale recovery, mid-flight rule removal/edit/reset, and reservation period boundaries. Run and confirm missing behavior.
- [x] Implement shared limits without duplicating the key accounting algorithm. Acquire deterministic locks, reserve both scopes in one transaction, retain attribution, and include both scopes in every existing finalization/recovery path. Preserve no-limit fast paths and warmup exclusions.
- [ ] Run `uv run pytest tests/integration/test_team_budget_reservations.py tests/unit/test_limit_windows.py tests/unit/test_api_keys_service.py tests/unit/test_api_keys_repository.py tests/unit/test_proxy_api_key_usage.py tests/unit/test_proxy_api_key_usage_virtual_time.py -q`; expect passing. Run new concurrency tests with SQLite and PostgreSQL; PostgreSQL evidence is required before PR readiness.
- [x] Add HTTP/WebSocket integration rejection assertions to the existing proxy tests and run them; expect the existing rate-limit envelopes with team-specific reset messages.
- [x] Review diff and make a scoped Conventional Commit only when authorized to commit.

## Task 4: Stable team and developer consumption reports

**Files:** Modify request-log/rollup models and migrations as needed; inspect and extend existing `app/modules/accounts/usage_rollup.py`, `usage_time_rollup.py`, request log ingestion, and `app/modules/reports/` read paths. Add typed report schemas/routes in `app/modules/teams/` and `tests/integration/test_team_consumption_reports.py`.

**Interfaces:** `GET /api/teams/usage` takes explicit start/end datetimes and optional team/developer filters. Typed response returns team totals, developer totals across teams, within-team breakdown, and unassigned developer totals using existing usage units. Store immutable attribution at admission/log persistence and preserve it in rollups that outlive raw logs.

- [x] Write fixtures with Ana in two teams, a shared key, service key, multiple upstream accounts, missing usage, warmup traffic, deleted raw logs, and identity/membership changes. Assert one request counts once per view; no team receives another team's usage; personal totals include both teams; unassigned stays explicit.
- [x] Run tests to confirm missing behavior. Implement stable dimensions/backfill and bounded aggregation using existing retained rollups rather than unbounded raw-log scans. Do not reprice or reset budget counters as a reporting side effect.
- [x] Run `uv run pytest tests/integration/test_team_consumption_reports.py tests/integration/test_request_usage_rollup_parity.py tests/integration/test_api_keys_trends_api.py tests/integration/test_usage_summary.py -q`; expect all passing.
- [x] Review diff and make a scoped Conventional Commit only when authorized to commit.

## Task 5: Dashboard, documentation, and whole-branch verification

**Files:** Extend `frontend/src/features/api-keys/{api,schemas}.ts`, existing key create/edit/table components, `frontend/src/features/apis/components/apis-page.tsx`; create `frontend/src/features/teams/` API/hooks/schemas and focused management/report components. Update existing localization catalogs, form tests, and mocks; add spec-backed `docs/team-consumption.md` and before/after screenshots.

**Interfaces:** Team picker defaults to Default; owner picker lists team members and permits shared/service keys. Team administration and usage live inside the existing APIs area. Reuse account/model-source selection and limit-rule editors; UI restrictions mirror server permissions. Show team/developer usage and clear shared-budget exhaustion/reset feedback.

- [x] Write failing form/render tests for default selection, team and owner validation, shared key creation, membership blocking, team resource/limit edits, loading/error/empty states, usage filters, and permission restrictions.
- [x] Implement UI with existing components/localization and no new dependencies or navigation item. Keep used-key attribution read-only; provide guidance to create a replacement key.
- [ ] Run focused frontend tests, then `bun run test`, `bun run typecheck`, `bun run lint`, and `bun run build` from `frontend/`; expect all passing. Capture and visually inspect before/after views at desktop/mobile sizes.
- [x] Sync normative requirements into `openspec/specs/team-consumption/`, keep rationale in context/design, and link user docs to that spec. Validate with `openspec validate --specs` and strict change validation. Do not edit CHANGELOG or release versions.
- [ ] Run focused backend regressions followed by the project's unit/integration suites and `uv run pre-commit run local-ci --hook-stage manual --all-files` (or equivalent documented jobs if host tools prevent the wrapper). Report every unavailable gate explicitly rather than claiming PR readiness.
- [ ] Obtain one fresh whole-branch code review; fix material findings with regression tests. Check migration topology, type/lint checks, diff whitespace and tracked secrets before publication.
- [ ] Publish only the approved feature branch to the user's fork; no upstream PR, merge, tags, or release. Archive OpenSpec only after verification succeeds.

## Execution record

- 2026-11-06: User approved design and requested a readable feature branch following CONTRIBUTING. Created branch from upstream/main because CONTRIBUTING explicitly requires main and no develop branch exists.
- Initial baseline: dependencies installed with uv; existing key unit tests passed 100. Team API tests ran RED (4 failures).
- 2026-11-06 implementation: Default migration, many-to-many memberships, key attribution, effective scopes, shared limit ownership, and centralized APIs implemented. Team API plus baseline passed 104, expanded focused set passed 113; shared budget tests expanded to 12 SQLite passes including HTTP rejection, concurrency, settlement/release/failure, rollback, stale recovery, and period reset.
- PostgreSQL 17 disposable localhost container: 22 collected team tests passed (including independent-session concurrency). Migration legacy-key preservation and downgrade/re-upgrade test passed; upgrade/check reported no drift.
- Reporting retains used keys/developers and locks attribution at admission, reusing existing permanent key rollups instead of duplicating dimensions. Multi-team totals and raw-retention parity passed.
- Dashboard uses existing APIs area and editors, with no new core navigation/dependencies. Form tests ran RED for missing Team selector, then 31 form tests and 3 panel tests passed; full frontend suite in progress with four workers. Before desktop/mobile screenshots captured.
- Native Windows full backend collection cannot run Unix-only uvloop/fcntl files and broad supported runs showed failures; these are not green gates. An isolated Linux container is being prepared for authoritative full backend checks. Full-suite, final screenshots, docs validation and publication remain in progress.
- Routine decisions: preserve historical attribution via immutable, retained used keys and referenced identities; use one generalized limit table and existing reservation item lifecycle for both scopes; use an admission-time one-shot attribution lock to close the delayed last-used update race. Final independent review belongs to coordinator after worker settlement, per dispatch instruction.

- 2026-11-06 final regressions: complete team/API/migration/reporting set passed 67; key service/repository/proxy/file-continuity/scope set passed 149; additional cache/peer-invalidation/scope set passed 9. PostgreSQL 22-pass evidence predates the final identity-lock/error-order adjustments; Docker later failed with HTTP 500 and its Linux engine pipe disappeared, preventing the final PostgreSQL rerun and authoritative Linux suite completion.
- Admission-versus-attribution race reproduced RED (edit wrongly succeeded), then GREEN after key-row serialization and a second immutable-usage check. Final race/API/budget/repository set passed 32. Existing disabled-owner API regression reproduced RED (400 instead of existing 409); reordered validation to preserve the established owner_disabled transport and reran identity regressions.
- Frontend focused management/forms/inventory passed 38, then detail/management/isolated route-scroll passed 22. Full run initially passed 1661 with one mock-inventory failure (fixed); later host-loaded full run passed 1656 with six timeouts. Sequential diagnosis cleared APIs/dashboard/firewall, and isolated route-scroll passed; the same two API-key flow tests also fail on an untouched upstream/main git-archive baseline. These are not a green full-suite claim.
- Final normal-state screenshots captured and visually inspected at desktop/mobile, team administration, and key creation; source selectors have settled fixtures and footer readiness/usage freshness are healthy. Existing baseline before screenshots remain available. Impeccable mechanical detector returned no findings. Frontend typecheck, lint and production build passed.
- Final SQLite upgrade/check: migration_policy=ok, schema_drift=none. Five architecture/topology scripts passed, one head at 20261106_120000_add_team_consumption. Ruff check/format passed; scoped application/new-test ty passed; full Windows ty has 14 diagnostics exclusively in unchanged POSIX-only tools/tests.
- Exact CI-pinned OpenSpec 1.11.0 validation passed 68 specs with zero failures; strict feature and change validation passed. The change stays active until whole-branch review and outstanding global gates are resolved.
- Ruling: service behavior is covered through real API/database integration tests rather than a separate mocked team-service module; team windows reuse the existing test_limit_windows.py and common accounting implementation rather than duplicate a team-specific window suite. This gives stronger end-to-end coverage with less duplicated machinery.
- Ruling: preserve existing key assignment form semantics (empty submitted assignments clear its enabled restriction); the effective resolver distinguishes an enabled empty key scope from unrestricted, and new team scopes explicitly distinguish null/empty. Changing the existing key request contract would violate client compatibility.
- Ruling: retain referenced dashboard identities and immutable used keys, with a RESTRICT owner foreign key, rather than duplicate historical dimensions into every rollup. Updated dashboard/SCIM owned-key fixtures to represent migrated Default memberships and changed deletion assertions to the approved retention contract.
- Ruling: coordinator dispatches the fresh whole-branch reviewer after this worker settles. No independent reviewer or worktree was created, per explicit dispatch ownership.

- Final regression fixes: preserved the existing disabled-owner 409 error; all dashboard-user API tests completed in a 62-pass run before the schema replay failure. Lost-ledger recovery ran RED on the new teams table, then GREEN after making the new revision idempotent; final full schema plus strengthened migration tests passed 22. Migration assertions now preserve legacy resource assignments and limit IDs/counters, removed memberships and non-Default attribution on replay, and schema parity after downgrade/re-upgrade.
- Final retention audit: expired-invite cleanup could hit the new RESTRICT references; two focused tests ran RED, then the conditional purge was narrowed to unreferenced identities. All team API plus established expiry/owner-error regressions passed 23. SCIM owned-key regressions passed 3; final shared window tests passed 20; mixed-account/missing-usage/report-filter/fold parity passed 3.
- Final feature slice passed 44; final key/proxy/file-continuity/scope slice passed 149; cache/sticky/peer invalidation slice passed 9. Final wheel rebuilt and assets plus team migration/module verified. Global gates and independent review remain explicitly outstanding in .local/team-consumption-implementation-report.md; no OpenSpec archive or PR-readiness claim.

- Publication checkpoint: authorized scoped commits created: 4ea9c07 (OpenSpec/docs), 6e91167 (backend/migration/regressions), 02b8dbc (dashboard). Credential-pattern scan and diff whitespace check completed; remaining unchecked items retain unavailable global gates and coordinator-owned independent review. Publishing only origin feature/team-usage-and-budgets; archive deferred.
