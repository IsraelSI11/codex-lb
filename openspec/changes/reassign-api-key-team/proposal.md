# Reassign used API keys without replacing credentials

## Why
Developers move between teams. Requiring a replacement Bearer key forces client configuration changes. Reassigning the current key row alone would incorrectly move all its historical usage.

## What changes
- Permit team/developer reassignment of used keys while preserving the secret, ID and individual counters.
- Capture immutable attribution per admitted request and preserve it in permanent hourly aggregates.
- Existing traffic remains attributed to its original team and developer; new admissions use the new assignment and shared budget.
- Validate membership and prevent stale cached assignments from admitting against mismatched budgets.

## Impact
API-key editing, admission, request logging, team reporting, time rollups and lifecycle mirrors, database migration, historical identity retention. No production deployment is part of implementation.
