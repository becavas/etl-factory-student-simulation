from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from pyspark.sql import Row

from enterprise_fabric.retail.devoluciones.silver import (
    QualityGateError,
    build_metrics,
    deduplicate,
    detect_conflicts,
    evaluate,
    prepare,
    publish_silver,
)

COVERED_GUARANTEES = {
    "DEV-003",
    "DEV-004",
    "DEV-005",
    "DEV-006",
    "DEV-007",
    "DEV-008",
    "DEV-009",
    "DEV-010",
}


def _metadata() -> dict[str, object]:
    return {
        "_source_system": "devoluciones_source",
        "_source_file_path": "/Volumes/retail_sbx_a001/landing/devoluciones.csv",
        "_source_file_modification_time": datetime(2026, 8, 20, 10, 0, 0, tzinfo=UTC),
        "_ingestion_batch_id": "2026-08-20",
        "_ingestion_run_id": "bronze-run-1",
        "_ingested_at_utc": datetime(2026, 8, 20, 10, 0, 0, tzinfo=UTC),
        "_record_hash": "a" * 64,
    }


def _devolucion(**overrides: object) -> dict[str, object]:
    row = {
        "devolucion_id": "DEV-LAB-001",
        "pedido_id": "PED-D15-001",
        "producto_id": "PROD-D15-001",
        "fecha_devolucion": "2026-08-20",
        "motivo": "Motivo sintetico de devolucion",
        "estado": "APROBADA",
        "importe_reembolsado": "15.50",
        "moneda": "PEN",
        "updated_at": "2026-08-20T10:00:00Z",
        **_metadata(),
    }
    row.update(overrides)
    return row


def test_prepare_normalizes_strings_and_parses_types(spark):
    raw = spark.createDataFrame([_devolucion()])
    prepared = prepare(raw)
    row = prepared.first()
    assert row["devolucion_id"] == "DEV-LAB-001"
    assert row["fecha_devolucion"] == date(2026, 8, 20)
    assert row["importe_reembolsado"] == Decimal("15.50")
    assert row["moneda"] == "PEN"
    assert row["updated_at"] is not None
    assert row["_raw_payload"] is not None


def test_deduplicate_keeps_highest_updated_at(spark):
    rows = [
        _devolucion(
            updated_at="2026-08-20T09:00:00Z",
            importe_reembolsado="10.00",
            _record_hash="1" * 64,
        ),
        _devolucion(
            updated_at="2026-08-20T11:00:00Z",
            importe_reembolsado="20.00",
            _record_hash="2" * 64,
        ),
    ]
    prepared = prepare(spark.createDataFrame(rows))
    dedup, duplicate_count = deduplicate(prepared)
    assert duplicate_count == 1
    assert dedup.count() == 1
    selected = dedup.first()
    assert selected["importe_reembolsado"] == Decimal("20.00")


def test_tie_conflict_detection_flags_differing_payloads_at_same_max_ts(spark):
    rows = [
        _devolucion(
            updated_at="2026-08-20T10:00:00Z",
            importe_reembolsado="10.00",
            _record_hash="1" * 64,
        ),
        _devolucion(
            updated_at="2026-08-20T10:00:00Z",
            importe_reembolsado="20.00",
            _record_hash="2" * 64,
        ),
    ]
    prepared = prepare(spark.createDataFrame(rows))
    conflicts = detect_conflicts(prepared)
    assert conflicts.count() == 1

    dedup, dup_count = deduplicate(prepared)
    checked, evaluated, fail_count = evaluate(dedup)
    assert evaluated["devolucion_tie_conflict"] == 1
    assert fail_count >= 1
    assert "devolucion_tie_conflict" in checked.first()["_quality_rule_ids"]


def test_identical_payload_at_same_timestamp_does_not_conflict(spark):
    rows = [
        _devolucion(
            updated_at="2026-08-20T10:00:00Z",
            importe_reembolsado="10.00",
            _record_hash="same_hash_64" + "0" * 52,
        ),
        _devolucion(
            updated_at="2026-08-20T10:00:00Z",
            importe_reembolsado="10.00",
            _record_hash="same_hash_64" + "0" * 52,
        ),
    ]
    prepared = prepare(spark.createDataFrame(rows))
    conflicts = detect_conflicts(prepared)
    assert conflicts.count() == 0


@pytest.mark.parametrize(
    ("override", "rule_id"),
    [
        ({"fecha_devolucion": "not-a-date"}, "devolucion_fecha_valid"),
        ({"motivo": "   "}, "devolucion_motivo_required"),
        ({"importe_reembolsado": "-5.00"}, "devolucion_importe_valid"),
        ({"moneda": "USD"}, "devolucion_moneda_valid"),
    ],
)
def test_quarantine_rules_do_not_increment_fail_count(spark, override, rule_id):
    prepared = prepare(spark.createDataFrame([_devolucion(**override)]))
    checked, evaluated, fail_count = evaluate(prepared)
    assert evaluated[rule_id] == 1
    assert fail_count == 0
    assert rule_id in checked.first()["_quality_rule_ids"]


@pytest.mark.parametrize(
    ("override", "rule_id"),
    [
        ({"devolucion_id": "  "}, "devolucion_id_required"),
        ({"producto_id": "   "}, "devolucion_producto_required"),
        ({"estado": "REEMBOLSADA"}, "devolucion_estado_valid"),
        ({"estado": "UNKNOWN"}, "devolucion_estado_valid"),
        ({"updated_at": "invalid-ts"}, "devolucion_updated_at_valid"),
    ],
)
def test_fail_rules_increment_fail_count(spark, override, rule_id):
    prepared = prepare(spark.createDataFrame([_devolucion(**override)]))
    checked, evaluated, fail_count = evaluate(prepared)
    assert evaluated[rule_id] == 1
    assert fail_count >= 1
    assert rule_id in checked.first()["_fail_rule_ids"]


def test_referential_integrity_requires_existing_pedido_in_same_batch(spark):
    prepared = prepare(spark.createDataFrame([_devolucion(pedido_id="PED-UNKNOWN")]))
    pedidos_curated = spark.createDataFrame(
        [Row(pedido_id="PED-D15-001", _source_batch_id="2026-08-20")]
    )
    checked, evaluated, fail_count = evaluate(prepared, pedidos_curated, "2026-08-20")
    assert evaluated["devolucion_pedido_exists"] == 1
    assert fail_count >= 1
    assert "devolucion_pedido_exists" in checked.first()["_fail_rule_ids"]


def test_referential_integrity_passes_when_pedido_exists_in_same_batch(spark):
    prepared = prepare(spark.createDataFrame([_devolucion(pedido_id="PED-D15-001")]))
    pedidos_curated = spark.createDataFrame(
        [Row(pedido_id="PED-D15-001", _source_batch_id="2026-08-20")]
    )
    checked, evaluated, fail_count = evaluate(prepared, pedidos_curated, "2026-08-20")
    assert evaluated["devolucion_pedido_exists"] == 0
    assert fail_count == 0


def test_motivo_privacy_is_preserved_without_leakage_in_metrics_or_errors(spark):
    secret_motivo = "CONFIDENTIAL_RETURN_REASON_XYZ"
    prepared = prepare(spark.createDataFrame([_devolucion(motivo=secret_motivo)]))
    checked, evaluated, fail_count = evaluate(prepared)
    metrics = build_metrics(
        spark,
        quality_run_id="q-run-1",
        batch_id="2026-08-20",
        total=1,
        duplicate_count=0,
        evaluated=evaluated,
    )
    metric_rows = metrics.collect()
    for row in metric_rows:
        for field in ("rule_id", "action", "entity", "batch_id", "quality_run_id"):
            assert secret_motivo not in str(row[field])


def test_quality_metrics_and_quarantine_preserve_batch_and_quality_run(spark):
    prepared = prepare(spark.createDataFrame([_devolucion(moneda="EUR")]))
    checked, evaluated, _ = evaluate(prepared)
    metrics = build_metrics(
        spark,
        quality_run_id="q-run-123",
        batch_id="2026-08-20",
        total=1,
        duplicate_count=0,
        evaluated=evaluated,
    )
    metric = metrics.where("rule_id = 'devolucion_moneda_valid'").first()
    assert metric["quality_run_id"] == "q-run-123"
    assert metric["batch_id"] == "2026-08-20"
    assert metric["failed_records"] == 1
    assert metric["action"] == "QUARANTINE"


def test_publish_silver_raises_quality_gate_error_on_failure(spark):
    raw = spark.createDataFrame([_devolucion(estado="INVALID_STATE")])
    pedidos = spark.createDataFrame([Row(pedido_id="PED-D15-001", _source_batch_id="2026-08-20")])
    mock_tables = {
        "sbx.bronze.devoluciones_raw": raw,
        "sbx.silver.pedidos_curated": pedidos,
    }
    with patch.object(spark, "table", side_effect=lambda name: mock_tables[name]):
        with patch(
            "enterprise_fabric.retail.devoluciones.silver.replace_where_value"
        ) as mock_replace:
            with pytest.raises(QualityGateError, match="mandatory devoluciones checks"):
                publish_silver(spark, "sbx", "2026-08-20", "q-run-fail")
            # Metrics and quarantine should have been persisted before raising
            assert mock_replace.call_count >= 2


def test_spec_and_bundle_generator_match():
    from pathlib import Path

    from tools.bundle_generator.generator import load_yaml, validate_spec

    root = Path(__file__).resolve().parents[3]
    spec_path = root / "domains/retail/capabilities/devoluciones/specs/jobs.yml"
    spec = load_yaml(spec_path)
    validate_spec(spec, spec_path)
    assert spec["metadata"]["capability"] == "devoluciones"
    assert spec["jobs"][0]["key"] == "devoluciones_pipeline_job"
