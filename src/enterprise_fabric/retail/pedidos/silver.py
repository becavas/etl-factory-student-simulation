"""Silver transformation and publication for retail/pedidos."""

from dataclasses import dataclass

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

from enterprise_fabric.retail.pedidos.bronze import validate_batch_id
from enterprise_fabric.retail.pedidos.quality import (
    Rule,
    add_rule_ids,
    build_metrics,
    duplicate_excess_count,
    normalize_text,
    rule_counts,
)
from enterprise_fabric.shared.delta import replace_where_value
from enterprise_fabric.shared.identifiers import require_safe_value
from enterprise_fabric.shared.spark import deterministic_latest


class QualityGateError(RuntimeError):
    """Raised after quality evidence is persisted for deterministic FAIL rules."""


@dataclass(frozen=True)
class SilverEvaluation:
    pedidos_curated: DataFrame
    items_curated: DataFrame
    quarantine: DataFrame
    metrics: DataFrame
    fail_count: int


@dataclass(frozen=True)
class SilverResult:
    batch_id: str
    quality_run_id: str
    pedidos_count: int
    item_count: int
    quarantined_count: int


def validate_run_id(run_id: str) -> str:
    return require_safe_value(run_id, "quality_run_id")


def _raw_payload(columns: tuple[str, ...]) -> Column:
    return F.to_json(
        F.struct(*(F.col(column) for column in columns)),
        {"ignoreNullFields": "false"},
    )


def _deduplicate(df: DataFrame, keys: list[str]) -> DataFrame:
    """Keep invalid keys for rule evaluation and rank complete keys deterministically."""
    latest, _ = deterministic_latest(df, keys, "fecha_actualizacion")
    return latest


def _prepare_pedidos(raw: DataFrame) -> DataFrame:
    source_columns = (
        "pedido_id",
        "cliente_id",
        "fecha_pedido",
        "fecha_actualizacion",
        "canal",
        "moneda",
        "monto_total",
        "estado",
    )
    return raw.select(
        normalize_text(F.col("pedido_id")).alias("pedido_id"),
        normalize_text(F.col("cliente_id")).alias("cliente_id"),
        F.expr("try_cast(nullif(trim(fecha_pedido), '') AS DATE)").alias("fecha_pedido"),
        F.try_to_timestamp(
            normalize_text(F.col("fecha_actualizacion")),
            F.lit("yyyy-MM-dd'T'HH:mm:ssX"),
        ).alias("fecha_actualizacion"),
        F.upper(normalize_text(F.col("canal"))).alias("canal"),
        F.upper(normalize_text(F.col("moneda"))).alias("moneda"),
        F.expr("try_cast(nullif(trim(monto_total), '') AS DECIMAL(18,2))").alias("monto_total"),
        F.upper(normalize_text(F.col("estado"))).alias("estado"),
        _raw_payload(source_columns).alias("_raw_payload"),
        "_source_system",
        "_source_file_path",
        "_source_file_modification_time",
        "_ingestion_batch_id",
        "_ingestion_run_id",
        "_ingested_at_utc",
        "_record_hash",
    )


def _prepare_items(raw: DataFrame) -> DataFrame:
    source_columns = (
        "pedido_id",
        "item_id",
        "producto_id",
        "cantidad",
        "precio_unitario",
        "importe_linea",
        "fecha_actualizacion",
    )
    return raw.select(
        normalize_text(F.col("pedido_id")).alias("pedido_id"),
        normalize_text(F.col("item_id")).alias("item_id"),
        normalize_text(F.col("producto_id")).alias("producto_id"),
        F.expr("try_cast(nullif(trim(cantidad), '') AS INTEGER)").alias("cantidad"),
        F.expr("try_cast(nullif(trim(precio_unitario), '') AS DECIMAL(18,2))").alias(
            "precio_unitario"
        ),
        F.expr("try_cast(nullif(trim(importe_linea), '') AS DECIMAL(18,2))").alias("importe_linea"),
        F.try_to_timestamp(
            normalize_text(F.col("fecha_actualizacion")),
            F.lit("yyyy-MM-dd'T'HH:mm:ssX"),
        ).alias("fecha_actualizacion"),
        _raw_payload(source_columns).alias("_raw_payload"),
        "_source_system",
        "_source_file_path",
        "_source_file_modification_time",
        "_ingestion_batch_id",
        "_ingestion_run_id",
        "_ingested_at_utc",
        "_record_hash",
    )


def _quarantine(entity: str, df: DataFrame, quality_run_id: str) -> DataFrame:
    return df.where(F.size("_quality_rule_ids") > 0).select(
        F.lit(entity).alias("entity"),
        "_raw_payload",
        "_quality_rule_ids",
        F.col("_ingestion_batch_id").alias("_source_batch_id"),
        "_ingestion_run_id",
        "_source_file_path",
        "_record_hash",
        F.lit(quality_run_id).alias("_quality_run_id"),
        F.current_timestamp().alias("_quarantined_at_utc"),
    )


def _curated(df: DataFrame, quality_run_id: str) -> DataFrame:
    return (
        df.where(F.size("_quality_rule_ids") == 0)
        .drop("_raw_payload", "_quality_rule_ids")
        .withColumnRenamed("_ingestion_batch_id", "_source_batch_id")
        .withColumn("_quality_run_id", F.lit(quality_run_id))
        .withColumn("_curated_at_utc", F.current_timestamp())
    )


def evaluate_silver(
    spark: SparkSession,
    pedidos_raw: DataFrame,
    items_raw: DataFrame,
    batch_id: str,
    quality_run_id: str,
) -> SilverEvaluation:
    """Transform one aligned Bronze batch and return data plus quality evidence."""
    pedidos_prepared = _prepare_pedidos(pedidos_raw).cache()
    items_prepared = _prepare_items(items_raw).cache()
    try:
        pedidos_total = pedidos_prepared.count()
        items_total = items_prepared.count()
        pedido_duplicates = duplicate_excess_count(pedidos_prepared, ["pedido_id"])
        item_duplicates = duplicate_excess_count(items_prepared, ["pedido_id", "item_id"])
        pedidos = _deduplicate(pedidos_prepared, ["pedido_id"])
        items = _deduplicate(items_prepared, ["pedido_id", "item_id"])

        pedido_rules = [
            Rule("pedido_id_required", "FAIL", F.col("pedido_id").isNull()),
            Rule(
                "pedido_updated_at_valid",
                "FAIL",
                F.col("fecha_actualizacion").isNull(),
            ),
            Rule("cliente_id_required", "QUARANTINE", F.col("cliente_id").isNull()),
            Rule("pedido_date_valid", "QUARANTINE", F.col("fecha_pedido").isNull()),
            Rule(
                "pedido_amount_valid",
                "QUARANTINE",
                F.col("monto_total").isNull() | (F.col("monto_total") < 0),
            ),
        ]
        pedido_counts = rule_counts(pedidos, pedido_rules)
        pedidos_checked = add_rule_ids(pedidos, pedido_rules).cache()

        valid_pedidos = pedidos_checked.where(F.size("_quality_rule_ids") == 0).select("pedido_id")
        items_with_parent = items.join(
            valid_pedidos.withColumn("_pedido_exists", F.lit(True)),
            on="pedido_id",
            how="left",
        )
        item_rules = [
            Rule("item_id_required", "FAIL", F.col("item_id").isNull()),
            Rule("item_pedido_id_required", "FAIL", F.col("pedido_id").isNull()),
            Rule(
                "item_updated_at_valid",
                "FAIL",
                F.col("fecha_actualizacion").isNull(),
            ),
            Rule("item_product_required", "QUARANTINE", F.col("producto_id").isNull()),
            Rule(
                "item_quantity_valid",
                "QUARANTINE",
                F.col("cantidad").isNull() | (F.col("cantidad") <= 0),
            ),
            Rule(
                "item_price_valid",
                "QUARANTINE",
                F.col("precio_unitario").isNull() | (F.col("precio_unitario") < 0),
            ),
            Rule(
                "item_amount_valid",
                "QUARANTINE",
                F.col("importe_linea").isNull() | (F.col("importe_linea") < 0),
            ),
            Rule(
                "item_pedido_orphan",
                "QUARANTINE",
                F.col("pedido_id").isNotNull() & F.col("_pedido_exists").isNull(),
            ),
        ]
        item_counts = rule_counts(items_with_parent, item_rules)
        items_checked = add_rule_ids(items_with_parent, item_rules).drop("_pedido_exists").cache()

        pedido_metric_rules = [Rule("pedido_duplicate", "OBSERVE", F.lit(False)), *pedido_rules]
        item_metric_rules = [Rule("item_duplicate", "OBSERVE", F.lit(False)), *item_rules]
        pedido_counts = {"pedido_duplicate": pedido_duplicates, **pedido_counts}
        item_counts = {"item_duplicate": item_duplicates, **item_counts}
        metrics = build_metrics(
            spark,
            quality_run_id,
            batch_id,
            "pedidos",
            pedidos_total,
            pedido_metric_rules,
            pedido_counts,
        ).unionByName(
            build_metrics(
                spark,
                quality_run_id,
                batch_id,
                "pedido_items",
                items_total,
                item_metric_rules,
                item_counts,
            )
        )
        quarantine = _quarantine("pedidos", pedidos_checked, quality_run_id).unionByName(
            _quarantine("pedido_items", items_checked, quality_run_id)
        )
        fail_rule_ids = {
            rule.rule_id
            for rule in [*pedido_metric_rules, *item_metric_rules]
            if rule.action == "FAIL"
        }
        fail_count = sum(
            count
            for rule_id, count in {**pedido_counts, **item_counts}.items()
            if rule_id in fail_rule_ids
        )
        return SilverEvaluation(
            pedidos_curated=_curated(pedidos_checked, quality_run_id),
            items_curated=_curated(items_checked, quality_run_id),
            quarantine=quarantine,
            metrics=metrics,
            fail_count=fail_count,
        )
    finally:
        pedidos_prepared.unpersist()
        items_prepared.unpersist()


def _assert_aligned_bronze(pedidos_raw: DataFrame, items_raw: DataFrame, batch_id: str) -> None:
    runs = {
        row["_ingestion_run_id"]
        for row in pedidos_raw.select("_ingestion_run_id")
        .union(items_raw.select("_ingestion_run_id"))
        .distinct()
        .collect()
    }
    if len(runs) != 1:
        raise ValueError(
            f"Bronze batch {batch_id} is not aligned; ingestion run IDs: {sorted(runs)}"
        )


def publish_silver(
    spark: SparkSession,
    catalog: str,
    batch_id: str,
    quality_run_id: str,
) -> SilverResult:
    """Evaluate and publish one Bronze batch to Silver."""
    batch_id = validate_batch_id(batch_id)
    quality_run_id = validate_run_id(quality_run_id)
    pedidos_raw = spark.table(f"{catalog}.bronze.pedidos_raw").where(
        F.col("_ingestion_batch_id") == batch_id
    )
    items_raw = spark.table(f"{catalog}.bronze.pedido_items_raw").where(
        F.col("_ingestion_batch_id") == batch_id
    )
    if pedidos_raw.limit(1).count() == 0 or items_raw.limit(1).count() == 0:
        raise ValueError(f"Both Bronze entities are required for batch {batch_id}")
    _assert_aligned_bronze(pedidos_raw, items_raw, batch_id)

    evaluation = evaluate_silver(spark, pedidos_raw, items_raw, batch_id, quality_run_id)
    metadata = {
        "capability": "retail/pedidos",
        "batch_id": batch_id,
        "quality_run_id": quality_run_id,
    }
    replace_where_value(
        evaluation.metrics,
        f"{catalog}.silver.pedidos_quality_metrics",
        "quality_run_id",
        quality_run_id,
        metadata,
    )
    replace_where_value(
        evaluation.quarantine,
        f"{catalog}.silver.pedidos_quarantine",
        "_quality_run_id",
        quality_run_id,
        metadata,
    )
    quarantined_count = evaluation.quarantine.count()
    if evaluation.fail_count:
        raise QualityGateError(
            f"Batch {batch_id} failed {evaluation.fail_count} mandatory quality checks; "
            f"evidence is stored for quality_run_id={quality_run_id}"
        )

    replace_where_value(
        evaluation.pedidos_curated,
        f"{catalog}.silver.pedidos_curated",
        "_source_batch_id",
        batch_id,
        metadata,
    )
    replace_where_value(
        evaluation.items_curated,
        f"{catalog}.silver.pedido_items_curated",
        "_source_batch_id",
        batch_id,
        metadata,
    )
    return SilverResult(
        batch_id=batch_id,
        quality_run_id=quality_run_id,
        pedidos_count=evaluation.pedidos_curated.count(),
        item_count=evaluation.items_curated.count(),
        quarantined_count=quarantined_count,
    )
