from pathlib import Path
from types import SimpleNamespace

import pytest

from sqlalchemy.dialects import mysql

from app.migrate import (
    AppliedMigration,
    BaselineRequirements,
    COMMAND_CENTER_INDEX_UPGRADES,
    MigrationError,
    MigrationFile,
    _migration_statement_already_satisfied,
    apply_pending_migrations,
    baseline_existing_database,
    build_baseline_index_requirements,
    build_baseline_requirements,
    build_command_center_index_upgrade_statements,
    discover_migrations,
    inspect_migration_status,
    split_sql_statements,
    validate_applied_migrations,
    validate_baseline_schema,
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


def test_custom_agent_runtime_migration_adds_dual_credentials_capabilities_and_run_metadata() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    sql = (
        repository_root
        / "backend-python/migrations/bootstrap_sql/V47__agent_review_custom_openai_runtime.sql"
    ).read_text(encoding="utf-8")

    statements = split_sql_statements(sql)

    assert len(statements) == 3
    assert "DEFAULT 'CLAUDE_CODE_DEEPSEEK'" in statements[0]
    assert "custom_api_key_ciphertext" in statements[0]
    assert "capabilities_json" in statements[1]
    assert "responses_runner_version" in statements[1]
    assert "runner_type" in statements[2]
    assert "provider" in statements[2]


def test_custom_agent_tls_migration_defaults_to_strict_verification() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    sql = (
        repository_root
        / "backend-python/migrations/bootstrap_sql/V48__agent_review_custom_tls_verify.sql"
    ).read_text(encoding="utf-8")

    statements = split_sql_statements(sql)

    assert len(statements) == 1
    assert "custom_tls_verify BOOLEAN NOT NULL DEFAULT TRUE" in statements[0]


def test_dynamic_agent_runtime_migration_preserves_legacy_slots_and_selection() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    sql = (
        repository_root
        / "backend-python/migrations/bootstrap_sql/V49__dynamic_agent_review_runtimes.sql"
    ).read_text(encoding="utf-8")

    statements = split_sql_statements(sql)

    assert len(statements) == 5
    assert "CREATE TABLE IF NOT EXISTS code_quality_agent_runtimes" in statements[0]
    assert "selected_runtime_code VARCHAR(40)" in statements[1]
    assert "settings.api_key_ciphertext" in statements[2]
    assert "settings.custom_api_key_ciphertext" in statements[3]
    assert "NOT EXISTS" in statements[2]
    assert "NOT EXISTS" in statements[3]
    assert "OPENAI_RESPONSES_CUSTOM" in statements[4]
    assert "ELSE 'CLAUDE_CODE_DEEPSEEK'" in statements[4]
    assert "DECRYPT" not in sql.upper()


def test_review_model_provider_preset_migration_backfills_visibility_and_reasoning() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    sql = (
        repository_root
        / "backend-python/migrations/bootstrap_sql/V50__review_model_provider_presets.sql"
    ).read_text(encoding="utf-8")

    statements = split_sql_statements(sql)

    assert len(statements) == 4
    assert "catalog_visible BOOLEAN NOT NULL DEFAULT FALSE" in statements[0]
    assert "reasoning_effort VARCHAR(16) NULL" in statements[1]
    assert "catalog_visible = TRUE" in statements[2]
    assert "built_in = FALSE" in statements[2]
    assert "TRIM(COALESCE(api_key, '')) <> ''" in statements[2]
    assert "provider_type = 'OPENAI_RESPONSES'" in statements[3]


def test_v48_reconciles_compatible_column_added_by_runtime_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = next(item for item in discover_migrations() if item.version == 48)
    statement = split_sql_statements(migration.path.read_text(encoding="utf-8"))[0]

    class Inspector:
        @staticmethod
        def get_columns(_table_name):
            return [
                {
                    "name": "custom_tls_verify",
                    "type": mysql.TINYINT(display_width=1),
                    "nullable": False,
                    "default": "1",
                }
            ]

    monkeypatch.setattr("app.migrate.inspect", lambda _connection: Inspector())

    assert _migration_statement_already_satisfied(object(), migration, statement) is True


def test_v49_reconciles_compatible_selected_runtime_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = next(item for item in discover_migrations() if item.version == 49)
    statement = split_sql_statements(migration.path.read_text(encoding="utf-8"))[1]

    class Inspector:
        @staticmethod
        def get_columns(_table_name):
            return [
                {
                    "name": "selected_runtime_code",
                    "type": mysql.VARCHAR(length=40),
                    "nullable": False,
                    "default": "CLAUDE_CODE_DEEPSEEK",
                }
            ]

    monkeypatch.setattr("app.migrate.inspect", lambda _connection: Inspector())

    assert _migration_statement_already_satisfied(object(), migration, statement) is True


@pytest.mark.parametrize(
    ("statement_index", "column"),
    [
        (
            0,
            {
                "name": "catalog_visible",
                "type": mysql.TINYINT(display_width=1),
                "nullable": False,
                "default": "0",
            },
        ),
        (
            1,
            {
                "name": "reasoning_effort",
                "type": mysql.VARCHAR(length=16),
                "nullable": True,
                "default": None,
            },
        ),
    ],
)
def test_v50_reconciles_compatible_provider_columns(
    monkeypatch: pytest.MonkeyPatch,
    statement_index: int,
    column: dict,
) -> None:
    migration = next(item for item in discover_migrations() if item.version == 50)
    statement = split_sql_statements(migration.path.read_text(encoding="utf-8"))[
        statement_index
    ]

    class Inspector:
        @staticmethod
        def get_columns(_table_name):
            return [column]

    monkeypatch.setattr("app.migrate.inspect", lambda _connection: Inspector())

    assert _migration_statement_already_satisfied(object(), migration, statement) is True


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


def test_discover_migrations_is_contiguous_and_includes_checksums() -> None:
    migrations = discover_migrations()

    assert migrations[0].version == 1
    assert migrations[-1].version == 50
    assert [item.version for item in migrations] == list(range(1, 51))
    assert all(len(item.checksum) == 64 for item in migrations)


def test_baseline_requirements_cover_latest_agent_runtime_schema() -> None:
    migrations = discover_migrations()
    requirements = build_baseline_requirements(migrations)

    assert "code_quality_agent_settings" in requirements.tables
    assert "runtime_type" in requirements.columns["code_quality_agent_settings"]
    assert "custom_api_key_ciphertext" in requirements.columns["code_quality_agent_settings"]
    assert "custom_tls_verify" in requirements.columns["code_quality_agent_settings"]
    assert "selected_runtime_code" in requirements.columns["code_quality_agent_settings"]
    assert "code_quality_agent_runtimes" in requirements.tables
    assert "runtime_code" in requirements.columns["code_quality_agent_runtimes"]
    assert (
        "idx_code_quality_agent_runtimes_enabled_sort"
        in requirements.indexes["code_quality_agent_runtimes"]
    )
    assert "capabilities_json" in requirements.columns["code_quality_agent_workers"]
    assert "runner_type" in requirements.columns["agent_review_runs"]
    assert "idx_agent_review_runs_cc_status_updated" in requirements.indexes["agent_review_runs"]
    assert "uk_task" not in requirements.indexes["code_quality_review_results"]
    assert (
        "uk_code_quality_result_task_review_key"
        in requirements.indexes["code_quality_review_results"]
    )
    assert (
        "uk_code_quality_fix_preview_task_finding"
        not in requirements.indexes["code_quality_fix_previews"]
    )

    index_requirements = {
        (item.table_name, item.index_name): item
        for item in build_baseline_index_requirements(migrations)
    }
    result_key = (
        "code_quality_review_results",
        "uk_code_quality_result_task_review_key",
    )
    assert index_requirements[result_key].unique is True
    assert index_requirements[result_key].column_names == ("task_id", "review_key")
    assert ("code_quality_review_results", "uk_task") not in index_requirements


def test_validate_baseline_schema_reports_missing_objects() -> None:
    requirements = BaselineRequirements(
        tables=frozenset({"review_tasks", "agent_review_runs"}),
        columns={
            "review_tasks": frozenset({"id", "review_status"}),
            "agent_review_runs": frozenset({"id"}),
        },
        indexes={"review_tasks": frozenset({"idx_review_status_created"})},
    )
    inspector = _BaselineInspector(
        tables={"review_tasks"},
        columns={"review_tasks": {"id"}},
        indexes={"review_tasks": set()},
    )

    assert validate_baseline_schema(inspector, requirements) == [
        "table:agent_review_runs",
        "column:review_tasks.review_status",
        "index:review_tasks.idx_review_status_created",
    ]


def test_applied_migration_checksum_change_is_rejected(tmp_path: Path) -> None:
    script = tmp_path / "V1__demo.sql"
    script.write_text("CREATE TABLE demo (id INT);", encoding="utf-8")
    migration = MigrationFile(1, "demo", script.name, "new-checksum", script)
    applied = AppliedMigration(1, "demo", script.name, "old-checksum", False)

    with pytest.raises(MigrationError, match="Checksum mismatch"):
        validate_applied_migrations((applied,), (migration,))


def test_empty_database_apply_is_recorded_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrations = _temporary_migrations(tmp_path)
    state = _MigrationState()
    engine = _MigrationEngine(state)
    monkeypatch.setattr(
        "app.migrate.inspect", lambda connection: _StateInspector(connection.state)
    )

    assert apply_pending_migrations(engine, migrations) == [1, 2]
    assert apply_pending_migrations(engine, migrations) == []

    status = inspect_migration_status(engine, migrations)
    assert status.ledger_exists is True
    assert status.baseline_required is False
    assert status.pending == ()
    assert [item.version for item in status.applied] == [1, 2]
    assert state.migration_statement_count == 2


def test_existing_database_requires_valid_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrations = _temporary_migrations(tmp_path)
    state = _MigrationState(
        tables={"review_tasks"},
        columns={"review_tasks": {"id", "review_status"}},
    )
    engine = _MigrationEngine(state)
    monkeypatch.setattr(
        "app.migrate.inspect", lambda connection: _StateInspector(connection.state)
    )

    baseline_existing_database(engine, migrations)

    assert [row["version"] for row in state.applied] == [1, 2]
    assert all(row["baseline"] is True for row in state.applied)

    incomplete = _MigrationState(
        tables={"review_tasks"}, columns={"review_tasks": {"id"}}
    )
    with pytest.raises(MigrationError, match="review_status"):
        baseline_existing_database(_MigrationEngine(incomplete), migrations)


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


class _BaselineInspector:
    def __init__(self, *, tables, columns, indexes) -> None:
        self.tables = tables
        self.columns = columns
        self.indexes = indexes

    def get_table_names(self) -> list[str]:
        return list(self.tables)

    def get_columns(self, table_name: str) -> list[dict]:
        return [{"name": item} for item in self.columns.get(table_name, set())]

    def get_indexes(self, table_name: str) -> list[dict]:
        return [{"name": item} for item in self.indexes.get(table_name, set())]

    def get_unique_constraints(self, _table_name: str) -> list[dict]:
        return []


def _temporary_migrations(tmp_path: Path) -> tuple[MigrationFile, ...]:
    first = tmp_path / "V1__core.sql"
    first.write_text("CREATE TABLE review_tasks (id BIGINT PRIMARY KEY);", encoding="utf-8")
    second = tmp_path / "V2__status.sql"
    second.write_text(
        "ALTER TABLE review_tasks ADD COLUMN review_status VARCHAR(32);",
        encoding="utf-8",
    )
    return discover_migrations(tmp_path)


class _MigrationState:
    def __init__(self, *, tables=None, columns=None, indexes=None) -> None:
        self.tables = set(tables or set())
        self.columns = {name: set(value) for name, value in (columns or {}).items()}
        self.indexes = {name: set(value) for name, value in (indexes or {}).items()}
        self.applied: list[dict] = []
        self.migration_statement_count = 0


class _StateInspector(_BaselineInspector):
    def __init__(self, state: _MigrationState) -> None:
        self.state = state
        super().__init__(tables=state.tables, columns=state.columns, indexes=state.indexes)

    def has_table(self, table_name: str) -> bool:
        return table_name in self.state.tables


class _Result:
    def __init__(self, *, scalar_value=None, rows=None) -> None:
        self.scalar_value = scalar_value
        self.rows = rows or []

    def scalar(self):
        return self.scalar_value

    def mappings(self):
        return iter(self.rows)


class _MigrationConnection:
    def __init__(self, state: _MigrationState) -> None:
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, statement, parameters=None):
        sql = str(statement)
        if "SELECT DATABASE()" in sql:
            return _Result(scalar_value="unit_test")
        if "GET_LOCK" in sql or "RELEASE_LOCK" in sql:
            return _Result(scalar_value=1)
        if sql.startswith("SELECT version"):
            return _Result(rows=sorted(self.state.applied, key=lambda row: row["version"]))
        if sql.startswith("INSERT INTO schema_migrations"):
            self.state.applied.append(dict(parameters or {}))
            return _Result()
        raise AssertionError(f"Unexpected SQL: {sql}")

    def exec_driver_sql(self, statement: str):
        normalized = " ".join(statement.split())
        if normalized.startswith("CREATE TABLE IF NOT EXISTS schema_migrations"):
            self.state.tables.add("schema_migrations")
            return _Result()
        if normalized.startswith("CREATE TABLE review_tasks"):
            self.state.tables.add("review_tasks")
            self.state.columns.setdefault("review_tasks", set()).add("id")
            self.state.migration_statement_count += 1
            return _Result()
        if normalized.startswith("ALTER TABLE review_tasks ADD COLUMN review_status"):
            self.state.columns.setdefault("review_tasks", set()).add("review_status")
            self.state.migration_statement_count += 1
            return _Result()
        raise AssertionError(f"Unexpected driver SQL: {normalized}")

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class _MigrationEngine:
    dialect = SimpleNamespace(name="mysql")

    def __init__(self, state: _MigrationState) -> None:
        self.state = state

    def connect(self) -> _MigrationConnection:
        return _MigrationConnection(self.state)
