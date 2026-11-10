from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.core.auth.key_attribution import attribution_id
from app.db.models import ApiKey, DashboardUser, RequestLog, RequestUsageHourlyRollup
from app.db.session import SessionLocal
from app.modules.accounts.usage_time_rollup import run_hourly_fold_pass

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_same_key_a_b_a_preserves_mid_hour_history_after_retention(async_client):
    teams = [(await async_client.post("/api/teams/", json={"name": name})).json() for name in ("A", "B")]
    key = (await async_client.post("/api/api-keys/", json={"name": "movable", "teamId": teams[0]["id"]})).json()
    at = datetime(2026, 5, 1, 12)
    original_hash = None
    for index, team in enumerate((teams[0], teams[1], teams[0])):
        if index:
            edited = await async_client.patch("/api/api-keys/" + key["id"], json={"teamId": team["id"]})
            assert edited.status_code == 200, edited.text
            assert edited.json()["id"] == key["id"]
        async with SessionLocal() as session:
            row = await session.get(ApiKey, key["id"])
            assert row is not None
            if original_hash is None:
                original_hash = row.key_hash
            assert row.key_hash == original_hash
            session.add(
                RequestLog(
                    api_key_id=key["id"],
                    api_key_attribution_id=attribution_id(key["id"], team["id"], None),
                    request_id=f"move-{index}",
                    model="gpt-test",
                    request_kind="responses",
                    status="success",
                    input_tokens=10 * (index + 1),
                    output_tokens=0,
                    requested_at=at + timedelta(minutes=index * 10),
                )
            )
            await session.commit()
    params = {"start": "2026-05-01T12:00:00Z", "end": "2026-05-01T13:00:00Z"}
    before = (await async_client.get("/api/teams/usage", params=params)).json()
    by_team = {x["teamId"]: x for x in before["teams"]}
    assert (by_team[teams[0]["id"]]["requestCount"], by_team[teams[0]["id"]]["totalTokens"]) == (2, 40)
    assert (by_team[teams[1]["id"]]["requestCount"], by_team[teams[1]["id"]]["totalTokens"]) == (1, 20)
    await run_hourly_fold_pass(now=at + timedelta(days=3))
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(RequestUsageHourlyRollup).where(RequestUsageHourlyRollup.api_key_id == key["id"])
            )
        ).all()
        assert len(rows) == 2
        await session.execute(delete(RequestLog))
        await session.commit()
    assert (await async_client.get("/api/teams/usage", params=params)).json() == before


async def test_late_completion_and_old_identity_protection(async_client):
    async with SessionLocal() as session:
        session.add(DashboardUser(id="old-owner", username="old-owner", role_id="3fe0d2b1-4327-5931-befc-55e04f945100"))
        await session.commit()
    a = (await async_client.post("/api/teams/", json={"name": "Old"})).json()
    b = (await async_client.post("/api/teams/", json={"name": "New"})).json()
    await async_client.post(f"/api/teams/{a['id']}/members", json={"userId": "old-owner"})
    key = (
        await async_client.post("/api/api-keys/", json={"name": "late", "teamId": a["id"], "ownerUserId": "old-owner"})
    ).json()
    snapshot = attribution_id(key["id"], a["id"], "old-owner")
    changed = await async_client.patch("/api/api-keys/" + key["id"], json={"teamId": b["id"], "ownerUserId": None})
    assert changed.status_code == 200
    at = datetime(2026, 5, 1, 12)
    async with SessionLocal() as session:
        # Completion persists the snapshot captured before reassignment.
        session.add(
            RequestLog(
                api_key_id=key["id"],
                api_key_attribution_id=snapshot,
                request_id="late",
                model="test",
                status="success",
                input_tokens=7,
                output_tokens=2,
                requested_at=at,
            )
        )
        await session.commit()
    params = {"start": "2026-05-01T00:00:00Z", "end": "2026-05-02T00:00:00Z"}
    report = (await async_client.get("/api/teams/usage", params=params)).json()
    assert report["teams"][0]["teamId"] == a["id"]
    assert report["developers"][0]["ownerUserId"] == "old-owner"
    removed = await async_client.delete(f"/api/teams/{a['id']}/members/old-owner")
    assert removed.status_code == 200
    assert (await async_client.delete(f"/api/teams/{a['id']}")).status_code == 409
    # Historical references must protect the identity even when no current key/membership remains.
    from app.core.exceptions import DashboardConflictError
    from app.modules.dashboard_users.repository import DashboardUsersRepository

    async with SessionLocal() as session:
        owner = await session.get(DashboardUser, "old-owner")
        assert owner is not None
        with pytest.raises(DashboardConflictError):
            await DashboardUsersRepository(session).delete_user(owner, require_other_admin=False)
