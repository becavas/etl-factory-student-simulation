"""Require exactly one workspace Job with an expected display name."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


class JobLookupError(ValueError):
    """The workspace response cannot resolve one unique Job."""


def _jobs(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        jobs = payload
    elif isinstance(payload, dict) and "jobs" in payload and isinstance(payload["jobs"], list):
        jobs = payload["jobs"]
    else:
        raise JobLookupError("jobs list output must be a list or contain a jobs list")
    if not all(isinstance(job, dict) for job in jobs):
        raise JobLookupError("jobs list contains a non-object item")
    return jobs


def _name(job: dict[str, Any]) -> str | None:
    settings = job.get("settings")
    if isinstance(settings, dict) and isinstance(settings.get("name"), str):
        return settings["name"]
    return job.get("name") if isinstance(job.get("name"), str) else None


def require_unique_job(payload: Any, expected_name: str) -> int:
    matches = [
        job for job in _jobs(payload) if (_name(job) or "").casefold() == expected_name.casefold()
    ]
    ids = sorted(int(job["job_id"]) for job in matches if isinstance(job.get("job_id"), int))
    if len(matches) != 1 or len(ids) != 1:
        raise JobLookupError(
            f"expected exactly one Job named {expected_name!r}; "
            f"found {len(matches)} with job_ids={ids}"
        )
    return ids[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        print(require_unique_job(payload, args.name))
    except (json.JSONDecodeError, JobLookupError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
