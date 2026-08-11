from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import database_migration_cli
from app.database_targets import (
    DatabaseTargetError,
    database_identity,
    load_isolated_database_targets,
    parse_dotenv,
)


def test_load_isolated_targets_supports_jdbc_and_sqlalchemy_urls(tmp_path: Path) -> None:
    _write_env(
        tmp_path / "database.local.env",
        """
        DATABASE_TARGET=LOCAL
        DATABASE_URL=
        MYSQL_URL=jdbc:mysql://127.0.0.1:3306/ai_code_review_local?characterEncoding=utf8
        MYSQL_USERNAME=local_user
        MYSQL_PASSWORD=local_password
        """,
    )
    _write_env(
        tmp_path / "database.test.env",
        """
        DATABASE_TARGET=TEST
        DATABASE_URL=mysql+pymysql://test_user:test_password@test-db:3307/ai_code_review
        MYSQL_URL=
        MYSQL_USERNAME=
        MYSQL_PASSWORD=
        """,
    )

    targets = load_isolated_database_targets(tmp_path)

    assert targets["local"].identity.safe_label == "127.0.0.1:3306/ai_code_review_local"
    assert targets["test"].identity.safe_label == "test-db:3307/ai_code_review"
    assert "local_password" in targets["local"].database_url


def test_same_database_identity_is_rejected(tmp_path: Path) -> None:
    for target in ("LOCAL", "TEST"):
        _write_env(
            tmp_path / f"database.{target.lower()}.env",
            f"""
            DATABASE_TARGET={target}
            DATABASE_URL=mysql+pymysql://user:password@db:3306/shared
            MYSQL_URL=
            MYSQL_USERNAME=
            MYSQL_PASSWORD=
            """,
        )

    with pytest.raises(DatabaseTargetError, match="same host, port, and schema"):
        load_isolated_database_targets(tmp_path)


def test_target_marker_and_credentials_are_required(tmp_path: Path) -> None:
    _write_env(
        tmp_path / "database.local.env",
        """
        DATABASE_TARGET=TEST
        MYSQL_URL=jdbc:mysql://localhost:3306/local_db
        MYSQL_USERNAME=user
        MYSQL_PASSWORD=password
        """,
    )
    _write_env(
        tmp_path / "database.test.env",
        """
        DATABASE_TARGET=TEST
        MYSQL_URL=jdbc:mysql://test:3306/test_db
        MYSQL_USERNAME=user
        MYSQL_PASSWORD=password
        """,
    )

    with pytest.raises(DatabaseTargetError, match="DATABASE_TARGET=LOCAL"):
        load_isolated_database_targets(tmp_path)


def test_dotenv_duplicate_key_is_rejected_without_echoing_value(tmp_path: Path) -> None:
    env_file = tmp_path / "database.local.env"
    _write_env(
        env_file,
        "DATABASE_TARGET=LOCAL\nDATABASE_URL=secret-one\nDATABASE_URL=secret-two\n",
    )

    with pytest.raises(DatabaseTargetError) as captured:
        parse_dotenv(env_file)

    assert "secret-one" not in str(captured.value)
    assert "secret-two" not in str(captured.value)


def test_database_identity_never_contains_credentials() -> None:
    identity = database_identity(
        "mysql+pymysql://private_user:private_password@db.example:3307/review"
    )

    assert identity.safe_label == "db.example:3307/review"
    assert "private" not in identity.safe_label


def test_database_identity_rejects_option_like_schema_name() -> None:
    with pytest.raises(DatabaseTargetError, match="schema name"):
        database_identity("mysql+pymysql://user:password@db/--defaults-file")


def test_database_migration_script_keeps_test_confirmation_gate() -> None:
    root = Path(__file__).resolve().parents[3]
    powershell = (root / "scripts/run-database-migration.ps1").read_text(encoding="utf-8")

    assert 'ValidateSet("local", "test")' in powershell
    assert "$ConfirmTest" in powershell
    assert 'arguments.Add("--confirm-test")' in powershell
    assert "database.local.env" not in powershell
    assert "database.test.env" not in powershell


def test_repository_scripts_use_powershell_without_new_script_types() -> None:
    root = Path(__file__).resolve().parents[3]
    scripts = root / "scripts"

    assert all(path.suffix.lower() == ".ps1" for path in scripts.iterdir())
    assert (scripts / "run-backend.ps1").is_file()
    assert (scripts / "run-frontend.ps1").is_file()
    assert (scripts / "setup-codegraph.ps1").is_file()


def test_backend_runner_loads_only_local_database_target_for_runtime() -> None:
    root = Path(__file__).resolve().parents[3]
    powershell = (root / "scripts/run-backend.ps1").read_text(
        encoding="utf-8"
    )

    assert '.local\\database.local.env' in powershell
    assert "database.test.env" not in powershell
    assert 'if ($command -in @("dev", "migrate"))' in powershell
    assert "database.local.env must declare DATABASE_TARGET=LOCAL" in powershell
    assert powershell.index("Import-DotEnvIfPresent $localGitLabEnv") < powershell.index(
        "Import-LocalDatabaseEnvIfPresent $localDatabaseEnv"
    )
    for key in ("DATABASE_URL", "MYSQL_URL", "MYSQL_USERNAME", "MYSQL_PASSWORD"):
        assert f'"{key}"' in powershell


def test_test_target_write_is_refused_before_engine_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_distinct_targets(tmp_path)
    engine_created = False

    def unexpected_engine(_database_url: str):
        nonlocal engine_created
        engine_created = True
        raise AssertionError("engine must not be created")

    monkeypatch.setattr(database_migration_cli, "create_migration_engine", unexpected_engine)

    with pytest.raises(SystemExit, match="explicit --confirm-test"):
        database_migration_cli.main(
            ["apply", "test", "--env-directory", str(tmp_path)]
        )

    assert engine_created is False


def test_database_execution_error_does_not_echo_connection_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_distinct_targets(tmp_path)

    class _Engine:
        def dispose(self) -> None:
            return None

    monkeypatch.setattr(
        database_migration_cli, "create_migration_engine", lambda _url: _Engine()
    )
    monkeypatch.setattr(
        database_migration_cli,
        "run_migration_action",
        lambda _engine, _action: (_ for _ in ()).throw(
            SQLAlchemyError("private_password@private-host")
        ),
    )

    with pytest.raises(SystemExit) as captured:
        database_migration_cli.main(
            ["status", "local", "--env-directory", str(tmp_path)]
        )

    assert "credentials and URLs are hidden" in str(captured.value)
    assert "private_password" not in str(captured.value)


def _write_env(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _write_distinct_targets(directory: Path) -> None:
    _write_env(
        directory / "database.local.env",
        """
        DATABASE_TARGET=LOCAL
        DATABASE_URL=mysql+pymysql://user:password@localhost/local_db
        MYSQL_URL=
        MYSQL_USERNAME=
        MYSQL_PASSWORD=
        """,
    )
    _write_env(
        directory / "database.test.env",
        """
        DATABASE_TARGET=TEST
        DATABASE_URL=mysql+pymysql://user:password@test-host/test_db
        MYSQL_URL=
        MYSQL_USERNAME=
        MYSQL_PASSWORD=
        """,
    )
