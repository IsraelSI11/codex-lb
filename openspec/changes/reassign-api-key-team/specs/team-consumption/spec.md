## MODIFIED Requirements

### Requirement: Team attribution
Every API key SHALL belong to one team and MAY identify a developer who is a member of that team. Administrators SHALL be able to reassign an already-used key while retaining its secret, ID, individual limits and counters. Invalid destination membership SHALL reject the edit without partial mutation.

#### Scenario: A used key moves teams
- **GIVEN** a key with prior consumption in team A
- **WHEN** an administrator changes its assignment to team B
- **THEN** the same Bearer key SHALL remain valid
- **AND** subsequent admitted requests SHALL use B's limits and attribution
- **AND** existing individual counters SHALL remain unchanged

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

### Requirement: Stable usage reporting
Every admitted request SHALL retain its immutable team and developer attribution through completion, retries, aggregation and raw-log retention. Reassignment SHALL NOT move historical usage. Reports SHALL preserve precise attribution for multiple changes within one hourly bucket.

#### Scenario: Reassignment while a request is in flight
- **GIVEN** a request admitted under A's shared budget
- **WHEN** its key is reassigned to B before completion
- **THEN** that request SHALL settle once against A and remain in A's reports
- **AND** a newly admitted request SHALL use B

#### Scenario: Same-hour changes survive retention
- **GIVEN** one key serves A, then B, then A during one UTC hour
- **WHEN** its usage is folded and raw logs are pruned
- **THEN** each request's original team and developer SHALL remain correctly reported without double counting

#### Scenario: A cached old assignment races an edit
- **GIVEN** authenticated data for A and a committed reassignment to B
- **WHEN** admission sees a mismatched assignment
- **THEN** it SHALL reject with a retryable conflict without reserving or executing under mismatched attribution

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
