# Delivery: same-secret API-key reassignment

Branch: `feature/api-key-team-reassignment`.
Suggested commit / PR title: `feat(api-keys): reassign used keys without moving historical usage`.
Base: existing team-consumption implementation, commit `7f80ce0c599affa11d166399b7c08a21c3f9ad81`.
Deployment remains a separate operator action. The EC2 preparation receipt records the exact committed revision and immutable image; this document contains no credentials.

## Behavior to review

Edit an already-used key in APIs. Its secret, ID, expiry, individual limits and counters remain unchanged. Select a destination team and a valid member, or explicitly choose shared usage. Historical requests remain attributed to their original team/developer, including folded history after raw-log retention. Already executing requests settle their original reservations. A reassignment racing admission or owner forwarding before upstream execution can return HTTP 409 `api_key_attribution_changed`; the rejected forward releases the origin reservation and a client retry is a new admission.

## Verification

- Linux preparation gate (2026-11-10): 150 passed, 2 PostgreSQL-only skips, covering admission, identity, budgets, reports, forwarding, logging and migration round-trips. PostgreSQL selections were separately exercised as recorded below.
- PostgreSQL budget/history/report selection: 27 passed.
- Attribution migration backfill/round-trip on SQLite and PostgreSQL plus guarded downgrade: 3 passed.
- Legacy migration replay and round-trip: passed.
- Offline real-copy migration: 169094 raw rows, 5632 hourly rows and 4 key records preserved; unchanged key records, individual counters and folded token/request totals; no schema drift.
- Architecture, cancellation safety, timing seams, settings tiers and migration topology checks passed.
- Full repository type checking passed in the Linux test image. Windows checks encounter Linux-only APIs and unavailable uvloop; use the Linux result.
- Focused frontend tests: 27 passed; frontend types, lint and build passed during implementation. The broader API-key flow test stalls at initial settings load before the edited dialog. No full frontend-suite success is claimed.
- Independent review traced the forwarding rejection and original-reservation cleanup; no remaining blocking findings. Dedicated end-to-end origin/owner regression: 1 passed, verifying HTTP 409 before upstream dispatch and complete reservation release after reassignment.
- External multi-instance/WebSocket end-to-end transcript and complete Linux local-ci remain release checks.

## Future deployment sequence (not executed)

1. Review and commit the branch, push to the fork, then run the full Linux CI gate specified by CONTRIBUTING.md. Capture the dashboard screenshots required for an upstream PR. Build an immutable image from the reviewed commit; record its digest and the previous image digest.
2. Use a brief maintenance stop for all instances sharing the database. Do not roll mixed old/new forwarding instances: older origins cannot supply the new immutable-attribution proof and upgraded owners reject those keyed forwards with 409.
3. With writers stopped, retain the previous container/image and create a consistent backup or clone of its complete data volume. Keep encryption/configuration files with that backup. Never migrate the sole rollback copy. Keep the existing public endpoint, proxy mapping and client API keys.
4. Start the reviewed image against the cloned volume. Allow Alembic revision `20261109_120000_add_key_attribution_history` to complete offline, then check schema drift. Starting the replacement on the existing ports reopens traffic; health checks continue afterward. Check dashboard access and preserved routing/keys. Recheck team/developer reports, original-secret authentication, shared budget rejection and an in-flight completion across an edit.
5. If offline validation fails before starting the replacement, resume the previous image with its untouched original volume and endpoint. If the replacement has already started, preserve its volume because it may contain new writes; automatic failure recovery still resumes the original volume. Never start the old binary against the migrated volume.
6. After real traffic/reassignments, do not attempt a blind Alembic downgrade: legacy reporting cannot represent split attribution and the migration intentionally refuses unsafe downgrade. Preserve both volumes and logs. Restoring the pre-switch volume excludes writes received during the trial; a rollback retaining those writes needs an explicit reconciliation plan.

Use only the revision-specific `start-codex-lb-reassignment.sh` prepared for this change. The previous `start-codex-lb-switch.sh` and supervisor remain unchanged and target an older release. Preparation and preflight do not start the replacement; only explicitly running the new launcher without `--check` does.
