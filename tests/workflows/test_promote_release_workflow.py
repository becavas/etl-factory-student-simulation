from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/promote-release.yml")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def smoke_step_script():
    steps = workflow()["jobs"]["deploy-certi"]["steps"]
    for step in steps:
        if step.get("name") == "Run domain smoke in CERTI":
            return step["run"]
    raise AssertionError("Smoke step 'Run domain smoke in CERTI' not found in deploy-certi")


def test_promotion_is_manual_and_serialized():
    document = workflow()
    assert set(document[True]) == {"workflow_dispatch"}
    assert document["concurrency"] == {
        "group": "promote-release",
        "cancel-in-progress": False,
    }


def test_release_verification_has_no_oidc():
    permissions = workflow()["jobs"]["verify-release"]["permissions"]
    assert permissions == {"contents": "read", "actions": "read"}


def test_certi_and_prod_use_separate_environments_and_oidc():
    jobs = workflow()["jobs"]
    assert jobs["deploy-certi"]["environment"] == "certi"
    assert jobs["deploy-prod"]["environment"] == "prod"
    for key in ("deploy-certi", "deploy-prod"):
        assert jobs[key]["permissions"]["id-token"] == "write"


def test_shared_jobs_reject_same_deployer_and_runtime():
    text = WORKFLOW.read_text(encoding="utf-8")
    check = 'test "$DATABRICKS_CLIENT_ID" != "$BUNDLE_VAR_runtime_sp_client_id"'
    assert text.count(check) == 2


def test_prod_depends_on_successful_certi():
    assert set(workflow()["jobs"]["deploy-prod"]["needs"]) == {
        "verify-release",
        "deploy-certi",
    }


def test_prod_deploy_does_not_execute_etl():
    prod = yaml.safe_dump(workflow()["jobs"]["deploy-prod"])
    assert "databricks bundle run" not in prod
    assert "databricks jobs run-now" not in prod
    assert "--target prod" in prod


def test_workflow_never_rebuilds_or_uses_databricks_secrets():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "python -m build" not in text
    assert "DATABRICKS_TOKEN" not in text
    assert "DATABRICKS_CLIENT_SECRET" not in text
    assert "secrets." not in text
    assert "continue-on-error" not in text
    assert 'EF_USE_PREBUILT_WHEEL: "true"' in text
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in text


# --- Behavioral tests for Run domain smoke in CERTI step ---

VALID_SUMMARY = {
    "resources": {
        "jobs": {
            "retail_domain_e2e_job": {
                "id": 874965929098030,
            }
        }
    }
}


def make_valid_run_metadata(
    job_id=874965929098030,
    run_id=607191181713567,
    batch_id="smoke_batch_001",
    snapshot_mode="INCREMENTAL",
    aggregate_mode="INCREMENTAL",
    life_cycle_state="TERMINATED",
    result_state="SUCCESS",
    tasks=None,
):
    if tasks is None:
        tasks = [
            {
                "task_key": "run_clientes",
                "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
            },
            {
                "task_key": "run_pedidos",
                "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
            },
            {
                "task_key": "run_productos",
                "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
            },
            {
                "task_key": "run_ventas",
                "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
            },
        ]
    return {
        "job_id": job_id,
        "run_id": run_id,
        "state": {
            "life_cycle_state": life_cycle_state,
            "result_state": result_state,
        },
        "tasks": tasks,
        "job_parameters": [
            {"name": "batch_id", "value": batch_id},
            {"name": "snapshot_mode", "value": snapshot_mode},
            {"name": "aggregate_mode", "value": aggregate_mode},
        ],
        "run_page_url": f"https://adb.net/jobs/{job_id}/runs/{run_id}",
    }


def execute_smoke_step(
    tmp_path, summary_data, run_data, run_exit_code=0, batch_id="smoke_batch_001"
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    mock_cli = bin_dir / "databricks"

    script_content = f"""#!/usr/bin/env python3
import sys, json

summary_payload = {json.dumps(summary_data)}
run_payload = {json.dumps(run_data)}
run_exit = {run_exit_code}

args = sys.argv[1:]
if "bundle" in args and "summary" in args:
    if summary_payload is not None:
        sys.stdout.write(json.dumps(summary_payload))
    sys.exit(0)
elif "jobs" in args and "run-now" in args:
    if run_exit != 0:
        sys.stderr.write("CLI run-now error\\n")
        sys.exit(run_exit)
    if run_payload is not None:
        sys.stdout.write(json.dumps(run_payload))
    sys.exit(0)
sys.stderr.write(f"Unexpected invocation: {{args}}\\n")
sys.exit(1)
"""
    mock_cli.write_text(script_content, encoding="utf-8")
    mock_cli.chmod(0o755)

    # Clean tmp evidence before running
    for temp_file in [
        "/tmp/certi-domain-summary.json",
        "/tmp/certi-smoke-request.json",
        "/tmp/certi-smoke-run.json",
        "/tmp/certi-smoke.json",
    ]:
        Path(temp_file).unlink(missing_ok=True)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SMOKE_BATCH_ID"] = batch_id

    script = smoke_step_script()
    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result


def test_smoke_step_succeeds_with_valid_run_metadata(tmp_path):
    run_meta = make_valid_run_metadata()
    res = execute_smoke_step(tmp_path, VALID_SUMMARY, run_meta)
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    smoke_file = Path("/tmp/certi-smoke.json")
    assert smoke_file.is_file()
    smoke_record = json.loads(smoke_file.read_text(encoding="utf-8"))
    assert smoke_record["run_id"] == 607191181713567
    assert smoke_record["job_id"] == 874965929098030
    assert smoke_record["batch_id"] == "smoke_batch_001"
    assert smoke_record["life_cycle_state"] == "TERMINATED"
    assert smoke_record["result_state"] == "SUCCESS"
    assert "run_page_url" in smoke_record

    # Verify run full json is also preserved
    assert Path("/tmp/certi-smoke-run.json").is_file()


def test_smoke_step_fails_on_cli_run_now_failure(tmp_path):
    res = execute_smoke_step(tmp_path, VALID_SUMMARY, None, run_exit_code=1)
    assert res.returncode != 0
    assert not Path("/tmp/certi-smoke.json").exists()


def test_smoke_step_fails_when_job_id_missing_in_summary(tmp_path):
    empty_summary = {"resources": {"jobs": {}}}
    res = execute_smoke_step(tmp_path, empty_summary, make_valid_run_metadata())
    assert res.returncode != 0
    assert not Path("/tmp/certi-smoke.json").exists()


def test_smoke_step_fails_on_failed_task(tmp_path):
    tasks_with_failure = [
        {
            "task_key": "run_clientes",
            "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
        },
        {
            "task_key": "run_pedidos",
            "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
        },
        {
            "task_key": "run_productos",
            "state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED"},
        },
        {
            "task_key": "run_ventas",
            "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
        },
    ]
    run_meta = make_valid_run_metadata(result_state="FAILED", tasks=tasks_with_failure)
    res = execute_smoke_step(tmp_path, VALID_SUMMARY, run_meta)
    assert res.returncode != 0
    assert not Path("/tmp/certi-smoke.json").exists()


def test_smoke_step_fails_on_omitted_task(tmp_path):
    tasks_missing = [
        {
            "task_key": "run_clientes",
            "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
        },
        {
            "task_key": "run_pedidos",
            "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
        },
        {
            "task_key": "run_ventas",
            "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
        },
    ]
    run_meta = make_valid_run_metadata(tasks=tasks_missing)
    res = execute_smoke_step(tmp_path, VALID_SUMMARY, run_meta)
    assert res.returncode != 0
    assert not Path("/tmp/certi-smoke.json").exists()


def test_smoke_step_fails_on_non_terminal_state(tmp_path):
    run_meta = make_valid_run_metadata(life_cycle_state="RUNNING", result_state=None)
    res = execute_smoke_step(tmp_path, VALID_SUMMARY, run_meta)
    assert res.returncode != 0
    assert not Path("/tmp/certi-smoke.json").exists()


def test_smoke_step_fails_on_inconsistent_job_or_batch_or_modes(tmp_path):
    # Inconsistent batch
    run_meta_bad_batch = make_valid_run_metadata(batch_id="wrong_batch")
    res = execute_smoke_step(
        tmp_path, VALID_SUMMARY, run_meta_bad_batch, batch_id="smoke_batch_001"
    )
    assert res.returncode != 0
    assert not Path("/tmp/certi-smoke.json").exists()

    # Inconsistent job_id
    run_meta_bad_job = make_valid_run_metadata(job_id=9999999)
    res = execute_smoke_step(tmp_path, VALID_SUMMARY, run_meta_bad_job)
    assert res.returncode != 0
    assert not Path("/tmp/certi-smoke.json").exists()

    # Inconsistent snapshot_mode
    run_meta_bad_mode = make_valid_run_metadata(snapshot_mode="FULL")
    res = execute_smoke_step(tmp_path, VALID_SUMMARY, run_meta_bad_mode)
    assert res.returncode != 0
    assert not Path("/tmp/certi-smoke.json").exists()


def test_smoke_step_fails_on_task_outputs_only_payload(tmp_path):
    # Defecto original de databricks bundle run --output json
    task_outputs_only = {"task_outputs": []}
    res = execute_smoke_step(tmp_path, VALID_SUMMARY, task_outputs_only)
    assert res.returncode != 0
    assert not Path("/tmp/certi-smoke.json").exists()
