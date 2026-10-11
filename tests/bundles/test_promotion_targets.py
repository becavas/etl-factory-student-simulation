from pathlib import Path

import yaml

BUNDLES = {
    "pedidos": Path("domains/retail/capabilities/pedidos/databricks.yml"),
    "clientes": Path("domains/retail/capabilities/clientes/databricks.yml"),
    "productos": Path("domains/retail/capabilities/productos/databricks.yml"),
    "ventas": Path("domains/retail/capabilities/ventas/databricks.yml"),
    "orchestration": Path("domains/retail/orchestration/databricks.yml"),
}


def load(name):
    return yaml.safe_load(BUNDLES[name].read_text(encoding="utf-8"))


def test_shared_targets_have_stable_identity_and_branch():
    for document in map(load, BUNDLES):
        assert document["bundle"]["databricks_cli_version"] == "1.12.*"
        assert document["targets"]["sandbox"]["default"] is True
        for environment in ("dev", "certi", "prod"):
            target = document["targets"][environment]
            assert target["mode"] == "production"
            assert target["git"] == {"branch": "main"}
            assert target["run_as"] == {"service_principal_name": "${var.runtime_sp_client_id}"}
            assert target["presets"]["tags"] == {"deployed_commit": "${var.git_sha}"}


def test_capability_catalogs_match_target():
    for name in ("pedidos", "clientes", "productos", "ventas"):
        document = load(name)
        assert document["targets"]["certi"]["variables"]["catalog"] == ("retail_certi")
        assert document["targets"]["prod"]["variables"]["catalog"] == ("retail_prod")


def test_source_volumes_never_cross_environments():
    for name in ("pedidos", "clientes", "productos"):
        document = load(name)
        for environment in ("certi", "prod"):
            path = document["targets"][environment]["variables"]["source_volume_path"]
            assert path == f"/Volumes/retail_{environment}/landing/{name}_source"


def test_orchestrator_names_are_unprefixed_in_shared_targets():
    document = load("orchestration")
    expected = {
        "pedidos_job_name": "retail-pedidos-e2e",
        "clientes_job_name": "retail-clientes-e2e",
        "productos_job_name": "retail-productos-e2e",
        "ventas_job_name": "retail-ventas-gold",
    }
    assert document["targets"]["certi"]["variables"] == expected
    assert document["targets"]["prod"]["variables"] == expected
