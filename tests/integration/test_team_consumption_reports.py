from datetime import timedelta

import pytest

from app.core.utils.time import utcnow
from app.db.models import RequestLog
from app.db.session import SessionLocal

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_team_reports_count_once_and_exclude_warmup(async_client):
    team = (await async_client.post("/api/teams/", json={"name": "Data"})).json()
    key = (await async_client.post("/api/api-keys/", json={"name": "shared", "teamId": team["id"]})).json()
    now = utcnow()
    async with SessionLocal() as session:
        for kind in ("responses", "warmup"):
            session.add(
                RequestLog(
                    account_id=None,
                    api_key_id=key["id"],
                    request_id=kind,
                    model="gpt-5.1",
                    input_tokens=10,
                    output_tokens=20,
                    cost_usd=0.1,
                    latency_ms=1,
                    status="success",
                    request_kind=kind,
                    requested_at=now,
                )
            )
        await session.commit()
    result = await async_client.get(
        "/api/teams/usage",
        params={"start": (now - timedelta(hours=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()},
    )
    assert result.status_code == 200
    report = result.json()
    assert report["teams"][0]["teamId"] == team["id"]
    assert report["teams"][0]["requestCount"] == 1
    assert report["teams"][0]["totalTokens"] == 30
    assert report["unassigned"][0]["requestCount"] == 1
    assert report["developers"] == []


async def test_personal_totals_span_teams_and_survive_raw_retention(async_client):
    from datetime import datetime

    from sqlalchemy import delete

    from app.db.models import DashboardUser
    from app.modules.accounts.usage_time_rollup import run_hourly_fold_pass

    async with SessionLocal() as session:
        session.add(DashboardUser(id="ana", username="ana", role_id="3fe0d2b1-4327-5931-befc-55e04f945100"))
        await session.commit()
    teams = [(await async_client.post("/api/teams/", json={"name": name})).json() for name in ("Backend", "Data")]
    keys = []
    for team in teams:
        await async_client.post(f"/api/teams/{team['id']}/members", json={"userId": "ana"})
        key = (
            await async_client.post("/api/api-keys/", json={"name": "Ana", "teamId": team["id"], "ownerUserId": "ana"})
        ).json()
        keys.append(key)
    at = datetime(2026, 1, 1, 12)
    async with SessionLocal() as session:
        for index, key in enumerate(keys):
            session.add(
                RequestLog(
                    api_key_id=key["id"],
                    request_id=f"ana-{index}",
                    model="gpt-5.1",
                    input_tokens=10,
                    reasoning_tokens=5,
                    status="success",
                    latency_ms=1,
                    requested_at=at,
                    cost_usd=0.2,
                )
            )
        await session.commit()
    params = {"start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"}
    before = (await async_client.get("/api/teams/usage", params=params)).json()
    assert before["developers"][0]["requestCount"] == 2
    assert before["developers"][0]["totalTokens"] == 30
    assert len(before["teams"]) == 2
    await run_hourly_fold_pass(now=datetime(2026, 1, 4))
    async with SessionLocal() as session:
        await session.execute(delete(RequestLog))
        await session.commit()
    after = (await async_client.get("/api/teams/usage", params=params)).json()
    assert after == before
    await async_client.patch("/api/api-keys/" + keys[0]["id"], json={"isActive": False})
    await async_client.delete(f"/api/teams/{teams[0]['id']}/members/ana")
    assert (await async_client.get("/api/teams/usage", params=params)).json() == before
    filtered = (await async_client.get("/api/teams/usage", params={**params, "team_id": teams[0]["id"]})).json()
    assert filtered["developers"][0]["requestCount"] == 1


async def test_reports_preserve_missing_usage_shared_keys_and_cross_account_attribution(async_client):
    from datetime import datetime

    from app.db.models import Account, DashboardUser
    from app.modules.accounts.usage_time_rollup import run_hourly_fold_pass

    at = datetime(2026, 2, 1, 12)
    async with SessionLocal() as session:
        session.add(DashboardUser(id="ana", username="ana", role_id="3fe0d2b1-4327-5931-befc-55e04f945100"))
        for account_id in ("a", "b"):
            session.add(
                Account(
                    id=account_id,
                    email=account_id + "@example.test",
                    plan_type="plus",
                    access_token_encrypted=b"fixture",
                    refresh_token_encrypted=b"fixture",
                    id_token_encrypted=b"fixture",
                    last_refresh=at,
                )
            )
        await session.commit()
    teams = [(await async_client.post("/api/teams/", json={"name": name})).json() for name in ("Backend", "Data")]
    keys = []
    for team in teams:
        await async_client.post(f"/api/teams/{team['id']}/members", json={"userId": "ana"})
        for owner in ("ana", None):
            keys.append(
                (
                    await async_client.post(
                        "/api/api-keys/",
                        json={"name": "owned" if owner else "shared", "teamId": team["id"], "ownerUserId": owner},
                    )
                ).json()
            )
    cases = [
        (0, "a", 5, 2, 1, 0.1, "responses"),
        (0, "b", None, None, None, None, "responses"),
        (1, "b", 3, 4, 2, 0.2, "responses"),
        (2, "a", 10, 0, 0, 0.4, "responses"),
        (3, "b", None, None, None, None, "responses"),
        (0, "a", 100, 100, 0, 1.0, "limit_warmup"),
    ]
    async with SessionLocal() as session:
        for index, (key_index, account, input_tokens, output_tokens, cached, cost, kind) in enumerate(cases):
            session.add(
                RequestLog(
                    api_key_id=keys[key_index]["id"],
                    account_id=account,
                    request_id=f"mixed-{index}",
                    model="gpt-5.1",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_input_tokens=cached,
                    cost_usd=cost,
                    request_kind=kind,
                    status="success" if input_tokens is not None else "error",
                    latency_ms=1,
                    requested_at=at,
                )
            )
        await session.commit()
    params = {"start": "2026-02-01T00:00:00Z", "end": "2026-02-03T00:00:00Z"}
    before = (await async_client.get("/api/teams/usage", params=params)).json()
    by_team = {row["teamId"]: row for row in before["teams"]}
    assert (by_team[teams[0]["id"]]["requestCount"], by_team[teams[0]["id"]]["totalTokens"]) == (3, 14)
    assert (by_team[teams[1]["id"]]["requestCount"], by_team[teams[1]["id"]]["totalTokens"]) == (2, 10)
    assert before["developers"][0]["requestCount"] == 3
    assert before["developers"][0]["totalTokens"] == 17
    assert len(before["unassigned"]) == 2
    assert sum(row["cachedInputTokens"] for row in before["teams"]) == 3
    assert sum(row["totalCostUsd"] for row in before["teams"]) == pytest.approx(0.7)
    await run_hourly_fold_pass(now=datetime(2026, 2, 4))
    assert (await async_client.get("/api/teams/usage", params=params)).json() == before
    personal = (await async_client.get("/api/teams/usage", params={**params, "developer_id": "ana"})).json()
    assert personal["developers"][0]["requestCount"] == 3
    assert personal["unassigned"] == []
