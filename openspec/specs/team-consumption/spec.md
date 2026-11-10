# Team consumption

## Purpose
Attribute developer and shared usage to teams and enforce aggregate budgets.

## Requirements

### Requirement: Team attribution
Every API key SHALL belong to one team and MAY identify one developer who is
a member of that team. A developer MAY be a member of several teams. Shared
team/service keys SHALL be usable without developer attribution.
Membership removal SHALL be rejected while the developer has active keys in
that team. Reactivating a developer key SHALL require current team membership.
Administrators SHALL be able to change the team or developer of used keys without
changing the key secret, ID, expiry, individual limits or counters. Destination
membership SHALL be validated without silently changing the developer.

#### Scenario: Developer serves two teams
- **GIVEN** Ana belongs to Backend and Data and has one key for each
- **WHEN** Ana consumes through the Backend key
- **THEN** usage SHALL contribute once to Backend and Ana, and not to Data

#### Scenario: A used key changes teams
- **GIVEN** a used key assigned to Backend
- **WHEN** its assignment changes to Data
- **THEN** the same Bearer secret SHALL remain usable
- **AND** later admissions SHALL use Data's limits and attribution
- **AND** previous consumption and already admitted requests SHALL retain Backend

### Requirement: Compatible Default team
The system SHALL create a built-in Default team and migrate all existing keys
without changing their secrets, limits, active state, or routing assignments.

#### Scenario: Existing deployment upgrades
- **GIVEN** an existing key with restricted accounts and historical usage
- **WHEN** the migration runs
- **THEN** the key SHALL retain its restrictions and belong to Default
- **AND** historical usage SHALL remain visible without fabricated developer identity

### Requirement: Shared resource eligibility
Team resource assignments SHALL be non-exclusive. Explicit key scope SHALL
only narrow the team's eligible accounts or model sources. Explicitly empty
scope SHALL deny all resources, while unrestricted scope SHALL inherit eligibility.

#### Scenario: Two teams share an account
- **GIVEN** teams Backend and Data are both assigned account B
- **WHEN** either team sends an otherwise eligible request
- **THEN** account B SHALL be eligible without exclusive ownership

### Requirement: Enforced aggregate budgets
Applicable key and team budgets SHALL be reserved atomically and settled or
released exactly once. Exhaustion SHALL reject new requests from the affected
scope until reset or administrative adjustment, preserving existing error transport.

#### Scenario: Several keys exhaust a team budget
- **GIVEN** two keys in one team and an exhausted applicable team limit
- **WHEN** either key sends a new request
- **THEN** the request SHALL be rejected even if its individual limit has capacity

#### Scenario: Concurrent reservation cannot bypass the team limit
- **GIVEN** different keys reserve against the same remaining team budget
- **WHEN** reservations run concurrently across workers
- **THEN** reservations SHALL serialize against shared counters
- **AND** rejected requests SHALL NOT leave partial key or team reservations

### Requirement: Stable usage reporting
Team and developer reports SHALL aggregate actual request attribution without
double counting. Membership changes SHALL NOT reassign historical usage.
Key reassignment SHALL NOT move prior usage, including permanent aggregates whose
raw logs have been pruned. Multiple reassignments within an hour SHALL retain
precise original attribution. Admission racing a changed assignment SHALL fail
with a retryable conflict rather than mixing budget and report identities.

#### Scenario: Developer leaves a team
- **GIVEN** a developer's prior consumption in Backend
- **WHEN** membership changes
- **THEN** prior requests SHALL retain Backend and developer attribution

#### Scenario: Reassignment within one folded hour
- **GIVEN** one key serves Backend, Data, then Backend within the same hour
- **WHEN** that hour is folded and raw logs are pruned
- **THEN** team and developer totals SHALL preserve each request's original assignment


#### Scenario: Forwarding races reassignment before upstream execution
- **GIVEN** an origin reserved a request for team A and forwards its signed attribution
- **WHEN** reassignment to B commits before the owner validates that forward
- **THEN** the owner MAY reject with retryable conflict before upstream execution
- **AND** the origin SHALL release A's reservation without charging B
- **AND** a client retry SHALL be a new admission using the current assignment

### Requirement: Central administration
The dashboard SHALL support team and membership management, key attribution,
eligible resources, shared limits, and team/developer usage using existing
administrative permissions without granting additional access to members or guests.

#### Scenario: Unprivileged user attempts management
- **GIVEN** a principal without the required existing API-key management permission
- **WHEN** the principal attempts a team or membership mutation
- **THEN** the operation SHALL be rejected
