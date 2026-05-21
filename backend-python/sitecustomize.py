"""Local Python startup customizations for backend scripts."""

from __future__ import annotations

import os
import platform
import sys


if sys.platform.startswith("win") and os.getenv("AI_REVIEW_SKIP_PYTHON_WMI") == "1":

    def _skip_wmi_query(*_args: object, **_kwargs: object) -> None:
        raise OSError("Python WMI query disabled for local backend startup")

    # Python 3.12's platform module may hang in WMI when the local CIM service is unhealthy.
    # Raising OSError makes platform.py use its built-in registry/env fallback paths instead.
    platform._wmi_query = _skip_wmi_query  # type: ignore[attr-defined]
