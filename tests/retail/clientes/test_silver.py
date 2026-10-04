from datetime import UTC, datetime

import pytest

from enterprise_fabric.retail.clientes.silver import (
    build_metrics,
    deduplicate,
    evaluate,
    prepare,
)

COVERED_GUARANTEES = {
    "CLI-003",
    "CLI-004",
    "CLI-005",
    "CLI-006",
    "CLI-007",
    "CLI-008",
}


def _metadata() -> dict[str, object]:
    return {
        "_source_system": "clientes_source",
        "_source_file_path": "/Volumes/test/clientes.csv",
        "_source_file_modification_time": datetime(2026, 1, 1, tzinfo=UTC),
        "_ingestion_batch_id": "test_batch",
        "_ingestion_run_id": "bronze-run-1",
        "_ingested_at_utc": datetime(2026, 1, 1, tzinfo=UTC),
        "_record_hash": "a" * 64,
    }


def _cliente(**overrides: object) -> dict[str, object]:
    row = {
        "cliente_id": "CLI-001",
        "nombres": " Ana ",
        "apellidos": " Paredes ",
        "email": " ANA@EXAMPLE.TEST ",
        "fecha_nacimiento": "1990-04-17",
        "pais_codigo": " pe ",
        "estado": " activo ",
        "fecha_actualizacion": "2026-01-01T10:00:00Z",
        **_metadata(),
    }
    row.update(overrides)
    return row


def test_normalizes_and_types_valid_cliente(spark):
    prepared = prepare(spark.createDataFrame([_cliente()]))
    row = prepared.first()
    assert row["email"] == "ana@example.test"
    assert row["pais_codigo"] == "PE"
    assert row["estado"] == "ACTIVO"
    assert str(row["fecha_nacimiento"]) == "1990-04-17"


def test_deduplication_keeps_latest_source_record(spark):
    older = _cliente()
    newer = _cliente(
        fecha_actualizacion="2026-01-01T11:00:00Z",
        estado="inactivo",
        _record_hash="b" * 64,
    )
    deduplicated, duplicate_count = deduplicate(prepare(spark.createDataFrame([older, newer])))
    assert duplicate_count == 1
    assert deduplicated.first()["estado"] == "INACTIVO"


@pytest.mark.parametrize(
    ("override", "rule_id", "expected_fail"),
    [
        ({"cliente_id": "  "}, "cliente_id_required", 1),
        (
            {"fecha_actualizacion": "invalid"},
            "cliente_updated_at_valid",
            1,
        ),
        ({"email": "invalid"}, "cliente_email_valid", 0),
        ({"fecha_nacimiento": "2999-01-01"}, "cliente_birth_date_valid", 0),
        ({"pais_codigo": "PER"}, "cliente_country_valid", 0),
        ({"estado": "UNKNOWN"}, "cliente_state_valid", 0),
        ({"nombres": "  "}, "cliente_name_required", 0),
    ],
)
def test_each_quality_rule(spark, override, rule_id, expected_fail):
    checked, evaluated, fail_count = evaluate(
        prepare(spark.createDataFrame([_cliente(**override)]))
    )
    assert evaluated[rule_id] == 1
    assert fail_count == expected_fail
    assert rule_id in checked.first()["_quality_rule_ids"]


def test_quality_metrics_and_checked_rows_preserve_run_and_lineage(spark):
    prepared = prepare(spark.createDataFrame([_cliente(email="invalid")]))
    checked, evaluated, _ = evaluate(prepared)
    metrics = build_metrics(
        spark,
        quality_run_id="quality-run-1",
        batch_id="test_batch",
        total=1,
        duplicate_count=0,
        evaluated=evaluated,
    )
    metric = metrics.where("rule_id = 'cliente_email_valid'").first()
    assert metric["quality_run_id"] == "quality-run-1"
    assert metric["batch_id"] == "test_batch"
    assert metric["failed_records"] == 1
    checked_row = checked.first()
    assert checked_row["_ingestion_run_id"] == "bronze-run-1"
    assert checked_row["_source_file_path"].endswith("clientes.csv")
