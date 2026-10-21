import re
from pathlib import Path

import pytest
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


MANDATORY_FIELD_PATTERNS = (
    ("Capability afectada", r"Capability[ \t]+afectada"),
    ("Technical Owner", r"Technical[ \t]+Owner"),
    ("Data Owner", r"Data[ \t]+Owner"),
    ("Fecha efectiva", r"(?:Fecha[ \t]+efectiva(?:[ \t]+del[ \t]+cambio)?|Fecha[ \t]+de[ \t]+retiro)"),
    ("Activo de reemplazo", r"(?:Activo[ \t]+de[ \t]+reemplazo(?:[ \t]+propuesto)?|Reemplazo)"),
    ("Política de retención", r"Pol[íi]tica[ \t]+de[ \t]+retenci[óo]n(?:[ \t]+aplicable)?"),
)


def is_deprecation_checklist_complete(checklist_text: str) -> bool:
    """Validates that all required fields and confirmations are present
    in a deprecation checklist.
    """
    required_sections = (
        "## 1. Identidad",
        "## 2. Consumidores",
        "## 3. Controles Operativos",
        "## 4. Datos",
        "## 5. Cierre",
    )
    for section in required_sections:
        if section not in checklist_text:
            return False

    # Check that there are checkboxes and NO checkbox is left unchecked
    if "[ ]" in checklist_text:
        return False
    if "[x]" not in checklist_text and "[X]" not in checklist_text:
        return False

    # Prohibit placeholder patterns like <...>
    placeholder_pattern = re.compile(r"<[^>]+>")
    if placeholder_pattern.search(checklist_text):
        return False

    # Mandatory fields must be present and each must have a non-empty value on its line
    for _, key_pattern in MANDATORY_FIELD_PATTERNS:
        line_pattern = re.compile(
            rf"^[ \t]*[-*]?[ \t]*{key_pattern}[ \t]*:[ \t]*(?P<val>[^\r\n]*)$",
            re.IGNORECASE | re.MULTILINE,
        )
        matches = list(line_pattern.finditer(checklist_text))
        if not matches:
            return False
        if not all(m.group("val").strip() for m in matches):
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


SYNTHETIC_COMPLETE_CHECKLIST = """
# Checklist de deprecación sintético completo

## 1. Identidad del Activo
- Capability afectada: synthetic_capability
- Tablas y recursos gobernados involucrados: retail_sbx_a001.silver.synthetic_table
- Jobs y workflows asociados: synthetic_job
- Technical Owner: synthetic_tech_owner
- Data Owner: synthetic_data_owner
- Estado actual: active
- Estado propuesto: deprecated
- Fecha efectiva del cambio: 2026-11-01
- Activo de reemplazo propuesto: retail_sbx_a001.silver.synthetic_replacement
- Política de retención aplicable: POL-RET-SYNTHETIC-30D
- Release / commit Git: abc1234

## 2. Consumidores y Dependencias Downstream
- [x] Lineage verificado
- [x] Consumidores notificados
- [x] Activo de reemplazo validado: retail_sbx_a001.silver.synthetic_replacement

## 3. Controles Operativos
- [x] Schedule pausado
- [x] Alertas actualizadas
- [x] Preservación de batches previa

## 4. Datos y Políticas de Retención
- [x] Política de retención formalizada: POL-RET-SYNTHETIC-30D
- [x] Tipo de almacenamiento verificado
- [x] Prohibición de borrado prematuro

## 5. Cierre y Aprobación
- [x] Bloqueo de acceso configurado
- [x] Evidencia de auditoría archivada
- [x] Aprobación formal registrada
"""

MANDATORY_DEPRECATION_FIELD_LINES = (
    ("Capability afectada", "- Capability afectada: synthetic_capability"),
    ("Technical Owner", "- Technical Owner: synthetic_tech_owner"),
    ("Data Owner", "- Data Owner: synthetic_data_owner"),
    ("Fecha efectiva", "- Fecha efectiva del cambio: 2026-11-01"),
    ("Activo de reemplazo", "- Activo de reemplazo propuesto: retail_sbx_a001.silver.synthetic_replacement"),
    ("Política de retención", "- Política de retención aplicable: POL-RET-SYNTHETIC-30D"),
)


@pytest.mark.parametrize("field_name,line", MANDATORY_DEPRECATION_FIELD_LINES)
def test_deprecation_checklist_rejects_each_missing_field(field_name, line):
    checklist = SYNTHETIC_COMPLETE_CHECKLIST.replace(line + "\n", "")
    assert is_deprecation_checklist_complete(checklist) is False


@pytest.mark.parametrize("field_name,line", MANDATORY_DEPRECATION_FIELD_LINES)
def test_deprecation_checklist_rejects_each_empty_field(field_name, line):
    prefix = line.split(":")[0] + ":"
    checklist = SYNTHETIC_COMPLETE_CHECKLIST.replace(line, prefix)
    assert is_deprecation_checklist_complete(checklist) is False


@pytest.mark.parametrize("field_name,line", MANDATORY_DEPRECATION_FIELD_LINES)
def test_deprecation_checklist_rejects_each_whitespace_field(field_name, line):
    prefix = line.split(":")[0] + ":    "
    checklist = SYNTHETIC_COMPLETE_CHECKLIST.replace(line, prefix)
    assert is_deprecation_checklist_complete(checklist) is False


def test_synthetic_complete_deprecation_checklist_is_accepted():
    assert is_deprecation_checklist_complete(SYNTHETIC_COMPLETE_CHECKLIST) is True


def test_deprecation_checklist_rejects_missing_owner():
    # Starting from valid synthetic checklist, removing Technical Owner
    sample = """
    ## 1. Identidad
    - Capability afectada: synthetic_capability
    - Data Owner: synthetic_data_owner
    - Fecha efectiva: 2026-11-01
    - Activo de reemplazo: replacement_table
    - Política de retención: POL-RET-01
    ## 2. Consumidores
    - [x] Consumidores confirmados
    ## 3. Controles Operativos
    - [x] Operación verificada
    ## 4. Datos
    - [x] Datos verificados
    ## 5. Cierre
    - [x] Cierre aprobado
    """
    assert is_deprecation_checklist_complete(sample) is False


def test_deprecation_checklist_rejects_missing_consumer_or_replacement():
    sample = """
    ## 1. Identidad
    - Capability afectada: synthetic_capability
    - Technical Owner: tech_owner
    - Data Owner: data_owner
    - Fecha efectiva: 2026-11-01
    - Política de retención: POL-RET-01
    ## 2. Consumidores
    - [x] Lineage consultado
    ## 3. Controles Operativos
    - [x] Operación verificada
    ## 4. Datos
    - [x] Datos verificados
    ## 5. Cierre
    - [x] Cierre aprobado
    """
    assert is_deprecation_checklist_complete(sample) is False


def test_deprecation_checklist_rejects_missing_retention_policy():
    sample = """
    ## 1. Identidad
    - Capability afectada: synthetic_capability
    - Technical Owner: tech_owner
    - Data Owner: data_owner
    - Fecha efectiva: 2026-11-01
    - Activo de reemplazo: replacement_table
    ## 2. Consumidores
    - [x] Consumidores confirmados
    ## 3. Controles Operativos
    - [x] Operación verificada
    ## 4. Datos
    - [x] Datos verificados
    ## 5. Cierre
    - [x] Cierre aprobado
    """
    assert is_deprecation_checklist_complete(sample) is False


def test_deprecation_checklist_rejects_missing_effective_date():
    sample = """
    ## 1. Identidad
    - Capability afectada: synthetic_capability
    - Technical Owner: tech_owner
    - Data Owner: data_owner
    - Activo de reemplazo: replacement_table
    - Política de retención: POL-RET-01
    ## 2. Consumidores
    - [x] Consumidores confirmados
    ## 3. Controles Operativos
    - [x] Operación verificada
    ## 4. Datos
    - [x] Datos verificados
    ## 5. Cierre
    - [x] Cierre aprobado
    """
    assert is_deprecation_checklist_complete(sample) is False


def test_deprecation_checklist_rejects_partially_marked_counterexample():
    # Codex counterexample: 1 checkbox checked, remaining unchecked
    counterexample = read(ROOT / "docs/operations/deprecation-checklist.md")
    counterexample = counterexample.replace(
        "- [ ] Lineage de Unity Catalog consultado y verificado (adjuntar timestamp y consulta).",
        "- [x] Lineage de Unity Catalog consultado y verificado (adjuntar timestamp y consulta).",
        1,
    )
    assert is_deprecation_checklist_complete(counterexample) is False


def test_lab_deprecation_checklist_instance_remains_incomplete():
    instance_path = ROOT / "docs/operations/deprecation-checklist-clientes-governance-lab.md"
    assert instance_path.exists()
    text = read(instance_path)
    assert "retail_sbx_a001.silver.clientes_governance_lab" in text
    assert "bcastillo@techdic.onmicrosoft.com" in text or "becavas" in text
    assert "retail_sbx_a001.silver.clientes_curated" in text
    assert "2026-11-20" in text
    # The lab instance has explicit pending items and must NOT be marked complete
    assert is_deprecation_checklist_complete(text) is False
