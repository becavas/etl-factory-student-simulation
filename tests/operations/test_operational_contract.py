import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path("domains/retail")
ORCHESTRATION = ROOT / "orchestration/databricks.yml"
GENERATED = sorted(ROOT.glob("capabilities/*/resources/jobs.generated.yml"))


def load(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "resources" not in document:
        resources = {}
        for pattern in document.get("include", []):
            for include_file in sorted(path.parent.glob(pattern)):
                included = yaml.safe_load(include_file.read_text(encoding="utf-8"))
                for resource_type, items in (included or {}).get("resources", {}).items():
                    resources.setdefault(resource_type, {}).update(items)
        if resources:
            document["resources"] = resources
    return document


def assert_schedule_contract(path: Path = ORCHESTRATION) -> None:
    document = load(path)
    # Para la activación programada (§22), PROD pasa a UNPAUSED mientras CERTI permanece en PAUSED.
    for target, state in (("certi", "PAUSED"), ("prod", "UNPAUSED")):
        job = document["targets"][target]["resources"]["jobs"]["retail_domain_e2e_job"]
        actual_tz = job["schedule"].get("timezone_id")
        assert job["schedule"]["timezone_id"] == "America/Lima", (
            f"Expected timezone America/Lima for target {target}, got {actual_tz}"
        )
        assert job["schedule"]["quartz_cron_expression"] == "0 0 2 * * ?"
        assert job["schedule"]["pause_status"] == state
        parameters = {item["name"]: item["default"] for item in job["parameters"]}
        assert parameters == {
            "batch_id": "{{job.trigger.time.iso_date}}",
            "snapshot_mode": "INCREMENTAL",
            "aggregate_mode": "INCREMENTAL",
        }


def assert_generated_jobs_contract(generated_paths: list[Path]) -> None:
    # El contrato no exige exactamente 4 capabilities; es extensible (§16 actualizado).
    reference_capabilities = {"pedidos", "clientes", "productos", "ventas"}
    actual_capabilities = {path.parents[1].name for path in generated_paths}
    assert reference_capabilities.issubset(actual_capabilities), (
        f"Missing required reference capabilities: {reference_capabilities - actual_capabilities}"
    )
    for path in generated_paths:
        jobs = load(path)["resources"]["jobs"]
        for job in jobs.values():
            assert job["max_concurrent_runs"] == 1
            for task in job["tasks"]:
                assert 0 < task["timeout_seconds"] <= 5400
                assert task["max_retries"] in {0, 1}
                if task["max_retries"] == 1:
                    assert task["min_retry_interval_millis"] >= 60000
                    assert task["retry_on_timeout"] is False


def test_certi_and_prod_share_schedule_contract_with_different_state():
    assert_schedule_contract(ORCHESTRATION)


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
        hooks = job.get("webhook_notifications", {})
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
    assert_generated_jobs_contract(GENERATED)


def test_parent_queues_without_automatic_child_retries():
    job = load(ORCHESTRATION)["resources"]["jobs"]["retail_domain_e2e_job"]
    assert job["max_concurrent_runs"] == 1
    assert job["timeout_seconds"] == 14400
    assert job["queue"] == {"enabled": True}
    assert all(task["max_retries"] == 0 for task in job["tasks"])


# =============================================================================
# Behavioral & Negative tests: Extensibilidad completa y Timezone sobre contrato real
# =============================================================================


def test_extensibility_with_isolated_fixture(tmp_path: Path):
    """Demuestra que el contrato operativo completo admite capabilities adicionales genéricas."""
    capabilities_dir = tmp_path / "capabilities"
    caps = ("pedidos", "clientes", "productos", "ventas", "notificaciones")
    for cap in caps:
        cap_dir = capabilities_dir / cap / "resources"
        cap_dir.mkdir(parents=True)
        job_def = {
            "resources": {
                "jobs": {
                    f"{cap}_job": {
                        "name": f"retail-{cap}-job",
                        "max_concurrent_runs": 1,
                        "tasks": [
                            {
                                "task_key": f"task_{cap}",
                                "timeout_seconds": 3600,
                                "max_retries": 1,
                                "min_retry_interval_millis": 60000,
                                "retry_on_timeout": False,
                            }
                        ],
                    }
                }
            }
        }
        (cap_dir / "jobs.generated.yml").write_text(yaml.safe_dump(job_def), encoding="utf-8")

    discovered = sorted(capabilities_dir.glob("*/resources/jobs.generated.yml"))
    assert len(discovered) == 5

    # Ejecutar el contrato completo sobre la fixture extensible
    assert_generated_jobs_contract(discovered)

    # Confirmar que si se exigiera longitud estricta de 4, fallaría
    def strict_four_contract(paths: list[Path]) -> None:
        assert len(paths) == 4, f"Exact 4 capabilities required, found {len(paths)}"
        assert_generated_jobs_contract(paths)

    with pytest.raises(AssertionError, match="Exact 4 capabilities required"):
        strict_four_contract(discovered)


def test_negative_timezone_mismatch(tmp_path: Path):
    """Demuestra rechazo si el schedule no utiliza timezone America/Lima sobre contrato real."""
    target_dir = tmp_path / "orchestration"
    shutil.copytree(ORCHESTRATION.parent, target_dir)
    copied_yaml = target_dir / "databricks.yml"

    # Verificar que la copia fiel pasa el contrato
    assert_schedule_contract(copied_yaml)

    # Modificar únicamente timezone_id a UTC en el YAML
    content = copied_yaml.read_text(encoding="utf-8")
    assert "timezone_id: America/Lima" in content
    tampered_content = content.replace("timezone_id: America/Lima", "timezone_id: UTC")
    copied_yaml.write_text(tampered_content, encoding="utf-8")

    # Ejecutar el contrato real contra el archivo modificado: debe fallar por timezone
    with pytest.raises(AssertionError, match="Expected timezone America/Lima.*got UTC"):
        assert_schedule_contract(copied_yaml)

    # Restaurar a America/Lima y comprobar que vuelve a pasar
    copied_yaml.write_text(content, encoding="utf-8")
    assert_schedule_contract(copied_yaml)
