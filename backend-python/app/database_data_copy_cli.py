from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.database_data_copy import (
    DatabaseCopyError,
    copy_test_database_to_local,
    inspect_database_copy_plan,
)
from app.database_targets import DatabaseTargetError, load_isolated_database_targets
from app.migrate import create_migration_engine


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Plan or execute a one-way test-line to local database copy"
    )
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--confirm-copy", action="store_true")
    parser.add_argument("--confirm-source-data", action="store_true")
    parser.add_argument("--env-directory", type=Path, default=None, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[2]
    env_directory = arguments.env_directory or repository_root / ".local"
    try:
        targets = load_isolated_database_targets(env_directory)
        source = targets["test"]
        target = targets["local"]
        if arguments.action == "apply" and not arguments.confirm_copy:
            raise DatabaseTargetError(
                "Database copy apply requires the explicit --confirm-copy flag"
            )
        if arguments.action == "apply" and not arguments.confirm_source_data:
            raise DatabaseTargetError(
                "Database copy includes review/source history and requires "
                "the explicit --confirm-source-data flag"
            )
        source_engine = create_migration_engine(source.database_url)
        target_engine = create_migration_engine(target.database_url)
        try:
            plan = inspect_database_copy_plan(source_engine, target_engine)
            print(
                f"Database copy source={source.identity.safe_label} "
                f"target={target.identity.safe_label} action={arguments.action}"
            )
            print(
                f"COPY_PLAN sourceTables={plan.source_table_count} "
                f"sourceRows~={plan.source_rows_estimate} "
                f"sourceDataBytes={plan.source_data_bytes} "
                f"sourceIndexBytes={plan.source_index_bytes} "
                f"targetTables={plan.target_table_count}"
            )
            if arguments.action == "apply":
                affected = copy_test_database_to_local(
                    source, target, plan, target_engine
                )
                print(
                    "Database stream copy and local side-effect sanitization completed; "
                    f"sanitizedTables={len(affected)}"
                )
        finally:
            source_engine.dispose()
            target_engine.dispose()
    except (DatabaseTargetError, DatabaseCopyError) as exception:
        raise SystemExit(f"Database copy refused: {exception}") from exception
    except SQLAlchemyError:
        raise SystemExit(
            "Database copy failed; credentials, URLs, and row values are hidden"
        ) from None


if __name__ == "__main__":
    main()
