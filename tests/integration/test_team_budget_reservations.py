import pytest

from app.db.session import SessionLocal
from app.modules.api_keys.repository import ApiKeysRepository
from app.modules.api_keys.service import ApiKeyRateLimitExceededError, ApiKeyRequestUsageBudget, ApiKeysService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_shared_team_limit_reserves_and_releases_with_no_key_limit(async_client):
    team = (await async_client.post("/api/teams/", json={"name": "Backend"})).json()
    await async_client.patch(
        "/api/teams/" + team["id"],
        json={"limits": [{"limitType": "total_tokens", "limitWindow": "daily", "maxValue": 10}]},
    )
    keys = [
        (await async_client.post("/api/api-keys/", json={"name": name, "teamId": team["id"]})).json()
        for name in ("one", "two")
    ]
    async with SessionLocal() as session:
        service = ApiKeysService(ApiKeysRepository(session))
        reservation = await service.enforce_limits_for_request(
            keys[0]["id"],
            request_model="gpt-5.1",
            request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=10, output_tokens=0),
        )
        assert reservation is not None
    async with SessionLocal() as session:
        with pytest.raises(ApiKeyRateLimitExceededError, match="Team"):
            await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(
                keys[1]["id"],
                request_model="gpt-5.1",
                request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=1, output_tokens=0),
            )
    async with SessionLocal() as session:
        await ApiKeysService(ApiKeysRepository(session)).release_usage_reservation(reservation.reservation_id)
    async with SessionLocal() as session:
        assert (
            await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(
                keys[1]["id"],
                request_model="gpt-5.1",
                request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=1, output_tokens=0),
            )
            is not None
        )


async def _setup_budget(client, team_max=10, key_max=None):
    team = (await client.post("/api/teams/", json={"name": "Budget"})).json()
    rule = {"limitType": "total_tokens", "limitWindow": "daily", "maxValue": team_max}
    await client.patch("/api/teams/" + team["id"], json={"limits": [rule]})
    keys = []
    for name in ("a", "b"):
        payload = {"name": name, "teamId": team["id"]}
        if key_max:
            payload["limits"] = [{**rule, "maxValue": key_max}]
        keys.append((await client.post("/api/api-keys/", json=payload)).json())
    return team, keys


async def test_different_keys_reserve_concurrently_without_overallocation(async_client):
    import asyncio

    team, keys = await _setup_budget(async_client)

    async def reserve(key):
        async with SessionLocal() as session:
            try:
                return await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(
                    key["id"],
                    request_model="gpt-5.1",
                    request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=10, output_tokens=0),
                )
            except ApiKeyRateLimitExceededError:
                return None

    results = await asyncio.gather(*(reserve(key) for key in keys))
    assert sum(result is not None for result in results) == 1
    teams = (await async_client.get("/api/teams/")).json()
    assert next(row for row in teams if row["id"] == team["id"])["limits"][0]["currentValue"] == 10


@pytest.mark.parametrize("terminal", ["finalize", "fail", "release"])
async def test_both_scopes_settle_exactly_once(async_client, terminal):
    team, keys = await _setup_budget(async_client, 100, 100)
    async with SessionLocal() as session:
        service = ApiKeysService(ApiKeysRepository(session))
        reservation = await service.enforce_limits_for_request(
            keys[0]["id"],
            request_model="gpt-5.1",
            request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=10, output_tokens=0),
        )
        assert reservation is not None
        for _ in range(2):
            if terminal == "finalize":
                await service.finalize_usage_reservation(
                    reservation.reservation_id, model="gpt-5.1", input_tokens=3, output_tokens=2
                )
            elif terminal == "fail":
                await service.fail_usage_reservation(reservation.reservation_id, model="gpt-5.1")
            else:
                await service.release_usage_reservation(reservation.reservation_id)
    expected = 5 if terminal == "finalize" else 0
    teams = (await async_client.get("/api/teams/")).json()
    assert next(row for row in teams if row["id"] == team["id"])["limits"][0]["currentValue"] == expected
    key = next(row for row in (await async_client.get("/api/api-keys/")).json() if row["id"] == keys[0]["id"])
    assert key["limits"][0]["currentValue"] == expected


@pytest.mark.parametrize("team_max,key_max", [(1, 100), (100, 1)])
async def test_rejection_rolls_back_both_scopes(async_client, team_max, key_max):
    team, keys = await _setup_budget(async_client, team_max, key_max)
    # Exhaust one scope with actual usage; the other must remain unchanged on rejection.
    from sqlalchemy import select

    from app.db.models import ApiKeyLimit

    async with SessionLocal() as session:
        limits = list((await session.scalars(select(ApiKeyLimit))).all())
        for limit in limits:
            if limit.max_value == 1:
                limit.current_value = 1
        await session.commit()
    async with SessionLocal() as session:
        with pytest.raises(ApiKeyRateLimitExceededError):
            await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(
                keys[0]["id"], request_model="gpt-5.1"
            )
    async with SessionLocal() as session:
        for limit in (await session.scalars(select(ApiKeyLimit))).all():
            assert limit.current_value == (1 if limit.max_value == 1 else 0)


async def test_reset_during_flight_does_not_charge_new_period(async_client):
    team, keys = await _setup_budget(async_client, 100)
    async with SessionLocal() as session:
        reservation = await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(
            keys[0]["id"],
            request_model="gpt-5.1",
            request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=10, output_tokens=0),
        )
    assert reservation is not None
    await async_client.patch("/api/teams/" + team["id"], json={"resetUsage": True})
    async with SessionLocal() as session:
        await ApiKeysService(ApiKeysRepository(session)).finalize_usage_reservation(
            reservation.reservation_id, model="gpt-5.1", input_tokens=30, output_tokens=0
        )
    teams = (await async_client.get("/api/teams/")).json()
    assert next(row for row in teams if row["id"] == team["id"])["limits"][0]["currentValue"] == 0


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/v1/responses/compact", {"model": "gpt-5.1", "input": []}),
        ("/v1/responses", {"model": "gpt-5.1", "input": [], "stream": True}),
        ("/backend-api/codex/responses", {"model": "gpt-5.1", "input": [], "stream": True}),
    ],
)
async def test_team_exhaustion_preserves_http_error_envelope(async_client, path, payload):
    from sqlalchemy import update

    from app.db.models import ApiKeyLimit

    await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})
    team, keys = await _setup_budget(async_client)
    async with SessionLocal() as session:
        await session.execute(update(ApiKeyLimit).where(ApiKeyLimit.team_id == team["id"]).values(current_value=10))
        await session.commit()
    response = await async_client.post(path, headers={"Authorization": "Bearer " + keys[0]["key"]}, json=payload)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert "Team" in response.json()["error"]["message"]
    assert "reset" in response.json()["error"]["message"]


async def test_stale_recovery_releases_shared_and_key_items(async_client):
    from datetime import timedelta

    from sqlalchemy import update

    from app.core.utils.time import utcnow
    from app.db.models import ApiKeyUsageReservation

    team, keys = await _setup_budget(async_client, 100, 100)
    async with SessionLocal() as session:
        service = ApiKeysService(ApiKeysRepository(session))
        reservation = await service.enforce_limits_for_request(
            keys[0]["id"],
            request_model="gpt-5.1",
            request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=10, output_tokens=0),
        )
        assert reservation is not None
        await session.execute(
            update(ApiKeyUsageReservation)
            .where(ApiKeyUsageReservation.id == reservation.reservation_id)
            .values(updated_at=utcnow() - timedelta(hours=2))
        )
        await session.commit()
        assert (
            await ApiKeysRepository(session).release_stale_usage_reservations(cutoff=utcnow() - timedelta(hours=1)) == 1
        )
        assert (
            await ApiKeysRepository(session).release_stale_usage_reservations(cutoff=utcnow() - timedelta(hours=1)) == 0
        )
    teams = (await async_client.get("/api/teams/")).json()
    assert next(row for row in teams if row["id"] == team["id"])["limits"][0]["currentValue"] == 0


async def test_team_exhaustion_preserves_websocket_error_envelope(async_client, app_instance):
    import asyncio

    from fastapi.testclient import TestClient
    from sqlalchemy import update

    from app.db.models import ApiKeyLimit

    await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})
    team, keys = await _setup_budget(async_client)
    async with SessionLocal() as session:
        await session.execute(update(ApiKeyLimit).where(ApiKeyLimit.team_id == team["id"]).values(current_value=10))
        await session.commit()

    def request():
        with TestClient(app_instance) as client:
            with client.websocket_connect(
                "/backend-api/codex/responses", headers={"Authorization": "Bearer " + keys[0]["key"]}
            ) as websocket:
                websocket.send_json({"type": "response.create", "model": "gpt-5.1", "input": "hi"})
                return websocket.receive_json()

    event = await asyncio.to_thread(request)
    assert event["type"] == "error"
    assert event["status"] == 429
    assert event["error"]["code"] == "rate_limit_exceeded"
    assert "Team" in event["error"]["message"]
    assert "reset" in event["error"]["message"]


async def test_model_filtered_team_budget_does_not_block_other_models_or_teams(async_client):
    team = (await async_client.post("/api/teams/", json={"name": "Filtered"})).json()
    await async_client.patch(
        "/api/teams/" + team["id"],
        json={
            "limits": [{"limitType": "total_tokens", "limitWindow": "daily", "maxValue": 1, "modelFilter": "gpt-5.1"}]
        },
    )
    key = (await async_client.post("/api/api-keys/", json={"name": "filtered", "teamId": team["id"]})).json()
    other = (await async_client.post("/api/api-keys/", json={"name": "other"})).json()
    async with SessionLocal() as session:
        service = ApiKeysService(ApiKeysRepository(session))
        first = await service.enforce_limits_for_request(
            key["id"],
            request_model="gpt-5.1",
            request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=1, output_tokens=0),
        )
        assert first is not None
        assert await service.enforce_limits_for_request(key["id"], request_model="gpt-5.2") is None
        assert await service.enforce_limits_for_request(other["id"], request_model="gpt-5.1") is None
        with pytest.raises(ApiKeyRateLimitExceededError):
            await service.enforce_limits_for_request(key["id"], request_model="gpt-5.1")


async def test_team_rule_removal_in_flight_keeps_key_settlement_exactly_once(async_client):
    team, keys = await _setup_budget(async_client, 100, 100)
    async with SessionLocal() as session:
        reservation = await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(
            keys[0]["id"],
            request_model="gpt-5.1",
            request_usage_budget=ApiKeyRequestUsageBudget(input_tokens=10, output_tokens=0),
        )
    assert reservation is not None
    assert (await async_client.patch("/api/teams/" + team["id"], json={"limits": []})).status_code == 200
    async with SessionLocal() as session:
        service = ApiKeysService(ApiKeysRepository(session))
        for _ in range(2):
            await service.finalize_usage_reservation(
                reservation.reservation_id, model="gpt-5.1", input_tokens=25, output_tokens=0
            )
    rows = (await async_client.get("/api/api-keys/")).json()
    assert next(row for row in rows if row["id"] == keys[0]["id"])["limits"][0]["currentValue"] == 25
