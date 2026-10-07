"""Write an immutable summary only after every selected Bundle was deployed."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def evidence_key(bundle_root: str) -> str:
    return bundle_root.replace("/", "_")


def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def build_record(args):
    actual_artifact_sha256 = file_sha256(args.artifact)
    if actual_artifact_sha256 != args.artifact_sha256.lower():
        raise ValueError("artifact checksum does not match deployment input")
    roots = [
        line.strip()
        for line in args.bundles_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not roots or len(set(roots)) != len(roots):
        raise ValueError("Bundle scope must be non-empty and contain unique roots")
    bundles = []
    for root in roots:
        key = evidence_key(root)
        validate_path = args.evidence_dir / f"{key}.validate.json"
        summary_path = args.evidence_dir / f"{key}.summary.json"
        if not validate_path.is_file() or not summary_path.is_file():
            raise ValueError(f"missing successful evidence for {root}")
        validated = json.loads(validate_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if validated["bundle"]["target"] != args.target:
            raise ValueError(f"validated target does not match {args.target}: {root}")
        bundles.append(
            {
                "root": root,
                "bundle_name": validated["bundle"]["name"],
                "target": validated["bundle"]["target"],
                "workspace_root": validated["workspace"]["root_path"],
                "resource_keys": sorted((validated.get("resources", {}).get("jobs", {})).keys()),
                "summary_captured": bool(summary),
                "git_sha": args.sha,
            }
        )
    return {
        "schema_version": 1,
        "status": "SUCCESS",
        "repository": args.repository,
        "git_sha": args.sha,
        "workflow_run_id": args.run_id,
        "workflow_run_attempt": args.run_attempt,
        "target": args.target,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "artifact": {
            "file_name": args.artifact.name,
            "sha256": actual_artifact_sha256,
        },
        "bundles": bundles,
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--bundles-file", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = build_record(args)
    args.output.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
