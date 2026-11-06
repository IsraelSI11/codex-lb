"""Team/developer views of retained key usage, without changing budget counters.

Used keys remain addressable and their attribution cannot change. Therefore the
existing permanent key dimensions are also stable team/developer dimensions.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.time import to_utc_naive
from app.db.models import ApiKey, RequestLog
from app.modules.accounts.usage_time_rollup import WARMUP_REQUEST_KINDS, from_dimension
from app.modules.accounts.usage_time_rollup_read import raw_windows_clause, read_hourly_window
from app.modules.teams.schemas import ConsumptionReport, ConsumptionTotal


@dataclass(slots=True)
class _UsageTotal:
    requests: int = 0
    tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: "_UsageTotal") -> None:
        self.requests += other.requests
        self.tokens += other.tokens
        self.cached_tokens += other.cached_tokens
        self.cost_usd += other.cost_usd

    def response(self, team: str | None = None, owner: str | None = None) -> ConsumptionTotal:
        return ConsumptionTotal(
            team_id=team,
            owner_user_id=owner,
            request_count=self.requests,
            total_tokens=self.tokens,
            cached_input_tokens=self.cached_tokens,
            total_cost_usd=round(self.cost_usd, 6),
        )


async def consumption_report(
    session: AsyncSession, start: datetime, end: datetime, team_id: str | None, developer_id: str | None
) -> ConsumptionReport:
    since, until = to_utc_naive(start), to_utc_naive(end)
    keys = list((await session.execute(select(ApiKey.id, ApiKey.team_id, ApiKey.owner_user_id))).all())
    attribution = {row.id: (row.team_id, row.owner_user_id) for row in keys}
    folded, windows = await read_hourly_window(session, since, until)
    # One aggregate per key, including the disjoint raw tail and partial edges.
    totals: dict[str, _UsageTotal] = defaultdict(_UsageTotal)
    for row in folded:
        if row.request_kind in WARMUP_REQUEST_KINDS:
            continue
        key_id = from_dimension(row.api_key_id)
        if key_id is None:
            continue
        totals[key_id].add(
            _UsageTotal(
                row.request_count,
                row.input_tokens + row.output_or_reasoning_tokens,
                row.cached_input_tokens,
                row.cost_usd,
            )
        )
    if windows:
        rows = await session.execute(
            select(
                RequestLog.api_key_id,
                func.count(),
                func.coalesce(func.sum(RequestLog.input_tokens), 0)
                + func.coalesce(func.sum(func.coalesce(RequestLog.output_tokens, RequestLog.reasoning_tokens, 0)), 0),
                func.coalesce(func.sum(RequestLog.cached_input_tokens), 0),
                func.coalesce(func.sum(RequestLog.cost_usd), 0),
            )
            .where(raw_windows_clause(windows), RequestLog.request_kind.not_in(WARMUP_REQUEST_KINDS))
            .group_by(RequestLog.api_key_id)
        )
        for row in rows:
            if row[0] is not None:
                totals[row[0]].add(_UsageTotal(row[1], row[2], row[3], row[4]))
    grouped: dict[tuple[str, str | None], _UsageTotal] = defaultdict(_UsageTotal)
    for key_id, values in totals.items():
        dimensions = attribution.get(key_id, ("default", None))
        if team_id is not None and dimensions[0] != team_id:
            continue
        if developer_id is not None and dimensions[1] != developer_id:
            continue
        grouped[dimensions].add(values)
    teams: dict[str, _UsageTotal] = defaultdict(_UsageTotal)
    developers: dict[str, _UsageTotal] = defaultdict(_UsageTotal)

    breakdown = []
    unassigned = []
    for (team, owner), values in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1] or "")):
        breakdown.append(values.response(team, owner))
        teams[team].add(values)
        if owner is not None:
            developers[owner].add(values)
        if owner is None:
            unassigned.append(values.response(team))
    return ConsumptionReport(
        start=start,
        end=end,
        teams=[values.response(team) for team, values in sorted(teams.items())],
        developers=[values.response(owner=owner) for owner, values in sorted(developers.items())],
        breakdown=breakdown,
        unassigned=unassigned,
    )
