"""Prove that DEV, CERTI, and PROD used one release."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_promotion(dev, certi, prod, smoke):
    records = {"dev": dev, "certi": certi, "prod": prod}
    if any(record.get("target") != name for name, record in records.items()):
        raise ValueError("deployment record target does not match its environment")
    if any(not record.get("bundles") for record in records.values()):
        raise ValueError("every environment must contain a non-empty Bundle scope")
    if any(
        bundle.get("target") != name
        for name, record in records.items()
        for bundle in record.get("bundles", [])
    ):
        raise ValueError("Bundle target does not match its environment")
    shas = {record["git_sha"] for record in records.values()}
    repositories = {record["repository"] for record in records.values()}
    checksums = {record["artifact"]["sha256"] for record in records.values()}
    scopes = {tuple(bundle["root"] for bundle in record["bundles"]) for record in records.values()}
    if len(shas) != 1:
        raise ValueError("environment records contain different SHAs")
    if len(repositories) != 1:
        raise ValueError("environment records contain different repositories")
    if len(checksums) != 1:
        raise ValueError("environment records contain different artifacts")
    if len(scopes) != 1:
        raise ValueError("environment records contain different Bundle scopes")
    if any(record["status"] != "SUCCESS" for record in records.values()):
        raise ValueError("every environment deployment must be successful")
    if smoke.get("result_state") != "SUCCESS":
        raise ValueError("CERTI smoke must be successful")
    return {
        "schema_version": 1,
        "status": "PROMOTED",
        "repository": repositories.pop(),
        "git_sha": shas.pop(),
        "artifact_sha256": checksums.pop(),
        "bundle_scope": list(scopes.pop()),
        "certi_smoke": smoke,
        "environments": {
            name: {
                "workflow_run_id": record["workflow_run_id"],
                "workflow_run_attempt": record["workflow_run_attempt"],
                "target": record["target"],
            }
            for name, record in records.items()
        },
        "github_environment_audit": (
            "Review deployment history for environment protection approvals"
        ),
        "created_at_utc": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev-record", type=Path, required=True)
    parser.add_argument("--certi-record", type=Path, required=True)
    parser.add_argument("--prod-record", type=Path, required=True)
    parser.add_argument("--certi-smoke", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = build_promotion(
        load(args.dev_record),
        load(args.certi_record),
        load(args.prod_record),
        load(args.certi_smoke),
    )
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
