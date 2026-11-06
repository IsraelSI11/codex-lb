# Team consumption and shared budgets

Status: approved by the user on 2026-11-06; implementation planning.

## Intent and agreed scope

Extend the existing API-key model so development teams and developers have
attributable usage, shareable upstream accounts, and enforced team budgets.
Administration remains central; this is not a separate tenant or organization
system. Developers can belong to multiple teams. Each API key charges exactly
one team and may identify one developer. A team key or service key need not
identify a developer. Clients continue to send a single existing Bearer key.

## Approaches

1. Extend API keys with teams and developer attribution (selected). Reuse key
   routing, usage settlement, and limit windows; add shared team reservations.
   This minimizes changes to proxy contracts and upstream maintenance.
2. Independent tenant/organization layer (rejected for this version). Offers
   independent administration but requires broad authorization and query changes.

## Data and defaults

- Create a protected built-in Default team automatically; its display name can
  change. All existing keys migrate into it without changing their secrets,
  active state, expiry, individual limits, or account/source assignments.
- Use existing dashboard users as developer identities, with many-to-many team
  membership. Membership does not grant dashboard permissions. Central admins
  manage identities and membership using existing access controls.
- Every key has a required team and optional developer identity. Assigning a
  developer requires membership in that team. Key attribution becomes immutable
  once used: create a replacement key to change its team or developer. This is
  an implementation proposal to keep historical limits and rollups unambiguous.
- Membership removal is rejected while that developer has active keys in the
  team; the administrator must deactivate them first. Historical inactive keys
  retain attribution, and reactivation requires current membership. This is an
  implementation proposal to avoid silently cutting off working credentials.
- Migration leaves existing keys without a developer. Historical usage belongs
  to Default and is displayed as unassigned developer usage. Do not invent a
  personal identity from key names or upstream account emails.
- Keep teams, identities, and used keys addressable for historical reporting;
  reject destructive removal when referenced. Disabling a developer continues
  to use the existing owned-key deactivation policy.

## Account and source selection

Assignment grants eligibility, never exclusivity. Several teams and developers
may consume the same upstream account. Effective eligibility is the intersection
of team scope and any explicit key scope; preserve all other routing checks.
A team's unrestricted scope is distinct from an explicitly empty scope: empty
means no eligible resources, not access to all resources. Default starts
unrestricted so migrated keys retain their current behavior. Model sources follow
the same scope semantics as upstream accounts, avoiding an alternative route
around team restrictions. Personal account restrictions use the developer's keys.

All retries, WebSocket/HTTP paths, failover, sticky sessions, and file continuity
must respect the resulting eligibility; an existing session cannot authorize
an account removed from the allowed set. Scope updates invalidate relevant caches.

## Usage and reporting

Each request is recorded once and contributes to its API key, its team, and its
developer when present. These are views of the same usage, not separate charges.
Capture team/developer attribution at reservation time and retain it through
settlement and retries. Reports provide a date range, totals by team, totals by
developer across teams, developer breakdown within a team, and unassigned usage.
Reuse reported token and cost semantics, including missing-usage handling and
warmup exclusions. USD values remain API-equivalent estimates, not subscription
invoices. Preserve historical attribution when memberships change.

## Shared limits

Team limits use the same types, windows, model filters, reset rules, and usage
units as existing key limits. No configured team limits means no added cap.
A request must pass every applicable individual-key and shared-team rule.
Exhausting a team rule blocks new requests for every key in that team until
reset (or an administrator changes/resets the rule). Existing error transport
behavior is retained, with the scope and reset time identified in the message.

Reserve individual and shared budgets atomically in the same database transaction.
Lock counters in deterministic order, respect SQLite writer serialization and
PostgreSQL row locking, and avoid check-then-increment races across workers.
If either scope rejects a request, neither scope retains a partial reservation.
Settlement, cancellation, failure, orphan recovery, and retries settle or release
both scopes exactly once. Already admitted requests finish using the existing
reservation semantics; this is not a promise to interrupt streams at an exact
token threshold. Reset-period transitions cannot charge a newer period for an
older reservation, and usage corrections must not silently reset budget counters.

## Dashboard and authorization

Use existing API-key management permissions for central team/member/budget
administration and existing read permissions for usage, without broadening guest
or Member access. Add team and optional developer selectors to key creation,
show attribution on key details, and expose team/developer totals and breakdowns.
Integrate team management into the existing API area to avoid a new core-nav item.
Reuse existing components, localization, forms, and account selectors.

## Non-goals

- Independent team-admin roles or team-isolated dashboards.
- Automatic detection of the human behind a shared key.
- Automatic project detection or charging one key to multiple teams.
- New vendor integrations, billing, invoicing, or subscription pricing changes.

## Verification and delivery

Cover migration of an existing database, default-team creation, membership and
assignment validation, immutable attribution, shared account routing, report
aggregation without double counting, parallel requests from different keys,
rollback of partial reservations, settlement/release/recovery, period boundaries,
HTTP and WebSocket rejection, permissions, and dashboard forms.

Validate OpenSpec and migration topology; run backend regression tests around
keys/routing/usage and frontend tests, type checking, lint, and build. Verify UI
screenshots before claiming dashboard completion. Keep the upstream remote and
publish the implementation to the user's fork only; no upstream PR is requested.

## Builder-owned choices

Exact table and method names, internal module boundaries, indexes, screen layout,
and narrowly scoped commit structure are implementation choices. Preserve existing
public API fields and defaults and add compatible attribution fields.
