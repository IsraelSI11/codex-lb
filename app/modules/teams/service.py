import json
from uuid import uuid4

from app.core.auth.api_key_cache import get_api_key_cache
from app.core.cache.invalidation import NAMESPACE_API_KEY, bump_cache_invalidation
from app.core.exceptions import DashboardBadRequestError, DashboardConflictError, DashboardNotFoundError
from app.core.utils.time import utcnow
from app.db.models import Team, TeamMember
from app.modules.api_keys.repository import ApiKeysRepository
from app.modules.api_keys.schemas import LimitRuleResponse
from app.modules.api_keys.service import LimitRuleInput, _limit_input_to_row, _validate_unique_limit_rule_identities
from app.modules.teams.repository import TeamsRepository
from app.modules.teams.schemas import TeamResponse, TeamUpdate


class TeamsService:
    def __init__(self, repository: TeamsRepository) -> None:
        self.repo = repository

    async def require(self, team_id: str) -> Team:
        team = await self.repo.get(team_id)
        if team is None:
            raise DashboardNotFoundError("Team not found")
        return team

    async def response(self, team: Team) -> TeamResponse:
        return TeamResponse(
            id=team.id,
            name=team.name,
            assigned_account_ids=json.loads(team.assigned_account_ids)
            if team.assigned_account_ids is not None
            else None,
            assigned_source_ids=json.loads(team.assigned_source_ids) if team.assigned_source_ids is not None else None,
            member_user_ids=await self.repo.members(team.id),
            limits=[
                LimitRuleResponse(
                    id=r.id,
                    limit_type=r.limit_type.value,
                    limit_window=r.limit_window.value,
                    max_value=r.max_value,
                    current_value=r.current_value,
                    model_filter=r.model_filter,
                    reset_at=r.reset_at,
                )
                for r in team.limits
            ],
        )

    async def list_all(self) -> list[TeamResponse]:
        return [await self.response(team) for team in await self.repo.list_all()]

    async def create(self, name: str) -> TeamResponse:
        if not name.strip():
            raise DashboardBadRequestError("Team name is required")
        team = Team(id=str(uuid4()), name=name.strip(), limits=[])
        self.repo.session.add(team)
        await self.repo.session.commit()
        return await self.response(team)

    async def changed(self) -> None:
        await self.repo.session.commit()
        get_api_key_cache().clear()
        await bump_cache_invalidation(NAMESPACE_API_KEY)

    async def update(self, team_id: str, payload: TeamUpdate) -> TeamResponse:
        team = await self.require(team_id)
        fields = payload.model_fields_set
        keys = ApiKeysRepository(self.repo.session)
        if "name" in fields:
            if payload.name is None or not payload.name.strip():
                raise DashboardBadRequestError("Team name is required")
            team.name = payload.name.strip()
        if "assigned_account_ids" in fields:
            ids = sorted(set(payload.assigned_account_ids)) if payload.assigned_account_ids is not None else None
            if ids is not None and len(await keys.list_accounts_by_ids(ids)) != len(ids):
                raise DashboardBadRequestError("Unknown assigned account")
            team.assigned_account_ids = json.dumps(ids) if ids is not None else None
        if "assigned_source_ids" in fields:
            ids = sorted(set(payload.assigned_source_ids)) if payload.assigned_source_ids is not None else None
            if ids is not None and len(await keys.list_model_sources_by_ids(ids)) != len(ids):
                raise DashboardBadRequestError("Unknown assigned model source")
            team.assigned_source_ids = json.dumps(ids) if ids is not None else None
        if "limits" in fields:
            inputs = [
                LimitRuleInput(
                    limit_type=r.limit_type,
                    limit_window=r.limit_window,
                    max_value=r.max_value,
                    model_filter=r.model_filter,
                )
                for r in (payload.limits or [])
            ]
            try:
                _validate_unique_limit_rule_identities(inputs)
                existing = {(r.limit_type.value, r.limit_window.value, r.model_filter): r for r in team.limits}
                rows = []
                for rule in inputs:
                    row = existing.get((rule.limit_type, rule.limit_window, rule.model_filter))
                    if row is None:
                        row = _limit_input_to_row(rule, "", utcnow())
                        row.api_key_id = None
                        row.team_id = team_id
                    else:
                        row.max_value = rule.max_value
                    rows.append(row)
                team.limits = rows
            except ValueError as exc:
                raise DashboardBadRequestError(str(exc)) from exc
        if payload.reset_usage:
            from app.modules.api_keys.limit_windows import next_limit_reset

            for row in team.limits:
                row.current_value = 0
                row.reset_at = next_limit_reset(utcnow(), row.limit_window)
        await self.changed()
        return await self.response(team)

    async def delete(self, team_id: str) -> None:
        team = await self.require(team_id)
        if team_id == "default" or await self.repo.has_keys(team_id):
            raise DashboardConflictError("Default and referenced teams cannot be deleted")
        await self.repo.session.delete(team)
        await self.changed()

    async def add_member(self, team_id: str, user_id: str) -> TeamResponse:
        team = await self.require(team_id)
        if not await self.repo.user_exists(user_id):
            raise DashboardBadRequestError("Unknown developer")
        if await self.repo.session.get(TeamMember, (team_id, user_id)) is None:
            self.repo.session.add(TeamMember(team_id=team_id, user_id=user_id))
        await self.changed()
        return await self.response(team)

    async def remove_member(self, team_id: str, user_id: str) -> TeamResponse:
        await self.repo.lock_membership_change(team_id, user_id)
        team = await self.require(team_id)
        if await self.repo.has_keys(team_id, user_id=user_id):
            raise DashboardConflictError("Deactivate the developer's team keys before removing membership")
        await self.repo.remove_member(team_id, user_id)
        await self.changed()
        return await self.response(team)
