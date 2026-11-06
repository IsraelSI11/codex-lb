# Team consumption and shared budgets

## Why

API keys already have individual limits and upstream account assignments, but
several developers' keys cannot currently share a team budget or attribution.

## What changes

- Add Default and custom teams, multi-team developer membership, and key attribution.
- Add shared non-exclusive account/model-source eligibility and team budgets.
- Preserve request attribution for team and personal reporting.
- Extend the existing central dashboard and migrate existing keys compatibly.

## Impact

Database migration, API-key contracts, proxy reservation and settlement paths,
scope invalidation, usage aggregates, dashboard forms, tests, and documentation.
Design and acceptance criteria are specified in design.md and specs/team-consumption/spec.md.
