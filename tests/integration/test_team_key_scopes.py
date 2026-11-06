import pytest

from app.db.session import SessionLocal
from app.modules.api_keys.repository import ApiKeysRepository
from app.modules.api_keys.service import ApiKeysService
from app.modules.teams.scope import resolve_effective_scope

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "team,key,expected",
    [
        (None, None, None),
        ([], None, frozenset()),
        (["b"], None, frozenset({"b"})),
        (None, ["a"], frozenset({"a"})),
        (["a", "b"], ["b", "c"], frozenset({"b"})),
        (["a"], [], frozenset()),
    ],
)
async def test_effective_scope(team, key, expected):
    assert resolve_effective_scope(team, key) == expected


async def test_team_empty_scopes_are_deny_all_without_rewriting_key(async_client):
    key = (await async_client.post("/api/api-keys/", json={"name": "scoped"})).json()
    await async_client.patch("/api/teams/default", json={"assignedAccountIds": [], "assignedSourceIds": []})
    async with SessionLocal() as session:
        snapshot = await ApiKeysService(ApiKeysRepository(session)).validate_key(key["key"])
        assert snapshot.account_assignment_scope_enabled
        assert snapshot.source_assignment_scope_enabled
        assert snapshot.assigned_account_ids == []
        assert snapshot.assigned_source_ids == []
    listed = (await async_client.get("/api/api-keys/")).json()[0]
    assert listed["accountAssignmentScopeEnabled"] is False
    await async_client.patch("/api/teams/default", json={"assignedAccountIds": None, "assignedSourceIds": None})
    async with SessionLocal() as session:
        snapshot = await ApiKeysService(ApiKeysRepository(session)).validate_key(key["key"])
        assert not snapshot.account_assignment_scope_enabled


async def test_shared_resources_intersect_key_scopes_and_refresh_after_team_tightening(async_client):
    from app.core.utils.time import utcnow
    from app.db.models import Account, ModelSource

    async with SessionLocal() as session:
        for name in ("a", "b", "c"):
            session.add(
                Account(
                    id=name,
                    email=name + "@example.test",
                    plan_type="plus",
                    access_token_encrypted=b"fixture",
                    refresh_token_encrypted=b"fixture",
                    id_token_encrypted=b"fixture",
                    last_refresh=utcnow(),
                )
            )
            session.add(ModelSource(id="source-" + name, name=name, base_url="https://example.invalid"))
        await session.commit()
    teams = [(await async_client.post("/api/teams/", json={"name": name})).json() for name in ("Backend", "Data")]
    for team in teams:
        assert (
            await async_client.patch(
                "/api/teams/" + team["id"],
                json={"assignedAccountIds": ["a", "b"], "assignedSourceIds": ["source-a", "source-b"]},
            )
        ).status_code == 200
    keys = [
        (
            await async_client.post(
                "/api/api-keys/",
                json={
                    "name": team["name"],
                    "teamId": team["id"],
                    "assignedAccountIds": ["b", "c"],
                    "assignedSourceIds": ["source-b", "source-c"],
                },
            )
        ).json()
        for team in teams
    ]
    for key in keys:
        async with SessionLocal() as session:
            service = ApiKeysService(ApiKeysRepository(session))
            for snapshot in (await service.validate_key(key["key"]), await service.get_key_by_id(key["id"])):
                assert snapshot.assigned_account_ids == ["b"]
                assert snapshot.assigned_source_ids == ["source-b"]
    await async_client.patch(
        "/api/teams/" + teams[0]["id"], json={"assignedAccountIds": ["a"], "assignedSourceIds": []}
    )
    async with SessionLocal() as session:
        snapshot = await ApiKeysService(ApiKeysRepository(session)).get_key_by_id(keys[0]["id"])
        assert snapshot.account_assignment_scope_enabled and snapshot.assigned_account_ids == []
        assert snapshot.source_assignment_scope_enabled and snapshot.assigned_source_ids == []
        # A bridge pinned before the scope change cannot reuse its old account.
        from types import SimpleNamespace
        from typing import Any, cast

        from app.modules.proxy._service.http_bridge.helpers import _http_bridge_session_allows_api_key

        pinned_session = cast(Any, SimpleNamespace(account=SimpleNamespace(id="b")))
        assert not _http_bridge_session_allows_api_key(pinned_session, snapshot)
        other = await ApiKeysService(ApiKeysRepository(session)).get_key_by_id(keys[1]["id"])
        assert other.assigned_account_ids == ["b"]
    inventory = (await async_client.get("/api/api-keys/")).json()
    assert next(key for key in inventory if key["id"] == keys[0]["id"])["assignedAccountIds"] == ["b", "c"]


async def test_team_scope_change_invalidates_local_and_peer_auth_caches(async_client):
    from app.core.auth.api_key_cache import get_api_key_cache
    from app.core.cache.invalidation import NAMESPACE_API_KEY, CacheInvalidationPoller

    peer = CacheInvalidationPoller(SessionLocal)
    await peer.initialize()
    observed = []
    peer.on_invalidation(NAMESPACE_API_KEY, lambda: observed.append("invalidated"))
    cache = get_api_key_cache()
    version = cache.version
    await cache.set("team-scope-fixture", "old-snapshot")
    assert (await async_client.patch("/api/teams/default", json={"assignedAccountIds": []})).status_code == 200
    assert cache.version > version
    assert await cache.get("team-scope-fixture") is None
    await peer.prime()
    assert observed == ["invalidated"]
