from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from app.core.config import get_settings
from app.core.database import create_engine_for_url


BOOTSTRAP_DIR = Path(__file__).resolve().parents[1] / "migrations" / "bootstrap_sql"


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
        return

    sql_files = sorted(BOOTSTRAP_DIR.glob("V*.sql"), key=_version_key)
    if not sql_files:
        raise SystemExit(f"Bootstrap SQL directory is empty: {BOOTSTRAP_DIR}")

    with engine.begin() as connection:
        for sql_file in sql_files:
            for statement in split_sql_statements(sql_file.read_text(encoding="utf-8")):
                connection.exec_driver_sql(statement)
            print(f"Applied {sql_file.name}")


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
