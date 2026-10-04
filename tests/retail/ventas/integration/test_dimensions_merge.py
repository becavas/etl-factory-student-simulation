"""Integration tests for Delta MERGE on dim_cliente and dim_producto."""

import time

import pytest
from delta.tables import DeltaTable

from enterprise_fabric.retail.ventas.dimensions import (
    UNKNOWN_NATURAL_KEY,
    _merge_type1,
)
from enterprise_fabric.retail.ventas.keys import UNKNOWN_SK
from enterprise_fabric.retail.ventas.tables import ensure_gold_tables

LOCAL_TABLES = ("dim_cliente", "dim_producto", "fact_ventas")


@pytest.fixture
def gold_spark(spark):
    spark.sql("CREATE SCHEMA IF NOT EXISTS spark_catalog.gold")
    for table_name in LOCAL_TABLES:
        spark.sql(f"DROP TABLE IF EXISTS spark_catalog.gold.{table_name}")
    ensure_gold_tables(spark, "spark_catalog")
    yield spark
    for table_name in LOCAL_TABLES:
        spark.sql(f"DROP TABLE IF EXISTS spark_catalog.gold.{table_name}")


def _client_source(spark, cliente_id: str, pais: str, status: str, batch_id: str, p_hash: str):
    schema = (
        "cliente_sk string, cliente_id string, pais_codigo string, "
        "source_status string, is_active boolean, _last_change_batch_id string, "
        "_payload_hash string"
    )
    rows = [
        (UNKNOWN_SK, UNKNOWN_NATURAL_KEY, None, "UNKNOWN", True, "SYSTEM", "UNKNOWN"),
        ("sk-" + cliente_id, cliente_id, pais, status, True, batch_id, p_hash),
    ]
    return spark.createDataFrame(rows, schema)


def test_dimension_type1_merge_idempotence_and_attribute_update(gold_spark):
    spark = gold_spark
    table = "gold.dim_cliente"

    # Initial merge
    initial = _client_source(spark, "CLI-1", "PE", "ACTIVO", "batch-1", "hash-1")
    _merge_type1(
        spark,
        table,
        initial,
        "cliente_id",
        ("cliente_sk", "pais_codigo", "source_status"),
        "INCREMENTAL",
        "batch-1",
    )

    row1 = spark.table(table).where("cliente_id = 'CLI-1'").first()
    assert row1.pais_codigo == "PE"
    assert row1.source_status == "ACTIVO"
    created_at = row1._created_at_utc

    # Idempotent second merge
    _merge_type1(
        spark,
        table,
        initial,
        "cliente_id",
        ("cliente_sk", "pais_codigo", "source_status"),
        "INCREMENTAL",
        "batch-1",
    )
    metrics = DeltaTable.forName(spark, table).history(1).first().operationMetrics
    assert metrics["numTargetRowsInserted"] == "0"
    assert metrics["numTargetRowsUpdated"] == "0"

    # Sleep slightly to ensure timestamp advances
    time.sleep(0.1)

    # Type 1 update with changed attribute
    updated = _client_source(spark, "CLI-1", "CO", "INACTIVO", "batch-2", "hash-2")
    _merge_type1(
        spark,
        table,
        updated,
        "cliente_id",
        ("cliente_sk", "pais_codigo", "source_status"),
        "INCREMENTAL",
        "batch-2",
    )

    row2 = spark.table(table).where("cliente_id = 'CLI-1'").first()
    assert row2.pais_codigo == "CO"
    assert row2.source_status == "INACTIVO"
    assert row2.cliente_sk == "sk-CLI-1"  # SK preserved
    assert row2._created_at_utc == created_at  # Created at preserved
    assert row2._last_change_batch_id == "batch-2"


def test_snapshot_mode_full_deactivates_absent_and_protects_unknown(gold_spark):
    spark = gold_spark
    table = "gold.dim_cliente"

    # Batch 1 with CLI-1 and CLI-2
    schema = (
        "cliente_sk string, cliente_id string, pais_codigo string, "
        "source_status string, is_active boolean, _last_change_batch_id string, "
        "_payload_hash string"
    )
    batch1_rows = [
        (UNKNOWN_SK, UNKNOWN_NATURAL_KEY, None, "UNKNOWN", True, "SYSTEM", "UNKNOWN"),
        ("sk-CLI-1", "CLI-1", "PE", "ACTIVO", True, "batch-1", "hash-cli-1"),
        ("sk-CLI-2", "CLI-2", "CL", "ACTIVO", True, "batch-1", "hash-cli-2"),
    ]
    _merge_type1(
        spark,
        table,
        spark.createDataFrame(batch1_rows, schema),
        "cliente_id",
        ("cliente_sk", "pais_codigo", "source_status"),
        "FULL",
        "batch-1",
    )
    assert spark.table(table).count() == 3

    # Batch 2 INCREMENTAL omitting CLI-2 -> CLI-2 remains active
    batch2_incremental = [
        (UNKNOWN_SK, UNKNOWN_NATURAL_KEY, None, "UNKNOWN", True, "SYSTEM", "UNKNOWN"),
        ("sk-CLI-1", "CLI-1", "PE", "ACTIVO", True, "batch-2", "hash-cli-1"),
    ]
    _merge_type1(
        spark,
        table,
        spark.createDataFrame(batch2_incremental, schema),
        "cliente_id",
        ("cliente_sk", "pais_codigo", "source_status"),
        "INCREMENTAL",
        "batch-2",
    )
    cli2_row = spark.table(table).where("cliente_id = 'CLI-2'").first()
    assert cli2_row.is_active is True

    # Batch 3 FULL omitting CLI-2 -> CLI-2 is marked is_active=false, unknown member remains active
    _merge_type1(
        spark,
        table,
        spark.createDataFrame(batch2_incremental, schema),
        "cliente_id",
        ("cliente_sk", "pais_codigo", "source_status"),
        "FULL",
        "batch-3",
    )

    cli2_after_full = spark.table(table).where("cliente_id = 'CLI-2'").first()
    assert cli2_after_full.is_active is False
    assert cli2_after_full._last_change_batch_id == "batch-3"

    unknown_row = spark.table(table).where(f"cliente_id = '{UNKNOWN_NATURAL_KEY}'").first()
    assert unknown_row.is_active is True
