# Team consumption context

Teams are central administrative scopes, not tenants or dashboard roles. Existing
clients continue using their Bearer key. Default is created during migration and
preserves the assignments and limits of migrated keys.

An upstream account or model source can be shared by several teams. `null` scope
means unrestricted, while an empty list denies every resource. Authentication
snapshots intersect team and key scopes; stored key assignments are unchanged.
Changes invalidate the existing distributed API-key cache namespace.

Team limits use the existing limit table with exactly one key or team owner. A
single canonical reservation holds both kinds of items, ordered by limit ID.
Conditional counter updates and transaction rollback prevent partial admission.
The existing reset, settlement, failure, release and orphan recovery paths handle
both scopes. Already-admitted streams retain the established reservation contract.

Successful admission retains a permanent used-key marker, even without budgets,
so used keys must be deactivated rather than deleted. Keys can change team or
developer while retaining their secret and individual counters. Immutable
attribution snapshots are captured per request and retained in the hourly grain;
reports join snapshots instead of current key assignments. A stale authenticated
snapshot at admission fails with a retryable 409 before any reservation or upstream
execution. Already admitted streams retain their old snapshot and reservation items.
Referenced developers/teams remain protected even after current keys move away.
Migration backfills existing folded buckets directly, preserving pruned history.
Downgrade refuses multiple historical assignments rather than silently moving them.
Existing historical orphan-key usage is attributed to Default without a developer.
Membership removal requires deactivation of active keys; reactivation requires
current membership and an enabled owner.

Reports combine retained hourly rollups with their disjoint raw tail, using the
existing watermark partition and token/cost semantics. Warmup is excluded. UTC
date ranges are half-open. Partial hour edges have the same retention caveat as
other dashboard reports: pruned sub-hour detail cannot be reconstructed.

For example, Ana belongs to Backend and Data. Her Backend key charges Backend
and her personal total, while her Data key charges Data and the same personal
total. A shared key contributes to its team and explicit unassigned usage.
USD figures are API-equivalent estimates, not subscription invoices.
