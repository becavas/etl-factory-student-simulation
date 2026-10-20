import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/deploy-dev.yml")
FORBIDDEN = {
    "DATABRICKS_CLIENT_SECRET",
    "DATABRICKS_TOKEN",
    "ARM_CLIENT_SECRET",
}


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_deploy_job_uses_oidc_and_minimum_github_permissions():
    job = workflow()["jobs"]["deploy-dev"]
    assert job["environment"] == "dev"
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    assert job["env"]["DATABRICKS_AUTH_TYPE"] == "github-oidc"


def test_workflow_contains_no_persistent_databricks_secret():
    text = WORKFLOW.read_text(encoding="utf-8")
    for name in FORBIDDEN:
        assert name not in text
    assert "secrets." not in text


def test_only_main_and_manual_runs_can_trigger_deployment():
    triggers = workflow()[True]
    assert triggers["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in triggers


def test_concurrent_dev_deployments_are_serialized_without_cancellation():
    concurrency = workflow()["concurrency"]
    assert concurrency == {
        "group": "deploy-dev",
        "cancel-in-progress": False,
    }


def run_step(name, tmp_path, extra_env, stubs, job_name="deploy-dev"):
    step = next(step for step in workflow()["jobs"][job_name]["steps"] if step["name"] == name)
    body = step["run"].replace("/tmp/", str(tmp_path) + "/")
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", stubs + "\n" + body],
        cwd=tmp_path,
        env={**os.environ, "RUNNER_TEMP": str(tmp_path), **extra_env},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "permissions,expected_code",
    [
        ([{"applicationId": "runtime"}], 0),
        ({"Resources": [{"applicationId": "runtime"}]}, 0),
        ([{"applicationId": "other"}], 1),
        ([], 1),
        ({"unexpected": []}, 1),
    ],
)
def test_run_as_guard_checks_effective_runtime_permission(tmp_path, permissions, expected_code):
    result = run_step(
        "Verify Run as authorization",
        tmp_path,
        {
            "BUNDLE_VAR_runtime_sp_client_id": "runtime",
            "EF_PERMISSION_FIXTURE": json.dumps(permissions),
        },
        'databricks() { printf "%s\\n" "$EF_PERMISSION_FIXTURE"; }',
    )
    assert result.returncode == expected_code, result.stderr


def test_run_as_guard_precedes_plans_and_deployments():
    names = [step["name"] for step in workflow()["jobs"]["deploy-dev"]["steps"]]
    assert (
        names.index("Verify federated caller")
        < names.index("Verify Run as authorization")
        < names.index("Validate and plan affected capabilities")
    )
    assert names.index("Verify Run as authorization") < names.index("Deploy capabilities first")


@pytest.mark.parametrize(
    "pause,attempt,capabilities,expected_code,expected_pause",
    [
        ("false", "1", 2, 0, False),
        ("true", "1", 2, 0, True),
        ("true", "2", 2, 0, False),
        ("true", "1", 1, 1, False),
    ],
)
def test_lab_pause_and_same_sha_recovery(
    tmp_path, pause, attempt, capabilities, expected_code, expected_pause
):
    roots = ["domains/retail/capabilities/clientes"]
    if capabilities == 2:
        roots.append("domains/retail/capabilities/productos")
    roots.append("domains/retail/orchestration")
    for root in roots:
        (tmp_path / root).mkdir(parents=True)
    result = run_step(
        "Deploy capabilities first",
        tmp_path,
        {
            "BUNDLES_JSON": json.dumps(roots),
            "EF_LAB_PAUSE": pause,
            "GITHUB_RUN_ATTEMPT": attempt,
        },
        'databricks() { printf "DEPLOY:%s\\n" "${PWD##*/}"; }\n'
        'sleep() { printf "PAUSE:%s\\n" "$1"; }',
    )
    assert result.returncode == expected_code, result.stderr
    lines = result.stdout.splitlines()
    assert ("PAUSE:300" in lines) == expected_pause
    assert "DEPLOY:orchestration" not in lines
    if expected_code:
        assert not any(line.startswith("DEPLOY:") for line in lines)
    else:
        assert "DEPLOY:clientes" in lines
        assert "DEPLOY:productos" in lines
    if expected_pause:
        assert lines.index("DEPLOY:clientes") < lines.index("PAUSE:300")
        assert lines.index("PAUSE:300") < lines.index("DEPLOY:productos")


def git_at(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def commit_path(repo, relative):
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture\n", encoding="utf-8")
    git_at(repo, "add", "--all")
    git_at(repo, "commit", "-m", "fixture")
    return git_at(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize(
    "scenario",
    [
        "root",
        "normal",
        "merge",
        "merge-docs",
        "push-range",
        "zero-before",
        "invalid-before",
        "deleted-path",
    ],
)
def test_changed_paths_on_real_git_history(tmp_path, scenario):
    git_at(tmp_path, "init", "-b", "main")
    git_at(tmp_path, "config", "user.name", "Fixture")
    git_at(tmp_path, "config", "user.email", "fixture@example.invalid")
    git_at(tmp_path, "config", "commit.gpgsign", "false")
    git_at(tmp_path, "config", "core.hooksPath", "/dev/null")
    base = commit_path(tmp_path, "README.md")
    before = ""
    clientes = "domains/retail/capabilities/clientes/source.py"
    productos = "domains/retail/capabilities/productos/source.py"
    if scenario == "root":
        current, expected = base, {"README.md"}
    elif scenario in {"merge", "merge-docs"}:
        git_at(tmp_path, "switch", "-c", "feature")
        feature_path = clientes if scenario == "merge" else "docs/notes.md"
        commit_path(tmp_path, feature_path)
        git_at(tmp_path, "switch", "main")
        commit_path(tmp_path, productos)
        git_at(tmp_path, "merge", "--no-ff", "feature", "-m", "merge fixture")
        current = git_at(tmp_path, "rev-parse", "HEAD")
        expected = {feature_path}
    elif scenario == "push-range":
        before = base
        commit_path(tmp_path, clientes)
        current = commit_path(tmp_path, productos)
        expected = {clientes, productos}
    elif scenario == "deleted-path":
        commit_path(tmp_path, clientes)
        (tmp_path / clientes).unlink()
        renamed = "domains/retail/capabilities/clientes/renamed.py"
        current = commit_path(tmp_path, renamed)
        expected = {clientes, renamed}
    else:
        current, expected = commit_path(tmp_path, clientes), {clientes}
        if scenario == "zero-before":
            before = "0" * 40
        elif scenario == "invalid-before":
            before = "unavailable-commit"
    result = run_step(
        "Determine changed paths",
        tmp_path,
        {"BEFORE_SHA": before, "CURRENT_SHA": current},
        "",
        job_name="select-and-check",
    )
    assert result.returncode == 0, result.stderr
    assert set((tmp_path / "changed-paths.txt").read_text().splitlines()) == expected


@pytest.mark.parametrize(
    "pause,capabilities,expected_code",
    [("false", 0, 0), ("true", 0, 1), ("true", 1, 1), ("true", 2, 0)],
)
def test_lab_scope_rejects_empty_or_insufficient_selection(
    tmp_path, pause, capabilities, expected_code
):
    roots = [
        "domains/retail/capabilities/clientes",
        "domains/retail/capabilities/productos",
    ][:capabilities]
    if roots:
        roots.append("domains/retail/orchestration")
    (tmp_path / "changed-paths.txt").write_text("fixture\n", encoding="utf-8")
    result = run_step(
        "Select affected Bundles",
        tmp_path,
        {
            "EF_LAB_PAUSE": pause,
            "EF_SCOPE_FIXTURE": "\n".join(roots),
            "GITHUB_OUTPUT": str(tmp_path / "outputs.txt"),
        },
        'python() { printf "%s\\n" "$EF_SCOPE_FIXTURE"; }',
        job_name="select-and-check",
    )
    assert result.returncode == expected_code, result.stderr
    if expected_code:
        assert "Lab cancellation requires" in result.stderr
    elif capabilities == 0:
        assert "count=0" in (tmp_path / "outputs.txt").read_text()


def test_real_selection_step_with_real_selector_isolates_sandbox_only_bundles(tmp_path):
    """Executes the exact 'Select affected Bundles' step from deploy-dev.yml with the real selector.

    Verifies that sandbox-only bundles are excluded from DEV scope for both direct
    and shared changes without using mock stubs for python or the selector.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    scripts_dir = repo_dir / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(Path("scripts/affected_bundles.py"), scripts_dir)

    # Capability 1: DEV-enabled capability
    std_cap = repo_dir / "domains" / "retail" / "capabilities" / "standard"
    std_cap.mkdir(parents=True)
    with open(std_cap / "databricks.yml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "bundle": {"name": "retail_standard"},
                "targets": {
                    "sandbox": {"mode": "development", "default": True},
                    "dev": {"mode": "production"},
                },
            },
            f,
        )

    # Capability 2: Sandbox-only capability (no DEV target)
    sbx_cap = repo_dir / "domains" / "retail" / "capabilities" / "sandbox_only"
    sbx_cap.mkdir(parents=True)
    with open(sbx_cap / "databricks.yml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "bundle": {"name": "retail_sandbox_only"},
                "targets": {
                    "sandbox": {"mode": "development", "default": True},
                },
            },
            f,
        )

    # Domain orchestration: DEV-enabled
    orch = repo_dir / "domains" / "retail" / "orchestration"
    orch.mkdir(parents=True)
    with open(orch / "databricks.yml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "bundle": {"name": "retail_orchestration"},
                "targets": {
                    "sandbox": {"mode": "development", "default": True},
                    "dev": {"mode": "production"},
                },
            },
            f,
        )

    step = next(
        s
        for s in workflow()["jobs"]["select-and-check"]["steps"]
        if s["name"] == "Select affected Bundles"
    )
    step_script = step["run"]
    assert "scripts/affected_bundles.py --target dev" in step_script

    def execute_step(changed_paths: list[str]) -> tuple[int, list[str], int, str]:
        paths_file = tmp_path / "changed-paths.txt"
        paths_file.write_text("\n".join(changed_paths) + "\n", encoding="utf-8")
        bundles_file = tmp_path / "affected-bundles.txt"
        if bundles_file.exists():
            bundles_file.unlink()
        output_file = tmp_path / "outputs.txt"
        if output_file.exists():
            output_file.unlink()

        adapted_script = step_script.replace("/tmp/", str(tmp_path) + "/")
        env = {
            **os.environ,
            "GITHUB_OUTPUT": str(output_file),
            "EF_LAB_PAUSE": "false",
        }
        # Run real bash, real python, NO STUBS
        proc = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", adapted_script],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        selected_bundles = (
            bundles_file.read_text(encoding="utf-8").splitlines() if bundles_file.exists() else []
        )
        outputs = output_file.read_text(encoding="utf-8") if output_file.exists() else ""
        count = 0
        for line in outputs.splitlines():
            if line.startswith("count="):
                count = int(line.split("=", 1)[1])
        return proc.returncode, selected_bundles, count, outputs

    # 1. Direct change to sandbox-only bundle is excluded from DEV
    code, bundles, count, _ = execute_step(
        ["domains/retail/capabilities/sandbox_only/specs/jobs.yml"]
    )
    assert code == 0
    assert bundles == []
    assert count == 0

    # 2. Direct change to DEV bundle is selected
    code, bundles, count, _ = execute_step(["domains/retail/capabilities/standard/specs/jobs.yml"])
    assert code == 0
    assert bundles == ["domains/retail/capabilities/standard"]
    assert count == 1

    # 3. Shared change selects only DEV-enabled bundles (excludes sandbox_only)
    code, bundles, count, _ = execute_step([".github/CODEOWNERS"])
    assert code == 0
    assert sorted(bundles) == [
        "domains/retail/capabilities/standard",
        "domains/retail/orchestration",
    ]
    assert "domains/retail/capabilities/sandbox_only" not in bundles
    assert count == 2


def test_workflow_step_fails_isolation_when_target_dev_is_removed(tmp_path):
    """Mutant test: confirms removing '--target dev' leaks sandbox-only bundles into DEV scope."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    scripts_dir = repo_dir / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(Path("scripts/affected_bundles.py"), scripts_dir)

    sbx_cap = repo_dir / "domains" / "retail" / "capabilities" / "sandbox_only"
    sbx_cap.mkdir(parents=True)
    with open(sbx_cap / "databricks.yml", "w", encoding="utf-8") as f:
        yaml.dump(
            {"bundle": {"name": "sbx"}, "targets": {"sandbox": {"default": True}}},
            f,
        )

    step = next(
        s
        for s in workflow()["jobs"]["select-and-check"]["steps"]
        if s["name"] == "Select affected Bundles"
    )
    mutated_script = step["run"].replace("--target dev", "")
    assert "--target dev" not in mutated_script

    paths_file = tmp_path / "changed-paths.txt"
    paths_file.write_text("domains/retail/capabilities/sandbox_only/specs/jobs.yml\n")
    output_file = tmp_path / "outputs.txt"

    adapted = mutated_script.replace("/tmp/", str(tmp_path) + "/")
    proc = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", adapted],
        cwd=repo_dir,
        env={
            **os.environ,
            "GITHUB_OUTPUT": str(output_file),
            "EF_LAB_PAUSE": "false",
        },
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    leaked_bundles = (tmp_path / "affected-bundles.txt").read_text().splitlines()
    # Removing --target dev causes the sandbox-only bundle to leak into deployment
    assert "domains/retail/capabilities/sandbox_only" in leaked_bundles


def _get_step_run(name: str) -> str:
    steps = workflow()["jobs"]["deploy-dev"]["steps"]
    for step in steps:
        if step.get("name") == name:
            return step["run"]
    raise KeyError(f"Step {name!r} not found in deploy-dev workflow")


def _setup_mock_databricks(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    state_file = tmp_path / "databricks_state.json"
    state_file.write_text(json.dumps({"deployed_jobs": []}), encoding="utf-8")

    mock_script = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

state_file = Path(os.environ["MOCK_DATABRICKS_STATE"])
if state_file.exists():
    state = json.loads(state_file.read_text(encoding="utf-8"))
else:
    state = {"deployed_jobs": []}
args = sys.argv[1:]

if args[0:2] == ["bundle", "validate"]:
    cwd = Path.cwd().as_posix()
    if "orchestration" in cwd:
        required = [
            "retail-pedidos-e2e",
            "retail-clientes-e2e",
            "retail-productos-e2e",
            "retail-ventas-gold",
        ]
        missing = [j for j in required if j not in state["deployed_jobs"]]
        if missing:
            sys.stderr.write(f"LookupError: jobs {missing} not found in empty workspace\\n")
            sys.exit(1)
        name = "retail_orchestration"
        resource_keys = ["retail_domain_e2e_job"]
    else:
        name = Path.cwd().name
        resource_keys = [f"{name}_job"]
    print(json.dumps({
        "bundle": {"name": name, "target": "dev"},
        "workspace": {"root_path": f"/Workspace/Shared/.bundle/{name}/dev"},
        "resources": {"jobs": {k: {} for k in resource_keys}},
    }))
    sys.exit(0)

elif args[0:2] == ["bundle", "plan"]:
    print("Plan: OK")
    sys.exit(0)

elif args[0:2] == ["bundle", "deploy"]:
    cwd = Path.cwd().as_posix()
    if os.environ.get("MOCK_FAIL_DEPLOY_ON") and os.environ["MOCK_FAIL_DEPLOY_ON"] in cwd:
        sys.stderr.write(f"Simulated failure deploying {cwd}\\n")
        sys.exit(1)
    if "pedidos" in cwd:
        state["deployed_jobs"].append("retail-pedidos-e2e")
    elif "clientes" in cwd:
        state["deployed_jobs"].append("retail-clientes-e2e")
    elif "productos" in cwd:
        state["deployed_jobs"].append("retail-productos-e2e")
    elif "ventas" in cwd:
        state["deployed_jobs"].append("retail-ventas-gold")
    elif "orchestration" in cwd:
        state["deployed_jobs"].append("retail-domain-e2e")
    state_file.write_text(json.dumps(state), encoding="utf-8")
    print(f"Deployed {cwd}")
    sys.exit(0)

elif args[0:2] == ["bundle", "summary"]:
    print(json.dumps({"resources": {}}))
    sys.exit(0)

else:
    sys.exit(0)
"""
    cli_path = bin_dir / "databricks"
    cli_path.write_text(mock_script, encoding="utf-8")
    cli_path.chmod(0o755)
    return bin_dir, state_file


def _run_step(name: str, env: dict, check: bool = True):
    return subprocess.run(
        ["bash", "-e", "-c", _get_step_run(name)],
        check=check,
        env=env,
    )


def test_empty_dev_deployment_flow_succeeds_by_deploying_children_before_parent_lookups(
    tmp_path,
):
    bin_dir, state_file = _setup_mock_databricks(tmp_path)

    wheel = tmp_path / "enterprise_fabric-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"mock-wheel-content")
    wheel_sha = hashlib.sha256(b"mock-wheel-content").hexdigest()

    bundles = [
        "domains/retail/capabilities/pedidos",
        "domains/retail/capabilities/clientes",
        "domains/retail/capabilities/productos",
        "domains/retail/capabilities/ventas",
        "domains/retail/orchestration",
    ]

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "MOCK_DATABRICKS_STATE": str(state_file),
        "BUNDLES_JSON": json.dumps(bundles),
        "RELEASE_WHEEL": str(wheel),
        "EF_EXPECTED_WHEEL_SHA256": wheel_sha,
        "GITHUB_REPOSITORY": "becavas/etl-factory-student-simulation",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "1",
    }

    shutil.rmtree("/tmp/dev-deployment", ignore_errors=True)
    shutil.rmtree("/tmp/dev-release", ignore_errors=True)
    try:
        # Step 1: Validate and plan affected capabilities
        _run_step("Validate and plan affected capabilities", env=env)
        # Step 2: Deploy capabilities first
        _run_step("Deploy capabilities first", env=env)

        # Children must be deployed before parent validates
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert set(state["deployed_jobs"]) == {
            "retail-pedidos-e2e",
            "retail-clientes-e2e",
            "retail-productos-e2e",
            "retail-ventas-gold",
        }

        # Step 3: Validate, plan, and deploy orchestration last
        _run_step("Validate, plan, and deploy orchestration last", env=env)

        # Step 4: Capture deployed summaries
        _run_step("Capture deployed summaries", env=env)

        # Step 5: Build successful deployment record
        _run_step("Build successful deployment record", env=env)

        record_file = Path("/tmp/dev-release/deployment-record.json")
        assert record_file.is_file()
        record = json.loads(record_file.read_text(encoding="utf-8"))
        assert record["status"] == "SUCCESS"
        assert len(record["bundles"]) == 5
    finally:
        shutil.rmtree("/tmp/dev-deployment", ignore_errors=True)
        shutil.rmtree("/tmp/dev-release", ignore_errors=True)


def test_premature_orchestration_validation_fails_in_empty_dev(tmp_path):
    bin_dir, state_file = _setup_mock_databricks(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "MOCK_DATABRICKS_STATE": str(state_file),
    }

    result = subprocess.run(
        "databricks bundle validate --target dev --output json",
        shell=True,
        cwd="domains/retail/orchestration",
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "LookupError" in result.stderr


def test_intermediate_failure_prevents_success_record(tmp_path):
    bin_dir, state_file = _setup_mock_databricks(tmp_path)
    wheel = tmp_path / "enterprise_fabric-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"mock-wheel-content")
    wheel_sha = hashlib.sha256(b"mock-wheel-content").hexdigest()

    bundles = [
        "domains/retail/capabilities/pedidos",
        "domains/retail/capabilities/clientes",
        "domains/retail/orchestration",
    ]
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "MOCK_DATABRICKS_STATE": str(state_file),
        "MOCK_FAIL_DEPLOY_ON": "clientes",
        "BUNDLES_JSON": json.dumps(bundles),
        "RELEASE_WHEEL": str(wheel),
        "EF_EXPECTED_WHEEL_SHA256": wheel_sha,
        "GITHUB_REPOSITORY": "becavas/etl-factory-student-simulation",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "1",
    }

    shutil.rmtree("/tmp/dev-deployment", ignore_errors=True)
    shutil.rmtree("/tmp/dev-release", ignore_errors=True)
    try:
        _run_step("Validate and plan affected capabilities", env=env)
        proc = _run_step("Deploy capabilities first", env=env, check=False)
        assert proc.returncode != 0

        assert not Path("/tmp/dev-release/deployment-record.json").exists()
    finally:
        shutil.rmtree("/tmp/dev-deployment", ignore_errors=True)
        shutil.rmtree("/tmp/dev-release", ignore_errors=True)
