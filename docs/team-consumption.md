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

Used key attribution is fixed. Deactivate a used key and create a replacement to
change its team or developer. Deactivate a developer's active team keys before
removing membership; reactivation requires current membership. Disable referenced
developer accounts rather than deleting them, so historical usage stays visible.

Consumption filters select a UTC date range (end date excluded), team, and
developer. Team totals, developer totals across teams, and within-team developer
breakdowns are views of the same requests; do not add these views together.
Shared keys appear as unassigned developer consumption. Warmup traffic is
excluded, retained hourly usage survives raw-log retention, and USD values are
API-equivalent estimates. Partially retained hours have the same edge precision
limits as other dashboard reports.
