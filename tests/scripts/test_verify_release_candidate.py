import hashlib

import pytest
from scripts.verify_release_candidate import (
    ReleaseCandidateError,
    verify_candidate,
)


def candidate(tmp_path):
    wheel = tmp_path / "enterprise_fabric-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"approved-wheel")
    digest = hashlib.sha256(b"approved-wheel").hexdigest()
    sha = "a" * 40
    record = {
        "status": "SUCCESS",
        "repository": "org/repo",
        "git_sha": sha,
        "workflow_run_id": "101",
        "workflow_run_attempt": "2",
        "target": "dev",
        "artifact": {"file_name": wheel.name, "sha256": digest},
        "bundles": [
            {
                "root": "domains/retail/capabilities/pedidos",
                "git_sha": sha,
                "target": "dev",
            }
        ],
    }
    return record, sha


def verify(record, sha, tmp_path):
    return verify_candidate(
        record,
        tmp_path,
        repository="org/repo",
        release_sha=sha,
        dev_run_id="101",
        dev_run_attempt="2",
    )


def test_successful_dev_record_and_wheel_are_eligible(tmp_path):
    record, sha = candidate(tmp_path)
    roots, _, _ = verify(record, sha, tmp_path)
    assert roots == ["domains/retail/capabilities/pedidos"]


def test_main_sha_without_dev_success_is_rejected(tmp_path):
    record, sha = candidate(tmp_path)
    record["status"] = "FAILED"
    with pytest.raises(ReleaseCandidateError, match="record status"):
        verify(record, sha, tmp_path)


def test_rebuilt_or_modified_wheel_is_rejected(tmp_path):
    record, sha = candidate(tmp_path)
    (tmp_path / record["artifact"]["file_name"]).write_bytes(b"rebuilt")
    with pytest.raises(ReleaseCandidateError, match="checksum"):
        verify(record, sha, tmp_path)


def test_mixed_bundle_sha_is_rejected(tmp_path):
    record, sha = candidate(tmp_path)
    record["bundles"][0]["git_sha"] = "b" * 40
    with pytest.raises(ReleaseCandidateError, match="every DEV Bundle"):
        verify(record, sha, tmp_path)
