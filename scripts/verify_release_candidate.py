"""Validate a DEV release artifact before any shared-environment authentication."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


class ReleaseCandidateError(ValueError):
    """The selected DEV deployment cannot be promoted."""


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_candidate(
    record,
    release_dir: Path,
    *,
    repository: str,
    release_sha: str,
    dev_run_id: str,
    dev_run_attempt: str,
):
    if not SHA_PATTERN.fullmatch(release_sha):
        raise ReleaseCandidateError("release SHA must contain 40 lowercase hex chars")
    expected = {
        "status": "SUCCESS",
        "repository": repository,
        "git_sha": release_sha,
        "workflow_run_id": dev_run_id,
        "workflow_run_attempt": dev_run_attempt,
        "target": "dev",
    }
    for key, value in expected.items():
        if str(record.get(key)) != value:
            raise ReleaseCandidateError(f"record {key}={record.get(key)!r}; expected {value!r}")
    bundles = record.get("bundles")
    if not isinstance(bundles, list) or not bundles:
        raise ReleaseCandidateError("release scope must contain Bundles")
    roots = [bundle.get("root") for bundle in bundles]
    if len(set(roots)) != len(roots) or not all(isinstance(x, str) for x in roots):
        raise ReleaseCandidateError("Bundle roots must be unique strings")
    if any(bundle.get("git_sha") != release_sha for bundle in bundles):
        raise ReleaseCandidateError("not every DEV Bundle has the release SHA")
    if any(bundle.get("target") != "dev" for bundle in bundles):
        raise ReleaseCandidateError("source record contains a non-DEV Bundle")
    artifact = record.get("artifact", {})
    wheel = release_dir / str(artifact.get("file_name", ""))
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ReleaseCandidateError("recorded wheel is missing")
    actual = sha256(wheel)
    if actual != artifact.get("sha256"):
        raise ReleaseCandidateError("recorded wheel checksum does not match")
    return roots, wheel, actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--dev-run-id", required=True)
    parser.add_argument("--dev-run-attempt", required=True)
    parser.add_argument("--bundles-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = json.loads(
            (args.release_dir / "deployment-record.json").read_text(encoding="utf-8")
        )
        roots, wheel, actual = verify_candidate(
            record,
            args.release_dir,
            repository=args.repository,
            release_sha=args.release_sha,
            dev_run_id=args.dev_run_id,
            dev_run_attempt=args.dev_run_attempt,
        )
        args.bundles_output.write_text("\n".join(roots) + "\n", encoding="utf-8")
        print(f"release_wheel={wheel.as_posix()}")
        print(f"release_wheel_sha256={actual}")
    except (OSError, json.JSONDecodeError, ReleaseCandidateError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
