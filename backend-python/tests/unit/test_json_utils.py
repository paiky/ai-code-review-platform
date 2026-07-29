from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.json_utils import format_datetime, utc_now


def test_format_datetime_displays_naive_utc_in_utc_plus_eight() -> None:
    assert format_datetime(datetime(2026, 7, 27, 6, 13, 29, 825000)) == (
        "2026-07-27T14:13:29.825+08:00"
    )


def test_format_datetime_normalizes_explicit_offset_to_utc_plus_eight() -> None:
    source = datetime(2026, 7, 27, 7, 13, tzinfo=timezone(timedelta(hours=1)))

    assert format_datetime(source) == "2026-07-27T14:13:00.000+08:00"


def test_utc_now_returns_naive_utc_for_legacy_datetime_columns() -> None:
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    actual = utc_now()
    after = datetime.now(timezone.utc).replace(tzinfo=None)

    assert actual.tzinfo is None
    assert before <= actual <= after
