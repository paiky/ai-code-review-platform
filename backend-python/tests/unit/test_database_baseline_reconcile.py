from pathlib import Path

import pytest
from sqlalchemy.dialects import mysql

from app import database_baseline_reconcile, database_baseline_reconcile_cli
from app.database_baseline_reconcile import (
    apply_missing_indexes,
    build_index_ddl,
    inspect_missing_index_plan,
)
from app.migrate import build_baseline_index_requirements, discover_migrations


def test_final_index_requirements_respect_drop_and_replacement() -> None:
    requirements = {
        (item.table_name, item.index_name): item
        for item in build_baseline_index_requirements(discover_migrations())
    }

    assert ("code_quality_review_results", "uk_task") not in requirements
    replacement = requirements[
        ("code_quality_review_results", "uk_code_quality_result_task_review_key")
    ]
    assert replacement.unique is True
    assert replacement.column_names == ("task_id", "review_key")


def test_plan_reports_metrics_and_unique_duplicate_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrations = _migration_files(tmp_path)
    connection = _Connection(duplicate=True)
    monkeypatch.setattr(
        database_baseline_reconcile, "inspect", lambda _connection: _Inspector()
    )

    plans = inspect_missing_index_plan(connection, migrations)

    assert len(plans) == 2
    assert {item.estimated_rows for item in plans} == {25}
    unique = next(item for item in plans if item.requirement.unique)
    assert unique.duplicate_found is True
    with pytest.raises(ValueError, match="uk_demo_code"):
        apply_missing_indexes(connection, plans)
    assert connection.driver_sql == []


def test_clear_plan_builds_online_index_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrations = _migration_files(tmp_path)
    connection = _Connection(duplicate=False)
    monkeypatch.setattr(
        database_baseline_reconcile, "inspect", lambda _connection: _Inspector()
    )
    plans = inspect_missing_index_plan(connection, migrations)

    unique = next(item for item in plans if item.requirement.unique)
    ddl = build_index_ddl(connection, unique.requirement)
    assert "ADD UNIQUE INDEX uk_demo_code" in ddl
    assert "ALGORITHM=INPLACE, LOCK=NONE" in ddl

    applied = apply_missing_indexes(connection, plans)
    assert applied == ["demo.idx_demo_created", "demo.uk_demo_code"]
    assert len(connection.driver_sql) == 2


def test_test_apply_requires_both_write_confirmations_before_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_targets(tmp_path)
    engine_created = False

    def unexpected_engine(_url: str):
        nonlocal engine_created
        engine_created = True
        raise AssertionError("engine must not be created")

    monkeypatch.setattr(
        database_baseline_reconcile_cli, "create_migration_engine", unexpected_engine
    )

    with pytest.raises(SystemExit, match="--confirm-write"):
        database_baseline_reconcile_cli.main(
            ["apply", "test", "--env-directory", str(tmp_path)]
        )
    with pytest.raises(SystemExit, match="--confirm-test"):
        database_baseline_reconcile_cli.main(
            [
                "apply",
                "test",
                "--confirm-write",
                "--env-directory",
                str(tmp_path),
            ]
        )

    assert engine_created is False


class _Inspector:
    def get_indexes(self, _table_name: str) -> list[dict]:
        return []

    def get_unique_constraints(self, _table_name: str) -> list[dict]:
        return []


class _Result:
    def __init__(self, *, row=None, scalar_value=None) -> None:
        self.row = row
        self.scalar_value = scalar_value

    def mappings(self):
        return self

    def first(self):
        return self.row

    def scalar(self):
        return self.scalar_value


class _Connection:
    dialect = mysql.dialect()

    def __init__(self, *, duplicate: bool) -> None:
        self.duplicate = duplicate
        self.driver_sql: list[str] = []

    def execute(self, statement, _parameters=None):
        sql = str(statement)
        if "information_schema.TABLES" in sql:
            return _Result(
                row={"table_rows": 25, "data_length": 4096, "index_length": 2048}
            )
        if "SELECT EXISTS" in sql:
            return _Result(scalar_value=1 if self.duplicate else 0)
        raise AssertionError(f"Unexpected SQL: {sql}")

    def exec_driver_sql(self, statement: str) -> None:
        self.driver_sql.append(statement)

    def commit(self) -> None:
        return None


def _migration_files(tmp_path: Path):
    (tmp_path / "V1__demo.sql").write_text(
        """
        CREATE TABLE demo (
          id BIGINT PRIMARY KEY,
          code VARCHAR(32) NOT NULL,
          created_at DATETIME NOT NULL,
          UNIQUE KEY uk_demo_code (code),
          KEY idx_demo_created (created_at)
        );
        """,
        encoding="utf-8",
    )
    return discover_migrations(tmp_path)


def _write_targets(directory: Path) -> None:
    (directory / "database.local.env").write_text(
        "DATABASE_TARGET=LOCAL\nDATABASE_URL=mysql+pymysql://u:p@localhost/local\n",
        encoding="utf-8",
    )
    (directory / "database.test.env").write_text(
        "DATABASE_TARGET=TEST\nDATABASE_URL=mysql+pymysql://u:p@test/test\n",
        encoding="utf-8",
    )
