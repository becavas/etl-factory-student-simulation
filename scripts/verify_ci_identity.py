"""Verify that Databricks current-user output belongs to the expected SP."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


class IdentityVerificationError(ValueError):
    """The authenticated principal is not the expected CI service principal."""


def _strings(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"applicationId", "application_id", "userName"}:
                if isinstance(item, str):
                    yield item
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def verify_identity(payload: Any, expected_client_id: str) -> None:
    if not isinstance(payload, dict):
        raise IdentityVerificationError("current-user output must be an object")
    candidates = set(_strings(payload))
    if expected_client_id not in candidates:
        raise IdentityVerificationError(
            "authenticated Databricks identity does not match "
            f"expected deployer client id; observed candidates={sorted(candidates)!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-client-id", required=True)
    args = parser.parse_args()
    try:
        verify_identity(json.load(sys.stdin), args.expected_client_id)
    except (json.JSONDecodeError, IdentityVerificationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
