"""Stable identities for immutable API-key attribution snapshots."""

import hashlib
import json


def attribution_id(key_id: str, team_id: str, owner_user_id: str | None) -> str:
    payload = json.dumps([key_id, team_id, owner_user_id], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
