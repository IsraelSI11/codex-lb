from datetime import datetime

from pydantic import Field

from app.modules.api_keys.schemas import LimitRuleCreate, LimitRuleResponse
from app.modules.shared.schemas import DashboardModel


class TeamCreate(DashboardModel):
    name: str = Field(min_length=1, max_length=128)


class TeamUpdate(DashboardModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    assigned_account_ids: list[str] | None = None
    assigned_source_ids: list[str] | None = None
    limits: list[LimitRuleCreate] | None = None
    reset_usage: bool = False


class MemberCreate(DashboardModel):
    user_id: str


class TeamResponse(DashboardModel):
    id: str
    name: str
    assigned_account_ids: list[str] | None
    assigned_source_ids: list[str] | None
    member_user_ids: list[str]
    limits: list[LimitRuleResponse]


class ConsumptionTotal(DashboardModel):
    team_id: str | None = None
    owner_user_id: str | None = None
    request_count: int = 0
    total_tokens: int = 0
    cached_input_tokens: int = 0
    total_cost_usd: float = 0


class ConsumptionReport(DashboardModel):
    start: datetime
    end: datetime
    teams: list[ConsumptionTotal]
    developers: list[ConsumptionTotal]
    breakdown: list[ConsumptionTotal]
    unassigned: list[ConsumptionTotal]


class DeveloperResponse(DashboardModel):
    id: str
    name: str
    status: str
