# Teams, developers, and shared budgets

Behavior is governed by the [team consumption specification](../openspec/specs/team-consumption/spec.md).

Open **APIs → Teams and consumption**. Administrators and operators can expand
team management to create or rename teams, manage developer memberships, choose
eligible upstream accounts/model sources, and configure shared budgets. Team
membership does not grant dashboard access or additional permissions.

Every key belongs to one team. Existing keys belong to the protected Default
team; their secrets, limits, and routing assignments are preserved. When creating
a key, select its team and optionally a developer who belongs to that team.
Leave the developer unset for shared or service use. A developer may belong to
several teams and have a separate key for each.

A team resource scope can be unrestricted or explicitly restricted. A restricted
scope with no selected resources denies access to every resource. Key scopes
can only narrow team eligibility. Accounts and sources are shared eligibility,
not exclusive ownership; several teams can select the same account.

Configure shared limits using the same types, model filters, and windows as key
limits. No team rules means no additional cap. A request must pass every
applicable key and team rule. Exhaustion blocks new requests for all affected
keys until reset or administrative adjustment. The shared-budget display shows
current usage, capacity, and reset time. Resetting a budget starts a new counter
period without repricing or changing usage reports. Already admitted streams
finish under the existing reservation policy.

Edit a key to change its team or developer, including after it has been used.
The same API key remains valid and individual limits/counters are preserved.
The change applies to future admissions: historical consumption stays with its
original team/developer, and requests already in flight finish against their
original team budgets. The selected developer must belong to the destination
team; choose a member or explicitly select shared usage. A request racing the
edit may receive `api_key_attribution_changed` (409); retry it with fresh policy.
This also applies to internal forwarding rejected before upstream execution;
the origin releases its original reservation. Upgrade all forwarding instances
together during a maintenance stop; mixed old/new attribution protocols are
not supported for keyed forwards.
Deactivate or reassign a developer's active team keys before removing membership;
reactivation requires current membership. Disable historically referenced
developer accounts rather than deleting them, so historical usage stays visible.

Consumption filters select a UTC date range (end date excluded), team, and
developer. Team totals, developer totals across teams, and within-team developer
breakdowns are views of the same requests; do not add these views together.
Shared keys appear as unassigned developer consumption. Warmup traffic is
excluded, retained hourly usage survives raw-log retention, and USD values are
API-equivalent estimates. Partially retained hours have the same edge precision
limits as other dashboard reports.
