from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.database_baseline_reconcile import (
    apply_missing_indexes,
    inspect_missing_index_plan,
)
from app.database_targets import DatabaseTargetError, load_isolated_database_targets
from app.migrate import create_migration_engine, discover_migrations


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Inspect or reconcile historical baseline indexes"
    )
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("target", choices=("local", "test"))
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--confirm-test", action="store_true")
    parser.add_argument("--env-directory", type=Path, default=None, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[2]
    env_directory = arguments.env_directory or repository_root / ".local"
    try:
        targets = load_isolated_database_targets(env_directory)
        target = targets[arguments.target]
        if arguments.action == "apply" and not arguments.confirm_write:
            raise DatabaseTargetError(
                "Index reconcile apply requires the explicit --confirm-write flag"
            )
        if (
            arguments.action == "apply"
            and arguments.target == "test"
            and not arguments.confirm_test
        ):
            raise DatabaseTargetError(
                "Test-line index reconcile requires the explicit --confirm-test flag"
            )
        print(
            f"Database target={target.name} identity={target.identity.safe_label} "
            f"action=index-{arguments.action}"
        )
        engine = create_migration_engine(target.database_url)
        try:
            with engine.connect() as connection:
                plans = inspect_missing_index_plan(connection, discover_migrations())
                _print_plan(plans)
                if arguments.action == "apply":
                    applied = apply_missing_indexes(connection, plans)
                    print(f"Applied baseline indexes={len(applied)}")
        finally:
            engine.dispose()
    except (DatabaseTargetError, ValueError) as exception:
        raise SystemExit(f"Database index reconcile refused: {exception}") from exception
    except SQLAlchemyError:
        raise SystemExit(
            "Database index reconcile failed; credentials, URLs, and row values are hidden"
        ) from None


def _print_plan(plans) -> None:
    print(f"Missing baseline indexes={len(plans)}")
    for item in plans:
        requirement = item.requirement
        duplicate = (
            "BLOCKED"
            if item.duplicate_found
            else "CLEAR" if item.duplicate_found is False else "N/A"
        )
        print(
            f"INDEX table={requirement.table_name} name={requirement.index_name} "
            f"unique={str(requirement.unique).lower()} rows~={item.estimated_rows} "
            f"dataBytes={item.data_bytes} indexBytes={item.index_bytes} "
            f"duplicates={duplicate} source=V{requirement.source_version}"
        )


if __name__ == "__main__":
    main()
