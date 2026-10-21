import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CAPABILITIES_ROOT = ROOT / "domains/retail/capabilities"
REQUIRED_HEADINGS = (
    "## Propósito",
    "## Ownership",
    "## Clasificación y acceso",
    "## Entradas",
    "## Salidas y grano",
    "## Garantías verificables",
    "## Operación",
    "## Lifecycle",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def capabilities() -> list[str]:
    return sorted(path.name for path in CAPABILITIES_ROOT.iterdir() if path.is_dir())


def test_every_reference_capability_has_one_complete_readme():
    discovered = capabilities()
    assert {"pedidos", "clientes", "productos", "ventas"}.issubset(discovered)
    for capability in discovered:
        root = CAPABILITIES_ROOT / capability
        readmes = list(root.rglob("README.md"))
        assert readmes == [root / "README.md"]
        text = read(readmes[0])
        for heading in REQUIRED_HEADINGS:
            assert heading in text, f"{capability}: missing {heading}"
        placeholder = re.compile(
            r"<(?:[^>]*(?:owner|grupo|equipo|organizacion|canal)[^>]*)>",
            re.IGNORECASE,
        )
        assert not placeholder.search(text), f"{capability}: contains unallowed placeholder"
        assert "specs/jobs.yml" in text


def test_codeowners_covers_governance_and_capability_surfaces():
    text = read(ROOT / ".github/CODEOWNERS")
    assert "@ORG/" not in text and "@empresa/" not in text
    for required in (
        "/.github/",
        "/docs/standards/",
        "/ops/governance/",
        "/tools/bundle_generator/",
    ):
        assert required in text
    for capability in capabilities():
        assert f"/domains/retail/capabilities/{capability}/" in text
        assert f"/src/enterprise_fabric/retail/{capability}/" in text
        assert f"/tests/retail/{capability}/" in text


def test_reusable_component_inventory_covers_all_three_categories():
    text = read(ROOT / "docs/architecture/reusable-components.md")
    for component in (
        "tools/bundle_generator/",
        "src/enterprise_fabric/shared/",
        "scripts/affected_bundles.py",
        "scripts/inspect_wheel.py",
        "scripts/write_deployment_record.py",
        "scripts/write_promotion_record.py",
        "scripts/verify_release_publication.py",
    ):
        assert component in text
    assert "runtime compartido" in text
    assert "tooling de desarrollo" in text
    assert "controles de entrega" in text


def test_metadata_script_cannot_administer_infrastructure_or_grants():
    text = read(ROOT / "ops/governance/sandbox_metadata.sql").upper()
    forbidden = (
        "CREATE CATALOG",
        "CREATE SCHEMA",
        "CREATE TAG",
        "GRANT ",
        "REVOKE ",
        "ALTER OWNER",
        "DROP ",
        "VACUUM ",
    )
    assert not any(statement in text for statement in forbidden)
    assert "CLIENTES_GOVERNANCE_LAB" in text
    assert "SET TAGS" in text
    assert "COMMENT" in text


def test_excessive_prod_grant_fixture_is_detected():
    fixture = yaml.safe_load(read(ROOT / "tests/governance/fixtures/excessive_grants.yml"))
    violations = [
        grant
        for grant in fixture["grants"]
        if grant["environment"] == "prod"
        and grant["principal_type"] == "user"
        and grant["privilege"] in {"MODIFY", "MANAGE", "ALL PRIVILEGES"}
    ]
    assert violations == fixture["grants"]


def is_deprecation_checklist_complete(checklist_text: str) -> bool:
    """Validates that all required fields and confirmations are present
    in a deprecation checklist.
    """
    required_sections = (
        "## 1. Identidad",
        "## 2. Consumidores",
        "## 3. Controles Operativos",
        "## 4. Datos y Políticas de Retención",
        "## 5. Cierre y Aprobación",
    )
    for section in required_sections:
        if section not in checklist_text:
            return False

    required_keywords = (
        "Technical Owner",
        "Data Owner",
        "Lineage",
        "reemplazo",
        "retención",
    )
    for kw in required_keywords:
        if kw.lower() not in checklist_text.lower():
            return False

    # Prohibit unfulfilled/blank placeholders in essential fields
    blank_field_pattern = re.compile(
        r"(?:Capability afectada|Technical Owner|Data Owner|Estado propuesto):\s*$",
        re.MULTILINE,
    )
    if blank_field_pattern.search(checklist_text):
        return False

    # Verify that checkboxes are not all unchecked if claiming completion
    if "[ ]" in checklist_text and "[x]" not in checklist_text:
        return False

    return True


def test_deprecation_checklist_structure():
    checklist_path = ROOT / "docs/operations/deprecation-checklist.md"
    assert checklist_path.exists()
    text = read(checklist_path)
    assert "## 1. Identidad" in text
    assert "## 2. Consumidores" in text
    assert "## 3. Controles Operativos" in text
    assert "## 4. Datos y Políticas de Retención" in text
    assert "## 5. Cierre y Aprobación" in text
    assert "DROP TABLE" in text
    assert "VACUUM" in text


def test_deprecation_checklist_rejects_missing_mandatory_fields():
    # Checklist template with pending unchecked items cannot be declared complete
    template_text = read(ROOT / "docs/operations/deprecation-checklist.md")
    assert not is_deprecation_checklist_complete(template_text)

    # Checklist missing owner or retention policy cannot be declared complete
    incomplete_sample = """
    ## 1. Identidad
    Capability afectada: clientes
    ## 2. Consumidores
    Lineage: verificado
    ## 3. Controles Operativos
    [x] Schedule pausado
    ## 5. Cierre y Aprobación
    [x] Cierre
    """
    assert not is_deprecation_checklist_complete(incomplete_sample)
