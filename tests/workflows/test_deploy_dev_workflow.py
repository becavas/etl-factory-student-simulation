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
