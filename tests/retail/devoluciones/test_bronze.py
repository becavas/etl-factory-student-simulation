import json
from pathlib import Path

import pytest

from enterprise_fabric.retail.devoluciones.bronze import (
    IngestionError,
    ingest_bronze,
    read_batch,
    replace_batch,
    validate_identifier,
)
from enterprise_fabric.retail.devoluciones.schemas import DEVOLUCIONES_SOURCE_COLUMNS

COVERED_GUARANTEES = {"DEV-001", "DEV-002"}


class RecordingWriter:
    def __init__(self):
        self.format_name = None
        self.mode_name = None
        self.options = {}
        self.table_name = None

    def format(self, value):
        self.format_name = value
        return self

    def mode(self, value):
        self.mode_name = value
        return self

    def option(self, key, value):
        self.options[key] = value
        return self

    def saveAsTable(self, value):  # noqa: N802 - mirrors PySpark API
        self.table_name = value


class FrameWithRecordingWriter:
    def __init__(self):
        self.columns = ["_ingestion_batch_id"]
        self.write = RecordingWriter()


def _write_source(path: Path) -> None:
    path.write_text(
        ",".join(DEVOLUCIONES_SOURCE_COLUMNS)
        + "\n"
        + "DEV-LAB-001,PED-D15-001,PROD-D15-001,2026-08-20,"
        + "Motivo sintetico,APROBADA,5.00,PEN,2026-08-20T09:00:00Z\n",
        encoding="utf-8",
    )


def test_read_batch_preserves_source_strings_and_adds_lineage(spark, tmp_path):
    source = tmp_path / "devoluciones.csv"
    _write_source(source)
    row = read_batch(
        spark,
        str(source),
        batch_id="test_batch",
        run_id="run_001",
    ).first()
    assert all(row[column] is not None for column in DEVOLUCIONES_SOURCE_COLUMNS)
    assert row["fecha_devolucion"] == "2026-08-20"
    assert row["motivo"] == "Motivo sintetico"
    assert row["_source_system"] == "devoluciones_source"
    assert row["_source_file_path"].endswith("devoluciones.csv")
    assert row["_ingestion_batch_id"] == "test_batch"
    assert row["batch_id"] == "test_batch"
    assert row["_ingestion_run_id"] == "run_001"
    assert len(row["_record_hash"]) == 64


def test_replace_batch_uses_selective_predicate_and_commit_metadata():
    frame = FrameWithRecordingWriter()
    replace_batch(
        frame,
        "retail_sbx_a001.bronze.devoluciones_raw",
        "test_batch",
        "run_001",
    )
    assert frame.write.format_name == "delta"
    assert frame.write.mode_name == "overwrite"
    assert frame.write.options["replaceWhere"] == ("_ingestion_batch_id = 'test_batch'")
    metadata = json.loads(frame.write.options["userMetadata"])
    assert metadata == {
        "batch_id": "test_batch",
        "capability": "retail/devoluciones",
        "run_id": "run_001",
    }
    assert frame.write.table_name == "retail_sbx_a001.bronze.devoluciones_raw"


@pytest.mark.parametrize("value", ["", "../batch", "batch id", "' OR 1=1"])
def test_identifier_rejects_unsafe_values(value):
    with pytest.raises(ValueError, match="safe identifier"):
        validate_identifier(value, "batch_id")


def test_malformed_input_preserves_motivo_privacy_across_exception_and_diagnostics(
    spark, tmp_path, capfd
):
    spark.sql("CREATE SCHEMA IF NOT EXISTS spark_catalog.bronze")
    spark.sql(
        "CREATE TABLE IF NOT EXISTS spark_catalog.bronze.devoluciones_raw "
        "USING delta AS SELECT 1 WHERE 1=0"
    )
    initial_count = spark.table("spark_catalog.bronze.devoluciones_raw").count()

    synthetic_marker = "SENSITIVE_MOTIVO_PARSE_MARKER_999"
    csv_file = tmp_path / "devoluciones_extra_col.csv"
    csv_file.write_text(
        ",".join(DEVOLUCIONES_SOURCE_COLUMNS)
        + "\n"
        + f"DEV-ERR-001,PED-ERR-001,PROD-ERR-001,2026-08-20,{synthetic_marker},"
        + "APROBADA,10.00,PEN,2026-08-20T10:00:00Z,EXTRA_COLUMN_TRIGGERING_FAIL\n",
        encoding="utf-8",
    )

    # 1. Test read_batch materialization
    df = read_batch(spark, str(csv_file), "batch_err", "run_err")
    with pytest.raises(Exception) as exc_info:
        df.first()

    err_msg = str(exc_info.value)
    assert synthetic_marker not in err_msg, "Sensitive motivo leaked in exception string"
    assert "Malformed CSV record detected" in err_msg

    # 2. Test ingest_bronze route
    batch_dir = tmp_path / "devoluciones" / "batch_id=batch_err"
    batch_dir.mkdir(parents=True)
    (batch_dir / "devoluciones.csv").write_text(
        csv_file.read_text(encoding="utf-8"), encoding="utf-8"
    )

    with pytest.raises(IngestionError) as ing_exc:
        ingest_bronze(spark, "spark_catalog", str(tmp_path), "batch_err", "run_err")

    assert synthetic_marker not in str(ing_exc.value)
    assert "malformed records detected" in str(ing_exc.value)

    # 3. Capture all stdout/stderr emitted by Spark/JVM and Python throughout the entire execution
    captured = capfd.readouterr()
    assert synthetic_marker not in captured.err, "Sensitive motivo leaked in stderr"
    assert synthetic_marker not in captured.out, "Sensitive motivo leaked in stdout"

    # 4. Verify absence of publication to Bronze
    after_count = spark.table("spark_catalog.bronze.devoluciones_raw").count()
    assert after_count == initial_count


def test_missing_header_preserves_motivo_privacy_across_exception_and_diagnostics(
    spark, tmp_path, capfd
):
    spark.sql("CREATE SCHEMA IF NOT EXISTS spark_catalog.bronze")
    spark.sql(
        "CREATE TABLE IF NOT EXISTS spark_catalog.bronze.devoluciones_raw "
        "USING delta AS SELECT 1 WHERE 1=0"
    )
    initial_count = spark.table("spark_catalog.bronze.devoluciones_raw").count()

    synthetic_marker = "SENSITIVE_MOTIVO_HEADER_ABSENT_888"
    csv_file = tmp_path / "devoluciones_no_header.csv"
    # Two data rows without header
    csv_file.write_text(
        f"DEV-001,PED-001,PROD-001,2026-08-20,{synthetic_marker},APROBADA,10.00,PEN,2026-08-20T10:00:00Z\n"
        f"DEV-002,PED-002,PROD-002,2026-08-20,{synthetic_marker},APROBADA,20.00,PEN,2026-08-20T10:00:00Z\n",
        encoding="utf-8",
    )

    # 1. Test read_batch directly on file without header
    with pytest.raises(IngestionError) as exc_info:
        read_batch(spark, str(csv_file), "batch_no_hdr", "run_err")

    err_msg = str(exc_info.value)
    assert synthetic_marker not in err_msg, "Sensitive motivo leaked in exception string"
    assert "Invalid or missing CSV header" in err_msg

    # 2. Test ingest_bronze route on directory without header
    batch_dir = tmp_path / "devoluciones" / "batch_id=batch_no_hdr"
    batch_dir.mkdir(parents=True)
    (batch_dir / "devoluciones.csv").write_text(
        csv_file.read_text(encoding="utf-8"), encoding="utf-8"
    )

    with pytest.raises(IngestionError) as ing_exc:
        ingest_bronze(spark, "spark_catalog", str(tmp_path), "batch_no_hdr", "run_err")

    ing_msg = str(ing_exc.value)
    assert synthetic_marker not in ing_msg, "Sensitive motivo leaked in ingest_bronze exception"
    assert "Invalid or missing CSV header" in ing_msg

    # 3. Capture all stdout/stderr emitted by Spark/JVM and Python throughout the entire execution
    captured = capfd.readouterr()
    assert synthetic_marker not in captured.err, "Sensitive motivo leaked in stderr"
    assert synthetic_marker not in captured.out, "Sensitive motivo leaked in stdout"

    # 4. Verify absence of publication to Bronze
    after_count = spark.table("spark_catalog.bronze.devoluciones_raw").count()
    assert after_count == initial_count


def test_bronze_strict_batch_selection_and_idempotence_with_real_delta(spark, tmp_path):
    spark.sql("CREATE SCHEMA IF NOT EXISTS spark_catalog.bronze")
    spark.sql("DROP TABLE IF EXISTS spark_catalog.bronze.devoluciones_raw")

    landing = tmp_path / "landing"
    batch1_dir = landing / "devoluciones" / "batch_id=2026-08-20"
    batch2_dir = landing / "devoluciones" / "batch_id=2026-08-22"
    batch1_dir.mkdir(parents=True)
    batch2_dir.mkdir(parents=True)

    (batch1_dir / "devoluciones.csv").write_text(
        ",".join(DEVOLUCIONES_SOURCE_COLUMNS)
        + "\n"
        + "DEV-001,PED-001,PROD-001,2026-08-20,Motivo B1,APROBADA,10.00,PEN,2026-08-20T10:00:00Z\n"
        + "DEV-002,PED-002,PROD-002,2026-08-20,Motivo B1,APROBADA,20.00,PEN,2026-08-20T10:00:00Z\n",
        encoding="utf-8",
    )
    (batch2_dir / "devoluciones.csv").write_text(
        ",".join(DEVOLUCIONES_SOURCE_COLUMNS)
        + "\n"
        + "DEV-003,PED-003,PROD-003,2026-08-22,Motivo B2,APROBADA,30.00,PEN,2026-08-22T10:00:00Z\n",
        encoding="utf-8",
    )

    # Ingest Batch 1 (Run 1)
    res1 = ingest_bronze(spark, "spark_catalog", str(landing), "2026-08-20", "run_1")
    assert res1.row_count == 2

    bronze_tbl = spark.table("spark_catalog.bronze.devoluciones_raw")
    assert bronze_tbl.count() == 2
    # Verify strict batch selection: only 2026-08-20 is present
    batches = [r[0] for r in bronze_tbl.select("_ingestion_batch_id").distinct().collect()]
    assert batches == ["2026-08-20"]

    # Ingest Batch 2 (Run 1)
    res2 = ingest_bronze(spark, "spark_catalog", str(landing), "2026-08-22", "run_other")
    assert res2.row_count == 1
    assert bronze_tbl.count() == 3

    b2_records_before = (
        bronze_tbl.where("_ingestion_batch_id = '2026-08-22'")
        .select("devolucion_id", "_ingestion_run_id", "_ingested_at_utc")
        .collect()
    )

    # Re-ingest Batch 1 (Run 2) - Idempotency test
    res1_retry = ingest_bronze(spark, "spark_catalog", str(landing), "2026-08-20", "run_2")
    assert res1_retry.row_count == 2

    # Assertions on post-retry state:
    # 1. Total count is still 3 (batch 1 was not duplicated)
    assert bronze_tbl.count() == 3

    # 2. Batch 2 is completely preserved and untouched
    b2_records_after = (
        bronze_tbl.where("_ingestion_batch_id = '2026-08-22'")
        .select("devolucion_id", "_ingestion_run_id", "_ingested_at_utc")
        .collect()
    )
    assert b2_records_before == b2_records_after

    # 3. Batch 1 has updated run_id and refreshed timestamp
    b1_records = (
        bronze_tbl.where("_ingestion_batch_id = '2026-08-20'")
        .select("devolucion_id", "_ingestion_run_id", "_ingested_at_utc")
        .collect()
    )
    assert len(b1_records) == 2
    for r in b1_records:
        assert r["_ingestion_run_id"] == "run_2"
        assert r["_ingested_at_utc"] is not None

    # 4. Verify real Delta history has 3 commits
    history = spark.sql("DESCRIBE HISTORY spark_catalog.bronze.devoluciones_raw").collect()
    assert len(history) == 3
    assert history[0]["operation"] == "WRITE"  # replaceWhere operation in Delta
