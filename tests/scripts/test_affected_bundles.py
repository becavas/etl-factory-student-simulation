import pytest
from scripts.affected_bundles import affected_bundles

CLIENTES = "domains/retail/capabilities/clientes"
PEDIDOS = "domains/retail/capabilities/pedidos"


def test_clientes_only_change_selects_only_clientes():
    assert affected_bundles(["src/enterprise_fabric/retail/clientes/silver.py"]) == [CLIENTES]


def test_pedidos_only_change_selects_only_pedidos():
    assert affected_bundles(["domains/retail/capabilities/pedidos/specs/jobs.yml"]) == [PEDIDOS]


def test_shared_generator_change_selects_every_capability():
    assert affected_bundles(["tools/bundle_generator/generator.py"]) == [CLIENTES, PEDIDOS]


def test_docs_only_change_selects_no_capability():
    assert affected_bundles(["docs/architecture/overview.md"]) == []


def test_removed_bundle_does_not_disappear_silently():
    with pytest.raises(ValueError, match="sin Bundle actual"):
        affected_bundles(["domains/retail/capabilities/retirada/databricks.yml"])
