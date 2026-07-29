from pathlib import Path

from app.migrate import split_sql_statements


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
