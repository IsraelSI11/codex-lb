from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("path", ["/v1/responses/compact", "/v1/responses", "/backend-api/codex/responses"])
async def test_stale_authenticated_assignment_returns_retryable_conflict(async_client, monkeypatch, path):
    from app.core.auth import dependencies
    from app.db.session import SessionLocal
    from app.modules.api_keys.repository import ApiKeysRepository
    from app.modules.api_keys.service import ApiKeysService

    await async_client.put("/api/settings", json={"apiKeyAuthEnabled": True})
    key = (await async_client.post("/api/api-keys/", json={"name": "cached assignment"})).json()
    async with SessionLocal() as session:
        stale = await ApiKeysService(ApiKeysRepository(session)).validate_key(key["key"])
    destination = (await async_client.post("/api/teams/", json={"name": "Destination"})).json()
    assert (
        await async_client.patch("/api/api-keys/" + key["id"], json={"teamId": destination["id"]})
    ).status_code == 200

    async def cached_authentication(token):
        return stale

    monkeypatch.setattr(dependencies, "_validate_api_key_token", cached_authentication)
    response = await async_client.post(
        path,
        headers={"Authorization": "Bearer " + key["key"]},
        json={"model": "gpt-5.1", "input": [], "stream": True}
        if path != "/v1/responses/compact"
        else {"model": "gpt-5.1", "input": []},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "api_key_attribution_changed"
    assert "retry" in response.json()["error"]["message"].lower()
