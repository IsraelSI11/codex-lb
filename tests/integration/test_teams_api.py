from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_default_team_and_legacy_key(async_client):
    teams = await async_client.get("/api/teams/")
    assert teams.status_code == 200
    assert [(t["id"], t["name"]) for t in teams.json()] == [("default", "Default")]
    key = await async_client.post("/api/api-keys/", json={"name": "legacy"})
    assert key.status_code == 200
    assert key.json()["teamId"] == "default"
    assert key.json()["ownerUserId"] is None


async def test_team_crud_and_shared_budget(async_client):
    response = await async_client.post("/api/teams/", json={"name": "Backend"})
    assert response.status_code == 200
    team = response.json()
    assert team["name"] == "Backend"
    updated = await async_client.patch(
        "/api/teams/" + team["id"],
        json={
            "name": "Platform",
            "assignedAccountIds": [],
            "limits": [{"limitType": "total_tokens", "limitWindow": "daily", "maxValue": 100}],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["assignedAccountIds"] == []
    assert updated.json()["limits"][0]["maxValue"] == 100
    key = await async_client.post("/api/api-keys/", json={"name": "team key", "teamId": team["id"]})
    assert key.status_code == 200
    assert key.json()["teamId"] == team["id"]
    assert (await async_client.delete("/api/teams/" + team["id"])).status_code == 409


async def test_default_protection_and_unknown_assignments(async_client):
    assert (await async_client.delete("/api/teams/default")).status_code == 409
    bad = await async_client.post("/api/api-keys/", json={"name": "bad", "teamId": "missing"})
    assert bad.status_code == 400
    bad = await async_client.patch("/api/teams/default", json={"assignedAccountIds": ["missing"]})
    assert bad.status_code == 400
    assert (await async_client.post("/api/teams/default/members", json={"userId": "missing"})).status_code == 400


async def test_developer_must_be_member(async_client):
    response = await async_client.post(
        "/api/api-keys/",
        json={
            "name": "bad owner",
            "teamId": "default",
            "ownerUserId": "missing",
        },
    )
    assert response.status_code == 400


async def test_memberships_owner_and_immutable_used_key(async_client):
    from app.db.models import DashboardUser, RequestLog
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        session.add(DashboardUser(id="ana", username="ana", role_id="3fe0d2b1-4327-5931-befc-55e04f945100"))
        await session.commit()
    team = (await async_client.post("/api/teams/", json={"name": "Backend"})).json()
    other = (await async_client.post("/api/teams/", json={"name": "Data"})).json()
    for team_id in (team["id"], other["id"]):
        assert (await async_client.post(f"/api/teams/{team_id}/members", json={"userId": "ana"})).status_code == 200
    key = (
        await async_client.post("/api/api-keys/", json={"name": "Ana", "teamId": team["id"], "ownerUserId": "ana"})
    ).json()
    assert key["ownerUserId"] == "ana"
    assert (await async_client.delete(f"/api/teams/{team['id']}/members/ana")).status_code == 409
    async with SessionLocal() as session:
        session.add(
            RequestLog(api_key_id=key["id"], request_id="used", model="gpt-5.1", status="success", latency_ms=1)
        )
        await session.commit()
    assert (await async_client.patch("/api/api-keys/" + key["id"], json={"teamId": other["id"]})).status_code == 409
    assert (await async_client.delete("/api/api-keys/" + key["id"])).status_code == 409
    assert (await async_client.patch("/api/api-keys/" + key["id"], json={"isActive": False})).status_code == 200
    assert (await async_client.delete(f"/api/teams/{team['id']}/members/ana")).status_code == 200
    assert (await async_client.patch("/api/api-keys/" + key["id"], json={"isActive": True})).status_code == 400


async def test_admission_without_limits_locks_attribution_immediately(async_client):
    from app.db.session import SessionLocal
    from app.modules.api_keys.repository import ApiKeysRepository
    from app.modules.api_keys.service import ApiKeysService

    key = (await async_client.post("/api/api-keys/", json={"name": "first request"})).json()
    async with SessionLocal() as session:
        assert (
            await ApiKeysService(ApiKeysRepository(session)).enforce_limits_for_request(
                key["id"], request_model="gpt-5.1"
            )
            is None
        )
    rows = (await async_client.get("/api/api-keys/")).json()
    assert rows[0]["attributionLocked"] is True
    team = (await async_client.post("/api/teams/", json={"name": "Other"})).json()
    assert (await async_client.patch("/api/api-keys/" + key["id"], json={"teamId": team["id"]})).status_code == 409


@pytest.mark.parametrize("path", ["/api/teams", "/api/teams/"])
async def test_team_creation_requires_write_with_or_without_slash(async_client, app_instance, monkeypatch, path):
    from app.core.auth.dashboard_access import guest_principal
    from tests.integration.test_dashboard_permission_gates import _use_principal

    _use_principal(app_instance, monkeypatch, guest_principal())
    response = await async_client.post(path, json={"name": "Forbidden"})
    assert response.status_code == 403


async def test_referenced_developer_retained_and_bulk_reactivation_requires_membership(async_client):
    from app.core.exceptions import DashboardConflictError
    from app.db.models import DashboardUser
    from app.db.session import SessionLocal
    from app.modules.dashboard_users.repository import DashboardUsersRepository

    async with SessionLocal() as session:
        session.add(DashboardUser(id="retained", username="retained", role_id="3fe0d2b1-4327-5931-befc-55e04f945100"))
        await session.commit()
    await async_client.post("/api/teams/default/members", json={"userId": "retained"})
    key = (await async_client.post("/api/api-keys/", json={"name": "owned", "ownerUserId": "retained"})).json()
    async with SessionLocal() as session:
        repo = DashboardUsersRepository(session)
        user = await session.get(DashboardUser, "retained")
        assert user is not None
        with pytest.raises(DashboardConflictError):
            await repo.delete_user(user)
        await session.rollback()
        await repo.deactivate_owned_keys("retained")
        await session.commit()
    assert (await async_client.delete("/api/teams/default/members/retained")).status_code == 200
    async with SessionLocal() as session:
        assert await DashboardUsersRepository(session).reactivate_owner_disabled_keys("retained") == []
    rows = (await async_client.get("/api/api-keys/")).json()
    assert next(row for row in rows if row["id"] == key["id"])["isActive"] is False


async def test_admission_racing_attribution_edit_cannot_move_consumption(async_client, monkeypatch):
    from app.core.exceptions import DashboardConflictError
    from app.db.session import SessionLocal
    from app.modules.api_keys.repository import ApiKeysRepository
    from app.modules.api_keys.service import ApiKeysService

    key = (await async_client.post("/api/api-keys/", json={"name": "race"})).json()
    team = (await async_client.post("/api/teams/", json={"name": "Destination"})).json()
    async with SessionLocal() as session:
        repo = ApiKeysRepository(session)
        validate = repo.validate_attribution

        async def admit_during_validation(team_id, owner_user_id):
            await validate(team_id, owner_user_id)
            async with SessionLocal() as admission:
                await ApiKeysService(ApiKeysRepository(admission)).enforce_limits_for_request(
                    key["id"], request_model="gpt-5.1"
                )

        monkeypatch.setattr(repo, "validate_attribution", admit_during_validation)
        with pytest.raises(DashboardConflictError):
            await repo.update_attribution(
                key["id"], team_id=team["id"], owner_user_id=None, team_set=True, owner_set=False
            )
        await session.rollback()
    rows = (await async_client.get("/api/api-keys/")).json()
    assert rows[0]["teamId"] == "default"


@pytest.mark.parametrize(
    "path", ["/api/teams/", "/api/teams/developers", "/api/teams/usage?start=2026-01-01&end=2026-02-01"]
)
async def test_team_reads_require_existing_api_key_permission(async_client, app_instance, monkeypatch, path):
    from app.core.auth.dashboard_access import Permission
    from tests.integration.test_dashboard_permission_gates import (
        _assert_permission_required,
        _principal_without,
        _use_principal,
    )

    _use_principal(app_instance, monkeypatch, _principal_without(Permission.API_KEYS_READ))
    _assert_permission_required(await async_client.get(path), Permission.API_KEYS_READ)


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("POST", "/api/teams/", {"name": "Denied"}),
        ("PATCH", "/api/teams/default", {"name": "Denied"}),
        ("DELETE", "/api/teams/default", None),
        ("POST", "/api/teams/default/members", {"userId": "missing"}),
        ("DELETE", "/api/teams/default/members/missing", None),
    ],
)
async def test_read_permission_does_not_grant_team_mutations(
    async_client, app_instance, monkeypatch, method, path, payload
):
    from app.core.auth.dashboard_access import Scope
    from tests.integration.test_dashboard_permission_gates import _principal_with_only, _use_principal

    _use_principal(app_instance, monkeypatch, _principal_with_only(dashboard__read=Scope.ALL, api_keys__read=Scope.ALL))
    assert (await async_client.get("/api/teams/")).status_code == 200
    assert (await async_client.request(method, path, json=payload)).status_code == 403


@pytest.mark.parametrize("reference", ["membership", "key"])
async def test_expired_invite_cleanup_retains_referenced_developers(async_client, reference):
    from datetime import timedelta

    from app.core.utils.time import utcnow
    from app.db.models import DashboardUser, DashboardUserInvite
    from app.db.session import SessionLocal
    from app.modules.dashboard_users.repository import DashboardUsersRepository

    async with SessionLocal() as session:
        session.add(
            DashboardUser(
                id="invited", username="invited", status="invited", role_id="3fe0d2b1-4327-5931-befc-55e04f945100"
            )
        )
        await session.flush()
        session.add(
            DashboardUserInvite(
                user_id="invited",
                token_hash=b"fixture-digest",
                created_by_user_id="fixture-admin",
                expires_at=utcnow() - timedelta(days=1),
            )
        )
        await session.commit()
    await async_client.post("/api/teams/default/members", json={"userId": "invited"})
    if reference == "key":
        key = (await async_client.post("/api/api-keys/", json={"name": "retained", "ownerUserId": "invited"})).json()
        await async_client.patch("/api/api-keys/" + key["id"], json={"isActive": False})
        await async_client.delete("/api/teams/default/members/invited")
    async with SessionLocal() as session:
        assert await DashboardUsersRepository(session).purge_expired_invited_users(utcnow()) == 0
        assert await session.get(DashboardUser, "invited") is not None
