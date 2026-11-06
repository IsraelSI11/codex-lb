from datetime import datetime

from fastapi import APIRouter, Depends, Response

from app.core.auth.dashboard_access import Permission
from app.core.auth.dependencies import (
    require_dashboard_permission,
    require_dashboard_write_access,
    set_dashboard_error_format,
    validate_dashboard_session,
)
from app.core.exceptions import DashboardBadRequestError
from app.dependencies import TeamsContext, get_teams_context
from app.modules.teams.reports import consumption_report
from app.modules.teams.schemas import (
    ConsumptionReport,
    DeveloperResponse,
    MemberCreate,
    TeamCreate,
    TeamResponse,
    TeamUpdate,
)

router = APIRouter(
    prefix="/api/teams",
    tags=["dashboard"],
    dependencies=[
        Depends(validate_dashboard_session),
        Depends(require_dashboard_permission(Permission.API_KEYS_READ)),
        Depends(set_dashboard_error_format),
    ],
)


@router.get("", response_model=list[TeamResponse], include_in_schema=False)
@router.get("/", response_model=list[TeamResponse])
async def list_teams(context: TeamsContext = Depends(get_teams_context)) -> list[TeamResponse]:
    return await context.service.list_all()


@router.post(
    "", response_model=TeamResponse, include_in_schema=False, dependencies=[Depends(require_dashboard_write_access)]
)
@router.post("/", response_model=TeamResponse, dependencies=[Depends(require_dashboard_write_access)])
async def create_team(payload: TeamCreate, context: TeamsContext = Depends(get_teams_context)) -> TeamResponse:
    return await context.service.create(payload.name)


@router.get("/developers", response_model=list[DeveloperResponse])
async def developers(context: TeamsContext = Depends(get_teams_context)) -> list[DeveloperResponse]:
    rows = await context.repository.developers()
    return [DeveloperResponse(id=row.id, name=row.display_name or row.username, status=row.status) for row in rows]


@router.get("/usage", response_model=ConsumptionReport)
async def usage(
    start: datetime,
    end: datetime,
    team_id: str | None = None,
    developer_id: str | None = None,
    context: TeamsContext = Depends(get_teams_context),
) -> ConsumptionReport:
    from app.core.utils.time import to_utc_naive

    if to_utc_naive(start) >= to_utc_naive(end):
        raise DashboardBadRequestError("Start must precede end")
    return await consumption_report(context.session, start, end, team_id, developer_id)


@router.patch("/{team_id}", response_model=TeamResponse, dependencies=[Depends(require_dashboard_write_access)])
async def update_team(
    team_id: str, payload: TeamUpdate, context: TeamsContext = Depends(get_teams_context)
) -> TeamResponse:
    return await context.service.update(team_id, payload)


@router.delete("/{team_id}", dependencies=[Depends(require_dashboard_write_access)])
async def delete_team(team_id: str, context: TeamsContext = Depends(get_teams_context)) -> Response:
    await context.service.delete(team_id)
    return Response(status_code=204)


@router.post("/{team_id}/members", response_model=TeamResponse, dependencies=[Depends(require_dashboard_write_access)])
async def add_member(
    team_id: str, payload: MemberCreate, context: TeamsContext = Depends(get_teams_context)
) -> TeamResponse:
    return await context.service.add_member(team_id, payload.user_id)


@router.delete(
    "/{team_id}/members/{user_id}", response_model=TeamResponse, dependencies=[Depends(require_dashboard_write_access)]
)
async def remove_member(team_id: str, user_id: str, context: TeamsContext = Depends(get_teams_context)) -> TeamResponse:
    return await context.service.remove_member(team_id, user_id)
