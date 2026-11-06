from datetime import datetime

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.migrate import _build_alembic_config, check_schema_drift, run_upgrade
from app.db.models import Account, ModelSource

pytestmark = pytest.mark.integration


def test_existing_key_migrates_without_changing_secret_or_state(tmp_path):
    url = "sqlite:///" + (tmp_path / "teams.db").as_posix()
    parent = "20260918_000000_merge_scim_and_overflow_heads"
    run_upgrade(url, parent, bootstrap_legacy=False)
    engine = create_engine(url)
    with Session(engine) as session:
        session.add(
            Account(
                id="shared",
                email="shared@example.test",
                plan_type="plus",
                access_token_encrypted=b"fixture",
                refresh_token_encrypted=b"fixture",
                id_token_encrypted=b"fixture",
                last_refresh=datetime(2026, 1, 1),
            )
        )
        session.add(ModelSource(id="source", name="Shared", base_url="https://example.invalid"))
        session.commit()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO api_keys (id,name,key_hash,key_prefix,is_active) "
                "VALUES ('legacy','Legacy','unchanged-hash','unchanged-prefix',1)"
            )
        )
        conn.execute(text("INSERT INTO api_key_accounts (api_key_id,account_id) VALUES ('legacy','shared')"))
        conn.execute(text("INSERT INTO api_key_model_sources (api_key_id,source_id) VALUES ('legacy','source')"))
        conn.execute(
            text(
                "INSERT INTO api_key_limits (id,api_key_id,limit_type,limit_window,max_value,current_value,reset_at) "
                "VALUES (51,'legacy','total_tokens','daily',100,7,'2027-01-01 00:00:00')"
            )
        )
    run_upgrade(url, "head", bootstrap_legacy=False)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT team_id,key_hash,key_prefix,is_active,owner_user_id FROM api_keys WHERE id='legacy'")
        ).one()
        assert tuple(row) == ("default", "unchanged-hash", "unchanged-prefix", 1, None)
        assert conn.execute(text("SELECT name FROM teams WHERE id='default'")).scalar() == "Default"
        assert (
            conn.execute(text("SELECT account_id FROM api_key_accounts WHERE api_key_id='legacy'")).scalar() == "shared"
        )
        assert (
            conn.execute(text("SELECT source_id FROM api_key_model_sources WHERE api_key_id='legacy'")).scalar()
            == "source"
        )
        assert conn.execute(text("SELECT current_value FROM api_key_limits WHERE id=51")).scalar() == 7
    assert check_schema_drift(url) == ()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO teams (id,name) VALUES ('backend','Backend')"))
        conn.execute(
            text(
                "INSERT INTO dashboard_users (id,username,role_id,status) "
                "VALUES ('ana','ana','3fe0d2b1-4327-5931-befc-55e04f945100','disabled')"
            )
        )
        conn.execute(
            text(
                "UPDATE api_keys SET team_id='backend',owner_user_id='ana',is_active=0,attribution_locked=1 "
                "WHERE id='legacy'"
            )
        )
        conn.execute(
            text(
                "INSERT INTO api_key_limits (id,team_id,limit_type,limit_window,max_value,current_value,reset_at) "
                "VALUES (52,'backend','total_tokens','daily',100,25,'2027-01-01 00:00:00')"
            )
        )
    # Replaying this revision must not restore a deliberately removed membership,
    # move existing keys back to Default, or reset a team's counter.
    command.stamp(_build_alembic_config(url), parent)
    run_upgrade(url, "head", bootstrap_legacy=False)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM teams WHERE id='default'")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM team_members WHERE user_id='ana'")).scalar() == 0
        assert conn.execute(text("SELECT team_id FROM api_keys WHERE id='legacy'")).scalar() == "backend"
        assert conn.execute(text("SELECT current_value FROM api_key_limits WHERE id=52")).scalar() == 25
    assert check_schema_drift(url) == ()
    command.downgrade(_build_alembic_config(url), parent)
    run_upgrade(url, "head", bootstrap_legacy=False)
    assert check_schema_drift(url) == ()
    engine.dispose()
