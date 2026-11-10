from __future__ import annotations

import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.db.models import ApiKeyUsageReservation
from app.db.session import SessionLocal
from app.dependencies import get_proxy_service_for_app
from app.modules.proxy import api
from app.modules.proxy import http_bridge_forwarding as forwarding
from app.modules.proxy._service import support
from tests.integration.test_http_promotion_accounting import _key
from tests.integration.test_http_responses_bridge import (
    _cleanup_http_bridge_sessions as cleanup_http_bridge_sessions,  # noqa: F401
)
from tests.integration.test_http_responses_bridge import (
    _promotion_history,
)
from tests.integration.test_http_responses_bridge import (
    promotion_transport as promotion_transport,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_reassigned_forward_rejects_before_dispatch_and_releases_origin_budget(
    async_client, app_instance, promotion_transport, monkeypatch
):
    upstreams, raw_calls, _ = promotion_transport
    key = await _key(async_client, "forward-race")
    destination = (await async_client.post("/api/teams/", json={"name": "Destination"})).json()
    for team_id in (key["teamId"], destination["id"]):
        budget = await async_client.patch(
            "/api/teams/" + team_id,
            json={"limits": [{"limitType": "total_tokens", "limitWindow": "weekly", "maxValue": 100_000}]},
        )
        assert budget.status_code == 200, budget.text
    service = get_proxy_service_for_app(app_instance)
    parse = forwarding.parse_forwarded_request
    owner_responses = []
    forwarded_reservations = []
    owner_stream = AsyncMock(side_effect=AssertionError("Rejected owner must not execute upstream"))

    # Keep signature verification real while routing both instances through ASGI.
    monkeypatch.setattr(
        api,
        "parse_forwarded_request",
        lambda headers, *, payload, current_instance: parse(headers, payload=payload, current_instance="owner"),
    )

    @asynccontextmanager
    async def owner_response(url, *, json, headers, **kwargs):
        response = await async_client.post("/internal/bridge/responses", json=json, headers=headers)
        owner_responses.append(response)

        async def text():
            return response.text

        yield SimpleNamespace(status=response.status_code, headers=response.headers, text=text)

    class OwnerSession:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        post = staticmethod(owner_response)

    monkeypatch.setattr(forwarding.aiohttp, "ClientSession", OwnerSession)

    async def forward_after_reassignment(payload, headers, *, api_key, api_key_reservation, **kwargs):
        assert api_key_reservation is not None
        forwarded_reservations.append(api_key_reservation.reservation_id)
        changed = await async_client.patch("/api/api-keys/" + key["id"], json={"teamId": destination["id"]})
        assert changed.status_code == 200, changed.text
        # The origin already entered this function; any new stream is owner execution.
        monkeypatch.setattr(api, "_stream_responses", owner_stream)
        context = forwarding.HTTPBridgeForwardContext(
            origin_instance="origin",
            target_instance="owner",
            codex_session_affinity=True,
            downstream_turn_state=None,
            api_key_attribution_id=api_key.attribution_id,
            reservation=api_key_reservation,
        )
        async for block in forwarding.HTTPBridgeOwnerClient().stream_responses(
            owner_endpoint="http://owner",
            payload=payload,
            headers=headers,
            context=context,
            request_started_at=time.monotonic(),
            on_request_dispatched=support._signal_propagated_responses_owner_forward_dispatched,
            on_response_rejected=support._signal_propagated_responses_owner_forward_rejected,
            on_response_ready=support._signal_propagated_responses_service_cleanup_ready,
        ):
            yield block

    monkeypatch.setattr(service, "stream_http_responses", forward_after_reassignment)
    response = await async_client.post(
        "/v1/responses",
        json={"model": "gpt-5.4", "input": _promotion_history()},
        headers={"Authorization": f"Bearer {key['key']}"},
    )
    assert len(owner_responses) == 1
    assert owner_responses[0].status_code == 409
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "api_key_attribution_changed"
    owner_stream.assert_not_awaited()
    assert not upstreams
    assert not raw_calls
    await service.drain_persistence_tasks(timeout_seconds=5)
    async with SessionLocal() as session:
        reservations = (await session.scalars(select(ApiKeyUsageReservation))).all()
        assert len(reservations) == 1
        assert reservations[0].id == forwarded_reservations[0]
        assert reservations[0].api_key_id == key["id"]
        assert reservations[0].status == "released"
    detail = (await async_client.get("/api/api-keys/")).json()
    assert next(item for item in detail if item["id"] == key["id"])["limits"][0]["currentValue"] == 0
    teams = (await async_client.get("/api/teams/")).json()
    for team_id in (key["teamId"], destination["id"]):
        assert next(item for item in teams if item["id"] == team_id)["limits"][0]["currentValue"] == 0
