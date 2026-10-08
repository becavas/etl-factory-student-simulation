from pathlib import Path

import yaml

BUNDLES = {
    "pedidos": Path("domains/retail/capabilities/pedidos/databricks.yml"),
    "clientes": Path("domains/retail/capabilities/clientes/databricks.yml"),
    "productos": Path("domains/retail/capabilities/productos/databricks.yml"),
    "ventas": Path("domains/retail/capabilities/ventas/databricks.yml"),
    "orchestration": Path("domains/retail/orchestration/databricks.yml"),
}


def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_every_bundle_uses_the_supported_cli_and_shared_dev_identity():
    for path in BUNDLES.values():
        document = load(path)
        target = document["targets"]["dev"]
        assert document["bundle"]["databricks_cli_version"] == "1.12.*"
        assert target["mode"] == "production"
        assert target["git"] == {"branch": "main"}
        assert target["run_as"] == {"service_principal_name": "${var.runtime_sp_client_id}"}
        assert target["workspace"]["root_path"].startswith("/Workspace/Shared/.bundle/")
        assert target["presets"]["tags"] == {"deployed_commit": "${var.git_sha}"}


def test_dev_catalog_and_source_volumes_are_isolated():
    for capability in ("pedidos", "clientes", "productos", "ventas"):
        variables = load(BUNDLES[capability])["targets"]["dev"]["variables"]
        assert variables["catalog"] == "retail_dev"
        if capability != "ventas":
            assert variables["source_volume_path"] == (
                f"/Volumes/retail_dev/landing/{capability}_source"
            )


def test_orchestrator_uses_unprefixed_dev_job_names():
    variables = load(BUNDLES["orchestration"])["targets"]["dev"]["variables"]
    assert variables == {
        "pedidos_job_name": "retail-pedidos-e2e",
        "clientes_job_name": "retail-clientes-e2e",
        "productos_job_name": "retail-productos-e2e",
        "ventas_job_name": "retail-ventas-gold",
    }


def test_child_jobs_grant_runtime_only_manage_run():
    keys = {
        "pedidos": "pedidos_e2e_job",
        "clientes": "clientes_e2e_job",
        "productos": "productos_e2e_job",
        "ventas": "ventas_gold_job",
    }
    for capability, job_key in keys.items():
        target = load(BUNDLES[capability])["targets"]["dev"]
        assert target["resources"]["jobs"][job_key]["permissions"] == [
            {
                "service_principal_name": "${var.runtime_sp_client_id}",
                "level": "CAN_MANAGE_RUN",
            }
        ]
