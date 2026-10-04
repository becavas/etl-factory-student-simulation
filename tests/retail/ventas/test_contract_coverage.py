"""Contract coverage verification for retail/ventas guarantees."""

import re
from pathlib import Path

COVERED_GUARANTEES = {
    "VEN-IN-001",  # Verified in publish_dimensions & prepare_fact input empty checks
    "VEN-IN-002",  # Verified by test_assert_unique_raises_on_duplicates
    "VEN-DI-001",  # Verified by test_canonical_json_avoids_delimiter_ambiguity
    "VEN-DI-002",  # Verified by test_prepare_clientes_filters_batch_and_minimizes_pii
    "VEN-DI-003",  # Verified by test_dimension_type1_merge_idempotence_and_attribute_update
    "VEN-DI-004",  # Verified by test_snapshot_mode_full_deactivates_absent_and_protects_unknown
    "VEN-FA-001",  # Verified by test_prepare_fact_assigns_unknown_sk_when_dimension_missing
    "VEN-FA-002",  # Verified by test_reconcile_orders_succeeds_on_matching_totals
    "VEN-FA-003",  # Verified by test_prepare_fact_assigns_unknown_sk_when_dimension_missing
    "VEN-FA-004",  # Verified by test_merge_inserts_updates_and_is_idempotent
    "VEN-FA-005",  # Verified by test_merge_preserves_omitted_fact_and_handles_cancellation
    "VEN-MG-001",  # Verified by test_merge_inserts_updates_and_is_idempotent
    "VEN-CO-001",  # Verified by bundle spec validation (shared compute for tasks)
    "VEN-KPI-001",  # Verified by test_formula_excludes_cancelled_lines_and_reconciles
    "VEN-KPI-002",  # Verified by test_two_channels_produce_two_rows_in_grain & assert_unique_grain
    "VEN-KPI-003",  # Verified by test_rejects_second_eligible_currency
    "VEN-KPI-004",  # Verified by test_assert_reconciled_accepts_one_cent_and_rejects_two_cents
    "VEN-KPI-005",  # Verified by test_publication_replaces_complete_affected_date
    "VEN-KPI-006",  # Verified by task execution timing analysis in job run
    "VEN-KPI-007",  # Verified by test_runtime_and_semantic_contract_do_not_drift
}

README = Path(__file__).parents[3] / "domains" / "retail" / "capabilities" / "ventas" / "README.md"


def documented_guarantees() -> list[str]:
    text = README.read_text(encoding="utf-8")
    start = text.index("<!-- guarantees:start -->")
    end = text.index("<!-- guarantees:end -->")
    return re.findall(r"`(VEN-[A-Z0-9]+-[0-9]{3})`", text[start:end])


def test_every_documented_guarantee_has_declared_test_coverage():
    documented = documented_guarantees()
    assert len(documented) == len(set(documented)), "duplicate guarantee IDs"
    assert len(documented) == 20
    assert set(documented) == COVERED_GUARANTEES
