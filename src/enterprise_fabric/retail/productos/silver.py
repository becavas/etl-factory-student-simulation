"""Typed Silver and explicit multi-entity quality for retail/productos."""

from dataclasses import dataclass
from decimal import Decimal

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from enterprise_fabric.retail.productos.schemas import (
    CATEGORIAS_SOURCE_COLUMNS,
    PRODUCTOS_SOURCE_COLUMNS,
)
from enterprise_fabric.shared.delta import replace_where_value
from enterprise_fabric.shared.identifiers import require_safe_value
from enterprise_fabric.shared.spark import deterministic_latest, normalized_text

ALLOWED_STATES = ("ACTIVO", "INACTIVO")
ALLOWED_CURRENCIES = ("PEN", "USD")


class QualityGateError(RuntimeError):
    """Raised after quality evidence is persisted."""


@dataclass(frozen=True)
class SilverResult:
    batch_id: str
    quality_run_id: str
    productos_count: int
    categorias_count: int
    quarantined_count: int


def prepare_productos(raw: DataFrame) -> DataFrame:
    payload = F.to_json(
        F.struct(*(F.col(name) for name in PRODUCTOS_SOURCE_COLUMNS)),
        {"ignoreNullFields": "false"},
    )
    return raw.select(
        normalized_text(F.col("producto_id")).alias("producto_id"),
        normalized_text(F.col("categoria_id")).alias("categoria_id"),
        normalized_text(F.col("nombre_producto")).alias("nombre_producto"),
        normalized_text(F.col("marca")).alias("marca"),
        F.upper(normalized_text(F.col("moneda"))).alias("moneda"),
        F.expr("try_cast(nullif(trim(precio_lista), '') AS DECIMAL(18,2))").alias("precio_lista"),
        F.upper(normalized_text(F.col("estado"))).alias("estado"),
        F.try_to_timestamp(
            normalized_text(F.col("fecha_actualizacion")),
            F.lit("yyyy-MM-dd'T'HH:mm:ssX"),
        ).alias("fecha_actualizacion"),
        payload.alias("_raw_payload"),
        "_source_system",
        "_source_entity",
        "_source_file_path",
        "_source_file_modification_time",
        "_ingestion_batch_id",
        "_ingestion_run_id",
        "_ingested_at_utc",
        "_record_hash",
    )


def prepare_categorias(raw: DataFrame) -> DataFrame:
    payload = F.to_json(
        F.struct(*(F.col(name) for name in CATEGORIAS_SOURCE_COLUMNS)),
        {"ignoreNullFields": "false"},
    )
    return raw.select(
        normalized_text(F.col("categoria_id")).alias("categoria_id"),
        normalized_text(F.col("nombre_categoria")).alias("nombre_categoria"),
        normalized_text(F.col("categoria_padre_id")).alias("categoria_padre_id"),
        F.upper(normalized_text(F.col("estado"))).alias("estado"),
        F.try_to_timestamp(
            normalized_text(F.col("fecha_actualizacion")),
            F.lit("yyyy-MM-dd'T'HH:mm:ssX"),
        ).alias("fecha_actualizacion"),
        payload.alias("_raw_payload"),
        "_source_system",
        "_source_entity",
        "_source_file_path",
        "_source_file_modification_time",
        "_ingestion_batch_id",
        "_ingestion_run_id",
        "_ingested_at_utc",
        "_record_hash",
    )


def category_duplicate_profile(frame: DataFrame) -> tuple[int, int]:
    """Return repeated rows and IDs with more than one source payload."""
    keyed = frame.where(F.col("categoria_id").isNotNull())
    groups = keyed.groupBy("categoria_id").agg(
        F.count("*").alias("rows"),
        F.countDistinct("_record_hash").alias("payloads"),
    )
    result = groups.agg(
        F.coalesce(F.sum(F.greatest(F.col("rows") - 1, F.lit(0))), F.lit(0)).alias("duplicates"),
        F.count(F.when(F.col("payloads") > 1, 1)).alias("conflicts"),
    ).first()
    return int(result["duplicates"]), int(result["conflicts"])


def with_product_rules(frame: DataFrame, category_ids: DataFrame) -> DataFrame:
    known = category_ids.select("categoria_id").where(F.col("categoria_id").isNotNull()).distinct()
    joined = frame.join(
        known.withColumn("_category_exists", F.lit(True)),
        on="categoria_id",
        how="left",
    )
    rules = (
        ("producto_id_required", F.col("producto_id").isNull()),
        ("producto_updated_at_valid", F.col("fecha_actualizacion").isNull()),
        ("producto_name_required", F.col("nombre_producto").isNull()),
        ("producto_category_required", F.col("categoria_id").isNull()),
        (
            "producto_category_exists",
            F.col("categoria_id").isNotNull() & F.col("_category_exists").isNull(),
        ),
        (
            "producto_currency_valid",
            F.col("moneda").isNull() | ~F.col("moneda").isin(*ALLOWED_CURRENCIES),
        ),
        (
            "producto_price_valid",
            F.col("precio_lista").isNull() | (F.col("precio_lista") < F.lit(Decimal("0.00"))),
        ),
        (
            "producto_state_valid",
            F.col("estado").isNull() | ~F.col("estado").isin(*ALLOWED_STATES),
        ),
    )
    fail_ids = {"producto_id_required", "producto_updated_at_valid"}
    return (
        joined.withColumn(
            "_quality_rule_ids",
            F.array_compact(
                F.array(*(F.when(condition, F.lit(rule_id)) for rule_id, condition in rules))
            ),
        )
        .withColumn(
            "_fail_rule_ids",
            F.array_intersect(
                "_quality_rule_ids",
                F.array(*(F.lit(rule_id) for rule_id in sorted(fail_ids))),
            ),
        )
        .drop("_category_exists")
    )


def with_category_rules(frame: DataFrame, conflict_ids: DataFrame) -> DataFrame:
    tagged = frame.join(
        conflict_ids.select("categoria_id")
        .distinct()
        .withColumn("_category_conflict", F.lit(True)),
        on="categoria_id",
        how="left",
    )
    rules = (
        ("categoria_id_required", F.col("categoria_id").isNull()),
        ("categoria_updated_at_valid", F.col("fecha_actualizacion").isNull()),
        ("categoria_name_required", F.col("nombre_categoria").isNull()),
        (
            "categoria_state_valid",
            F.col("estado").isNull() | ~F.col("estado").isin(*ALLOWED_STATES),
        ),
        (
            "categoria_parent_not_self",
            F.col("categoria_id").isNotNull()
            & (F.col("categoria_id") == F.col("categoria_padre_id")),
        ),
        (
            "categoria_conflicting_duplicate",
            F.coalesce(F.col("_category_conflict"), F.lit(False)),
        ),
    )
    fail_ids = {
        "categoria_id_required",
        "categoria_updated_at_valid",
        "categoria_conflicting_duplicate",
    }
    return (
        tagged.withColumn(
            "_quality_rule_ids",
            F.array_compact(
                F.array(*(F.when(condition, F.lit(rule_id)) for rule_id, condition in rules))
            ),
        )
        .withColumn(
            "_fail_rule_ids",
            F.array_intersect(
                "_quality_rule_ids",
                F.array(*(F.lit(rule_id) for rule_id in sorted(fail_ids))),
            ),
        )
        .drop("_category_conflict")
    )


def metric_rows(
    spark: SparkSession,
    quality_run_id: str,
    batch_id: str,
    entity: str,
    checked: DataFrame,
    actions: dict[str, str],
    observations: dict[str, int],
) -> DataFrame:
    total = checked.count()
    counts = {
        rule_id: checked.where(F.array_contains("_quality_rule_ids", rule_id)).count()
        for rule_id in actions
    }
    observed_at = spark.sql("SELECT current_timestamp() AS ts").first()["ts"]
    values = [(rule_id, actions[rule_id], count) for rule_id, count in counts.items()]
    values.extend((rule_id, "OBSERVE", count) for rule_id, count in observations.items())
    return spark.createDataFrame(
        [
            (
                quality_run_id,
                batch_id,
                entity,
                rule_id,
                action,
                count,
                total,
                observed_at,
            )
            for rule_id, action, count in values
        ],
        "quality_run_id string, batch_id string, entity string, rule_id string, "
        "action string, failed_records long, total_records long, observed_at_utc timestamp",
    )


def _assert_same_bronze_run(productos: DataFrame, categorias: DataFrame, batch_id: str) -> None:
    product_runs = {row[0] for row in productos.select("_ingestion_run_id").distinct().collect()}
    category_runs = {row[0] for row in categorias.select("_ingestion_run_id").distinct().collect()}
    if len(product_runs) != 1 or product_runs != category_runs:
        raise ValueError(f"Bronze entities for batch {batch_id} do not share one ingestion run")


def _quarantine(frame: DataFrame, entity: str, quality_run_id: str) -> DataFrame:
    return frame.where(F.size("_quality_rule_ids") > 0).select(
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


def _curated(frame: DataFrame, quality_run_id: str) -> DataFrame:
    return (
        frame.where(F.size("_quality_rule_ids") == 0)
        .drop("_raw_payload", "_quality_rule_ids", "_fail_rule_ids")
        .withColumnRenamed("_ingestion_batch_id", "_source_batch_id")
        .withColumn("_quality_run_id", F.lit(quality_run_id))
        .withColumn("_curated_at_utc", F.current_timestamp())
    )


def publish_silver(
    spark: SparkSession,
    catalog: str,
    batch_id: str,
    quality_run_id: str,
) -> SilverResult:
    batch_id = require_safe_value(batch_id, "batch_id")
    quality_run_id = require_safe_value(quality_run_id, "quality_run_id")
    productos_raw = spark.table(f"{catalog}.bronze.productos_raw").where(
        F.col("_ingestion_batch_id") == batch_id
    )
    categorias_raw = spark.table(f"{catalog}.bronze.categorias_raw").where(
        F.col("_ingestion_batch_id") == batch_id
    )
    if productos_raw.limit(1).count() == 0 or categorias_raw.limit(1).count() == 0:
        raise ValueError(f"Both Bronze entities are required for batch {batch_id}")
    _assert_same_bronze_run(productos_raw, categorias_raw, batch_id)

    productos_prepared = prepare_productos(productos_raw).cache()
    categorias_prepared = prepare_categorias(categorias_raw).cache()
    try:
        category_groups = (
            categorias_prepared.where(F.col("categoria_id").isNotNull())
            .groupBy("categoria_id")
            .agg(F.countDistinct("_record_hash").alias("payloads"))
        )
        conflict_ids = category_groups.where(F.col("payloads") > 1).select("categoria_id")
        category_duplicates, category_conflicts = category_duplicate_profile(categorias_prepared)

        categories_evidence = with_category_rules(categorias_prepared, conflict_ids).cache()
        categorias_dedup, _ = deterministic_latest(
            categories_evidence, ["categoria_id"], "fecha_actualizacion"
        )
        productos_dedup, product_duplicates = deterministic_latest(
            productos_prepared, ["producto_id"], "fecha_actualizacion"
        )
        categories_checked = categorias_dedup.cache()
        products_checked = with_product_rules(
            productos_dedup,
            categories_checked.where(F.size("_quality_rule_ids") == 0),
        ).cache()
        try:
            category_actions = {
                "categoria_id_required": "FAIL",
                "categoria_updated_at_valid": "FAIL",
                "categoria_name_required": "QUARANTINE",
                "categoria_state_valid": "QUARANTINE",
                "categoria_parent_not_self": "QUARANTINE",
                "categoria_conflicting_duplicate": "FAIL",
            }
            product_actions = {
                "producto_id_required": "FAIL",
                "producto_updated_at_valid": "FAIL",
                "producto_name_required": "QUARANTINE",
                "producto_category_required": "QUARANTINE",
                "producto_category_exists": "QUARANTINE",
                "producto_currency_valid": "QUARANTINE",
                "producto_price_valid": "QUARANTINE",
                "producto_state_valid": "QUARANTINE",
            }
            metrics = metric_rows(
                spark,
                quality_run_id,
                batch_id,
                "categorias",
                categories_evidence,
                category_actions,
                {
                    "categoria_duplicate": category_duplicates,
                    "categoria_conflict": category_conflicts,
                },
            ).unionByName(
                metric_rows(
                    spark,
                    quality_run_id,
                    batch_id,
                    "productos",
                    products_checked,
                    product_actions,
                    {"producto_duplicate": product_duplicates},
                )
            )
            quarantine = _quarantine(categories_evidence, "categorias", quality_run_id).unionByName(
                _quarantine(products_checked, "productos", quality_run_id)
            )
            metadata = {
                "capability": "retail/productos",
                "batch_id": batch_id,
                "quality_run_id": quality_run_id,
            }
            replace_where_value(
                metrics,
                f"{catalog}.silver.productos_quality_metrics",
                "quality_run_id",
                quality_run_id,
                metadata,
            )
            replace_where_value(
                quarantine,
                f"{catalog}.silver.productos_quarantine",
                "_quality_run_id",
                quality_run_id,
                metadata,
            )

            fail_count = (
                categories_evidence.where(F.size("_fail_rule_ids") > 0).count()
                + products_checked.where(F.size("_fail_rule_ids") > 0).count()
            )
            if fail_count:
                raise QualityGateError(f"Batch {batch_id} failed {fail_count} mandatory checks")

            categories_curated = _curated(categories_checked, quality_run_id)
            products_curated = _curated(products_checked, quality_run_id)
            replace_where_value(
                categories_curated,
                f"{catalog}.silver.categorias_curated",
                "_source_batch_id",
                batch_id,
                metadata,
            )
            replace_where_value(
                products_curated,
                f"{catalog}.silver.productos_curated",
                "_source_batch_id",
                batch_id,
                metadata,
            )
            return SilverResult(
                batch_id,
                quality_run_id,
                products_curated.count(),
                categories_curated.count(),
                quarantine.count(),
            )
        finally:
            categories_evidence.unpersist()
            categories_checked.unpersist()
            products_checked.unpersist()
    finally:
        productos_prepared.unpersist()
        categorias_prepared.unpersist()
