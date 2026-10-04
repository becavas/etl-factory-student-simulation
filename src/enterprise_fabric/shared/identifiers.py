"""Validation for values embedded in paths, predicates and run metadata."""

import re

SAFE_VALUE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def require_safe_value(value: str, field: str) -> str:
    if not SAFE_VALUE_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must contain only safe identifier characters")
    return value
