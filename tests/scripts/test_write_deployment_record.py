import hashlib
import json
from argparse import Namespace

import pytest
from scripts.write_deployment_record import build_record, evidence_key


def write_evidence(directory, root, target="dev"):
    key = evidence_key(root)
    (directory / f"{key}.validate.json").write_text(
        json.dumps(
            {
                "bundle": {"name": root.rsplit("/", 1)[-1], "target": target},
                "workspace": {"root_path": f"/Workspace/Shared/.bundle/x/{target}"},
                "resources": {"jobs": {"job": {}}},
            }
        )
    )
    (directory / f"{key}.summary.json").write_text('{"resources": {}}')


def args(tmp_path, roots):
    bundles_file = tmp_path / "bundles.txt"
    bundles_file.write_text("\n".join(roots) + "\n")
    artifact = tmp_path / "enterprise_fabric-0.1.0-py3-none-any.whl"
    artifact.write_bytes(b"release-wheel")
    return Namespace(
        repository="org/repo",
        sha="a" * 40,
        run_id="100",
        run_attempt="2",
        target="dev",
        bundles_file=bundles_file,
        evidence_dir=tmp_path,
        artifact=artifact,
        artifact_sha256=hashlib.sha256(b"release-wheel").hexdigest(),
    )


def test_record_uses_one_sha_for_every_deployed_bundle(tmp_path):
    roots = ["domains/retail/capabilities/pedidos", "domains/retail/orchestration"]
    for root in roots:
        write_evidence(tmp_path, root)
    record = build_record(args(tmp_path, roots))
    assert record["status"] == "SUCCESS"
    assert {bundle["git_sha"] for bundle in record["bundles"]} == {"a" * 40}
    assert [bundle["root"] for bundle in record["bundles"]] == roots
    assert record["artifact"]["sha256"] == hashlib.sha256(b"release-wheel").hexdigest()


def test_missing_summary_prevents_success_record(tmp_path):
    root = "domains/retail/capabilities/pedidos"
    data = args(tmp_path, [root])
    with pytest.raises(ValueError, match="missing successful evidence"):
        build_record(data)


def test_artifact_checksum_mismatch_prevents_success_record(tmp_path):
    data = args(tmp_path, [])
    data.artifact_sha256 = "0" * 64
    with pytest.raises(ValueError, match="artifact checksum"):
        build_record(data)


def test_wrong_validated_target_prevents_success_record(tmp_path):
    root = "domains/retail/capabilities/pedidos"
    write_evidence(tmp_path, root, target="certi")
    with pytest.raises(ValueError, match="validated target"):
        build_record(args(tmp_path, [root]))


def test_empty_or_duplicate_scope_prevents_success_record(tmp_path):
    with pytest.raises(ValueError, match="non-empty"):
        build_record(args(tmp_path, []))
