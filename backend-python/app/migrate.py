from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from app.core.config import get_settings
from app.core.database import create_engine_for_url


BOOTSTRAP_DIR = Path(__file__).resolve().parents[1] / "migrations" / "bootstrap_sql"
COMMAND_CENTER_INDEX_UPGRADES = (
    (
        "review_tasks",
        "idx_review_tasks_cc_created",
        ("created_at", "id"),
    ),
    (
        "code_quality_review_results",
        "idx_cq_results_cc_updated",
        ("updated_at", "id"),
    ),
    (
        "code_quality_review_results",
        "idx_cq_results_cc_provider_updated_status",
        ("provider", "updated_at", "status"),
    ),
    (
        "deterministic_check_runs",
        "idx_deterministic_runs_cc_created",
        ("created_at", "id"),
    ),
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


def main() -> None:
    settings = get_settings()
    engine = create_engine_for_url(settings.database_url)
    if engine.dialect.name != "mysql":
        raise SystemExit(
            "Python migrate currently supports MySQL only. "
            "Use DATABASE_URL / MYSQL_URL that points to MySQL."
        )

    inspector = inspect(engine)
    if inspector.has_table("review_tasks"):
        print("Core review tables already exist. Skip bootstrap SQL.")
        applied = apply_command_center_index_upgrades(engine)
        if not applied:
            print("Command Center query indexes are already up to date.")
        return

    sql_files = sorted(BOOTSTRAP_DIR.glob("V*.sql"), key=_version_key)
    if not sql_files:
        raise SystemExit(f"Bootstrap SQL directory is empty: {BOOTSTRAP_DIR}")

    with engine.begin() as connection:
        for sql_file in sql_files:
            for statement in split_sql_statements(sql_file.read_text(encoding="utf-8")):
                connection.exec_driver_sql(statement)
            print(f"Applied {sql_file.name}")


def apply_command_center_index_upgrades(engine) -> list[str]:
    if engine.dialect.name != "mysql":
        raise ValueError("Command Center index upgrades support MySQL only.")

    applied: list[str] = []
    with engine.begin() as connection:
        inspector = inspect(connection)
        statements = build_command_center_index_upgrade_statements(
            inspector,
            engine.dialect.identifier_preparer,
        )
        for index_names, statement in statements:
            connection.exec_driver_sql(statement)
            applied.extend(index_names)
            print(f"Applied Command Center indexes: {', '.join(index_names)}")
    return applied


def build_command_center_index_upgrade_statements(
    inspector,
    identifier_preparer,
) -> list[tuple[list[str], str]]:
    missing_by_table: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for table_name, index_name, columns in COMMAND_CENTER_INDEX_UPGRADES:
        if not inspector.has_table(table_name):
            raise RuntimeError(
                f"Command Center index target table is missing: {table_name}"
            )
        existing = {
            item["name"] for item in inspector.get_indexes(table_name)
        }
        if index_name not in existing:
            missing_by_table.setdefault(table_name, []).append(
                (index_name, columns)
            )

    statements: list[tuple[list[str], str]] = []
    quote = identifier_preparer.quote
    for table_name, indexes in missing_by_table.items():
        clauses = []
        for index_name, columns in indexes:
            column_sql = ", ".join(quote(column) for column in columns)
            clauses.append(
                f"ADD INDEX {quote(index_name)} ({column_sql})"
            )
        statements.append((
            [index_name for index_name, _ in indexes],
            (
                f"ALTER TABLE {quote(table_name)} "
                f"{', '.join(clauses)}, ALGORITHM=INPLACE, LOCK=NONE"
            ),
        ))
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
            escaped = index > 0 and sql[index - 1] == "\\"
            if not escaped:
                in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            escaped = index > 0 and sql[index - 1] == "\\"
            if not escaped:
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


def _version_key(path: Path) -> tuple[int, str]:
    name = path.stem
    version_text = name.split("__", 1)[0].removeprefix("V")
    return int(version_text), path.name


if __name__ == "__main__":
    main()
