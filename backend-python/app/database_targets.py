from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping

from sqlalchemy.engine import make_url

from app.core.config import jdbc_mysql_url_to_sqlalchemy


_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DatabaseTargetError(ValueError):
    pass


@dataclass(frozen=True)
class DatabaseIdentity:
    host: str
    port: int
    database: str

    @property
    def safe_label(self) -> str:
        return f"{self.host}:{self.port}/{self.database}"


@dataclass(frozen=True)
class DatabaseTarget:
    name: str
    database_url: str
    identity: DatabaseIdentity
    env_path: Path


def load_database_target(env_path: Path, expected_target: str) -> DatabaseTarget:
    values = parse_dotenv(env_path)
    expected = expected_target.strip().upper()
    actual = str(values.get("DATABASE_TARGET") or "").strip().upper()
    if actual != expected:
        raise DatabaseTargetError(
            f"{env_path.name} must declare DATABASE_TARGET={expected}"
        )
    database_url = resolve_target_database_url(values)
    return DatabaseTarget(
        name=expected,
        database_url=database_url,
        identity=database_identity(database_url),
        env_path=env_path,
    )


def load_isolated_database_targets(env_directory: Path) -> dict[str, DatabaseTarget]:
    local = load_database_target(env_directory / "database.local.env", "LOCAL")
    test = load_database_target(env_directory / "database.test.env", "TEST")
    assert_distinct_database_targets(local, test)
    return {"local": local, "test": test}


def assert_distinct_database_targets(
    local: DatabaseTarget, test: DatabaseTarget
) -> None:
    if local.identity == test.identity:
        raise DatabaseTargetError(
            "Local and test database targets resolve to the same host, port, and schema"
        )


def resolve_target_database_url(values: Mapping[str, str]) -> str:
    direct = str(values.get("DATABASE_URL") or "").strip()
    if direct:
        return direct
    jdbc_url = str(values.get("MYSQL_URL") or "").strip()
    username = str(values.get("MYSQL_USERNAME") or "").strip()
    password = str(values.get("MYSQL_PASSWORD") or "")
    if not jdbc_url:
        raise DatabaseTargetError("DATABASE_URL or MYSQL_URL is required")
    if not username or not password:
        raise DatabaseTargetError(
            "MYSQL_USERNAME and MYSQL_PASSWORD are required with MYSQL_URL"
        )
    try:
        return jdbc_mysql_url_to_sqlalchemy(jdbc_url, username, password)
    except ValueError as exception:
        raise DatabaseTargetError(str(exception)) from exception


def database_identity(database_url: str) -> DatabaseIdentity:
    try:
        url = make_url(database_url)
    except Exception as exception:
        raise DatabaseTargetError("Database URL is invalid") from exception
    if not url.drivername.startswith("mysql"):
        raise DatabaseTargetError("Database target must use MySQL")
    host = str(url.host or "").strip().casefold()
    database = str(url.database or "").strip()
    if not host or not database:
        raise DatabaseTargetError("Database URL must include host and schema name")
    if not re.fullmatch(r"[A-Za-z0-9_$-]{1,64}", database) or database.startswith("-"):
        raise DatabaseTargetError("Database schema name contains unsupported characters")
    return DatabaseIdentity(host=host, port=int(url.port or 3306), database=database)


def parse_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise DatabaseTargetError(f"Database environment file is missing: {path.name}")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise DatabaseTargetError(
                f"Invalid environment entry in {path.name} at line {line_number}"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not _ENV_KEY.fullmatch(key):
            raise DatabaseTargetError(
                f"Invalid environment key in {path.name} at line {line_number}"
            )
        if key in values:
            raise DatabaseTargetError(f"Duplicate environment key in {path.name}: {key}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values
