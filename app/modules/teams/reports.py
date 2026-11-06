"""Team/developer views of retained key usage, without changing budget counters.

Used keys remain addressable and their attribution cannot change. Therefore the
existing permanent key dimensions are also stable team/developer dimensions.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import BigInteger, Integer, cast, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.time import to_utc_naive
from app.db.models import AccountUsageRollupState, ApiKey, RequestLog, RequestUsageHourlyRollup
from app.modules.accounts.usage_time_rollup import (
    _STATE_ROW_ID,
    DIMENSION_SENTINEL,
    HOURLY_BUCKET_SECONDS,
    WARMUP_REQUEST_KINDS,
    _dimension_expr,
    epoch_seconds,
)
from app.modules.accounts.usage_time_rollup_read import ceil_to_grid, floor_to_grid
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
    # Both branches use one statement/snapshot of the watermark. Folded whole
    # hours and raw partial edges/tail remain disjoint, including before backfill.
    lo = ceil_to_grid(since, HOURLY_BUCKET_SECONDS)
    hi = floor_to_grid(until, HOURLY_BUCKET_SECONDS)
    watermark = (
        select(AccountUsageRollupState.hourly_folded_through)
        .where(AccountUsageRollupState.id == _STATE_ROW_ID)
        .scalar_subquery()
    )
    postgres = session.get_bind().dialect.name == "postgresql"
    watermark_epoch = (
        cast(func.extract("epoch", watermark), BigInteger)
        if postgres
        else cast(func.strftime("%s", watermark), Integer)
    )
    least = func.least if postgres else func.min
    greatest = func.greatest if postgres else func.max
    tail_start = greatest(lo, least(func.coalesce(watermark, lo), hi))
    team = func.coalesce(ApiKey.team_id, "default")
    owner = ApiKey.owner_user_id
    filters = []
    if team_id is not None:
        filters.append(team == team_id)
    if developer_id is not None:
        filters.append(owner == developer_id)
    hourly = RequestUsageHourlyRollup
    folded = (
        select(
            team.label("team"),
            owner.label("owner"),
            func.sum(hourly.request_count).label("requests"),
            func.sum(hourly.input_tokens + hourly.output_or_reasoning_tokens).label("tokens"),
            func.sum(hourly.cached_input_tokens).label("cached"),
            func.sum(hourly.cost_usd).label("cost"),
        )
        .select_from(hourly)
        .outerjoin(ApiKey, hourly.api_key_id == _dimension_expr(ApiKey.id))
        .where(
            hourly.bucket_epoch >= epoch_seconds(lo),
            hourly.bucket_epoch < epoch_seconds(hi),
            hourly.bucket_epoch < watermark_epoch,
            hourly.api_key_id != DIMENSION_SENTINEL,
            hourly.request_kind.not_in(WARMUP_REQUEST_KINDS),
            *filters,
        )
        .group_by(team, owner)
    )
    raw = (
        select(
            team,
            owner,
            func.count(),
            func.coalesce(func.sum(RequestLog.input_tokens), 0)
            + func.coalesce(func.sum(func.coalesce(RequestLog.output_tokens, RequestLog.reasoning_tokens, 0)), 0),
            func.coalesce(func.sum(RequestLog.cached_input_tokens), 0),
            func.coalesce(func.sum(RequestLog.cost_usd), 0),
        )
        .select_from(RequestLog)
        .outerjoin(ApiKey, RequestLog.api_key_id == ApiKey.id)
        .where(
            RequestLog.requested_at >= since,
            RequestLog.requested_at < until,
            or_(RequestLog.requested_at < lo, RequestLog.requested_at >= tail_start),
            RequestLog.api_key_id.is_not(None),
            RequestLog.request_kind.not_in(WARMUP_REQUEST_KINDS),
            *filters,
        )
        .group_by(team, owner)
    )
    usage = union_all(folded, raw).subquery()
    rows = await session.execute(
        select(
            usage.c.team,
            usage.c.owner,
            func.sum(usage.c.requests),
            func.sum(usage.c.tokens),
            func.sum(usage.c.cached),
            func.sum(usage.c.cost),
        ).group_by(usage.c.team, usage.c.owner)
    )
    # Only final report dimensions cross the wire, never keys or hourly grains.
    grouped = {(row[0], row[1]): _UsageTotal(row[2], row[3], row[4], row[5]) for row in rows}
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
