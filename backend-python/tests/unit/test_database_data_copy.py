from pathlib import Path

import pytest

from app import database_data_copy, database_data_copy_cli
from app.database_data_copy import inspect_database_copy_plan, sanitize_local_database


def test_copy_plan_requires_clients_and_reports_source_target_sizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        database_data_copy.shutil,
        "which",
        lambda name: f"C:/mysql/{name}.exe",
    )
    source = _Engine(_Connection(source=True))
    target = _Engine(_Connection(source=False))

    plan = inspect_database_copy_plan(source, target)

    assert plan.source_table_count == 32
    assert plan.source_rows_estimate == 19459
    assert plan.source_data_bytes == 129171456
    assert plan.target_table_count == 0
    assert plan.mysqldump_path.endswith("mysqldump.exe")


def test_copy_apply_requires_both_confirmations_before_engine_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_targets(tmp_path)
    engine_created = False

    def unexpected_engine(_url: str):
        nonlocal engine_created
        engine_created = True
        raise AssertionError("engine must not be created")

    monkeypatch.setattr(database_data_copy_cli, "create_migration_engine", unexpected_engine)

    with pytest.raises(SystemExit, match="--confirm-copy"):
        database_data_copy_cli.main(
            ["apply", "--env-directory", str(tmp_path)]
        )
    with pytest.raises(SystemExit, match="--confirm-source-data"):
        database_data_copy_cli.main(
            [
                "apply",
                "--confirm-copy",
                "--env-directory",
                str(tmp_path),
            ]
        )

    assert engine_created is False


def test_local_sanitization_clears_credentials_workers_jobs_and_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _SanitizeConnection()
    engine = _SanitizeEngine(connection)
    monkeypatch.setattr(
        database_data_copy,
        "inspect",
        lambda _connection: _SanitizeInspector(),
    )

    affected = sanitize_local_database(engine)
    sql = "\n".join(connection.statements)

    assert "api_key = NULL" in sql
    assert "review_enabled = FALSE" in sql
    assert "DELETE FROM notification_webhooks" in sql
    assert "DELETE FROM code_quality_agent_workers" in sql
    assert "DELETE FROM code_quality_scheduler_jobs" in sql
    assert "runtime_type = 'CLAUDE_CODE_DEEPSEEK'" in sql
    assert "custom_tls_verify = TRUE" in sql
    assert "agent_review_runs" in affected


class _Rows:
    def __init__(self, value) -> None:
        self.value = value

    def mappings(self):
        return self

    def one(self):
        return self.value

    def scalar(self):
        return self.value


class _Connection:
    def __init__(self, *, source: bool) -> None:
        self.source = source

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, statement):
        sql = str(statement)
        if self.source and "SUM(TABLE_ROWS)" in sql:
            return _Rows(
                {
                    "table_count": 32,
                    "rows_estimate": 19459,
                    "data_bytes": 129171456,
                    "index_bytes": 2686976,
                }
            )
        if not self.source and "SELECT COUNT(*)" in sql:
            return _Rows(0)
        raise AssertionError(f"Unexpected SQL: {sql}")


class _Engine:
    def __init__(self, connection) -> None:
        self.connection = connection

    def connect(self):
        return self.connection


class _SanitizeInspector:
    def get_table_names(self) -> list[str]:
        return [
            "projects",
            "notification_webhooks",
            "notification_records",
            "code_quality_model_providers",
            "code_quality_review_settings",
            "project_groups",
            "code_quality_agent_settings",
            "code_quality_agent_workers",
            "code_quality_scheduler_jobs",
            "agent_review_runs",
        ]


class _ExecuteResult:
    rowcount = 1


class _SanitizeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement):
        self.statements.append(str(statement))
        return _ExecuteResult()


class _Begin:
    def __init__(self, connection) -> None:
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args) -> None:
        return None


class _SanitizeEngine:
    def __init__(self, connection) -> None:
        self.connection = connection

    def begin(self):
        return _Begin(self.connection)


def _write_targets(directory: Path) -> None:
    (directory / "database.local.env").write_text(
        "DATABASE_TARGET=LOCAL\nDATABASE_URL=mysql+pymysql://u:p@localhost/local\n",
        encoding="utf-8",
    )
    (directory / "database.test.env").write_text(
        "DATABASE_TARGET=TEST\nDATABASE_URL=mysql+pymysql://u:p@test/test\n",
        encoding="utf-8",
    )
