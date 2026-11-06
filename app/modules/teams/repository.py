from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApiKey, DashboardUser, Team, TeamMember


class TeamsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Team]:
        return list((await self.session.scalars(select(Team).order_by(Team.created_at, Team.id))).all())

    async def get(self, team_id: str) -> Team | None:
        return (
            await self.session.execute(select(Team).where(Team.id == team_id).with_for_update())
        ).scalar_one_or_none()

    async def members(self, team_id: str) -> list[str]:
        return list(
            (
                await self.session.scalars(
                    select(TeamMember.user_id).where(TeamMember.team_id == team_id).order_by(TeamMember.user_id)
                )
            ).all()
        )

    async def user_exists(self, user_id: str) -> bool:
        return await self.session.get(DashboardUser, user_id) is not None

    async def has_keys(self, team_id: str, *, user_id: str | None = None) -> bool:
        stmt = select(ApiKey.id).where(ApiKey.team_id == team_id)
        if user_id is not None:
            stmt = stmt.where(ApiKey.owner_user_id == user_id, ApiKey.is_active.is_(True))
        return (await self.session.execute(stmt.limit(1))).first() is not None

    async def remove_member(self, team_id: str, user_id: str) -> None:
        await self.session.execute(
            delete(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )

    async def developers(self) -> list[DashboardUser]:
        return list((await self.session.scalars(select(DashboardUser).order_by(DashboardUser.username))).all())

    async def lock_membership_change(self, team_id: str, user_id: str) -> None:
        if self.session.get_bind().dialect.name == "sqlite":
            await self.session.execute(update(Team).where(Team.id == team_id).values(name=Team.name))
        else:
            await self.session.execute(select(DashboardUser.id).where(DashboardUser.id == user_id).with_for_update())
