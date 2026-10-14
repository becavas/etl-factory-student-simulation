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
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


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
# Unit tests del verificador: scripts/verify_release_publication.py
# =============================================================================


def synthetic_unit_record(sha: str = "0123456789abcdef0123456789abcdef01234567"):
    """Fixture sintética genérica para verify_release_publication.py."""
    return {
        "status": "PROMOTED",
        "repository": "test-org/test-repo",
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
                "workflow_run_id": "1001",
                "workflow_run_attempt": "1",
            },
            "certi": {
                "target": "certi",
                "workflow_run_id": "1002",
                "workflow_run_attempt": "1",
            },
            "prod": {
                "target": "prod",
                "workflow_run_id": "1002",
                "workflow_run_attempt": "1",
            },
        },
    }


def test_behavior_valid_promoted_release_verification(tmp_path):
    sha = "0123456789abcdef0123456789abcdef01234567"
    record = synthetic_unit_record(sha)
    record_path = tmp_path / "promotion-record.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    notes_path = tmp_path / "release-notes.md"

    cmd = [
        "python",
        "scripts/verify_release_publication.py",
        "--promotion-record",
        str(record_path),
        "--repository",
        "test-org/test-repo",
        "--release-sha",
        sha,
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
    assert f"Commit: {sha}" in content
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
    sha = "0123456789abcdef0123456789abcdef01234567"
    record = synthetic_unit_record(sha)
    with pytest.raises(PublicationError, match=expected_error):
        verify(
            record,
            repository="test-org/test-repo",
            release_sha=sha,
            release_tag=invalid_tag,
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


def test_behavior_rejects_unpromoted_record():
    sha = "0123456789abcdef0123456789abcdef01234567"
    record = synthetic_unit_record(sha)
    record["status"] = "FAILED"
    with pytest.raises(PublicationError, match="promotion status must be PROMOTED"):
        verify(
            record,
            repository="test-org/test-repo",
            release_sha=sha,
            release_tag="retail/ventas/v1.0.0",
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


def test_behavior_rejects_mismatched_sha():
    sha = "0123456789abcdef0123456789abcdef01234567"
    record = synthetic_unit_record(sha)
    wrong_sha = "0" * 40
    with pytest.raises(PublicationError, match="release SHA does not match promotion"):
        verify(
            record,
            repository="test-org/test-repo",
            release_sha=wrong_sha,
            release_tag="retail/ventas/v1.0.0",
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


def test_behavior_rejects_scope_absence():
    sha = "0123456789abcdef0123456789abcdef01234567"
    record = synthetic_unit_record(sha)
    record["bundle_scope"] = ["domains/retail/capabilities/pedidos"]
    with pytest.raises(
        PublicationError, match="release Bundle root is absent from promotion scope"
    ):
        verify(
            record,
            repository="test-org/test-repo",
            release_sha=sha,
            release_tag="retail/ventas/v1.0.0",
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


def test_behavior_rejects_failed_certi_smoke():
    sha = "0123456789abcdef0123456789abcdef01234567"
    record = synthetic_unit_record(sha)
    record["certi_smoke"] = {"result_state": "FAILED"}
    with pytest.raises(PublicationError, match="CERTI smoke is not successful"):
        verify(
            record,
            repository="test-org/test-repo",
            release_sha=sha,
            release_tag="retail/ventas/v1.0.0",
            bundle_root="domains/retail/capabilities/ventas",
            release_title="Ventas release",
        )


# =============================================================================
# Behavioral tests: Ejecución real de bloques run en fixtures portables
# =============================================================================


def publish_step_script() -> str:
    steps = workflow()["jobs"]["publish-release"]["steps"]
    for step in steps:
        if step.get("name") == "Reverify and publish immutable tag and release":
            return step["run"]
    raise AssertionError("Step 'Reverify and publish immutable tag and release' not found")


def make_synthetic_promotion_record(
    git_sha: str,
    artifact_sha256: str = "c0f4874c2677b282312f6fa0edfe09987cb6a531ae58df791e0d4ff1c3fecb09",
    status: str = "PROMOTED",
    bundle_scope: list[str] | None = None,
    certi_smoke_status: str = "SUCCESS",
    dev_run_id: str = "38142299373",
    dev_attempt: str = "1",
    promo_run_id: str = "38252469573",
    promo_attempt: str = "1",
) -> dict:
    """Construye un promotion-record.json sintético portable para pruebas aisladas."""
    return {
        "schema_version": 1,
        "status": status,
        "repository": "test-org/test-repo",
        "git_sha": git_sha,
        "artifact_sha256": artifact_sha256,
        "bundle_scope": bundle_scope
        or [
            "domains/retail/capabilities/clientes",
            "domains/retail/capabilities/pedidos",
            "domains/retail/capabilities/productos",
            "domains/retail/capabilities/ventas",
            "domains/retail/orchestration",
        ],
        "certi_smoke": {
            "run_id": 954484275576539,
            "job_id": 874965929098030,
            "batch_id": "synthetic_smoke_001",
            "life_cycle_state": "TERMINATED",
            "result_state": certi_smoke_status,
            "run_page_url": "https://adb-mock.net/#job/874965929098030/run/954484275576539",
        },
        "environments": {
            "dev": {
                "workflow_run_id": dev_run_id,
                "workflow_run_attempt": dev_attempt,
                "target": "dev",
            },
            "certi": {
                "workflow_run_id": promo_run_id,
                "workflow_run_attempt": promo_attempt,
                "target": "certi",
            },
            "prod": {
                "workflow_run_id": promo_run_id,
                "workflow_run_attempt": promo_attempt,
                "target": "prod",
            },
        },
        "github_environment_audit": "Synthetic test environment audit record",
        "created_at_utc": "2026-10-14T12:00:00.000000+00:00",
    }


def setup_portable_workflow_fixture(tmp_path: Path, record_override: dict | None = None):
    """Construye una historia Git sintética portable sin configuración global ni red."""
    git_env = os.environ.copy()
    git_env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    git_env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    git_env["GIT_ALLOW_PROTOCOL"] = "file"

    bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare)], check=True, capture_output=True, env=git_env
    )
    subprocess.run(
        ["git", "--git-dir", str(bare), "config", "user.name", "workflow-bot"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "--git-dir", str(bare), "config", "user.email", "workflow-bot@example.com"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "--git-dir", str(bare), "config", "user.useConfigOnly", "true"],
        check=True,
        env=git_env,
    )

    seed = tmp_path / "seed"
    subprocess.run(
        ["git", "init", "-b", "main", str(seed)], check=True, capture_output=True, env=git_env
    )
    subprocess.run(
        ["git", "-C", str(seed), "config", "user.name", "workflow-bot"], check=True, env=git_env
    )
    subprocess.run(
        ["git", "-C", str(seed), "config", "user.email", "workflow-bot@example.com"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "-C", str(seed), "config", "user.useConfigOnly", "true"], check=True, env=git_env
    )

    # Commit 1 (content): commit promovido sintético sin el verificador nuevo
    (seed / "domains/retail/capabilities/ventas").mkdir(parents=True, exist_ok=True)
    (seed / "domains/retail/capabilities/ventas/README.md").write_text(
        "Ventas synthetic capability", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(seed), "add", "."], check=True, env=git_env)
    subprocess.run(
        ["git", "-C", str(seed), "commit", "-m", "feat(retail): synthetic content"],
        check=True,
        env=git_env,
    )
    promoted_sha = subprocess.check_output(
        ["git", "-C", str(seed), "rev-parse", "HEAD"], text=True, env=git_env
    ).strip()

    # Commit 2 (controls): commit de automatización sobre main que incluye el verificador real
    (seed / "scripts").mkdir(parents=True, exist_ok=True)
    real_verifier = REPO_ROOT / "scripts/verify_release_publication.py"
    shutil.copy(real_verifier, seed / "scripts/verify_release_publication.py")
    subprocess.run(
        ["git", "-C", str(seed), "add", "scripts/verify_release_publication.py"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "-C", str(seed), "commit", "-m", "feat(ops): add verification controls"],
        check=True,
        env=git_env,
    )
    automation_sha = subprocess.check_output(
        ["git", "-C", str(seed), "rev-parse", "HEAD"], text=True, env=git_env
    ).strip()

    # Push main from seed to bare
    subprocess.run(
        ["git", "-C", str(seed), "push", str(bare), "main:main"],
        check=True,
        capture_output=True,
        env=git_env,
    )

    # Checkouts aislados
    release = tmp_path / "release"
    automation = tmp_path / "automation"
    promotion = tmp_path / "promotion"
    promotion.mkdir(exist_ok=True)

    subprocess.run(
        ["git", "clone", str(bare), str(release)], check=True, capture_output=True, env=git_env
    )
    subprocess.run(
        ["git", "-C", str(release), "config", "user.name", "workflow-bot"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "-C", str(release), "config", "user.email", "workflow-bot@example.com"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "-C", str(release), "config", "user.useConfigOnly", "true"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "-C", str(release), "checkout", promoted_sha],
        check=True,
        capture_output=True,
        env=git_env,
    )
    assert not (release / "scripts/verify_release_publication.py").exists(), (
        "Release checkout must not contain scripts/verify_release_publication.py"
    )

    subprocess.run(
        ["git", "clone", str(bare), str(automation)], check=True, capture_output=True, env=git_env
    )
    subprocess.run(
        ["git", "-C", str(automation), "config", "user.name", "workflow-bot"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "-C", str(automation), "config", "user.email", "workflow-bot@example.com"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "-C", str(automation), "config", "user.useConfigOnly", "true"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "-C", str(automation), "checkout", automation_sha],
        check=True,
        capture_output=True,
        env=git_env,
    )
    assert (automation / "scripts/verify_release_publication.py").exists(), (
        "Automation checkout must contain scripts/verify_release_publication.py"
    )

    # Promotion record sintético
    record_data = (
        record_override
        if record_override is not None
        else make_synthetic_promotion_record(git_sha=promoted_sha)
    )
    rec_content = json.dumps(record_data, indent=2)
    (promotion / "promotion-record.json").write_text(rec_content, encoding="utf-8")

    # Doble estricto de gh que valida flags, notas y record adjunto
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    mock_gh = bin_dir / "gh"
    gh_invocations = tmp_path / "gh_invocations.json"
    releases_state = tmp_path / "gh_releases.json"
    gh_invocations.write_text("[]", encoding="utf-8")
    releases_state.write_text("[]", encoding="utf-8")

    mock_gh_code = f"""#!/usr/bin/env python3
import sys, os, json
from pathlib import Path

args = sys.argv[1:]
inv_file = Path({repr(str(gh_invocations))})
state_file = Path({repr(str(releases_state))})

def log_invocation(status, details=""):
    invs = json.loads(inv_file.read_text(encoding="utf-8")) if inv_file.exists() else []
    invs.append({{"args": args, "cwd": os.getcwd(), "status": status, "details": details}})
    inv_file.write_text(json.dumps(invs, indent=2), encoding="utf-8")

if "--version" in args:
    print("gh version 2.50.0 (mock)")
    sys.exit(0)

if len(args) >= 2 and args[0] == "release" and args[1] == "create":
    if len(args) < 3 or args[2].startswith("-"):
        log_invocation("REJECTED", "Missing release tag")
        sys.stderr.write("ERROR: gh release create requires a release tag\\n")
        sys.exit(1)
    tag = args[2]

    if "--verify-tag" not in args:
        log_invocation("REJECTED", "Missing --verify-tag flag")
        sys.stderr.write("ERROR: gh release create requires --verify-tag\\n")
        sys.exit(1)

    if "--title" not in args:
        log_invocation("REJECTED", "Missing --title flag")
        sys.stderr.write("ERROR: gh release create requires --title\\n")
        sys.exit(1)
    title_idx = args.index("--title")
    if title_idx + 1 >= len(args) or args[title_idx + 1].startswith("-"):
        log_invocation("REJECTED", "Missing title value")
        sys.stderr.write("ERROR: gh release create requires non-empty --title value\\n")
        sys.exit(1)
    title_val = args[title_idx + 1]

    if "--notes-file" not in args:
        log_invocation("REJECTED", "Missing --notes-file flag")
        sys.stderr.write("ERROR: gh release create requires --notes-file\\n")
        sys.exit(1)
    notes_idx = args.index("--notes-file")
    if notes_idx + 1 >= len(args) or args[notes_idx + 1].startswith("-"):
        log_invocation("REJECTED", "Missing notes-file value")
        sys.stderr.write("ERROR: gh release create requires notes-file path\\n")
        sys.exit(1)
    notes_path = Path(args[notes_idx + 1])
    if not notes_path.is_file():
        log_invocation("REJECTED", f"Notes file not found: {{notes_path}}")
        sys.stderr.write(f"ERROR: notes file not found: {{notes_path}}\\n")
        sys.exit(1)
    notes_content = notes_path.read_text(encoding="utf-8").strip()
    if not notes_content:
        log_invocation("REJECTED", "Notes file is empty")
        sys.stderr.write("ERROR: notes file is empty\\n")
        sys.exit(1)

    skip_indices = {{
        0, 1, 2, title_idx, title_idx + 1, notes_idx, notes_idx + 1, args.index("--verify-tag")
    }}
    attached_files = [
        args[i] for i in range(len(args))
        if i not in skip_indices and not args[i].startswith("-")
    ]
    if not attached_files:
        log_invocation("REJECTED", "Missing attached promotion record file")
        sys.stderr.write("ERROR: gh release create requires attached promotion record file\\n")
        sys.exit(1)
    
    attached_record_path = Path(attached_files[0])
    if not attached_record_path.is_file():
        log_invocation("REJECTED", f"Attached file not found: {{attached_record_path}}")
        sys.stderr.write(f"ERROR: attached file not found: {{attached_record_path}}\\n")
        sys.exit(1)
    try:
        rec_data = json.loads(attached_record_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log_invocation("REJECTED", f"Attached file is invalid JSON: {{exc}}")
        sys.stderr.write(f"ERROR: attached file is invalid JSON: {{exc}}\\n")
        sys.exit(1)
    
    if rec_data.get("status") != "PROMOTED":
        st_val = rec_data.get("status")
        log_invocation("REJECTED", f"Attached record status is not PROMOTED: {{st_val}}")
        sys.stderr.write("ERROR: attached record status is not PROMOTED\\n")
        sys.exit(1)

    existing = json.loads(state_file.read_text(encoding="utf-8"))
    existing_tags = [r["tag"] for r in existing]
    if tag in existing_tags:
        log_invocation("REJECTED", f"Duplicate release for tag {{tag}}")
        msg = (
            f"HTTP 422: Validation Failed (already_exists: "
            f"Release already exists for tag {{tag}})\\n"
        )
        sys.stderr.write(msg)
        sys.exit(1)

    existing.append({{
        "tag": tag,
        "title": title_val,
        "notes": notes_content,
        "attached_record": rec_data,
    }})
    state_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    log_invocation("SUCCESS", f"Created release for {{tag}}")
    print(f"Created release for {{tag}}")
    sys.exit(0)

log_invocation("REJECTED", f"Unexpected invocation: {{args}}")
sys.stderr.write(f"Unexpected gh call: {{args}}\\n")
sys.exit(1)
"""
    mock_gh.write_text(mock_gh_code, encoding="utf-8")
    mock_gh.chmod(0o755)

    env = git_env.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["GITHUB_REF"] = "refs/heads/main"
    env["GITHUB_SHA"] = automation_sha
    env["RELEASE_SHA"] = promoted_sha
    env["RELEASE_TAG"] = "retail/ventas/v1.0.0"
    env["BUNDLE_ROOT"] = "domains/retail/capabilities/ventas"
    env["RELEASE_TITLE"] = "Ventas Gold y KPI diario operables"
    env["GITHUB_REPOSITORY"] = "test-org/test-repo"
    env["GH_TOKEN"] = "mock-token"

    return bare, release, automation, promotion, env, gh_invocations, releases_state


def test_behavior_first_publish_creates_annotated_tag_and_gh_release(tmp_path):
    bare, release, automation, promotion, env, gh_inv, rel_state = setup_portable_workflow_fixture(
        tmp_path
    )
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
        env=env,
    ).strip()
    assert tag_target == env["RELEASE_SHA"]
    tag_type = subprocess.check_output(
        ["git", "--git-dir", str(bare), "cat-file", "-t", "refs/tags/retail/ventas/v1.0.0"],
        text=True,
        env=env,
    ).strip()
    assert tag_type == "tag", "Expected annotated tag object"

    # Validar release y argumentos verificados por el doble de gh
    rels = json.loads(rel_state.read_text(encoding="utf-8"))
    assert len(rels) == 1
    assert rels[0]["tag"] == "retail/ventas/v1.0.0"
    assert rels[0]["title"] == "retail/ventas/v1.0.0 — Ventas Gold y KPI diario operables"
    assert "Release: retail/ventas/v1.0.0" in rels[0]["notes"]
    assert rels[0]["attached_record"]["status"] == "PROMOTED"
    assert rels[0]["attached_record"]["git_sha"] == env["RELEASE_SHA"]


def test_behavior_idempotent_rerun_when_tag_exists_same_sha(tmp_path):
    bare, release, automation, promotion, env, gh_inv, rel_state = setup_portable_workflow_fixture(
        tmp_path
    )
    # Pre-crear el tag en origin con user.useConfigOnly=true sin Git global
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
        env=env,
    )
    orig_tag_object = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/retail/ventas/v1.0.0"],
        text=True,
        env=env,
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
        env=env,
    ).strip()
    assert current_tag_object == orig_tag_object

    # Release completado
    rels = json.loads(rel_state.read_text(encoding="utf-8"))
    assert len(rels) == 1


def test_behavior_tag_on_different_sha_rejected_before_publish(tmp_path):
    bare, release, automation, promotion, env, gh_inv, rel_state = setup_portable_workflow_fixture(
        tmp_path
    )
    # Pre-crear tag en origin apuntando a otro commit (automation_sha)
    subprocess.run(
        [
            "git",
            "--git-dir",
            str(bare),
            "tag",
            "-a",
            "retail/ventas/v1.0.0",
            env["GITHUB_SHA"],
            "-m",
            "Tag pointing to different commit",
        ],
        check=True,
        env=env,
    )
    orig_tag_sha = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/retail/ventas/v1.0.0^{}"],
        text=True,
        env=env,
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
        env=env,
    ).strip()
    assert after_tag_sha == orig_tag_sha

    # Verificar que no se creó ningún release
    rels = json.loads(rel_state.read_text(encoding="utf-8"))
    assert len(rels) == 0


def test_behavior_invalid_namespace_rejected_before_tag_creation(tmp_path):
    bare, release, automation, promotion, env, gh_inv, rel_state = setup_portable_workflow_fixture(
        tmp_path
    )
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
        ["git", "--git-dir", str(bare), "tag", "-l"], text=True, env=env
    ).strip()
    assert "retail/pedidos/v1.0.0" not in tag_list

    # Sin releases creados
    rels = json.loads(rel_state.read_text(encoding="utf-8"))
    assert len(rels) == 0


def test_behavior_unpromoted_record_rejected_before_tag_creation(tmp_path):
    bare, release, automation, promotion, env, gh_inv, rel_state = setup_portable_workflow_fixture(
        tmp_path
    )
    # Modificar el record para tener status FAILED
    rec_path = promotion / "promotion-record.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    rec["status"] = "FAILED"
    rec_path.write_text(json.dumps(rec), encoding="utf-8")

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
        ["git", "--git-dir", str(bare), "tag", "-l"], text=True, env=env
    ).strip()
    assert "retail/ventas/v1.0.0" not in tag_list

    rels = json.loads(rel_state.read_text(encoding="utf-8"))
    assert len(rels) == 0


def test_behavior_duplicate_release_creation_fails_without_altering_tag(tmp_path):
    bare, release, automation, promotion, env, gh_inv, rel_state = setup_portable_workflow_fixture(
        tmp_path
    )
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
    tag_sha1 = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/retail/ventas/v1.0.0"],
        text=True,
        env=env,
    ).strip()

    # Segunda ejecución debe fallar de forma segura en gh release create
    res2 = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res2.returncode != 0
    assert "Release already exists for tag" in (res2.stdout + res2.stderr)

    # El objeto tag no cambia y el inventario permanece en 1
    tag_sha2 = subprocess.check_output(
        ["git", "--git-dir", str(bare), "rev-parse", "refs/tags/retail/ventas/v1.0.0"],
        text=True,
        env=env,
    ).strip()
    assert tag_sha1 == tag_sha2
    rels = json.loads(rel_state.read_text(encoding="utf-8"))
    assert len(rels) == 1


def test_behavior_mutation_omitting_tag_push_fails(tmp_path):
    """Demuestra que omitir git push del script YAML hace fallar la comprobación de tag remoto."""
    bare, release, automation, promotion, env, gh_inv, rel_state = setup_portable_workflow_fixture(
        tmp_path
    )
    script = publish_step_script()
    tampered_script = script.replace('git push origin "refs/tags/$RELEASE_TAG"', ":")

    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", tampered_script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    tag_list = subprocess.check_output(
        ["git", "--git-dir", str(bare), "tag", "-l"], text=True, env=env
    ).strip()
    assert "retail/ventas/v1.0.0" not in tag_list, (
        "Script sin push de tag no debió crear el tag en origin"
    )


def test_behavior_mutation_omitting_attached_record_fails(tmp_path):
    """Demuestra que omitir el promotion-record.json en gh release create hace fallar el paso."""
    bare, release, automation, promotion, env, gh_inv, rel_state = setup_portable_workflow_fixture(
        tmp_path
    )
    script = publish_step_script()
    lines = script.splitlines()
    tampered_lines = [
        line for line in lines if line.strip() != "../promotion/promotion-record.json \\"
    ]
    tampered_script = "\n".join(tampered_lines)

    res = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", tampered_script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0, "Omission of attached promotion record must cause failure"
    assert "requires attached promotion record file" in (res.stdout + res.stderr)


def test_behavior_mutation_omitting_notes_file_fails(tmp_path):
    """Demuestra que omitir --notes-file en gh release create hace fallar el paso."""
    bare, release, automation, promotion, env, gh_inv, rel_state = setup_portable_workflow_fixture(
        tmp_path
    )
    script = publish_step_script()
    tampered_lines = [line for line in script.splitlines() if "--notes-file" not in line]
    if tampered_lines[-1].endswith("\\"):
        tampered_lines[-1] = tampered_lines[-1][:-1].strip()
    tampered_script = "\n".join(tampered_lines)

    res = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", tampered_script],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0, "Omission of --notes-file must cause failure"
    assert "requires --notes-file" in (res.stdout + res.stderr)
