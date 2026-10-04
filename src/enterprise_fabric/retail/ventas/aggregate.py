"""Build and publish the ventas_netas_diarias aggregate."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from enterprise_fabric.retail.ventas.semantic import (
    ABSOLUTE_TOLERANCE,
    METRIC_ID,
    METRIC_VERSION,
    OUTPUT_GRAIN,
    REPORTING_CURRENCY,
    SemanticContractError,
)
from enterprise_fabric.shared.delta import replace_where_value
from enterprise_fabric.shared.identifiers import require_safe_value


@dataclass(frozen=True)
class AggregateResult:
    batch_id: str
    aggregate_mode: str
    affected_dates: int
    published_rows: int
    status: str


REQUIRED_FACT_COLUMNS = {
    "fecha_pedido",
    "canal",
    "moneda",
    "importe_linea",
    "cantidad",
    "is_cancelled",
    "_last_change_batch_id",
    "_updated_at_utc",
}


def require_fact_contract(facts: DataFrame) -> None:
    missing = sorted(REQUIRED_FACT_COLUMNS.difference(facts.columns))
    if missing:
        raise SemanticContractError(f"fact_ventas missing columns: {missing}")


def require_aggregate_mode(value: str) -> str:
    value = require_safe_value(value.upper(), "aggregate_mode")
    if value not in {"FULL", "INCREMENTAL"}:
        raise SemanticContractError("aggregate_mode must be FULL or INCREMENTAL")
    return value


def incremental_dates(facts: DataFrame, batch_id: str) -> list[date]:
    batch_id = require_safe_value(batch_id, "batch_id")
    rows = (
        facts.where(F.col("_last_change_batch_id") == batch_id)
        .select("fecha_pedido")
        .distinct()
        .orderBy("fecha_pedido")
        .collect()
    )
    if any(row.fecha_pedido is None for row in rows):
        raise SemanticContractError("affected fact has null fecha_pedido")
    return [row.fecha_pedido for row in rows]


def scope_for_dates(facts: DataFrame, dates: list[date]) -> DataFrame:
    if not dates:
        return facts.limit(0)
    return facts.where(F.col("fecha_pedido").isin(dates))


def validate_scope(scope: DataFrame) -> None:
    invalid = scope.where(
        F.col("fecha_pedido").isNull()
        | F.col("canal").isNull()
        | F.col("moneda").isNull()
        | F.col("importe_linea").isNull()
        | F.col("cantidad").isNull()
        | F.col("is_cancelled").isNull()
    ).count()
    if invalid:
        raise SemanticContractError(
            f"metric scope contains {invalid} rows with required null values"
        )


def require_reporting_currency(scope: DataFrame) -> None:
    currencies = [
        row.moneda
        for row in scope.where(~F.col("is_cancelled"))
        .select("moneda")
        .distinct()
        .orderBy("moneda")
        .collect()
    ]
    unexpected = [value for value in currencies if value != REPORTING_CURRENCY]
    if unexpected:
        raise SemanticContractError(
            f"ventas_netas_diarias only supports PEN; unexpected eligible currencies: {unexpected}"
        )


def build_daily_aggregate(scope: DataFrame) -> DataFrame:
    validate_scope(scope)
    require_reporting_currency(scope)
    eligible = scope.where(~F.col("is_cancelled"))
    return (
        eligible.groupBy(*OUTPUT_GRAIN)
        .agg(
            F.sum("importe_linea").cast("decimal(28,2)").alias("ventas_netas"),
            F.count(F.lit(1)).cast("long").alias("lineas_incluidas"),
            F.sum("cantidad").cast("long").alias("unidades_vendidas"),
            F.max("_updated_at_utc").alias("_source_max_updated_at_utc"),
        )
        .withColumn("_metric_id", F.lit(METRIC_ID))
        .withColumn("_metric_version", F.lit(METRIC_VERSION))
        .withColumn("_published_at_utc", F.current_timestamp())
        .select(
            "fecha_pedido",
            "canal",
            "moneda",
            "ventas_netas",
            "lineas_incluidas",
            "unidades_vendidas",
            "_metric_id",
            "_metric_version",
            "_source_max_updated_at_utc",
            "_published_at_utc",
        )
    )


def assert_unique_grain(aggregate: DataFrame) -> None:
    duplicates = aggregate.groupBy(*OUTPUT_GRAIN).count().where(F.col("count") > 1).count()
    if duplicates:
        raise SemanticContractError(f"aggregate contains {duplicates} duplicate metric grains")


def assert_reconciled(scope: DataFrame, aggregate: DataFrame) -> None:
    expected = (
        scope.where(~F.col("is_cancelled"))
        .groupBy("fecha_pedido", "moneda")
        .agg(F.sum("importe_linea").cast("decimal(28,2)").alias("expected"))
    )
    observed = aggregate.groupBy("fecha_pedido", "moneda").agg(
        F.sum("ventas_netas").cast("decimal(28,2)").alias("observed")
    )
    zero = F.lit(Decimal("0.00")).cast("decimal(28,2)")
    comparison = (
        expected.join(observed, ["fecha_pedido", "moneda"], "full")
        .select(
            "fecha_pedido",
            "moneda",
            F.coalesce("expected", zero).alias("expected"),
            F.coalesce("observed", zero).alias("observed"),
        )
        .withColumn("difference", F.abs(F.col("expected") - F.col("observed")))
    )
    failures = comparison.where(F.col("difference") > F.lit(ABSOLUTE_TOLERANCE)).collect()
    if failures:
        raise SemanticContractError(
            f"metric reconciliation exceeded {ABSOLUTE_TOLERANCE} PEN: {failures}"
        )


def publish_daily_aggregate(
    spark: SparkSession,
    catalog: str,
    batch_id: str,
    aggregate_mode: str,
) -> AggregateResult:
    batch_id = require_safe_value(batch_id, "batch_id")
    aggregate_mode = require_aggregate_mode(aggregate_mode)
    fact_name = f"{catalog}.gold.fact_ventas"
    target_name = f"{catalog}.gold.agg_ventas_netas_diarias"
    facts = spark.table(fact_name)
    require_fact_contract(facts)
    require_reporting_currency(facts)
    dates: list[date] = []
    if aggregate_mode == "FULL":
        affected_date_count = facts.select("fecha_pedido").distinct().count()
        scope = facts.cache()
    else:
        dates = incremental_dates(facts, batch_id)
        if not dates:
            return AggregateResult(batch_id, aggregate_mode, 0, 0, "NO_CHANGES")
        affected_date_count = len(dates)
        scope = scope_for_dates(facts, dates).cache()
    aggregate = build_daily_aggregate(scope).cache()
    try:
        assert_unique_grain(aggregate)
        assert_reconciled(scope, aggregate)
        published_rows = aggregate.count()
        metadata = {
            "aggregate_mode": aggregate_mode,
            "batch_id": batch_id,
            "metric_id": METRIC_ID,
            "metric_version": METRIC_VERSION,
        }
        if aggregate_mode == "FULL":
            (
                aggregate.write.format("delta")
                .mode("overwrite")
                .option("replaceWhere", "true")
                .option("userMetadata", json.dumps(metadata, sort_keys=True))
                .saveAsTable(target_name)
            )
        else:
            for affected_date in dates:
                date_value = affected_date.isoformat()
                replace_where_value(
                    aggregate.where(F.col("fecha_pedido") == affected_date),
                    target_name,
                    "fecha_pedido",
                    date_value,
                    metadata,
                )
        return AggregateResult(
            batch_id,
            aggregate_mode,
            affected_date_count,
            published_rows,
            "PUBLISHED",
        )
    finally:
        aggregate.unpersist()
        scope.unpersist()
