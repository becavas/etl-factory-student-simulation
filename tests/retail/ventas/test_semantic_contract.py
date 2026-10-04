"""Test that runtime constants and semantic contract YAML do not drift."""

from decimal import Decimal
from pathlib import Path

import yaml

from enterprise_fabric.retail.ventas.semantic import (
    ABSOLUTE_TOLERANCE,
    MAX_HOURS_AFTER_FACT_SUCCESS,
    METRIC_ID,
    METRIC_VERSION,
    OUTPUT_GRAIN,
    REPORTING_CURRENCY,
)

CONTRACT = (
    Path(__file__).parents[3]
    / "domains"
    / "retail"
    / "capabilities"
    / "ventas"
    / "contracts"
    / "ventas-netas-diarias.yml"
)


def load_contract():
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["metric"]


def test_runtime_and_semantic_contract_do_not_drift():
    metric = load_contract()
    assert metric["id"] == METRIC_ID
    assert metric["version"] == METRIC_VERSION
    assert metric["output"]["grain"] == list(OUTPUT_GRAIN)
    assert metric["formula"] == {
        "aggregation": "sum",
        "measure": "importe_linea",
        "filters": {"is_cancelled": False},
    }
    assert metric["currency"] == {
        "mode": "single",
        "code": REPORTING_CURRENCY,
        "unexpected_value": "fail",
        "conversion": "none",
    }
    assert Decimal(metric["reconciliation"]["absolute_tolerance"]) == ABSOLUTE_TOLERANCE
    assert metric["freshness"]["max_hours_after_fact_success"] == MAX_HOURS_AFTER_FACT_SUCCESS
    assert metric["publication"]["supported_modes"] == ["FULL", "INCREMENTAL"]
    assert metric["compatibility"] == {
        "additive_columns": "backward_compatible_when_nullable",
        "breaking_changes": [
            "rename_or_delete",
            "type_or_grain_change",
            "semantic_change",
        ],
        "migration_pattern": "expand_migrate_retire",
        "rollback_requires": "prior_code_can_read_current_schema",
    }


def test_contract_has_real_owners_and_publication_guarantees():
    metric = load_contract()
    for owner_key in ("business_owner", "technical_owner"):
        owner = metric[owner_key]
        assert owner.strip()
        assert "<" not in owner and ">" not in owner
    assert set(metric["publication"]["requires"]) == {
        "valid_required_fields",
        "expected_currency_only",
        "unique_output_grain",
        "reconciliation_within_tolerance",
    }
