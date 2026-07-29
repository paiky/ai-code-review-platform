import json
from datetime import datetime, timedelta, timezone
from typing import Any


UTC_PLUS_EIGHT = timezone(timedelta(hours=8))


def utc_now() -> datetime:
    """Return a timezone-neutral UTC value for storage in legacy DATETIME columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def read_json(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}


def read_json_array(value: Any) -> list[Any]:
    parsed = read_json(value, [])
    return parsed if isinstance(parsed, list) else []


def format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return aware.astimezone(UTC_PLUS_EIGHT).isoformat(timespec="milliseconds")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def page_response(items: list[dict], page_no: int, page_size: int, total: int) -> dict:
    return {
        "items": items,
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }
