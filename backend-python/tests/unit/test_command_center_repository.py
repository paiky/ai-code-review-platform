from types import SimpleNamespace

from sqlalchemy import column, literal, select
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects import sqlite

from app.command_center.repository import (
    MYSQL_ALERT_UNION_COLLATION,
    _alert_union_text,
    _case_insensitive_equal,
)


def test_mysql_alert_union_text_uses_explicit_shared_collation() -> None:
    expression = literal("RUNNING")

    normalized = _alert_union_text(_SessionStub("mysql"), expression)
    statement = select(normalized.label("status"))
    compiled = str(statement.compile(dialect=mysql.dialect()))

    assert f"COLLATE {MYSQL_ALERT_UNION_COLLATION}" in compiled


def test_non_mysql_alert_union_text_preserves_original_expression() -> None:
    expression = literal("RUNNING")

    assert _alert_union_text(_SessionStub("sqlite"), expression) is expression


def test_mysql_case_insensitive_provider_match_keeps_indexable_columns() -> None:
    expression = _case_insensitive_equal(
        _SessionStub("mysql"),
        column("provider"),
        column("provider_code"),
    )
    compiled = str(select(expression).compile(dialect=mysql.dialect()))

    assert "provider = provider_code" in compiled
    assert "upper(" not in compiled.lower()


def test_non_mysql_case_insensitive_provider_match_keeps_compatibility() -> None:
    expression = _case_insensitive_equal(
        _SessionStub("sqlite"),
        column("provider"),
        column("provider_code"),
    )
    compiled = str(select(expression).compile(dialect=sqlite.dialect()))

    assert "upper(provider) = upper(provider_code)" in compiled.lower()


class _SessionStub:
    def __init__(self, dialect_name: str) -> None:
        self.bind = SimpleNamespace(
            dialect=SimpleNamespace(name=dialect_name)
        )

    def get_bind(self) -> SimpleNamespace:
        return self.bind
