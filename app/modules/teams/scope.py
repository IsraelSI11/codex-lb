from collections.abc import Collection


def resolve_effective_scope(team_ids: Collection[str] | None, key_ids: Collection[str] | None) -> frozenset[str] | None:
    if team_ids is None:
        return None if key_ids is None else frozenset(key_ids)
    if key_ids is None:
        return frozenset(team_ids)
    return frozenset(team_ids).intersection(key_ids)
