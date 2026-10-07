from pathlib import Path

import yaml

RESOURCE = Path("domains/retail/orchestration/resources/domain-workflow.yml")
BUNDLE = Path("domains/retail/orchestration/databricks.yml")


def workflow():
    document = yaml.safe_load(RESOURCE.read_text(encoding="utf-8"))
    return document["resources"]["jobs"]["retail_domain_e2e_job"]


def tasks_by_key():
    return {task["task_key"]: task for task in workflow()["tasks"]}


def test_dag_has_three_parallel_producers_and_sales_fan_in():
    tasks = tasks_by_key()
    assert set(tasks) == {
        "run_pedidos",
        "run_clientes",
        "run_productos",
        "run_ventas",
    }
    for key in ("run_pedidos", "run_clientes", "run_productos"):
        assert "depends_on" not in tasks[key]
    assert tasks["run_ventas"]["depends_on"] == [
        {"task_key": "run_pedidos"},
        {"task_key": "run_clientes"},
        {"task_key": "run_productos"},
    ]


def test_every_child_receives_same_batch_parameter():
    for task in tasks_by_key().values():
        assert task["run_job_task"]["job_parameters"]["batch_id"] == ("{{job.parameters.batch_id}}")


def test_only_sales_receives_gold_modes():
    tasks = tasks_by_key()
    for key in ("run_pedidos", "run_clientes", "run_productos"):
        assert set(tasks[key]["run_job_task"]["job_parameters"]) == {"batch_id"}
    assert tasks["run_ventas"]["run_job_task"]["job_parameters"] == {
        "batch_id": "{{job.parameters.batch_id}}",
        "snapshot_mode": "{{job.parameters.snapshot_mode}}",
        "aggregate_mode": "{{job.parameters.aggregate_mode}}",
    }


def test_parent_has_limits_and_no_compute_or_artifacts():
    job = workflow()
    assert job["max_concurrent_runs"] == 1
    assert job["queue"] == {"enabled": True}
    assert job["timeout_seconds"] == 14400
    assert "job_clusters" not in job
    for task in job["tasks"]:
        assert task["timeout_seconds"] > 0
        assert task["max_retries"] == 0
        assert "run_job_task" in task
        assert not {
            "job_cluster_key",
            "new_cluster",
            "existing_cluster_id",
            "libraries",
            "environment_key",
        }.intersection(task)


def test_child_job_ids_are_lookup_variables():
    expected = {
        "run_pedidos": "${var.pedidos_job_id}",
        "run_clientes": "${var.clientes_job_id}",
        "run_productos": "${var.productos_job_id}",
        "run_ventas": "${var.ventas_job_id}",
    }
    assert {key: task["run_job_task"]["job_id"] for key, task in tasks_by_key().items()} == expected


def test_every_job_id_uses_a_name_lookup():
    document = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
    variables = document["variables"]
    for capability in ("pedidos", "clientes", "productos", "ventas"):
        assert variables[f"{capability}_job_id"]["lookup"] == {
            "job": f"${{var.{capability}_job_name}}"
        }


def test_lookup_defaults_match_public_child_job_names():
    document = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
    variables = document["variables"]
    assert {
        capability: variables[f"{capability}_job_name"]["default"]
        for capability in ("pedidos", "clientes", "productos", "ventas")
    } == {
        "pedidos": ("[dev ${workspace.current_user.short_name}] retail-pedidos-e2e"),
        "clientes": ("[dev ${workspace.current_user.short_name}] retail-clientes-e2e"),
        "productos": ("[dev ${workspace.current_user.short_name}] retail-productos-e2e"),
        "ventas": ("[dev ${workspace.current_user.short_name}] retail-ventas-gold"),
    }


def test_orchestrator_bundle_has_no_artifact_or_platform_resources():
    document = yaml.safe_load(BUNDLE.read_text(encoding="utf-8"))
    assert document["bundle"]["name"] == "retail_orchestration"
    assert "artifacts" not in document
    assert "sync" not in document
    assert set(document["targets"]) == {"sandbox", "dev"}
