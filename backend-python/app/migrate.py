from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import time
from typing import Iterable

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings


BOOTSTRAP_DIR = Path(__file__).resolve().parents[1] / "migrations" / "bootstrap_sql"
MIGRATION_TABLE = "schema_migrations"
MIGRATION_LOCK_PREFIX = "ai-code-review-schema-migrations"
BASELINE_VERSION = 47
COMMAND_CENTER_INDEX_UPGRADES = (
    ("review_tasks", "idx_review_tasks_cc_created", ("created_at", "id")),
    ("code_quality_review_results", "idx_cq_results_cc_updated", ("updated_at", "id")),
    (
        "code_quality_review_results",
        "idx_cq_results_cc_provider_updated_status",
        ("provider", "updated_at", "status"),
    ),
    ("deterministic_check_runs", "idx_deterministic_runs_cc_created", ("created_at", "id")),
    (
        "notification_records",
        "idx_notification_records_cc_created_status_task",
        ("created_at", "status", "task_id"),
    ),
    (
        "agent_review_runs",
        "idx_agent_review_runs_cc_status_updated",
        ("status", "updated_at", "id"),
    ),
)


class MigrationError(RuntimeError):
    pass


class MigrationBaselineRequired(MigrationError):
    pass


@dataclass(frozen=True)
class MigrationFile:
    version: int
    description: str
    script_name: str
    checksum: str
    path: Path


@dataclass(frozen=True)
class AppliedMigration:
    version: int
    description: str
    script_name: str
    checksum: str
    baseline: bool


@dataclass(frozen=True)
class BaselineRequirements:
    tables: frozenset[str]
    columns: dict[str, frozenset[str]]
    indexes: dict[str, frozenset[str]]


@dataclass(frozen=True)
class IndexRequirement:
    table_name: str
    index_name: str
    columns_sql: str
    column_names: tuple[str, ...]
    unique: bool
    source_version: int


@dataclass(frozen=True)
class MigrationStatus:
    database_empty: bool
    ledger_exists: bool
    baseline_required: bool
    applied: tuple[AppliedMigration, ...]
    pending: tuple[MigrationFile, ...]
    baseline_missing: tuple[str, ...]


def main(argv: list[str] | None = None, *, database_url: str | None = None) -> None:
    parser = argparse.ArgumentParser(description="AI Code Review schema migration tool")
    parser.add_argument(
        "action",
        nargs="?",
        default="apply",
        choices=("status", "dry-run", "baseline", "apply", "verify"),
    )
    arguments = parser.parse_args(argv)
    url = database_url or get_settings().database_url
    engine = create_migration_engine(url)
    try:
        result = run_migration_action(engine, arguments.action)
        print_migration_result(arguments.action, result)
    except MigrationError as exception:
        raise SystemExit(f"Database migration refused: {exception}") from exception
    except SQLAlchemyError:
        raise SystemExit(
            "Database migration failed while connecting or executing; credentials and URLs are hidden"
        ) from None
    finally:
        engine.dispose()


def run_migration_action(engine, action: str) -> MigrationStatus:
    _assert_mysql(engine)
    migrations = discover_migrations()
    if action in {"status", "dry-run", "verify"}:
        status = inspect_migration_status(engine, migrations)
        if action == "verify":
            _assert_verified(status)
        return status
    if action == "baseline":
        baseline_existing_database(engine, migrations)
        return inspect_migration_status(engine, migrations)
    if action == "apply":
        apply_pending_migrations(engine, migrations)
        return inspect_migration_status(engine, migrations)
    raise MigrationError(f"Unsupported migration action: {action}")


def create_migration_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def discover_migrations(directory: Path = BOOTSTRAP_DIR) -> tuple[MigrationFile, ...]:
    discovered: list[MigrationFile] = []
    versions: set[int] = set()
    for path in sorted(directory.glob("V*.sql"), key=_version_key):
        version = _version_key(path)[0]
        if version in versions:
            raise MigrationError(f"Duplicate migration version: V{version}")
        versions.add(version)
        stem_parts = path.stem.split("__", 1)
        if len(stem_parts) != 2 or not stem_parts[1]:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        discovered.append(
            MigrationFile(
                version=version,
                description=stem_parts[1].replace("_", " "),
                script_name=path.name,
                checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
                path=path,
            )
        )
    if not discovered:
        raise MigrationError(f"Migration SQL directory is empty: {directory}")
    expected = list(range(1, discovered[-1].version + 1))
    actual = [item.version for item in discovered]
    if actual != expected:
        raise MigrationError("Migration versions must be contiguous from V1")
    return tuple(discovered)


def inspect_migration_status(
    engine, migrations: tuple[MigrationFile, ...] | None = None
) -> MigrationStatus:
    migration_files = migrations or discover_migrations()
    with engine.connect() as connection:
        inspector = inspect(connection)
        core_exists = inspector.has_table("review_tasks")
        ledger_exists = inspector.has_table(MIGRATION_TABLE)
        applied = _load_applied_migrations(connection) if ledger_exists else ()
        validate_applied_migrations(applied, migration_files)
        applied_versions = {item.version for item in applied}
        pending = tuple(item for item in migration_files if item.version not in applied_versions)
        baseline_required = core_exists and not applied
        missing: tuple[str, ...] = ()
        if baseline_required:
            requirements = build_baseline_requirements(
                item for item in migration_files if item.version <= BASELINE_VERSION
            )
            missing = tuple(validate_baseline_schema(inspector, requirements))
        return MigrationStatus(
            database_empty=not core_exists,
            ledger_exists=ledger_exists,
            baseline_required=baseline_required,
            applied=tuple(applied),
            pending=pending,
            baseline_missing=missing,
        )


def apply_pending_migrations(
    engine, migrations: tuple[MigrationFile, ...] | None = None
) -> list[int]:
    migration_files = migrations or discover_migrations()
    applied_versions: list[int] = []
    with engine.connect() as connection:
        lock_name = _acquire_migration_lock(connection)
        try:
            inspector = inspect(connection)
            core_exists = inspector.has_table("review_tasks")
            ledger_exists = inspector.has_table(MIGRATION_TABLE)
            existing = _load_applied_migrations(connection) if ledger_exists else ()
            if core_exists and not existing:
                raise MigrationBaselineRequired(
                    "Existing database has no migration ledger; run baseline after schema verification"
                )
            _ensure_migration_table(connection)
            existing = _load_applied_migrations(connection)
            validate_applied_migrations(existing, migration_files)
            recorded = {item.version for item in existing}
            for migration in migration_files:
                if migration.version in recorded:
                    continue
                started = time.perf_counter()
                try:
                    sql = migration.path.read_text(encoding="utf-8")
                    for statement in split_sql_statements(sql):
                        if not _migration_statement_already_satisfied(
                            connection, migration, statement
                        ):
                            connection.exec_driver_sql(statement)
                    _record_migration(
                        connection,
                        migration,
                        baseline=False,
                        execution_ms=int((time.perf_counter() - started) * 1000),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                applied_versions.append(migration.version)
        finally:
            _release_migration_lock(connection, lock_name)
    return applied_versions


def _migration_statement_already_satisfied(
    connection, migration: MigrationFile, statement: str
) -> bool:
    """Reconcile migration effects that already exist outside the migration ledger."""
    if migration.version == 54:
        add_column = re.fullmatch(
            r"\s*ALTER\s+TABLE\s+\x60?(\w+)\x60?\s+ADD\s+COLUMN\s+"
            r"\x60?(\w+)\x60?\s+(.+?)\s*",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if add_column:
            table_name, column_name, definition = add_column.groups()
            inspector = inspect(connection)
            if not inspector.has_table(table_name):
                return False
            columns = {
                str(column.get("name") or ""): column
                for column in inspector.get_columns(table_name)
            }
            existing = columns.get(column_name)
            if existing is None:
                return False
            type_name = str(existing.get("type") or "").casefold().replace(" ", "")
            definition_name = definition.casefold().replace(" ", "")
            expected_nullable = "notnull" not in definition_name
            compatible_type = (
                ("varchar(" in definition_name and "varchar(" in type_name)
                or ("bigint" in definition_name and "bigint" in type_name)
                or ("boolean" in definition_name and any(
                    marker in type_name for marker in ("bool", "tinyint")
                ))
                or ("datetime" in definition_name and "datetime" in type_name)
            )
            if existing.get("nullable", True) != expected_nullable or not compatible_type:
                raise MigrationError(
                    f"Existing {table_name}.{column_name} is incompatible with V54"
                )
            return True

        add_index = re.fullmatch(
            r"\s*ALTER\s+TABLE\s+\x60?(\w+)\x60?\s+ADD\s+INDEX\s+"
            r"\x60?(\w+)\x60?\s*\(.+\)\s*",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if add_index:
            table_name, index_name = add_index.groups()
            inspector = inspect(connection)
            if not inspector.has_table(table_name):
                return False
            return index_name in {
                str(index.get("name") or "")
                for index in inspector.get_indexes(table_name)
            }
        return False
    if migration.version == 52:
        match = re.fullmatch(
            r"\s*ALTER\s+TABLE\s+`?agent_review_runs`?\s+"
            r"MODIFY\s+COLUMN\s+`?input_json`?\s+LONGTEXT\s+NULL\s*,\s*"
            r"MODIFY\s+COLUMN\s+`?completion_context_json`?\s+LONGTEXT\s+NULL\s*",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return False
        inspector = inspect(connection)
        columns = {
            str(column.get("name") or ""): column
            for column in inspector.get_columns("agent_review_runs")
        }
        return all(
            column is not None
            and "longtext" in str(column.get("type") or "").casefold().replace(" ", "")
            and column.get("nullable") is not False
            for column in (
                columns.get("input_json"),
                columns.get("completion_context_json"),
            )
        )
    if migration.version == 51:
        match = re.fullmatch(
            r"\s*ALTER\s+TABLE\s+`?code_quality_model_providers`?\s+"
            r"ADD\s+COLUMN\s+`?tls_verify`?\s+BOOLEAN\s+NOT\s+NULL\s+"
            r"DEFAULT\s+TRUE\s+AFTER\s+reasoning_effort\s*",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return False
        inspector = inspect(connection)
        columns = {
            str(column.get("name") or ""): column
            for column in inspector.get_columns("code_quality_model_providers")
        }
        existing = columns.get("tls_verify")
        if existing is None:
            return False
        type_name = str(existing.get("type") or "").casefold().replace(" ", "")
        default = str(existing.get("default") or "").strip("()'\"").casefold()
        compatible = (
            existing.get("nullable") is False
            and any(marker in type_name for marker in ("bool", "tinyint"))
            and default in {"1", "true"}
        )
        if not compatible:
            raise MigrationError(
                "Existing code_quality_model_providers.tls_verify is incompatible with V51"
            )
        return True
    if migration.version == 50:
        match = re.fullmatch(
            r"\s*ALTER\s+TABLE\s+`?code_quality_model_providers`?\s+"
            r"ADD\s+COLUMN\s+`?(catalog_visible|reasoning_effort)`?\s+"
            r"(.+?)\s+AFTER\s+`?(timeout_seconds|catalog_visible)`?\s*",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return False
        column_name = match.group(1).casefold()
        inspector = inspect(connection)
        columns = {
            str(column.get("name") or ""): column
            for column in inspector.get_columns("code_quality_model_providers")
        }
        existing = columns.get(column_name)
        if existing is None:
            return False
        type_name = str(existing.get("type") or "").casefold().replace(" ", "")
        if column_name == "catalog_visible":
            default = str(existing.get("default") or "").strip("()'\"").casefold()
            compatible = (
                existing.get("nullable") is False
                and any(marker in type_name for marker in ("bool", "tinyint"))
                and default in {"0", "false"}
            )
        else:
            compatible = (
                existing.get("nullable") is not False
                and "varchar(16)" in type_name
            )
        if not compatible:
            raise MigrationError(
                f"Existing code_quality_model_providers.{column_name} is incompatible with V50"
            )
        return True
    if migration.version == 49:
        match = re.fullmatch(
            r"\s*ALTER\s+TABLE\s+`?code_quality_agent_settings`?\s+"
            r"ADD\s+COLUMN\s+`?selected_runtime_code`?\s+VARCHAR\(40\)\s+"
            r"NOT\s+NULL\s+DEFAULT\s+'CLAUDE_CODE_DEEPSEEK'\s+AFTER\s+runtime_type\s*",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return False
        inspector = inspect(connection)
        columns = {
            str(column.get("name") or ""): column
            for column in inspector.get_columns("code_quality_agent_settings")
        }
        existing = columns.get("selected_runtime_code")
        if existing is None:
            return False
        type_name = str(existing.get("type") or "").casefold()
        default = str(existing.get("default") or "").strip("()'\"").upper()
        if (
            existing.get("nullable") is not False
            or "varchar(40)" not in type_name.replace(" ", "")
            or default != "CLAUDE_CODE_DEEPSEEK"
        ):
            raise MigrationError(
                "Existing code_quality_agent_settings.selected_runtime_code is incompatible with V49"
            )
        return True
    if migration.version != 48:
        return False
    match = re.fullmatch(
        r"\s*ALTER\s+TABLE\s+`?code_quality_agent_settings`?\s+"
        r"ADD\s+COLUMN\s+`?custom_tls_verify`?\s+BOOLEAN\s+NOT\s+NULL\s+"
        r"DEFAULT\s+TRUE\s+AFTER\s+custom_reasoning_effort\s*",
        statement,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return False
    inspector = inspect(connection)
    columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns("code_quality_agent_settings")
    }
    existing = columns.get("custom_tls_verify")
    if existing is None:
        return False
    type_name = str(existing.get("type") or "").casefold()
    default = str(existing.get("default") or "").strip("()'\"").casefold()
    if (
        existing.get("nullable") is not False
        or not any(marker in type_name for marker in ("bool", "tinyint"))
        or default not in {"1", "true"}
    ):
        raise MigrationError(
            "Existing code_quality_agent_settings.custom_tls_verify is incompatible with V48"
        )
    return True


def baseline_existing_database(
    engine, migrations: tuple[MigrationFile, ...] | None = None
) -> list[int]:
    migration_files = migrations or discover_migrations()
    baseline_files = tuple(
        item for item in migration_files if item.version <= BASELINE_VERSION
    )
    with engine.connect() as connection:
        lock_name = _acquire_migration_lock(connection)
        try:
            inspector = inspect(connection)
            if not inspector.has_table("review_tasks"):
                raise MigrationError("Cannot baseline an empty database; run apply instead")
            if inspector.has_table(MIGRATION_TABLE):
                existing = _load_applied_migrations(connection)
                if existing:
                    validate_applied_migrations(existing, migration_files)
                    raise MigrationError("Migration ledger is not empty; baseline is only allowed once")
            requirements = build_baseline_requirements(baseline_files)
            missing = validate_baseline_schema(inspector, requirements)
            if missing:
                preview = ", ".join(missing[:20])
                suffix = " ..." if len(missing) > 20 else ""
                raise MigrationError(
                    f"Existing schema does not satisfy V{BASELINE_VERSION} baseline: "
                    f"{preview}{suffix}"
                )
            _ensure_migration_table(connection)
            recorded: list[int] = []
            for migration in baseline_files:
                _record_migration(connection, migration, baseline=True, execution_ms=0)
                recorded.append(migration.version)
            connection.commit()
            return recorded
        except Exception:
            connection.rollback()
            raise
        finally:
            _release_migration_lock(connection, lock_name)


def validate_applied_migrations(
    applied: Iterable[AppliedMigration], migrations: Iterable[MigrationFile]
) -> None:
    available = {item.version: item for item in migrations}
    for record in applied:
        migration = available.get(record.version)
        if migration is None:
            raise MigrationError(
                f"Applied migration V{record.version} is missing from the repository"
            )
        if record.checksum != migration.checksum:
            raise MigrationError(
                f"Checksum mismatch for applied migration {migration.script_name}"
            )
        if record.script_name != migration.script_name:
            raise MigrationError(
                f"Script name mismatch for applied migration V{record.version}"
            )


def build_baseline_requirements(
    migrations: Iterable[MigrationFile],
) -> BaselineRequirements:
    tables: set[str] = set()
    columns: dict[str, set[str]] = {}
    indexes: dict[str, set[str]] = {}
    for migration in migrations:
        sql = migration.path.read_text(encoding="utf-8")
        for statement in split_sql_statements(sql):
            create_match = re.match(
                r"\s*CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+`?([A-Za-z0-9_]+)`?\s*\((.*)\)",
                statement,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if create_match:
                table_name = create_match.group(1)
                tables.add(table_name)
                table_columns, table_indexes = _parse_create_table_body(create_match.group(2))
                columns.setdefault(table_name, set()).update(table_columns)
                indexes.setdefault(table_name, set()).update(table_indexes)
                continue
            alter_match = re.match(
                r"\s*ALTER\s+TABLE\s+`?([A-Za-z0-9_]+)`?\s+(.*)",
                statement,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not alter_match:
                continue
            table_name = alter_match.group(1)
            body = alter_match.group(2)
            tables.add(table_name)
            columns.setdefault(table_name, set()).update(
                re.findall(
                    r"\bADD\s+COLUMN\s+`?([A-Za-z0-9_]+)`?",
                    body,
                    flags=re.IGNORECASE,
                )
            )
            _apply_alter_index_requirements(
                body, indexes.setdefault(table_name, set())
            )
    return BaselineRequirements(
        tables=frozenset(tables),
        columns={name: frozenset(values) for name, values in columns.items()},
        indexes={name: frozenset(values) for name, values in indexes.items()},
    )


def build_baseline_index_requirements(
    migrations: Iterable[MigrationFile],
) -> tuple[IndexRequirement, ...]:
    requirements: dict[tuple[str, str], IndexRequirement] = {}
    for migration in migrations:
        sql = migration.path.read_text(encoding="utf-8")
        for statement in split_sql_statements(sql):
            create_match = re.match(
                r"\s*CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+`?([A-Za-z0-9_]+)`?\s*\((.*)\)",
                statement,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if create_match:
                table_name = create_match.group(1)
                for clause in _split_top_level_clauses(create_match.group(2)):
                    parsed = _parse_index_clause(
                        clause, table_name=table_name, source_version=migration.version
                    )
                    if parsed:
                        requirements[(table_name, parsed.index_name)] = parsed
                continue
            alter_match = re.match(
                r"\s*ALTER\s+TABLE\s+`?([A-Za-z0-9_]+)`?\s+(.*)",
                statement,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not alter_match:
                continue
            table_name = alter_match.group(1)
            for clause in _split_top_level_clauses(alter_match.group(2)):
                normalized = clause.strip()
                drop_match = re.match(
                    r"DROP\s+(?:KEY|INDEX)\s+`?([A-Za-z0-9_]+)`?",
                    normalized,
                    flags=re.IGNORECASE,
                )
                if drop_match:
                    requirements.pop((table_name, drop_match.group(1)), None)
                    continue
                add_match = re.match(
                    r"ADD\s+(.*)", normalized, flags=re.IGNORECASE | re.DOTALL
                )
                if add_match:
                    parsed = _parse_index_clause(
                        add_match.group(1),
                        table_name=table_name,
                        source_version=migration.version,
                    )
                    if parsed:
                        requirements[(table_name, parsed.index_name)] = parsed
    return tuple(
        requirements[key]
        for key in sorted(requirements, key=lambda item: (item[0], item[1]))
    )


def validate_baseline_schema(inspector, requirements: BaselineRequirements) -> list[str]:
    existing_tables = set(inspector.get_table_names())
    missing: list[str] = []
    for table_name in sorted(requirements.tables):
        if table_name not in existing_tables:
            missing.append(f"table:{table_name}")
            continue
        existing_columns = {
            str(item["name"]) for item in inspector.get_columns(table_name)
        }
        for column_name in sorted(requirements.columns.get(table_name, frozenset())):
            if column_name not in existing_columns:
                missing.append(f"column:{table_name}.{column_name}")
        existing_indexes = {
            str(item["name"])
            for item in inspector.get_indexes(table_name)
            if item.get("name")
        }
        existing_indexes.update(
            str(item["name"])
            for item in inspector.get_unique_constraints(table_name)
            if item.get("name")
        )
        for index_name in sorted(requirements.indexes.get(table_name, frozenset())):
            if index_name not in existing_indexes:
                missing.append(f"index:{table_name}.{index_name}")
    return missing


def print_migration_result(action: str, status: MigrationStatus) -> None:
    applied_versions = [item.version for item in status.applied]
    current = max(applied_versions, default=0)
    pending = ",".join(f"V{item.version}" for item in status.pending) or "none"
    print(
        f"Migration action={action} current=V{current} pending={pending} "
        f"ledger={'present' if status.ledger_exists else 'absent'}"
    )
    if status.baseline_required:
        if status.baseline_missing:
            print(
                "Baseline required; missing schema objects: "
                + ", ".join(status.baseline_missing[:20])
            )
        else:
            print("Baseline required; schema satisfies the tracked structural requirements")


def apply_command_center_index_upgrades(engine) -> list[str]:
    _assert_mysql(engine)
    applied: list[str] = []
    with engine.begin() as connection:
        inspector = inspect(connection)
        statements = build_command_center_index_upgrade_statements(
            inspector, engine.dialect.identifier_preparer
        )
        for index_names, statement in statements:
            connection.exec_driver_sql(statement)
            applied.extend(index_names)
            print(f"Applied Command Center indexes: {', '.join(index_names)}")
    return applied


def build_command_center_index_upgrade_statements(
    inspector, identifier_preparer
) -> list[tuple[list[str], str]]:
    missing_by_table: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for table_name, index_name, columns in COMMAND_CENTER_INDEX_UPGRADES:
        if not inspector.has_table(table_name):
            raise RuntimeError(f"Command Center index target table is missing: {table_name}")
        existing = {item["name"] for item in inspector.get_indexes(table_name)}
        if index_name not in existing:
            missing_by_table.setdefault(table_name, []).append((index_name, columns))

    statements: list[tuple[list[str], str]] = []
    quote = identifier_preparer.quote
    for table_name, indexes in missing_by_table.items():
        clauses = []
        for index_name, columns in indexes:
            column_sql = ", ".join(quote(column) for column in columns)
            clauses.append(f"ADD INDEX {quote(index_name)} ({column_sql})")
        statements.append(
            (
                [index_name for index_name, _ in indexes],
                f"ALTER TABLE {quote(table_name)} {', '.join(clauses)}, "
                "ALGORITHM=INPLACE, LOCK=NONE",
            )
        )
    return statements


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    index = 0
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                buffer.append(char)
            index += 1
            continue
        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if not in_single_quote and not in_double_quote:
            if char == "-" and next_char == "-":
                in_line_comment = True
                index += 2
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                index += 2
                continue
        if char == "'" and not in_double_quote:
            if not (index > 0 and sql[index - 1] == "\\"):
                in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            if not (index > 0 and sql[index - 1] == "\\"):
                in_double_quote = not in_double_quote
        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue
        buffer.append(char)
        index += 1
    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def _parse_create_table_body(body: str) -> tuple[set[str], set[str]]:
    columns: set[str] = set()
    indexes: set[str] = set()
    for clause in _split_top_level_clauses(body):
        normalized = clause.strip()
        column_match = re.match(r"`?([A-Za-z0-9_]+)`?\s+", normalized)
        if column_match and column_match.group(1).upper() not in {
            "PRIMARY", "UNIQUE", "KEY", "INDEX", "CONSTRAINT", "FOREIGN", "CHECK"
        }:
            columns.add(column_match.group(1))
        index_match = re.match(
            r"(?:UNIQUE\s+)?(?:KEY|INDEX)\s+`?([A-Za-z0-9_]+)`?",
            normalized,
            flags=re.IGNORECASE,
        )
        if index_match:
            indexes.add(index_match.group(1))
    return columns, indexes


def _parse_index_clause(
    clause: str, *, table_name: str, source_version: int
) -> IndexRequirement | None:
    match = re.match(
        r"(UNIQUE\s+)?(?:KEY|INDEX)\s+`?([A-Za-z0-9_]+)`?\s*\((.*)\)\s*$",
        clause.strip(),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    columns_sql = match.group(3).strip()
    column_names: list[str] = []
    for item in _split_top_level_clauses(columns_sql):
        column_match = re.match(r"`?([A-Za-z0-9_]+)`?", item.strip())
        if not column_match:
            raise MigrationError(
                f"Unsupported index expression for {table_name}.{match.group(2)}"
            )
        column_names.append(column_match.group(1))
    return IndexRequirement(
        table_name=table_name,
        index_name=match.group(2),
        columns_sql=columns_sql,
        column_names=tuple(column_names),
        unique=bool(match.group(1)),
        source_version=source_version,
    )


def _apply_alter_index_requirements(body: str, indexes: set[str]) -> None:
    pattern = re.compile(
        r"\b(?:"
        r"(ADD)\s+(?:UNIQUE\s+)?(?:KEY|INDEX)\s+`?([A-Za-z0-9_]+)`?"
        r"|"
        r"(DROP)\s+(?:KEY|INDEX)\s+`?([A-Za-z0-9_]+)`?"
        r")",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(body):
        if match.group(1):
            indexes.add(match.group(2))
        else:
            indexes.discard(match.group(4))


def _split_top_level_clauses(value: str) -> list[str]:
    clauses: list[str] = []
    buffer: list[str] = []
    depth = 0
    quote: str | None = None
    for index, char in enumerate(value):
        previous = value[index - 1] if index else ""
        if quote:
            buffer.append(char)
            if char == quote and previous != "\\":
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            buffer.append(char)
        elif char == "(":
            depth += 1
            buffer.append(char)
        elif char == ")":
            depth = max(depth - 1, 0)
            buffer.append(char)
        elif char == "," and depth == 0:
            clauses.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
    if buffer:
        clauses.append("".join(buffer).strip())
    return clauses


def _ensure_migration_table(connection) -> None:
    connection.exec_driver_sql(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
          version INT NOT NULL,
          description VARCHAR(255) NOT NULL,
          script_name VARCHAR(255) NOT NULL,
          checksum CHAR(64) NOT NULL,
          baseline BOOLEAN NOT NULL DEFAULT FALSE,
          execution_ms BIGINT NOT NULL DEFAULT 0,
          applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          PRIMARY KEY (version),
          UNIQUE KEY uk_schema_migrations_script (script_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    connection.commit()


def _load_applied_migrations(connection) -> tuple[AppliedMigration, ...]:
    rows = connection.execute(
        text(
            f"SELECT version, description, script_name, checksum, baseline "
            f"FROM {MIGRATION_TABLE} ORDER BY version"
        )
    ).mappings()
    return tuple(
        AppliedMigration(
            version=int(row["version"]),
            description=str(row["description"]),
            script_name=str(row["script_name"]),
            checksum=str(row["checksum"]),
            baseline=bool(row["baseline"]),
        )
        for row in rows
    )


def _record_migration(
    connection,
    migration: MigrationFile,
    *,
    baseline: bool,
    execution_ms: int,
) -> None:
    connection.execute(
        text(
            f"INSERT INTO {MIGRATION_TABLE} "
            "(version, description, script_name, checksum, baseline, execution_ms) "
            "VALUES (:version, :description, :script_name, :checksum, :baseline, :execution_ms)"
        ),
        {
            "version": migration.version,
            "description": migration.description,
            "script_name": migration.script_name,
            "checksum": migration.checksum,
            "baseline": baseline,
            "execution_ms": max(int(execution_ms), 0),
        },
    )


def _acquire_migration_lock(connection) -> str:
    database_name = str(connection.execute(text("SELECT DATABASE()")).scalar() or "unknown")
    connection.commit()
    lock_name = f"{MIGRATION_LOCK_PREFIX}:{database_name}"[:64]
    acquired = connection.execute(
        text("SELECT GET_LOCK(:lock_name, 10)"), {"lock_name": lock_name}
    ).scalar()
    connection.commit()
    if acquired != 1:
        raise MigrationError("Could not acquire the database migration lock")
    return lock_name


def _release_migration_lock(connection, lock_name: str) -> None:
    try:
        connection.execute(
            text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name}
        )
        connection.commit()
    except Exception:
        connection.rollback()


def _assert_mysql(engine) -> None:
    if engine.dialect.name != "mysql":
        raise MigrationError(
            "Python migrate currently supports MySQL only; configure a MySQL target"
        )


def _assert_verified(status: MigrationStatus) -> None:
    if status.baseline_required:
        raise MigrationBaselineRequired("Database requires an explicit baseline")
    if status.pending:
        raise MigrationError("Database has pending migrations")
    if not status.ledger_exists:
        raise MigrationError("Migration ledger is missing")


def _version_key(path: Path) -> tuple[int, str]:
    name = path.stem
    version_text = name.split("__", 1)[0].removeprefix("V")
    return int(version_text), path.name


if __name__ == "__main__":
    main()
