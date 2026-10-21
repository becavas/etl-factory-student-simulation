"""Typed Silver publication and explicit quality rules for retail/devoluciones."""

from dataclasses import dataclass
from decimal import Decimal

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from enterprise_fabric.retail.devoluciones.schemas import DEVOLUCIONES_SOURCE_COLUMNS
from enterprise_fabric.shared.delta import replace_where_value
from enterprise_fabric.shared.identifiers import require_safe_value
from enterprise_fabric.shared.spark import deterministic_latest, normalized_text

ALLOWED_STATES = ("SOLICITADA", "APROBADA", "RECHAZADA", "PROCESADA")


class QualityGateError(RuntimeError):
    """Raised after evidence is persisted for mandatory rule failures."""


@dataclass(frozen=True)
class SilverResult:
    batch_id: str
    quality_run_id: str
    curated_count: int
    quarantined_count: int


def prepare(raw: DataFrame) -> DataFrame:
    """Normalize fields, parse typed representations and attach raw payload."""
    payload = F.to_json(
        F.struct(*(F.col(column) for column in DEVOLUCIONES_SOURCE_COLUMNS)),
        {"ignoreNullFields": "false"},
    )
    return raw.select(
        normalized_text(F.col("devolucion_id")).alias("devolucion_id"),
        normalized_text(F.col("pedido_id")).alias("pedido_id"),
        normalized_text(F.col("producto_id")).alias("producto_id"),
        F.expr("try_cast(nullif(trim(fecha_devolucion), '') AS DATE)").alias("fecha_devolucion"),
        normalized_text(F.col("motivo")).alias("motivo"),
        F.upper(normalized_text(F.col("estado"))).alias("estado"),
        F.expr("try_cast(nullif(trim(importe_reembolsado), '') AS DECIMAL(18,2))").alias(
            "importe_reembolsado"
        ),
        F.upper(normalized_text(F.col("moneda"))).alias("moneda"),
        F.coalesce(
            F.try_to_timestamp(
                normalized_text(F.col("updated_at")),
                F.lit("yyyy-MM-dd'T'HH:mm:ssX"),
            ),
            F.try_to_timestamp(normalized_text(F.col("updated_at"))),
        ).alias("updated_at"),
        payload.alias("_raw_payload"),
        F.col("_source_system"),
        F.col("_source_file_path"),
        F.col("_source_file_modification_time"),
        F.col("_ingestion_batch_id"),
        F.col("_ingestion_run_id"),
        F.col("_ingested_at_utc"),
        F.col("_record_hash"),
    )


def detect_conflicts(prepared: DataFrame) -> DataFrame:
    """Detect keys where multiple differing payloads share the maximum updated_at."""
    keyed = prepared.where(F.col("devolucion_id").isNotNull() & F.col("updated_at").isNotNull())
    window_max = Window.partitionBy("devolucion_id")
    with_max = keyed.withColumn("_max_updated_at", F.max("updated_at").over(window_max))
    candidates = with_max.where(F.col("updated_at") == F.col("_max_updated_at"))
    conflict_groups = (
        candidates.groupBy("devolucion_id")
        .agg(F.countDistinct("_record_hash").alias("payloads"))
        .where(F.col("payloads") > 1)
        .select("devolucion_id")
    )
    return conflict_groups


def deduplicate(prepared: DataFrame) -> tuple[DataFrame, int]:
    """Tag tie conflicts and deterministically select latest record per devolucion_id."""
    conflicts = detect_conflicts(prepared)
    tagged = prepared.join(
        conflicts.withColumn("_has_tie_conflict", F.lit(True)),
        on="devolucion_id",
        how="left",
    ).withColumn("_has_tie_conflict", F.coalesce(F.col("_has_tie_conflict"), F.lit(False)))

    deduplicated, duplicate_count = deterministic_latest(tagged, ["devolucion_id"], "updated_at")
    return deduplicated, duplicate_count


def evaluate(
    prepared: DataFrame,
    pedidos_curated: DataFrame | None = None,
    batch_id: str | None = None,
) -> tuple[DataFrame, dict[str, int], int]:
    """Evaluate quality rules and return tagged DataFrame, counts and fail count."""
    frame = prepared
    if "_has_tie_conflict" not in frame.columns:
        frame = frame.withColumn("_has_tie_conflict", F.lit(False))

    if pedidos_curated is not None and batch_id is not None:
        known_pedidos = (
            pedidos_curated.where(F.col("_source_batch_id") == batch_id)
            .select("pedido_id")
            .where(F.col("pedido_id").isNotNull())
            .distinct()
            .withColumn("_pedido_exists", F.lit(True))
        )
        joined = frame.join(known_pedidos, on="pedido_id", how="left")
    elif pedidos_curated is not None:
        known_pedidos = (
            pedidos_curated.select("pedido_id")
            .where(F.col("pedido_id").isNotNull())
            .distinct()
            .withColumn("_pedido_exists", F.lit(True))
        )
        joined = frame.join(known_pedidos, on="pedido_id", how="left")
    else:
        # If pedido_id is not null, consider it present for isolated rule tests
        joined = frame.withColumn(
            "_pedido_exists",
            F.when(F.col("pedido_id").isNotNull(), F.lit(True)),
        )

    rules = {
        "devolucion_id_required": (
            "FAIL",
            F.col("devolucion_id").isNull(),
        ),
        "devolucion_updated_at_valid": (
            "FAIL",
            F.col("updated_at").isNull(),
        ),
        "devolucion_producto_required": (
            "FAIL",
            F.col("producto_id").isNull(),
        ),
        "devolucion_fecha_valid": (
            "QUARANTINE",
            F.col("fecha_devolucion").isNull(),
        ),
        "devolucion_motivo_required": (
            "QUARANTINE",
            F.col("motivo").isNull(),
        ),
        "devolucion_estado_valid": (
            "FAIL",
            F.col("estado").isNull() | ~F.col("estado").isin(*ALLOWED_STATES),
        ),
        "devolucion_importe_valid": (
            "QUARANTINE",
            F.col("importe_reembolsado").isNull()
            | (F.col("importe_reembolsado") < F.lit(Decimal("0.00"))),
        ),
        "devolucion_moneda_valid": (
            "QUARANTINE",
            F.col("moneda").isNull() | (F.col("moneda") != "PEN"),
        ),
        "devolucion_pedido_exists": (
            "FAIL",
            F.col("pedido_id").isNull() | F.col("_pedido_exists").isNull(),
        ),
        "devolucion_tie_conflict": (
            "FAIL",
            F.col("_has_tie_conflict") == True,  # noqa: E712
        ),
    }

    evaluated: dict[str, int] = {}
    rule_arrays = []
    fail_arrays = []
    for rule_id, (action, condition) in rules.items():
        evaluated[rule_id] = joined.where(condition).count()
        rule_arrays.append(F.when(condition, F.lit(rule_id)))
        if action == "FAIL":
            fail_arrays.append(F.when(condition, F.lit(rule_id)))

    checked = (
        joined.withColumn(
            "_quality_rule_ids",
            F.array_compact(F.array(*rule_arrays)),
        )
        .withColumn(
            "_fail_rule_ids",
            F.array_compact(F.array(*fail_arrays)),
        )
        .drop("_pedido_exists")
    )
    fail_count = sum(
        evaluated[rule_id] for rule_id, (action, _) in rules.items() if action == "FAIL"
    )
    return checked, evaluated, fail_count


def build_metrics(
    spark: SparkSession,
    quality_run_id: str,
    batch_id: str,
    total: int,
    duplicate_count: int,
    evaluated: dict[str, int],
) -> DataFrame:
    """Build quality metrics DataFrame without leaking sensitive field values."""
    observed_at = spark.sql("SELECT current_timestamp() AS ts").first()["ts"]
    actions = {
        "devolucion_id_required": "FAIL",
        "devolucion_updated_at_valid": "FAIL",
        "devolucion_producto_required": "FAIL",
        "devolucion_fecha_valid": "QUARANTINE",
        "devolucion_motivo_required": "QUARANTINE",
        "devolucion_estado_valid": "FAIL",
        "devolucion_importe_valid": "QUARANTINE",
        "devolucion_moneda_valid": "QUARANTINE",
        "devolucion_pedido_exists": "FAIL",
        "devolucion_tie_conflict": "FAIL",
    }
    rows = [
        (
            quality_run_id,
            batch_id,
            "devoluciones",
            "devolucion_duplicate",
            "OBSERVE",
            duplicate_count,
            total,
            observed_at,
        )
    ]
    for rule_id, failed in evaluated.items():
        rows.append(
            (
                quality_run_id,
                batch_id,
                "devoluciones",
                rule_id,
                actions[rule_id],
                failed,
                total,
                observed_at,
            )
        )
    return spark.createDataFrame(
        rows,
        "quality_run_id string, batch_id string, entity string, rule_id string, "
        "action string, failed_records long, total_records long, observed_at_utc timestamp",
    )


def publish_silver(
    spark: SparkSession,
    catalog: str,
    batch_id: str,
    quality_run_id: str,
) -> SilverResult:
    """Validate, evaluate quality rules, publish quarantine and metrics, then curated."""
    batch_id = require_safe_value(batch_id, "batch_id")
    quality_run_id = require_safe_value(quality_run_id, "quality_run_id")

    raw = spark.table(f"{catalog}.bronze.devoluciones_raw").where(
        F.col("_ingestion_batch_id") == batch_id
    )
    if raw.limit(1).count() == 0:
        raise ValueError(f"Bronze batch not found: {batch_id}")
    run_ids = [row[0] for row in raw.select("_ingestion_run_id").distinct().collect()]
    if len(run_ids) != 1:
        raise ValueError(f"Bronze batch {batch_id} has multiple ingestion run IDs")

    pedidos_curated = spark.table(f"{catalog}.silver.pedidos_curated").where(
        F.col("_source_batch_id") == batch_id
    )

    prepared = prepare(raw).cache()
    try:
        total = prepared.count()
        deduplicated, duplicate_count = deduplicate(prepared)
        checked, evaluated, fail_count = evaluate(deduplicated, pedidos_curated, batch_id)
        metrics = build_metrics(spark, quality_run_id, batch_id, total, duplicate_count, evaluated)
        quarantine = checked.where(F.size("_quality_rule_ids") > 0).select(
            F.lit("devoluciones").alias("entity"),
            "_raw_payload",
            "_quality_rule_ids",
            F.col("_ingestion_batch_id").alias("_source_batch_id"),
            "_ingestion_run_id",
            "_source_file_path",
            "_record_hash",
            F.lit(quality_run_id).alias("_quality_run_id"),
            F.current_timestamp().alias("_quarantined_at_utc"),
        )
        curated = (
            checked.where(F.size("_quality_rule_ids") == 0)
            .drop("_raw_payload", "_quality_rule_ids", "_fail_rule_ids", "_has_tie_conflict")
            .withColumnRenamed("_ingestion_batch_id", "_source_batch_id")
            .withColumn("batch_id", F.lit(batch_id))
            .withColumn("_quality_run_id", F.lit(quality_run_id))
            .withColumn("_curated_at_utc", F.current_timestamp())
        )
        metadata = {
            "capability": "retail/devoluciones",
            "batch_id": batch_id,
            "quality_run_id": quality_run_id,
        }
        replace_where_value(
            metrics,
            f"{catalog}.silver.devoluciones_quality_metrics",
            "quality_run_id",
            quality_run_id,
            metadata,
        )
        replace_where_value(
            quarantine,
            f"{catalog}.silver.devoluciones_quarantine",
            "_quality_run_id",
            quality_run_id,
            metadata,
        )
        quarantined_count = quarantine.count()
        if fail_count:
            raise QualityGateError(
                f"Batch {batch_id} failed {fail_count} mandatory devoluciones checks"
            )
        replace_where_value(
            curated,
            f"{catalog}.silver.devoluciones_curated",
            "_source_batch_id",
            batch_id,
            metadata,
        )
        return SilverResult(batch_id, quality_run_id, curated.count(), quarantined_count)
    finally:
        prepared.unpersist()
