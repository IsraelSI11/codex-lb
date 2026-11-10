import os

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from app.db.migrate import _build_alembic_config, check_schema_drift, run_upgrade

pytestmark = pytest.mark.integration
PARENT = "20261106_120000_add_team_consumption"


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_existing_folded_and_raw_history_keeps_assignment(tmp_path, backend):
    url = "sqlite:///" + (tmp_path / "attribution.db").as_posix()
    if backend == "postgresql":
        url = os.environ.get("CODEX_LB_MIGRATION_TEST_DATABASE_URL", "")
        if not url:
            pytest.skip("Dedicated empty PostgreSQL migration database not configured")
    run_upgrade(url, PARENT, bootstrap_legacy=False)
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO teams (id,name) VALUES ('a','A'),('b','B')"))
        c.execute(
            text(
                "INSERT INTO api_keys (id,name,key_hash,key_prefix,team_id,is_active) "
                "VALUES ('key','Key','secret-hash','prefix','a',TRUE)"
            )
        )
        c.execute(
            text(
                "INSERT INTO request_logs (request_id,model,status,api_key_id) "
                "VALUES ('raw','gpt-test','success','key')"
            )
        )
        c.execute(
            text(
                "INSERT INTO request_usage_hourly_rollups "
                "(bucket_epoch,account_id,api_key_id,model,service_tier,request_kind,"
                "is_deleted,request_count,input_tokens) "
                "VALUES (0,'account','key','gpt-test','','responses',FALSE,7,42)"
            )
        )
    run_upgrade(url, "head", bootstrap_legacy=False)
    with engine.connect() as c:
        snapshot = c.execute(text("SELECT id FROM api_key_attributions WHERE api_key_id='key'")).scalar_one()
        assert (
            c.execute(text("SELECT team_id FROM api_key_attributions WHERE id=:id"), {"id": snapshot}).scalar_one()
            == "a"
        )
        assert (
            c.execute(text("SELECT api_key_attribution_id FROM request_logs WHERE request_id='raw'")).scalar_one()
            == snapshot
        )
        assert c.execute(
            text("SELECT api_key_attribution_id,request_count,input_tokens FROM request_usage_hourly_rollups")
        ).one() == (snapshot, 7, 42)
        assert c.execute(text("SELECT key_hash,key_prefix FROM api_keys WHERE id='key'")).one() == (
            "secret-hash",
            "prefix",
        )
    assert check_schema_drift(url) == ()
    command.downgrade(_build_alembic_config(url), PARENT)
    run_upgrade(url, "head", bootstrap_legacy=False)
    assert check_schema_drift(url) == ()
    engine.dispose()


def test_downgrade_refuses_to_move_multi_assignment_history(tmp_path):
    url = "sqlite:///" + (tmp_path / "guard.db").as_posix()
    run_upgrade(url, "head", bootstrap_legacy=False)
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO teams (id,name) VALUES ('a','A'),('b','B')"))
        c.execute(
            text(
                "INSERT INTO api_keys (id,name,key_hash,key_prefix,team_id,is_active) "
                "VALUES ('key','Key','hash','prefix','b',1)"
            )
        )
        c.execute(
            text(
                "INSERT INTO api_key_attributions (id,api_key_id,team_id) "
                "VALUES ('first','key','a'),('second','key','b')"
            )
        )
    with pytest.raises(RuntimeError, match="multiple historical assignments"):
        command.downgrade(_build_alembic_config(url), PARENT)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM api_key_attributions")).scalar_one() == 2
    engine.dispose()
