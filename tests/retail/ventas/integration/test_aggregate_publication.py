"""Integration tests for Delta publication and selective overwrite of daily aggregate."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from pyspark.sql import functions as F

from enterprise_fabric.retail.ventas.aggregate import publish_daily_aggregate
from enterprise_fabric.retail.ventas.fact import merge_fact
from enterprise_fabric.retail.ventas.keys import payload_hash
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


def fact_source(spark, rows):
    source = (
        spark.createDataFrame(
            rows,
            """venta_linea_sk string, fecha_pedido date,
            importe_linea decimal(18,2), _last_change_batch_id string""",
        )
        .withColumn("canal", F.lit("WEB"))
        .withColumn("moneda", F.lit("PEN"))
        .withColumn("cantidad", F.lit(1))
        .withColumn("is_cancelled", F.lit(False))
    )
    return source.withColumn(
        "_payload_hash",
        payload_hash(
            "fact_ventas",
            ["venta_linea_sk", "fecha_pedido", "importe_linea", "cantidad"],
        ),
    )


def seed_fact(spark, source):
    (
        source.limit(0)
        .withColumn("_created_at_utc", F.current_timestamp())
        .withColumn("_updated_at_utc", F.current_timestamp())
        .write.format("delta")
        .mode("overwrite")
        .saveAsTable("spark_catalog.gold.fact_ventas")
    )
    merge_fact(spark, "gold.fact_ventas", source)


@pytest.mark.parametrize("remaining_amount", [Decimal("0.00"), Decimal("25.00")])
def test_date_correction_recomputes_old_and_new_dates(aggregate_spark, remaining_amount):
    spark = aggregate_spark
    target = "spark_catalog.gold.agg_ventas_netas_diarias"
    old_date, new_date, untouched_date = (
        date(2026, 8, 13),
        date(2026, 8, 14),
        date(2026, 8, 15),
    )
    rows = [
        ("1" * 64, old_date, Decimal("100.00"), "b1"),
        ("3" * 64, untouched_date, Decimal("50.00"), "b1"),
    ]
    if remaining_amount:
        rows.append(("2" * 64, old_date, remaining_amount, "b1"))
    seed_fact(spark, fact_source(spark, rows))
    publish_daily_aggregate(spark, "spark_catalog", "b1", "FULL")
    untouched = spark.table(target).where(F.col("fecha_pedido") == untouched_date).first()

    corrected = fact_source(spark, [("1" * 64, new_date, Decimal("100.00"), "b2")])
    merge_fact(spark, "gold.fact_ventas", corrected)
    result = publish_daily_aggregate(spark, "spark_catalog", "b2", "INCREMENTAL")
    expected = {new_date: Decimal("100.00"), untouched_date: Decimal("50.00")}
    if remaining_amount:
        expected[old_date] = remaining_amount
    actual = {
        row.fecha_pedido: row.ventas_netas
        for row in spark.table(target).select("fecha_pedido", "ventas_netas").collect()
    }
    assert result.affected_dates == 2
    assert result.published_rows == (2 if remaining_amount else 1)
    assert actual == expected
    assert spark.table("gold.fact_ventas").count() == len(rows)
    assert spark.table(target).where(F.col("fecha_pedido") == untouched_date).first() == untouched

    repeated = publish_daily_aggregate(spark, "spark_catalog", "b2", "INCREMENTAL")
    assert repeated.status == "PUBLISHED"
    assert {
        row.fecha_pedido: row.ventas_netas
        for row in spark.table(target).select("fecha_pedido", "ventas_netas").collect()
    } == expected


def test_incremental_no_changes_does_not_write(aggregate_spark):
    spark = aggregate_spark
    target = "spark_catalog.gold.agg_ventas_netas_diarias"
    seed_fact(
        spark,
        fact_source(spark, [("1" * 64, date(2026, 8, 13), Decimal("100.00"), "b1")]),
    )
    publish_daily_aggregate(spark, "spark_catalog", "b1", "FULL")
    before = spark.table(target).collect()
    version = spark.sql(f"DESCRIBE HISTORY {target}").first().version

    result = publish_daily_aggregate(spark, "spark_catalog", "missing_batch", "INCREMENTAL")
    assert (result.status, result.affected_dates, result.published_rows) == (
        "NO_CHANGES",
        0,
        0,
    )
    assert spark.table(target).collect() == before
    assert spark.sql(f"DESCRIBE HISTORY {target}").first().version == version


def test_incremental_detects_date_correction_even_with_nonexistent_batch(aggregate_spark):
    spark = aggregate_spark
    target = "spark_catalog.gold.agg_ventas_netas_diarias"
    old_date = date(2026, 8, 13)
    new_date = date(2026, 8, 14)

    # Initial publish with b1
    seed_fact(spark, fact_source(spark, [("1" * 64, old_date, Decimal("100.00"), "b1")]))
    publish_daily_aggregate(spark, "spark_catalog", "b1", "FULL")

    # Correct date in fact with batch b2
    corrected = fact_source(spark, [("1" * 64, new_date, Decimal("100.00"), "b2")])
    merge_fact(spark, "gold.fact_ventas", corrected)

    # Publish with a batch that does not exist in fact ('missing_batch')
    # Since expected aggregate differs from published, differences must be detected and published
    result = publish_daily_aggregate(spark, "spark_catalog", "missing_batch", "INCREMENTAL")
    assert result.status == "PUBLISHED"
    assert result.affected_dates == 2
    actual = {
        row.fecha_pedido: row.ventas_netas
        for row in spark.table(target).select("fecha_pedido", "ventas_netas").collect()
    }
    assert actual == {new_date: Decimal("100.00")}


def test_incremental_detects_lines_or_units_change_with_same_amount(aggregate_spark):
    spark = aggregate_spark
    target = "spark_catalog.gold.agg_ventas_netas_diarias"
    order_date = date(2026, 8, 13)

    # Initial: 1 line, quantity 1, 100.00 PEN
    seed_fact(spark, fact_source(spark, [("1" * 64, order_date, Decimal("100.00"), "b1")]))
    publish_daily_aggregate(spark, "spark_catalog", "b1", "FULL")
    initial_row = spark.table(target).first()
    assert initial_row.ventas_netas == Decimal("100.00")
    assert initial_row.lineas_incluidas == 1
    assert initial_row.unidades_vendidas == 1

    # Modify line 1: quantity changes from 1 to 3, but importe_linea remains 100.00
    modified = (
        spark.createDataFrame(
            [("1" * 64, order_date, Decimal("100.00"), "b2")],
            """venta_linea_sk string, fecha_pedido date,
            importe_linea decimal(18,2), _last_change_batch_id string""",
        )
        .withColumn("canal", F.lit("WEB"))
        .withColumn("moneda", F.lit("PEN"))
        .withColumn("cantidad", F.lit(3))
        .withColumn("is_cancelled", F.lit(False))
    )
    modified = modified.withColumn(
        "_payload_hash",
        payload_hash(
            "fact_ventas",
            ["venta_linea_sk", "fecha_pedido", "importe_linea", "cantidad"],
        ),
    )
    merge_fact(spark, "gold.fact_ventas", modified)

    # Incremental publish should detect difference in unidades_vendidas
    result = publish_daily_aggregate(spark, "spark_catalog", "b2", "INCREMENTAL")
    assert result.status == "PUBLISHED"
    assert result.affected_dates == 1
    updated_row = spark.table(target).first()
    assert updated_row.ventas_netas == Decimal("100.00")
    assert updated_row.lineas_incluidas == 1
    assert updated_row.unidades_vendidas == 3
