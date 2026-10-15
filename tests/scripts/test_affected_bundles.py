import pytest
from scripts.affected_bundles import affected_bundles

CLIENTES = "domains/retail/capabilities/clientes"
PEDIDOS = "domains/retail/capabilities/pedidos"
PRODUCTOS = "domains/retail/capabilities/productos"
VENTAS = "domains/retail/capabilities/ventas"
ORCHESTRATION = "domains/retail/orchestration"
ALL_BUNDLES = sorted([CLIENTES, PEDIDOS, PRODUCTOS, VENTAS, ORCHESTRATION])


def test_clientes_only_change_selects_only_clientes():
    assert affected_bundles(["src/enterprise_fabric/retail/clientes/silver.py"]) == [CLIENTES]


def test_pedidos_only_change_selects_only_pedidos():
    assert affected_bundles(["domains/retail/capabilities/pedidos/specs/jobs.yml"]) == [PEDIDOS]


def test_productos_only_change_selects_only_productos():
    assert affected_bundles(["src/enterprise_fabric/retail/productos/silver.py"]) == [PRODUCTOS]


def test_ventas_only_change_selects_only_ventas():
    assert affected_bundles(["src/enterprise_fabric/retail/ventas/fact.py"]) == [VENTAS]


def test_orchestration_change_selects_only_orchestration():
    assert affected_bundles(["domains/retail/orchestration/resources/domain-workflow.yml"]) == [
        ORCHESTRATION
    ]


def test_shared_change_selects_capabilities_and_orchestration():
    assert affected_bundles([".github/workflows/pull-request.yml"]) == ALL_BUNDLES


def test_shared_release_delivery_controls_select_all_bundles():
    for path in (
        ".github/workflows/promote-release.yml",
        ".github/workflows/publish-release.yml",
        "scripts/verify_release_candidate.py",
        "scripts/verify_release_publication.py",
        "scripts/write_promotion_record.py",
    ):
        assert affected_bundles([path]) == ALL_BUNDLES


def test_shared_generator_change_selects_every_capability():
    assert affected_bundles(["tools/bundle_generator/generator.py"]) == ALL_BUNDLES


def test_shared_code_change_selects_every_capability():
    assert affected_bundles(["src/enterprise_fabric/shared/spark.py"]) == ALL_BUNDLES


def test_docs_only_change_selects_no_capability():
    assert affected_bundles(["docs/architecture/overview.md"]) == []


def test_removed_bundle_does_not_disappear_silently():
    with pytest.raises(ValueError, match="sin Bundle actual"):
        affected_bundles(["domains/retail/capabilities/retirada/databricks.yml"])


def test_removed_orchestration_bundle_does_not_disappear_silently():
    with pytest.raises(ValueError, match="sin Bundle actual"):
        affected_bundles(["domains/retail_other/orchestration/databricks.yml"])
