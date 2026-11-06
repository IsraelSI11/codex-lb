"""Teams, memberships and shared limit ownership."""

import sqlalchemy as sa
from alembic import op

revision = "20261106_120000_add_team_consumption"
down_revision = "20260918_000000_merge_scim_and_overflow_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "teams" in tables:
        key_columns = {column["name"] for column in inspector.get_columns("api_keys")}
        limit_columns = {column["name"] for column in inspector.get_columns("api_key_limits")}
        if {"team_id", "attribution_locked"} <= key_columns and "team_id" in limit_columns and "team_members" in tables:
            # Lost-ledger bootstrap replays the whole chain over a live schema.
            # Do not recreate tables, reassign keys or restore removed members.
            op.execute(
                sa.text(
                    "INSERT INTO teams (id, name) SELECT 'default', 'Default' "
                    "WHERE NOT EXISTS (SELECT 1 FROM teams WHERE id = 'default')"
                )
            )
            return
    op.create_table(
        "teams",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("assigned_account_ids", sa.Text(), nullable=True),
        sa.Column("assigned_source_ids", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.execute(sa.text("INSERT INTO teams (id, name) VALUES ('default', 'Default')"))
    op.create_table(
        "team_members",
        sa.Column("team_id", sa.String(), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("dashboard_users.id", ondelete="RESTRICT"), primary_key=True),
    )
    op.execute(
        sa.text(
            "INSERT INTO team_members (team_id, user_id) SELECT DISTINCT 'default', owner_user_id "
            "FROM api_keys WHERE owner_user_id IS NOT NULL"
        )
    )
    with op.batch_alter_table("api_keys") as batch:
        batch.add_column(sa.Column("team_id", sa.String(), nullable=False, server_default="default"))
        batch.add_column(sa.Column("attribution_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.drop_constraint("fk_api_keys_owner_user_id", type_="foreignkey")
        batch.create_foreign_key(
            "fk_api_keys_owner_user_id", "dashboard_users", ["owner_user_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_foreign_key("fk_api_keys_team", "teams", ["team_id"], ["id"], ondelete="RESTRICT")
    op.execute(
        sa.text(
            "UPDATE api_keys SET attribution_locked = true WHERE last_used_at IS NOT NULL "
            "OR id IN (SELECT api_key_id FROM request_logs WHERE api_key_id IS NOT NULL) "
            "OR id IN (SELECT api_key_id FROM api_key_usage_rollups) "
            "OR id IN (SELECT api_key_id FROM api_key_usage_reservations)"
        )
    )
    with op.batch_alter_table("api_key_limits") as batch:
        batch.add_column(sa.Column("team_id", sa.String(), nullable=True))
        batch.alter_column("api_key_id", existing_type=sa.String(), nullable=True)
        batch.create_foreign_key("fk_api_key_limits_team", "teams", ["team_id"], ["id"], ondelete="CASCADE")
        batch.create_check_constraint(
            "ck_limit_one_owner",
            "(api_key_id IS NOT NULL AND team_id IS NULL) OR (api_key_id IS NULL AND team_id IS NOT NULL)",
        )
        batch.create_index("ix_api_key_limits_team_id", ["team_id"])


def downgrade() -> None:
    # Team limits have no legacy representation.
    op.execute(sa.text("DELETE FROM api_key_limits WHERE team_id IS NOT NULL"))
    with op.batch_alter_table("api_key_limits") as batch:
        batch.drop_index("ix_api_key_limits_team_id")
        batch.drop_constraint("ck_limit_one_owner", type_="check")
        batch.drop_constraint("fk_api_key_limits_team", type_="foreignkey")
        batch.drop_column("team_id")
        batch.alter_column("api_key_id", existing_type=sa.String(), nullable=False)
    with op.batch_alter_table("api_keys") as batch:
        batch.drop_constraint("fk_api_keys_owner_user_id", type_="foreignkey")
        batch.create_foreign_key(
            "fk_api_keys_owner_user_id", "dashboard_users", ["owner_user_id"], ["id"], ondelete="SET NULL"
        )
        batch.drop_constraint("fk_api_keys_team", type_="foreignkey")
        batch.drop_column("team_id")
        batch.drop_column("attribution_locked")
    op.drop_table("team_members")
    op.drop_table("teams")
