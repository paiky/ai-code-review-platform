from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.database_targets import DatabaseTargetError, load_isolated_database_targets
from app.migrate import (
    MigrationError,
    create_migration_engine,
    print_migration_result,
    run_migration_action,
)


WRITE_ACTIONS = frozenset({"baseline", "apply"})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run a migration action against an isolated database target"
    )
    parser.add_argument(
        "action", choices=("status", "dry-run", "baseline", "apply", "verify")
    )
    parser.add_argument("target", choices=("local", "test"))
    parser.add_argument(
        "--confirm-test",
        action="store_true",
        help="required for write actions against the test-line database",
    )
    parser.add_argument("--env-directory", type=Path, default=None, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[2]
    env_directory = arguments.env_directory or repository_root / ".local"
    try:
        targets = load_isolated_database_targets(env_directory)
        target = targets[arguments.target]
        if (
            arguments.target == "test"
            and arguments.action in WRITE_ACTIONS
            and not arguments.confirm_test
        ):
            raise DatabaseTargetError(
                "Test-line baseline/apply requires the explicit --confirm-test flag"
            )
        print(
            f"Database target={target.name} identity={target.identity.safe_label} "
            f"action={arguments.action}"
        )
        engine = create_migration_engine(target.database_url)
        try:
            result = run_migration_action(engine, arguments.action)
        finally:
            engine.dispose()
        print_migration_result(arguments.action, result)
    except (DatabaseTargetError, MigrationError) as exception:
        raise SystemExit(f"Database migration refused: {exception}") from exception
    except SQLAlchemyError:
        raise SystemExit(
            "Database migration failed while connecting or executing; credentials and URLs are hidden"
        ) from None


if __name__ == "__main__":
    main()
