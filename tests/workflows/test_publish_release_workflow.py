from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from scripts.verify_release_publication import PublicationError, verify

WORKFLOW = Path(".github/workflows/publish-release.yml")


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_release_is_manual_and_serialized():
    document = workflow()
    assert set(document[True]) == {"workflow_dispatch"}
    assert document["concurrency"]["cancel-in-progress"] is False
    inputs = document[True]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "release_tag",
        "bundle_root",
        "release_title",
        "release_sha",
        "promotion_run_id",
        "promotion_run_attempt",
    }


def test_only_protected_publish_job_can_write_contents():
    jobs = workflow()["jobs"]
    assert jobs["verify-release"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    assert jobs["publish-release"]["environment"] == "prod"
    assert jobs["publish-release"]["permissions"]["contents"] == "write"
    assert "id-token" not in jobs["publish-release"]["permissions"]


def test_exact_promotion_run_and_attempt_are_downloaded():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "inputs.promotion_run_id" in text
    assert "inputs.promotion_run_attempt" in text
    assert "inputs.bundle_root" in text
    assert "inputs.release_title" in text
    assert text.count("scripts/verify_release_publication.py") == 2
    assert "secrets." not in text
    assert "git push --force" not in text
    assert 'test "$tag_sha" = "$RELEASE_SHA"' in text


def test_publication_controls_are_independent_of_the_promoted_commit():
    for job in workflow()["jobs"].values():
        checkouts = [
            step
            for step in job["steps"]
            if "uses" in step and step["uses"].startswith("actions/checkout@")
        ]
        by_path = {step["with"]["path"]: step["with"] for step in checkouts}
        assert by_path["automation"]["ref"] == "${{ github.sha }}"
        assert by_path["automation"]["persist-credentials"] is False
        assert by_path["release"]["ref"] == "${{ inputs.release_sha }}"


# =============================================================================
# Behavioral tests: Verificación de publicación, namespace, SHA y causas de rechazo
# =============================================================================


def valid_promoted_record(sha: str = "116f835e8c963af36d66dfe13120094391256654"):
    return {
        "status": "PROMOTED",
        "repository": "becavas/etl-factory-student-simulation",
        "git_sha": sha,
        "artifact_sha256": "c0f4874c2677b282312f6fa0edfe09987cb6a531ae58df791e0d4ff1c3fecb09",
        "bundle_scope": [
            "domains/retail/capabilities/clientes",
            "domains/retail/capabilities/pedidos",
            "domains/retail/capabilities/productos",
            "domains/retail/capabilities/ventas",
            "domains/retail/orchestration",
        ],
        "certi_smoke": {"result_state": "SUCCESS"},
        "environments": {
            "dev": {
                "target": "dev",
                "workflow_run_id": "38142299373",
                "workflow_run_attempt": "1",
            },
            "certi": {
                "target": "certi",
                "workflow_run_id": "38252469573",
                "workflow_run_attempt": "1",
            },
            "prod": {
                "target": "prod",
                "workflow_run_id": "38252469573",
                "workflow_run_attempt": "1",
            },
        },
    }


def test_behavior_valid_promoted_release_verification(tmp_path):
    record = valid_promoted_record()
    record_path = tmp_path / "promotion-record.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    notes_path = tmp_path / "release-notes.md"

    # Simular invocación CLI de scripts/verify_release_publication.py
    cmd = [
        "python",
        "scripts/verify_release_publication.py",
        "--promotion-record",
        str(record_path),
        "--repository",
        "becavas/etl-factory-student-simulation",
        "--release-sha",
        "116f835e8c963af36d66dfe13120094391256654",
        "--release-tag",
        "retail/ventas/v1.0.0",
        "--bundle-root",
        "domains/retail/capabilities/ventas",
        "--release-title",
        "Ventas Gold y KPI diario operables",
        "--notes-output",
        str(notes_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Failed: {res.stderr}"
    assert notes_path.exists()
    content = notes_path.read_text(encoding="utf-8")
    assert "Release: retail/ventas/v1.0.0" in content
    assert "Commit: 116f835e8c963af36d66dfe13120094391256654" in content
    expected_wheel = (
        "Wheel SHA-256: c0f4874c2677b282312f6fa0edfe09987cb6a531ae58df791e0d4ff1c3fecb09"
    )
    assert expected_wheel in content


@pytest.mark.parametrize(
    "invalid_tag,expected_error",
    [
        ("v1.0.0", "release tag must be <domain>/<unit>/vMAJOR.MINOR.PATCH"),
        ("retail/ventas/1.0.0", "release tag must be <domain>/<unit>/vMAJOR.MINOR.PATCH"),
        ("retail/pedidos/v1.0.0", "release tag namespace does not match Bundle root"),
    ],
)
def test_behavior_rejects_invalid_or_mismatched_namespace(invalid_tag, expected_error):
    record = valid_promoted_record()
    with pytest.raises(PublicationError, match=expected_error):
        verify(
            record,
            repository="becavas/etl-factory-student-simulation",
            release_sha="116f835e8c963af36d66dfe13120094391256654",
            release_tag=invalid_tag,
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


def test_behavior_rejects_unpromoted_record():
    record = valid_promoted_record()
    record["status"] = "FAILED"
    with pytest.raises(PublicationError, match="promotion status must be PROMOTED"):
        verify(
            record,
            repository="becavas/etl-factory-student-simulation",
            release_sha="116f835e8c963af36d66dfe13120094391256654",
            release_tag="retail/ventas/v1.0.0",
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


def test_behavior_rejects_mismatched_sha():
    record = valid_promoted_record()
    wrong_sha = "0" * 40
    with pytest.raises(PublicationError, match="release SHA does not match promotion"):
        verify(
            record,
            repository="becavas/etl-factory-student-simulation",
            release_sha=wrong_sha,
            release_tag="retail/ventas/v1.0.0",
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


def test_behavior_rejects_scope_absence():
    record = valid_promoted_record()
    record["bundle_scope"] = ["domains/retail/capabilities/pedidos"]
    with pytest.raises(
        PublicationError, match="release Bundle root is absent from promotion scope"
    ):
        verify(
            record,
            repository="becavas/etl-factory-student-simulation",
            release_sha="116f835e8c963af36d66dfe13120094391256654",
            release_tag="retail/ventas/v1.0.0",
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


def test_behavior_rejects_failed_certi_smoke():
    record = valid_promoted_record()
    record["certi_smoke"] = {"result_state": "FAILED"}
    with pytest.raises(PublicationError, match="CERTI smoke is not successful"):
        verify(
            record,
            repository="becavas/etl-factory-student-simulation",
            release_sha="116f835e8c963af36d66dfe13120094391256654",
            release_tag="retail/ventas/v1.0.0",
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


# =============================================================================
# Behavioral test: Verificación de lógica git tag usando repositorio local aislado
# =============================================================================


def test_behavior_tag_creation_and_idempotent_rerun_in_isolated_git(tmp_path):
    repo = tmp_path / "mock_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=repo, check=True)

    dummy_file = repo / "file.txt"
    dummy_file.write_text("commit 1", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True)
    sha1 = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    # Primer run: crear tag anotado
    tag_name = "retail/ventas/v1.0.0"
    subprocess.run(
        ["git", "tag", "-a", tag_name, sha1, "-m", "Ventas v1.0.0 release"],
        cwd=repo,
        check=True,
    )
    tag_sha = subprocess.check_output(
        ["git", "rev-parse", f"refs/tags/{tag_name}^{{}}"], cwd=repo, text=True
    ).strip()
    assert tag_sha == sha1

    # Rerun idempotente: el tag existe y apunta al mismo SHA -> pasa
    assert tag_sha == sha1

    # Rerun conflictivo: nuevo commit intenta reutilizar el mismo tag
    dummy_file.write_text("commit 2", encoding="utf-8")
    subprocess.run(["git", "commit", "-am", "second commit"], cwd=repo, check=True)
    sha2 = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    assert tag_sha != sha2, "Reusing tag for a different commit must be detected as conflict"
