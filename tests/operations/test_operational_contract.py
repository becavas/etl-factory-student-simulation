from pathlib import Path

import yaml

ROOT = Path("domains/retail")
ORCHESTRATION = ROOT / "orchestration/databricks.yml"
GENERATED = sorted(ROOT.glob("capabilities/*/resources/jobs.generated.yml"))


def load(path):
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "resources" not in document and "include" in document:
        resources = {}
        for pattern in document["include"]:
            for include_file in path.parent.glob(pattern):
                included = yaml.safe_load(include_file.read_text(encoding="utf-8"))
                if included and "resources" in included:
                    for key, val in included["resources"].items():
                        resources.setdefault(key, {}).update(val)
        if resources:
            document["resources"] = resources
    return document


def test_certi_and_prod_share_schedule_contract_with_different_state():
    document = load(ORCHESTRATION)
    # En la primera PR ambos targets inician en PAUSED por seguridad operativa (§19).
    for target, state in (("certi", "PAUSED"), ("prod", "PAUSED")):
        job = document["targets"][target]["resources"]["jobs"]["retail_domain_e2e_job"]
        assert job["schedule"] == {
            "quartz_cron_expression": "0 0 2 * * ?",
            "timezone_id": "America/Lima",
            "pause_status": state,
        }
        parameters = {item["name"]: item["default"] for item in job["parameters"]}
        assert parameters == {
            "batch_id": "{{job.trigger.time.iso_date}}",
            "snapshot_mode": "INCREMENTAL",
            "aggregate_mode": "INCREMENTAL",
        }


def test_shared_targets_have_duration_health_and_notifications():
    document = load(ORCHESTRATION)
    for target, warning in (("certi", 60), ("prod", 7200)):
        job = document["targets"][target]["resources"]["jobs"]["retail_domain_e2e_job"]
        assert job["health"]["rules"] == [
            {
                "metric": "RUN_DURATION_SECONDS",
                "op": "GREATER_THAN",
                "value": warning,
            }
        ]
        hooks = job["webhook_notifications"]
        expected = [{"id": "${var.notification_destination_id}"}]
        assert hooks["on_failure"] == expected
        assert hooks["on_duration_warning_threshold_exceeded"] == expected
        assert job["permissions"] == [
            {
                "group_name": "${var.operator_group}",
                "level": "CAN_MANAGE_RUN",
            }
        ]


def test_generated_jobs_have_bounded_execution_and_safe_retries():
    assert len(GENERATED) == 4
    for path in GENERATED:
        jobs = load(path)["resources"]["jobs"]
        for job in jobs.values():
            assert job["max_concurrent_runs"] == 1
            for task in job["tasks"]:
                assert 0 < task["timeout_seconds"] <= 5400
                assert task["max_retries"] in {0, 1}
                if task["max_retries"] == 1:
                    assert task["min_retry_interval_millis"] >= 60000
                    assert task["retry_on_timeout"] is False


def test_parent_queues_without_automatic_child_retries():
    job = load(ORCHESTRATION)["resources"]["jobs"]["retail_domain_e2e_job"]
    assert job["max_concurrent_runs"] == 1
    assert job["timeout_seconds"] == 14400
    assert job["queue"] == {"enabled": True}
    assert all(task["max_retries"] == 0 for task in job["tasks"])
