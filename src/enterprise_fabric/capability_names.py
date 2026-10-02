"""Small naming helpers shared by factory capabilities."""

import re

VALID_CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def normalize_capability_name(value: str) -> str:
    """Return a machine-friendly capability name or reject an invalid value."""
    normalized = re.sub(r"[-\s]+", "_", value.strip().lower())
    if not VALID_CAPABILITY_NAME.fullmatch(normalized):
        raise ValueError(f"Invalid capability name: {value!r}")
    return normalized
