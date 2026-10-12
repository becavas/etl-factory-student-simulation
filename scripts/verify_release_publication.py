"""Validate promoted evidence before creating a GitHub release."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")
CHECKSUM = re.compile(r"[0-9a-f]{64}")
TAG = re.compile(
    r"(?P<namespace>[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*)/"
    r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
)


class PublicationError(ValueError):
    """Promotion evidence cannot be published as a release."""


def unit_namespace(bundle_root: str) -> str:
    parts = bundle_root.split("/")
    if len(parts) == 4 and parts[0] == "domains" and parts[2] == "capabilities":
        return f"{parts[1]}/{parts[3]}"
    if len(parts) == 3 and parts[0] == "domains" and parts[2] == "orchestration":
        return f"{parts[1]}/orchestration"
    raise PublicationError("release Bundle root is not a deployable unit")


def verify(
    record,
    *,
    repository: str,
    release_sha: str,
    release_tag: str,
    bundle_root: str,
    release_title: str,
):
    if record.get("status") != "PROMOTED":
        raise PublicationError("promotion status must be PROMOTED")
    if record.get("repository") != repository:
        raise PublicationError("promotion repository does not match")
    if not SHA.fullmatch(release_sha) or record.get("git_sha") != release_sha:
        raise PublicationError("release SHA does not match promotion")
    match = TAG.fullmatch(release_tag)
    if not match:
        raise PublicationError("release tag must be <domain>/<unit>/vMAJOR.MINOR.PATCH")
    if match.group("namespace") != unit_namespace(bundle_root):
        raise PublicationError("release tag namespace does not match Bundle root")
    if not release_title.strip() or "\n" in release_title or len(release_title) > 120:
        raise PublicationError("release title must be a single descriptive line")
    if not CHECKSUM.fullmatch(str(record.get("artifact_sha256", ""))):
        raise PublicationError("promotion artifact checksum is invalid")
    scope = record.get("bundle_scope")
    if not isinstance(scope, list) or not scope or len(scope) != len(set(scope)):
        raise PublicationError("promotion Bundle scope is invalid")
    if bundle_root not in scope:
        raise PublicationError("release Bundle root is absent from promotion scope")
    environments = record.get("environments", {})
    if set(environments) != {"dev", "certi", "prod"}:
        raise PublicationError("promotion must contain DEV, CERTI, and PROD")
    for name, environment in environments.items():
        if environment.get("target") != name:
            raise PublicationError(f"environment target mismatch: {name}")
        if not str(environment.get("workflow_run_id", "")):
            raise PublicationError(f"environment run ID missing: {name}")
        if not str(environment.get("workflow_run_attempt", "")):
            raise PublicationError(f"environment run attempt missing: {name}")
    if record.get("certi_smoke", {}).get("result_state") != "SUCCESS":
        raise PublicationError("CERTI smoke is not successful")
    return {
        "tag": release_tag,
        "title": release_title.strip(),
        "bundle_root": bundle_root,
        "sha": release_sha,
        "wheel_sha256": record["artifact_sha256"],
        "scope": scope,
        "environments": environments,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--promotion-record", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--release-title", required=True)
    parser.add_argument("--notes-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = json.loads(args.promotion_record.read_text(encoding="utf-8"))
        verified = verify(
            record,
            repository=args.repository,
            release_sha=args.release_sha,
            release_tag=args.release_tag,
            bundle_root=args.bundle_root,
            release_title=args.release_title,
        )
        lines = [
            f"Release: {verified['tag']}",
            f"Description: {verified['title']}",
            f"Commit: {verified['sha']}",
            f"Wheel SHA-256: {verified['wheel_sha256']}",
            f"Released unit: {verified['bundle_root']}",
            "",
            "Promoted environments:",
        ]
        lines.extend(
            f"- {name}: workflow run {value['workflow_run_id']} "
            f"attempt {value['workflow_run_attempt']}"
            for name, value in verified["environments"].items()
        )
        lines.extend(["", "Bundle scope:"])
        lines.extend(f"- {root}" for root in verified["scope"])
        args.notes_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, KeyError, PublicationError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
