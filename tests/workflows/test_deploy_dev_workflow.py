import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

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
