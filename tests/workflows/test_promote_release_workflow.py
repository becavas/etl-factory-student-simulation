from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/promote-release.yml")


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


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
