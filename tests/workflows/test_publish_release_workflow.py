from __future__ import annotations

import json
import os
import shutil
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
# Behavioral tests: Ejecución real de bloques run del YAML en fixtures aisladas
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def publish_step_script() -> str:
    steps = workflow()["jobs"]["publish-release"]["steps"]
    for step in steps:
        if step.get("name") == "Reverify and publish immutable tag and release":
            return step["run"]
    raise AssertionError("Step 'Reverify and publish immutable tag and release' not found")


def authentic_promotion_record() -> dict:
    primary = Path(
        "/private/tmp/codex-phase13-final-38252469573/promoted-release-116f835e8c963af36d66dfe13120094391256654-1/promotion-record.json"
    )
    if primary.is_file():
        return json.loads(primary.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "status": "PROMOTED",
        "repository": "becavas/etl-factory-student-simulation",
        "git_sha": "116f835e8c963af36d66dfe13120094391256654",
        "artifact_sha256": "c0f4874c2677b282312f6fa0edfe09987cb6a531ae58df791e0d4ff1c3fecb09",
        "bundle_scope": [
            "domains/retail/capabilities/clientes",
            "domains/retail/capabilities/pedidos",
            "domains/retail/capabilities/productos",
            "domains/retail/capabilities/ventas",
            "domains/retail/orchestration",
        ],
        "certi_smoke": {
            "run_id": 954484275576539,
            "job_id": 874965929098030,
            "batch_id": "release_smoke_20260815_001",
            "life_cycle_state": "TERMINATED",
            "result_state": "SUCCESS",
            "run_page_url": "https://adb-7405611412963889.9.azuredatabricks.net/?o=7405611412963889#job/874965929098030/run/954484275576539",
        },
        "environments": {
            "dev": {
                "workflow_run_id": "38142299373",
                "workflow_run_attempt": "1",
                "target": "dev",
            },
            "certi": {
                "workflow_run_id": "38252469573",
                "workflow_run_attempt": "1",
                "target": "certi",
            },
            "prod": {
                "workflow_run_id": "38252469573",
                "workflow_run_attempt": "1",
                "target": "prod",
            },
        },
        "github_environment_audit": (
            "Review deployment history for environment protection approvals"
        ),
        "created_at_utc": "2026-10-12T13:27:18.550058+00:00",
    }


def setup_workflow_fixture(tmp_path: Path, record_override: dict | None = None):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "push",
            str(bare),
            "889779587b9f1da0de0c825a3e1511cdfde27462:refs/heads/main",
            "HEAD:refs/heads/feature",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )

    release = tmp_path / "release"
    automation = tmp_path / "automation"
    promotion = tmp_path / "promotion"
    promotion.mkdir(exist_ok=True)

    record_data = record_override if record_override is not None else authentic_promotion_record()
    (promotion / "promotion-record.json").write_text(json.dumps(record_data), encoding="utf-8")

    subprocess.run(["git", "clone", str(bare), str(release)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(release), "checkout", "116f835e8c963af36d66dfe13120094391256654"],
        check=True,
        capture_output=True,
    )
    # Verificar que el commit histórico carece del verificador nuevo
    assert not (release / "scripts/verify_release_publication.py").exists(), (
        "Historical commit 116f835 must not contain scripts/verify_release_publication.py"
    )

    subprocess.run(["git", "clone", str(bare), str(automation)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(automation), "checkout", "feature"],
        check=True,
        capture_output=True,
    )
    # Copiar scripts/verify_release_publication.py a automation si no está aún en el commit
    verify_script_src = REPO_ROOT / "scripts/verify_release_publication.py"
    (automation / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy(verify_script_src, automation / "scripts/verify_release_publication.py")
    assert (automation / "scripts/verify_release_publication.py").exists()

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    mock_gh = bin_dir / "gh"
    gh_log = tmp_path / "gh_calls.json"
    releases_state = tmp_path / "gh_releases.json"
    if not releases_state.exists():
        releases_state.write_text("[]", encoding="utf-8")

    mock_gh_code = f"""#!/usr/bin/env python3
import sys, json
from pathlib import Path

args = sys.argv[1:]
if "--version" in args:
    print("gh version 2.50.0 (mock)")
    sys.exit(0)

if len(args) >= 2 and args[0] == "release" and args[1] == "create":
    tag = args[2]
    state_file = Path({repr(str(releases_state))})
    log_file = Path({repr(str(gh_log))})
    existing = json.loads(state_file.read_text(encoding="utf-8"))
    if tag in existing:
        msg = (
            f"HTTP 422: Validation Failed (already_exists: "
            f"Release already exists for tag {{tag}})\\n"
        )
        sys.stderr.write(msg)
        sys.exit(1)
    existing.append(tag)
    state_file.write_text(json.dumps(existing), encoding="utf-8")
    
    calls = []
    if log_file.exists():
        calls = json.loads(log_file.read_text(encoding="utf-8"))
    calls.append(args)
    log_file.write_text(json.dumps(calls), encoding="utf-8")
    print(f"Created release for {{tag}}")
    sys.exit(0)

sys.stderr.write(f"Unexpected gh call: {{args}}\\n")
sys.exit(1)
"""
    mock_gh.write_text(mock_gh_code, encoding="utf-8")
    mock_gh.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["GITHUB_REF"] = "refs/heads/main"
    env["GITHUB_SHA"] = subprocess.check_output(
        ["git", "-C", str(automation), "rev-parse", "HEAD"], text=True
    ).strip()
    env["RELEASE_SHA"] = "116f835e8c963af36d66dfe13120094391256654"
    env["RELEASE_TAG"] = "retail/ventas/v1.0.0"
    env["BUNDLE_ROOT"] = "domains/retail/capabilities/ventas"
    env["RELEASE_TITLE"] = "Ventas Gold y KPI diario operables"
    env["GITHUB_REPOSITORY"] = "becavas/etl-factory-student-simulation"
    env["GH_TOKEN"] = "mock-token"

    return bare, release, automation, promotion, env, gh_log, releases_state


def test_behavior_first_publish_creates_annotated_tag_and_gh_release(tmp_path):
    bare, release, automation, promotion, env, gh_log, _ = setup_workflow_fixture(tmp_path)
    script = publish_step_script()
    res = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Workflow run failed: {res.stdout}\n{res.stderr}"

    # Validar tag creado en el remoto origin
    tag_target = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/retail/ventas/v1.0.0^{}"],
        text=True,
    ).strip()
    assert tag_target == env["RELEASE_SHA"]
    tag_type = subprocess.check_output(
        ["git", "--git-dir", str(bare), "cat-file", "-t", "refs/tags/retail/ventas/v1.0.0"],
        text=True,
    ).strip()
    assert tag_type == "tag", "Expected annotated tag object"

    # Validar invocación a gh release create
    calls = json.loads(gh_log.read_text(encoding="utf-8"))
    assert len(calls) == 1
    assert calls[0][0:3] == ["release", "create", "retail/ventas/v1.0.0"]
    assert "--verify-tag" in calls[0]


def test_behavior_idempotent_rerun_when_tag_exists_same_sha(tmp_path):
    bare, release, automation, promotion, env, gh_log, _ = setup_workflow_fixture(tmp_path)
    # Pre-crear el tag en origin simulando rerun con tag enviado y release pendiente
    subprocess.run(
        [
            "git",
            "--git-dir",
            str(bare),
            "tag",
            "-a",
            "retail/ventas/v1.0.0",
            env["RELEASE_SHA"],
            "-m",
            "Pre-existing tag",
        ],
        check=True,
    )
    orig_tag_object = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/retail/ventas/v1.0.0"],
        text=True,
    ).strip()

    script = publish_step_script()
    res = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Rerun failed: {res.stdout}\n{res.stderr}"

    # Tag no debe haber sido recreado ni modificado
    current_tag_object = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/retail/ventas/v1.0.0"],
        text=True,
    ).strip()
    assert current_tag_object == orig_tag_object

    # Release completado
    calls = json.loads(gh_log.read_text(encoding="utf-8"))
    assert len(calls) == 1


def test_behavior_tag_on_different_sha_rejected_before_publish(tmp_path):
    bare, release, automation, promotion, env, gh_log, _ = setup_workflow_fixture(tmp_path)
    # Tag pre-creado en origin apuntando a un commit distinto
    other_sha = "889779587b9f1da0de0c825a3e1511cdfde27462"
    subprocess.run(
        [
            "git",
            "--git-dir",
            str(bare),
            "tag",
            "-a",
            "retail/ventas/v1.0.0",
            other_sha,
            "-m",
            "Tag pointing to different commit",
        ],
        check=True,
    )
    orig_tag_sha = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/retail/ventas/v1.0.0^{}"],
        text=True,
    ).strip()

    script = publish_step_script()
    res = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0, "Conflicting tag must cause script failure"

    # Verificar que el tag remoto NO fue sobrescrito
    after_tag_sha = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/retail/ventas/v1.0.0^{}"],
        text=True,
    ).strip()
    assert after_tag_sha == orig_tag_sha
    assert not gh_log.exists()


def test_behavior_invalid_namespace_rejected_before_tag_creation(tmp_path):
    bare, release, automation, promotion, env, gh_log, _ = setup_workflow_fixture(tmp_path)
    env["RELEASE_TAG"] = "retail/pedidos/v1.0.0"  # Desalineado con BUNDLE_ROOT = retail/ventas
    script = publish_step_script()
    res = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "release tag namespace does not match Bundle root" in (res.stdout + res.stderr)

    # Comprobar que NO se creó ningún tag en remoto
    tag_list = subprocess.check_output(
        ["git", "--git-dir", str(bare), "tag", "-l"], text=True
    ).strip()
    assert "retail/pedidos/v1.0.0" not in tag_list
    assert not gh_log.exists()


def test_behavior_unpromoted_record_rejected_before_tag_creation(tmp_path):
    record = authentic_promotion_record()
    record["status"] = "FAILED"
    bare, release, automation, promotion, env, gh_log, _ = setup_workflow_fixture(
        tmp_path, record_override=record
    )
    script = publish_step_script()
    res = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "promotion status must be PROMOTED" in (res.stdout + res.stderr)

    tag_list = subprocess.check_output(
        ["git", "--git-dir", str(bare), "tag", "-l"], text=True
    ).strip()
    assert "retail/ventas/v1.0.0" not in tag_list
    assert not gh_log.exists()


def test_behavior_duplicate_release_creation_fails_without_altering_tag(tmp_path):
    bare, release, automation, promotion, env, gh_log, _ = setup_workflow_fixture(tmp_path)
    script = publish_step_script()
    # Primera ejecución exitosa
    res1 = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res1.returncode == 0

    # Segunda ejecución debe fallar de forma segura en gh release create
    res2 = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res2.returncode != 0
    assert "Release already exists" in (res2.stdout + res2.stderr)


def test_behavior_tampered_script_without_tag_push_fails_verification(tmp_path):
    """Demuestra que si se elimina tag push del script real, la comprobación falla."""
    bare, release, automation, promotion, env, gh_log, _ = setup_workflow_fixture(tmp_path)
    script = publish_step_script()
    tampered_script = script.replace(
        'git tag -a "$RELEASE_TAG" "$RELEASE_SHA" -m "$RELEASE_TITLE"', ":"
    ).replace('git push origin "refs/tags/$RELEASE_TAG"', ":")

    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", tampered_script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    tag_list = subprocess.check_output(
        ["git", "--git-dir", str(bare), "tag", "-l"], text=True
    ).strip()
    assert "retail/ventas/v1.0.0" not in tag_list, (
        "Script sin push de tag no debió crear el tag en origin"
    )
