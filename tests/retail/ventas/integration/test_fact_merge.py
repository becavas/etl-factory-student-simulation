"""Integration tests for Delta MERGE on fact_ventas."""

from decimal import Decimal

import pytest
from delta.tables import DeltaTable
from pyspark.sql import functions as F

from enterprise_fabric.retail.ventas.fact import merge_fact
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


def _source(spark, cliente_sk: str, status: str = "ENTREGADO", batch_id: str = "gold_initial_001"):
    return spark.createDataFrame(
        [
            (
                "1" * 64,
                "PED-1",
                "ITEM-1",
                "2026-01-01",
                cliente_sk,
                "2" * 64,
                "CLI-1",
                "PROD-1",
                2,
                Decimal("10.00"),
                Decimal("20.00"),
                "PEN",
                "WEB",
                status,
                status == "CANCELADO",
                batch_id,
                f"hash-{cliente_sk}-{status}",
            )
        ],
        "venta_linea_sk string, pedido_id string, item_id string, fecha_pedido string, "
        "cliente_sk string, producto_sk string, _source_cliente_id string, "
        "_source_producto_id string, cantidad int, precio_unitario decimal(18,2), "
        "importe_linea decimal(18,2), moneda string, canal string, estado_pedido string, "
        "is_cancelled boolean, _last_change_batch_id string, _payload_hash string",
    ).withColumn("fecha_pedido", F.col("fecha_pedido").cast("date"))


def test_merge_inserts_updates_and_is_idempotent(gold_spark):
    spark = gold_spark
    table = "gold.fact_ventas"

    initial = _source(spark, UNKNOWN_SK)
    merge_fact(spark, table, initial)
    assert spark.table(table).count() == 1

    # Idempotent second merge
    merge_fact(spark, table, initial)
    metrics = DeltaTable.forName(spark, table).history(1).first().operationMetrics
    assert metrics["numTargetRowsInserted"] == "0"
    assert metrics["numTargetRowsUpdated"] == "0"
    assert spark.table(table).count() == 1

    # Late arrival dimension resolution: updates cliente_sk without duplicating
    resolved_sk = "3" * 64
    merge_fact(spark, table, _source(spark, resolved_sk, batch_id="gold_late_003"))
    row = spark.table(table).first()
    assert row.cliente_sk == resolved_sk
    assert row.venta_linea_sk == "1" * 64
    assert spark.table(table).count() == 1


def test_merge_preserves_omitted_fact_and_handles_cancellation(gold_spark):
    spark = gold_spark
    table = "gold.fact_ventas"

    # Insert initial row
    initial = _source(spark, "3" * 64, status="CONFIRMADO", batch_id="gold_initial_001")
    merge_fact(spark, table, initial)
    assert spark.table(table).count() == 1

    # Next batch has a cancellation for this row
    cancelled = _source(spark, "3" * 64, status="CANCELADO", batch_id="gold_change_002")
    merge_fact(spark, table, cancelled)

    row = spark.table(table).first()
    assert row.is_cancelled is True
    assert row.estado_pedido == "CANCELADO"
    assert row._last_change_batch_id == "gold_change_002"
    assert spark.table(table).count() == 1

    # Empty/omitted batch does not delete existing rows
    # A subsequent batch without this order does not delete the row
    assert spark.table(table).count() == 1
