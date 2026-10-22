import re
from pathlib import Path

import tests.retail.devoluciones.test_bronze as test_bronze
import tests.retail.devoluciones.test_silver as test_silver
from tests.retail.devoluciones.test_bronze import (
    COVERED_GUARANTEES as BRONZE_GUARANTEES,
)
from tests.retail.devoluciones.test_silver import (
    COVERED_GUARANTEES as SILVER_GUARANTEES,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
README = REPO_ROOT / "domains/retail/capabilities/devoluciones/README.md"

GUARANTEE_TEST_MAPPING: dict[str, list[str]] = {
    "DEV-001": [
        "test_read_batch_preserves_source_strings_and_adds_lineage",
        "test_bronze_strict_batch_selection_and_idempotence_with_real_delta",
    ],
    "DEV-002": [
        "test_replace_batch_uses_selective_predicate_and_commit_metadata",
        "test_bronze_strict_batch_selection_and_idempotence_with_real_delta",
        "test_silver_real_delta_idempotence_and_preservation_across_runs",
    ],
    "DEV-003": [
        "test_prepare_normalizes_strings_and_parses_types",
    ],
    "DEV-004": [
        "test_deduplicate_keeps_highest_updated_at",
    ],
    "DEV-005": [
        "test_tie_conflict_detection_flags_differing_payloads_at_same_max_ts",
        "test_identical_payload_at_same_timestamp_does_not_conflict",
    ],
    "DEV-006": [
        "test_quarantine_rules_do_not_increment_fail_count",
    ],
    "DEV-007": [
        "test_fail_rules_increment_fail_count",
        "test_referential_integrity_requires_existing_pedido_in_same_batch",
        "test_referential_integrity_passes_when_pedido_exists_in_same_batch",
        "test_publish_silver_raises_quality_gate_error_on_failure",
        "test_silver_real_delta_fail_persists_evidence_and_prohibits_curated",
    ],
    "DEV-008": [
        "test_motivo_privacy_is_preserved_without_leakage_in_metrics_or_errors",
        "test_malformed_input_preserves_motivo_privacy_across_exception_and_diagnostics",
        "test_missing_header_preserves_motivo_privacy_across_exception_and_diagnostics",
    ],
    "DEV-009": [
        "test_quality_metrics_and_quarantine_preserve_batch_and_quality_run",
        "test_silver_real_delta_idempotence_and_preservation_across_runs",
    ],
    "DEV-010": [
        "test_spec_and_bundle_generator_match",
    ],
}


def documented_guarantees() -> list[str]:
    text = README.read_text(encoding="utf-8")
    start = text.index("<!-- guarantees:start -->")
    end = text.index("<!-- guarantees:end -->")
    return re.findall(r"`(DEV-[0-9]{3})`", text[start:end])


def test_every_documented_guarantee_has_declared_test_coverage():
    documented = documented_guarantees()
    assert len(documented) == len(set(documented)), "duplicate guarantee IDs"
    assert set(documented) == BRONZE_GUARANTEES | SILVER_GUARANTEES


def test_every_guarantee_has_concrete_callable_test_implementations():
    documented = set(documented_guarantees())
    assert set(GUARANTEE_TEST_MAPPING.keys()) == documented

    for guarantee_id, test_func_names in GUARANTEE_TEST_MAPPING.items():
        assert len(test_func_names) > 0, f"No test functions mapped for {guarantee_id}"
        for name in test_func_names:
            func = getattr(test_bronze, name, None) or getattr(test_silver, name, None)
            assert callable(func), f"Mapped test function {name} for {guarantee_id} is not callable"
