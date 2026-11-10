# Same-secret API-key reassignment

Status: user approved behavior on 2026-11-09, explicitly retaining the same API key.

## Contract
Changing team or developer preserves the Bearer secret, key ID, activation/expiry, individual limits and counters, scopes and existing session identity. Historical usage stays with its original attribution. A request admitted before the change settles against its original team's reservation; a later request uses the destination team's rules. Assignment is atomic with admission. Developer membership must be valid in the destination; do not silently clear or change the developer. Reassignment never resets a shared or individual counter.

## Approaches
Selected: immutable attribution snapshots referenced by raw request logs and hourly usage dimensions. This preserves aggregates after raw-log retention and supports changes inside an hour. Rejected: joining all history to the current key assignment (moves old usage); replacing internal key identities while retaining the secret (risks session identity and individual counters); timestamp-only assignment intervals (cannot split existing hourly aggregates precisely).

## Storage and migration
Add `api_key_attributions` with deterministic immutable ID from `(key_id, team_id, owner_user_id)`, stable key identity, and restrictive references to team/developer. Keep the current assignment on `api_keys`. Insert a snapshot when a key is created or its assignment changes. Referenced historical snapshots protect identities independently of current membership.

Add nullable `api_key_attribution_id` to `request_logs`. Add its sentinel-encoded equivalent to the primary-key grain of `request_usage_hourly_rollups`; all existing readers must retain totals. The migration captures current assignments for existing keys and backfills raw logs and existing folded buckets directly, including buckets whose raw logs have been pruned. It must not reset the fold watermark or regenerate old usage from raw. Initial assignments are knowable because the previous implementation prohibited reassignment of used keys. Unkeyed rows retain NULL/sentinel. Migration downgrade must refuse if a key has multiple attribution snapshots: legacy reporting cannot represent that without moving history. No silent loss of new attribution.

## Admission and persistence
Derive snapshot ID from immutable authenticated `ApiKeyData`. At the serialized admission boundary verify it still equals the current DB assignment; stale cache races fail with an explicit retryable conflict rather than charging one team's budget and another team's report. Invalidating key auth/policy caches on reassignment makes subsequent requests resolve the new assignment. Preserve reservation items' original limit IDs for settlement/release/recovery.

Pass the admitted snapshot explicitly through HTTP, WebSocket turns, compact, image, transcription, model-source and background/forwarding log paths. Do not infer attribution from the current key at completion, from a mutable session-wide value, or from a user-supplied request ID. Concurrent turns need separate immutable snapshots. Capture unlimited-key traffic too. Pre-admission failures can retain the authenticated snapshot but do not reserve budgets.

## Reporting and lifecycle
Reports join immutable snapshots, never current assignments, with the existing raw-tail/folded-watermark split. Folding includes the new dimension. Audit destructive account and cost/model/deletion correction mirrors so changes cannot duplicate or erase dimension-split rows. Old snapshot references retain protected team/developer identities after raw retention. Used keys remain retained/deactivated; attribution_locked remains a permanent used-marker for deletion protection, not a reassignment lock.

## Dashboard
Enable team/developer editing on used keys. Explain that changes affect future requests and preserve previous usage. Keep the existing membership validation. No regeneration or display of a new secret.

## Verification
SQLite and PostgreSQL migration/schema checks; used and unused keys; no secret/ID/counter changes; A -> B -> A within one hour; old in-flight settlement after change; unlimited usage; empty/narrow resource scopes; stale auth/cache admission race; invalid membership; shared-limit exhaustion and rollback; folded data with raw logs removed; date-range and developer report filtering; history-preserving deletion protections; UI tests, types, lint and build. Rehearse migration on an isolated real-data copy with external networking disabled.

## Forwarding race and rollout boundary
A signed forward whose attribution differs from current authentication is cancelled before upstream execution with retryable HTTP 409. The origin releases its original reservation; a retry is a new admission. This exception does not move any executed usage or reservation to the destination team. Rollout uses a maintenance stop across forwarding instances: old origins lack the immutable-attribution proof and are intentionally rejected rather than silently assigned current history.
