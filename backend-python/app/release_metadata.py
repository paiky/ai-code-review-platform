"""Source revision recorded in a built review image."""

import re
from functools import lru_cache
from pathlib import Path


_RELEASE_FILE = Path("/usr/local/share/ai-review/release-sha")
_RELEASE_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def normalize_release_sha(value: object) -> str | None:
    return value if isinstance(value, str) and _RELEASE_SHA.fullmatch(value) else None


@lru_cache(maxsize=1)
def image_release_sha() -> str | None:
    try:
        with _RELEASE_FILE.open("rb") as release_file:
            revision = release_file.read(66).decode("ascii").removesuffix("\n")
    except (OSError, ValueError):
        return None
    return normalize_release_sha(revision)
