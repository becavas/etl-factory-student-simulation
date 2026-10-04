"""Integration tests for Delta publication and selective overwrite of daily aggregate."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from pyspark.sql import functions as F

from enterprise_fabric.retail.ventas.aggregate import publish_daily_aggregate
from enterprise_fabric.retail.ventas.tables import ensure_aggregate_table

LOCAL_TABLES = ("fact_ventas", "agg_ventas_netas_diarias")


@pytest.fixture
def aggregate_spark(spark):
    spark.sql("CREATE SCHEMA IF NOT EXISTS spark_catalog.gold")
    for table_name in LOCAL_TABLES:
        spark.sql(f"DROP TABLE IF EXISTS spark_catalog.gold.{table_name}")
    ensure_aggregate_table(spark, "spark_catalog")
    yield spark
    for table_name in LOCAL_TABLES:
        spark.sql(f"DROP TABLE IF EXISTS spark_catalog.gold.{table_name}")


def test_publication_replaces_complete_affected_date(aggregate_spark):
    spark = aggregate_spark
    catalog = "spark_catalog"
    fact_name = f"{catalog}.gold.fact_ventas"
    target_name = f"{catalog}.gold.agg_ventas_netas_diarias"

    initial = spark.createDataFrame(
        [
            (
                date(2026, 8, 13),
                "WEB",
                "PEN",
                Decimal("100.00"),
                1,
                False,
                "b1",
                datetime(2026, 8, 14, 10, 0),
            ),
            (
                date(2026, 8, 13),
                "TIENDA",
                "PEN",
                Decimal("50.00"),
                2,
                False,
                "b1",
                datetime(2026, 8, 14, 10, 0),
            ),
        ],
        """fecha_pedido date, canal string, moneda string,
        importe_linea decimal(18,2), cantidad int, is_cancelled boolean,
        _last_change_batch_id string, _updated_at_utc timestamp""",
    )
    initial.write.format("delta").mode("overwrite").saveAsTable(fact_name)

    first = publish_daily_aggregate(spark, catalog, "b1", "FULL")
    assert first.published_rows == 2
    assert spark.table(target_name).count() == 2

    changed = initial.withColumn("is_cancelled", F.col("canal") == "TIENDA").withColumn(
        "_last_change_batch_id", F.lit("b2")
    )
    changed.write.format("delta").mode("overwrite").saveAsTable(fact_name)

    second = publish_daily_aggregate(spark, catalog, "b2", "INCREMENTAL")
    rows = spark.table(target_name).select("canal", "ventas_netas").collect()
    assert second.published_rows == 1
    assert [(row.canal, row.ventas_netas) for row in rows] == [("WEB", Decimal("100.00"))]

    repeated = publish_daily_aggregate(spark, catalog, "b2", "INCREMENTAL")
    assert repeated.status == "PUBLISHED"
    assert spark.table(target_name).count() == 1


def test_date_completely_cancelled_removes_stale_aggregate(aggregate_spark):
    spark = aggregate_spark
    catalog = "spark_catalog"
    fact_name = f"{catalog}.gold.fact_ventas"
    target_name = f"{catalog}.gold.agg_ventas_netas_diarias"

    initial = spark.createDataFrame(
        [
            (
                date(2026, 8, 13),
                "WEB",
                "PEN",
                Decimal("100.00"),
                1,
                False,
                "b1",
                datetime(2026, 8, 14, 10, 0),
            ),
        ],
        """fecha_pedido date, canal string, moneda string,
        importe_linea decimal(18,2), cantidad int, is_cancelled boolean,
        _last_change_batch_id string, _updated_at_utc timestamp""",
    )
    initial.write.format("delta").mode("overwrite").saveAsTable(fact_name)

    # Initial publish
    publish_daily_aggregate(spark, catalog, "b1", "FULL")
    assert spark.table(target_name).count() == 1

    # Batch 2: The only order for 2026-08-13 is cancelled
    cancelled = initial.withColumn("is_cancelled", F.lit(True)).withColumn(
        "_last_change_batch_id", F.lit("b2")
    )
    cancelled.write.format("delta").mode("overwrite").saveAsTable(fact_name)

    result = publish_daily_aggregate(spark, catalog, "b2", "INCREMENTAL")
    assert result.published_rows == 0
    # The stale aggregate for 2026-08-13 was overwritten with empty DataFrame via replaceWhere
    assert spark.table(target_name).where("fecha_pedido = '2026-08-13'").count() == 0
