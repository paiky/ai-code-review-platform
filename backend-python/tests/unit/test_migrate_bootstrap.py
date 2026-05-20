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
