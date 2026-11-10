"""Keep immutable team attribution across same-secret API-key reassignment."""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "20261109_120000_add_key_attribution_history"
down_revision = "20261106_120000_add_team_consumption"
branch_labels = None
depends_on = None

_SENTINEL = "\x1f"
_HOURLY = "request_usage_hourly_rollups"
_OLD_PK = ["bucket_epoch", "account_id", "api_key_id", "model", "service_tier", "request_kind", "is_deleted"]
_NEW_PK = [
    "bucket_epoch",
    "account_id",
    "api_key_id",
    "api_key_attribution_id",
    "model",
    "service_tier",
    "request_kind",
    "is_deleted",
]


def _snapshot_id(key_id: str, team_id: str, owner: str | None) -> str:
    # Frozen migration algorithm: do not import changing runtime helpers.
    return hashlib.sha256(
        json.dumps([key_id, team_id, owner], separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _replace_hourly_pk(columns: list[str]) -> None:
    bind = op.get_bind()
    name = sa.inspect(bind).get_pk_constraint(_HOURLY)["name"] or "pk_request_usage_hourly_rollups"
    with op.batch_alter_table(_HOURLY, naming_convention={"pk": "pk_%(table_name)s"}) as batch:
        batch.drop_constraint(name, type_="primary")
        batch.create_primary_key("pk_request_usage_hourly_rollups", columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "api_key_attributions" in tables:
        if (
            "api_key_attribution_id" in {c["name"] for c in inspector.get_columns("request_logs")}
            and "api_key_attribution_id" in inspector.get_pk_constraint(_HOURLY)["constrained_columns"]
        ):
            # Lost-ledger replay must never reassign historical rows.
            return
        raise RuntimeError("Partial key-attribution schema requires recovery before retry")
    op.create_table(
        "api_key_attributions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("api_key_id", sa.String(), sa.ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.String(), sa.ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "owner_user_id", sa.String(), sa.ForeignKey("dashboard_users.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    for column in ("api_key_id", "team_id", "owner_user_id"):
        op.create_index("ix_api_key_attributions_" + column, "api_key_attributions", [column])
    snapshots = sa.table(
        "api_key_attributions",
        sa.column("id", sa.String(64)),
        sa.column("api_key_id", sa.String()),
        sa.column("team_id", sa.String()),
        sa.column("owner_user_id", sa.String()),
    )
    # Keys are small administrative metadata, not request history. History is
    # backfilled set-wise below, including already-pruned folded buckets.
    keys = bind.execute(sa.text("SELECT id,team_id,owner_user_id FROM api_keys")).all()
    if keys:
        bind.execute(
            snapshots.insert(),
            [{"id": _snapshot_id(k, t, u), "api_key_id": k, "team_id": t, "owner_user_id": u} for k, t, u in keys],
        )
    with op.batch_alter_table("request_logs") as batch:
        batch.add_column(sa.Column("api_key_attribution_id", sa.String(64), nullable=True))
        batch.create_foreign_key(
            "fk_request_logs_key_attribution",
            "api_key_attributions",
            ["api_key_attribution_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    bind.execute(
        sa.text(
            "UPDATE request_logs SET api_key_attribution_id = "
            "(SELECT id FROM api_key_attributions a WHERE a.api_key_id=request_logs.api_key_id) "
            "WHERE api_key_id IS NOT NULL"
        )
    )
    op.add_column(_HOURLY, sa.Column("api_key_attribution_id", sa.String(64), nullable=False, server_default=_SENTINEL))
    # api_key_id uses the collision-free rollup dimension encoding, not raw IDs.
    hourly = sa.table(_HOURLY, sa.column("api_key_id", sa.String()), sa.column("api_key_attribution_id", sa.String(64)))
    encoded_key = sa.case(
        (sa.func.substr(snapshots.c.api_key_id, 1, 1) == _SENTINEL, sa.literal(_SENTINEL) + snapshots.c.api_key_id),
        else_=snapshots.c.api_key_id,
    )
    snapshot = sa.select(snapshots.c.id).where(encoded_key == hourly.c.api_key_id).scalar_subquery()
    bind.execute(hourly.update().values(api_key_attribution_id=sa.func.coalesce(snapshot, _SENTINEL)))
    _replace_hourly_pk(_NEW_PK)


def downgrade() -> None:
    bind = op.get_bind()
    multiple = bind.execute(
        sa.text("SELECT api_key_id FROM api_key_attributions GROUP BY api_key_id HAVING COUNT(*)>1 LIMIT 1")
    ).first()
    mismatch = bind.execute(
        sa.text(
            "SELECT a.id FROM api_key_attributions a JOIN api_keys k ON k.id=a.api_key_id "
            "WHERE a.team_id<>k.team_id OR a.owner_user_id<>k.owner_user_id "
            "OR (a.owner_user_id IS NULL AND k.owner_user_id IS NOT NULL) "
            "OR (a.owner_user_id IS NOT NULL AND k.owner_user_id IS NULL) LIMIT 1"
        )
    ).first()
    if multiple is not None or mismatch is not None:
        raise RuntimeError(
            "Cannot downgrade keys with multiple historical assignments; restore the pre-upgrade volume instead"
        )
    _replace_hourly_pk(_OLD_PK)
    op.drop_column(_HOURLY, "api_key_attribution_id")
    with op.batch_alter_table("request_logs") as batch:
        batch.drop_constraint("fk_request_logs_key_attribution", type_="foreignkey")
        batch.drop_column("api_key_attribution_id")
    op.drop_table("api_key_attributions")
