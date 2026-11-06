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

Attribution locks on successful admission, even without configured budgets.
Used keys cannot be reassigned or deleted: deactivate them and create replacement
keys. Referenced developers cannot be deleted: disable their accounts instead.
Preserving these identities makes the existing permanent key rollup dimension a
stable team/developer dimension without duplicating all usage rollup tables.
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
