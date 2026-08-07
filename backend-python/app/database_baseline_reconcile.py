from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import inspect, text

from app.migrate import IndexRequirement, MigrationFile, build_baseline_index_requirements


@dataclass(frozen=True)
class MissingIndexPlan:
    requirement: IndexRequirement
    estimated_rows: int
    data_bytes: int
    index_bytes: int
    duplicate_found: bool | None


def inspect_missing_index_plan(
    connection, migrations: Iterable[MigrationFile]
) -> tuple[MissingIndexPlan, ...]:
    inspector = inspect(connection)
    requirements = build_baseline_index_requirements(migrations)
    existing_by_table: dict[str, set[str]] = {}
    metrics: dict[str, tuple[int, int, int]] = {}
    result: list[MissingIndexPlan] = []
    for requirement in requirements:
        existing = existing_by_table.get(requirement.table_name)
        if existing is None:
            existing = {
                str(item["name"])
                for item in inspector.get_indexes(requirement.table_name)
                if item.get("name")
            }
            existing.update(
                str(item["name"])
                for item in inspector.get_unique_constraints(requirement.table_name)
                if item.get("name")
            )
            existing_by_table[requirement.table_name] = existing
        if requirement.index_name in existing:
            continue
        if requirement.table_name not in metrics:
            metrics[requirement.table_name] = _table_metrics(
                connection, requirement.table_name
            )
        estimated_rows, data_bytes, index_bytes = metrics[requirement.table_name]
        duplicate_found = (
            _unique_duplicate_exists(connection, requirement)
            if requirement.unique
            else None
        )
        result.append(
            MissingIndexPlan(
                requirement=requirement,
                estimated_rows=estimated_rows,
                data_bytes=data_bytes,
                index_bytes=index_bytes,
                duplicate_found=duplicate_found,
            )
        )
    return tuple(result)


def apply_missing_indexes(connection, plans: Iterable[MissingIndexPlan]) -> list[str]:
    plan_items = tuple(plans)
    blocked = [
        item.requirement.index_name
        for item in plan_items
        if item.requirement.unique and item.duplicate_found
    ]
    if blocked:
        raise ValueError(
            "Unique indexes have duplicate rows and cannot be created: "
            + ", ".join(blocked)
        )
    applied: list[str] = []
    for item in plan_items:
        connection.exec_driver_sql(build_index_ddl(connection, item.requirement))
        connection.commit()
        applied.append(
            f"{item.requirement.table_name}.{item.requirement.index_name}"
        )
    return applied


def build_index_ddl(connection, requirement: IndexRequirement) -> str:
    quote = connection.dialect.identifier_preparer.quote
    unique_sql = "UNIQUE " if requirement.unique else ""
    return (
        f"ALTER TABLE {quote(requirement.table_name)} "
        f"ADD {unique_sql}INDEX {quote(requirement.index_name)} "
        f"({requirement.columns_sql}), ALGORITHM=INPLACE, LOCK=NONE"
    )


def _table_metrics(connection, table_name: str) -> tuple[int, int, int]:
    row = connection.execute(
        text(
            "SELECT COALESCE(TABLE_ROWS, 0) AS table_rows, "
            "COALESCE(DATA_LENGTH, 0) AS data_length, "
            "COALESCE(INDEX_LENGTH, 0) AS index_length "
            "FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
        ),
        {"table_name": table_name},
    ).mappings().first()
    if not row:
        return 0, 0, 0
    return int(row["table_rows"]), int(row["data_length"]), int(row["index_length"])


def _unique_duplicate_exists(connection, requirement: IndexRequirement) -> bool:
    quote = connection.dialect.identifier_preparer.quote
    columns = ", ".join(quote(name) for name in requirement.column_names)
    non_null = " AND ".join(
        f"{quote(name)} IS NOT NULL" for name in requirement.column_names
    )
    table_name = quote(requirement.table_name)
    sql = (
        "SELECT EXISTS(SELECT 1 FROM ("
        f"SELECT 1 FROM {table_name} WHERE {non_null} "
        f"GROUP BY {columns} HAVING COUNT(*) > 1 LIMIT 1"
        ") duplicate_groups)"
    )
    return bool(connection.execute(text(sql)).scalar())
