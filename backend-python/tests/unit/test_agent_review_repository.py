from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_review.repository import _supports_skip_locked


class _Session:
    def __init__(
        self,
        *,
        dialect_name: str,
        version: tuple[object, ...] | None,
        is_mariadb: bool = False,
    ) -> None:
        dialect = SimpleNamespace(
            name=dialect_name,
            server_version_info=version,
            is_mariadb=is_mariadb,
        )
        self._bind = SimpleNamespace(dialect=dialect)

    def get_bind(self):
        return self._bind


@pytest.mark.parametrize(
    ("session", "expected"),
    [
        (_Session(dialect_name="mysql", version=(5, 7, 31)), False),
        (_Session(dialect_name="mysql", version=(8, 0, 0)), True),
        (_Session(dialect_name="mysql", version=(8, 4, 1)), True),
        (_Session(dialect_name="mysql", version=(10, 6, 0), is_mariadb=True), False),
        (_Session(dialect_name="sqlite", version=(3, 45, 0)), False),
        (_Session(dialect_name="mysql", version=None), False),
        (_Session(dialect_name="mysql", version=("unknown",)), False),
    ],
)
def test_skip_locked_support_is_enabled_only_for_mysql_8_or_newer(session: _Session, expected: bool) -> None:
    assert _supports_skip_locked(session) is expected
