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
    # Order exists globally in pedidos_curated, but in a DIFFERENT batch (2026-08-19).
    # Devolución belongs to 2026-08-20. This discriminates global existence from batch existence.
    prepared = prepare(spark.createDataFrame([_devolucion(pedido_id="PED-OTHER-BATCH")]))
    pedidos_curated = spark.createDataFrame(
        [Row(pedido_id="PED-OTHER-BATCH", _source_batch_id="2026-08-19")]
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
            # Metrics and quarantine must have been persisted, and curated strictly PROHIBITED
            target_tables = [call.args[1] for call in mock_replace.call_args_list]
            assert "sbx.silver.devoluciones_quality_metrics" in target_tables
            assert "sbx.silver.devoluciones_quarantine" in target_tables
            assert "sbx.silver.devoluciones_curated" not in target_tables
            assert mock_replace.call_count == 2


def test_silver_real_delta_fail_persists_evidence_and_prohibits_curated(spark):
    spark.sql("CREATE SCHEMA IF NOT EXISTS spark_catalog.bronze")
    spark.sql("CREATE SCHEMA IF NOT EXISTS spark_catalog.silver")
    for tbl in (
        "bronze.devoluciones_raw",
        "silver.pedidos_curated",
        "silver.devoluciones_curated",
        "silver.devoluciones_quarantine",
        "silver.devoluciones_quality_metrics",
    ):
        spark.sql(f"DROP TABLE IF EXISTS spark_catalog.{tbl}")

    raw = spark.createDataFrame([_devolucion(estado="INVALID_STATE")])
    raw.write.format("delta").mode("overwrite").saveAsTable("spark_catalog.bronze.devoluciones_raw")

    pedidos = spark.createDataFrame([Row(pedido_id="PED-D15-001", _source_batch_id="2026-08-20")])
    pedidos.write.format("delta").mode("overwrite").saveAsTable(
        "spark_catalog.silver.pedidos_curated"
    )

    with pytest.raises(QualityGateError, match="mandatory devoluciones checks"):
        publish_silver(spark, "spark_catalog", "2026-08-20", "q-run-fail")

    # Metrics and quarantine persisted
    metrics = spark.table("spark_catalog.silver.devoluciones_quality_metrics")
    quarantine = spark.table("spark_catalog.silver.devoluciones_quarantine")
    assert metrics.where("quality_run_id = 'q-run-fail' AND action = 'FAIL'").count() >= 1
    assert quarantine.where("_quality_run_id = 'q-run-fail'").count() == 1

    # Curated MUST NOT be created or published
    curated_exists = spark.catalog.tableExists("spark_catalog.silver.devoluciones_curated")
    assert (
        not curated_exists or spark.table("spark_catalog.silver.devoluciones_curated").count() == 0
    )


def test_silver_real_delta_idempotence_and_preservation_across_runs(spark):
    spark.sql("CREATE SCHEMA IF NOT EXISTS spark_catalog.bronze")
    spark.sql("CREATE SCHEMA IF NOT EXISTS spark_catalog.silver")
    for tbl in (
        "bronze.devoluciones_raw",
        "silver.pedidos_curated",
        "silver.devoluciones_curated",
        "silver.devoluciones_quarantine",
        "silver.devoluciones_quality_metrics",
    ):
        spark.sql(f"DROP TABLE IF EXISTS spark_catalog.{tbl}")

    # Seed Bronze with batch 2026-08-20 and 2026-08-22
    b1_records = [
        _devolucion(
            devolucion_id="DEV-D15-001",
            pedido_id="PED-D15-001",
            _ingestion_batch_id="2026-08-20",
            _record_hash="1" * 64,
        ),
        _devolucion(
            devolucion_id="DEV-D15-002",
            pedido_id="PED-D15-002",
            moneda="EUR",  # Goes to quarantine
            _ingestion_batch_id="2026-08-20",
            _record_hash="2" * 64,
        ),
    ]
    b2_records = [
        _devolucion(
            devolucion_id="DEV-D15-003",
            pedido_id="PED-D15-003",
            _ingestion_batch_id="2026-08-22",
            _record_hash="3" * 64,
        ),
    ]
    raw_df = spark.createDataFrame(b1_records + b2_records)
    raw_df.write.format("delta").mode("overwrite").saveAsTable(
        "spark_catalog.bronze.devoluciones_raw"
    )

    pedidos_df = spark.createDataFrame(
        [
            Row(pedido_id="PED-D15-001", _source_batch_id="2026-08-20"),
            Row(pedido_id="PED-D15-002", _source_batch_id="2026-08-20"),
            Row(pedido_id="PED-D15-003", _source_batch_id="2026-08-22"),
        ]
    )
    pedidos_df.write.format("delta").mode("overwrite").saveAsTable(
        "spark_catalog.silver.pedidos_curated"
    )

    # Run 1 for 2026-08-20
    res_b1_r1 = publish_silver(spark, "spark_catalog", "2026-08-20", "q-run-b1-1")
    assert res_b1_r1.curated_count == 1
    assert res_b1_r1.quarantined_count == 1

    # Run 1 for 2026-08-22 (concurrent/other batch in environment)
    res_b2 = publish_silver(spark, "spark_catalog", "2026-08-22", "q-run-b2")
    assert res_b2.curated_count == 1

    # Capture state of batch 2026-08-22 before re-run
    curated_tbl = spark.table("spark_catalog.silver.devoluciones_curated")
    b2_curated_before = (
        curated_tbl.where("_source_batch_id = '2026-08-22'")
        .select("devolucion_id", "_quality_run_id", "_curated_at_utc")
        .collect()
    )

    # Re-run 2026-08-20 with new quality_run_id
    res_b1_r2 = publish_silver(spark, "spark_catalog", "2026-08-20", "q-run-b1-2")
    assert res_b1_r2.curated_count == 1
    assert res_b1_r2.quarantined_count == 1

    # Assertions on post-re-run state:
    # 1. Batch 2026-08-22 is completely preserved and untouched
    b2_curated_after = (
        curated_tbl.where("_source_batch_id = '2026-08-22'")
        .select("devolucion_id", "_quality_run_id", "_curated_at_utc")
        .collect()
    )
    assert b2_curated_before == b2_curated_after

    # 2. Batch 2026-08-20 in curated: count not doubled, stable deduplication
    b1_curated = curated_tbl.where("_source_batch_id = '2026-08-20'").collect()
    assert len(b1_curated) == 1
    assert b1_curated[0]["devolucion_id"] == "DEV-D15-001"
    assert b1_curated[0]["_quality_run_id"] == "q-run-b1-2"
    assert b1_curated[0]["_curated_at_utc"] is not None

    # 3. Both quality runs are preserved in metrics (isolated by quality_run_id)
    metrics_tbl = spark.table("spark_catalog.silver.devoluciones_quality_metrics")
    b1_run1_metrics = metrics_tbl.where("quality_run_id = 'q-run-b1-1'").count()
    b1_run2_metrics = metrics_tbl.where("quality_run_id = 'q-run-b1-2'").count()
    b2_metrics = metrics_tbl.where("quality_run_id = 'q-run-b2'").count()
    assert b1_run1_metrics > 0
    assert b1_run2_metrics > 0
    assert b2_metrics > 0

    # 4. Both quality runs are preserved in quarantine
    quarantine_tbl = spark.table("spark_catalog.silver.devoluciones_quarantine")
    assert quarantine_tbl.where("_quality_run_id = 'q-run-b1-1'").count() == 1
    assert quarantine_tbl.where("_quality_run_id = 'q-run-b1-2'").count() == 1


def test_spec_and_bundle_generator_match():
    from pathlib import Path

    from tools.bundle_generator.generator import load_yaml, validate_spec

    root = Path(__file__).resolve().parents[3]
    spec_path = root / "domains/retail/capabilities/devoluciones/specs/jobs.yml"
    spec = load_yaml(spec_path)
    validate_spec(spec, spec_path)
    assert spec["metadata"]["capability"] == "devoluciones"
    assert spec["jobs"][0]["key"] == "devoluciones_pipeline_job"
