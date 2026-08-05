from pathlib import Path

from sqlalchemy.dialects import mysql

from app.migrate import (
    COMMAND_CENTER_INDEX_UPGRADES,
    build_command_center_index_upgrade_statements,
    split_sql_statements,
)


def test_split_sql_statements_ignores_comments_and_keeps_case_blocks() -> None:
    sql = """
    -- line comment
    CREATE TABLE demo (
      id BIGINT PRIMARY KEY
    );

    /* block comment */
    INSERT INTO demo(name, note) VALUES ('semi;colon', 'keep');

    UPDATE demo
    SET name = CASE
      WHEN id = 1 THEN 'first'
      ELSE 'other'
    END;
    """

    statements = split_sql_statements(sql)

    assert len(statements) == 3
    assert statements[0].startswith("CREATE TABLE demo")
    assert "semi;colon" in statements[1]
    assert "CASE" in statements[2]


def test_worker_pool_bootstrap_sql_creates_registration_table_and_index() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    sql = (
        repository_root
        / "backend-python/migrations/bootstrap_sql/V44__agent_review_worker_pool.sql"
    ).read_text(encoding="utf-8")

    statements = split_sql_statements(sql)

    assert len(statements) == 1
    assert "CREATE TABLE IF NOT EXISTS code_quality_agent_workers" in statements[0]
    assert "PRIMARY KEY" in statements[0]
    assert "idx_code_quality_agent_workers_heartbeat" in statements[0]


def test_command_center_bootstrap_sql_creates_only_authorized_online_indexes() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    sql = (
        repository_root
        / "backend-python/migrations/bootstrap_sql/V45__command_center_query_indexes.sql"
    ).read_text(encoding="utf-8")

    statements = split_sql_statements(sql)

    assert len(statements) == 5
    assert all("ALGORITHM=INPLACE" in statement for statement in statements)
    assert all("LOCK=NONE" in statement for statement in statements)
    for _, index_name, _ in COMMAND_CENTER_INDEX_UPGRADES:
        assert index_name in sql


def test_fixed_agent_review_policy_migration_updates_existing_groups_and_defaults() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    sql = (
        repository_root
        / "backend-python/migrations/bootstrap_sql/V46__fixed_agent_review_project_group_policy.sql"
    ).read_text(encoding="utf-8")

    statements = split_sql_statements(sql)

    assert len(statements) == 2
    assert "review_engine = 'AGENT'" in statements[0]
    assert "agent_source_export_allowed = TRUE" in statements[0]
    assert "ai_review_enabled = TRUE" in statements[0]
    assert "trigger_on_manual = TRUE" in statements[0]
    assert "DEFAULT 'AGENT'" in statements[1]
    assert statements[1].count("DEFAULT TRUE") == 3


def test_existing_schema_upgrade_is_idempotent_and_groups_indexes_by_table() -> None:
    inspector = _InspectorStub()
    statements = build_command_center_index_upgrade_statements(
        inspector,
        mysql.dialect().identifier_preparer,
    )

    assert len(statements) == 5
    result_upgrade = next(
        item for item in statements
        if "code_quality_review_results" in item[1]
    )
    assert result_upgrade[0] == [
        "idx_cq_results_cc_updated",
        "idx_cq_results_cc_provider_updated_status",
    ]
    assert result_upgrade[1].count("ADD INDEX") == 2

    complete = {
        table_name: {index_name}
        for table_name, index_name, _ in COMMAND_CENTER_INDEX_UPGRADES
    }
    complete["code_quality_review_results"] = {
        "idx_cq_results_cc_updated",
        "idx_cq_results_cc_provider_updated_status",
    }
    assert build_command_center_index_upgrade_statements(
        _InspectorStub(complete),
        mysql.dialect().identifier_preparer,
    ) == []


class _InspectorStub:
    def __init__(self, indexes=None) -> None:
        self.indexes = indexes or {}

    def has_table(self, table_name: str) -> bool:
        return table_name in {
            item[0] for item in COMMAND_CENTER_INDEX_UPGRADES
        }

    def get_indexes(self, table_name: str) -> list[dict]:
        return [
            {"name": name} for name in self.indexes.get(table_name, set())
        ]
