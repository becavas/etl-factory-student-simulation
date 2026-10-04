"""Typed Silver publication and explicit quality rules for retail/clientes."""

from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from enterprise_fabric.retail.clientes.schemas import CLIENTES_SOURCE_COLUMNS
from enterprise_fabric.shared.delta import replace_where_value
from enterprise_fabric.shared.identifiers import require_safe_value
from enterprise_fabric.shared.spark import deterministic_latest, normalized_text

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
ALLOWED_STATES = ("ACTIVO", "INACTIVO")


class QualityGateError(RuntimeError):
    """Raised after evidence is persisted for mandatory rule failures."""


@dataclass(frozen=True)
class SilverResult:
    batch_id: str
    quality_run_id: str
    curated_count: int
    quarantined_count: int


def prepare(raw: DataFrame) -> DataFrame:
    payload = F.to_json(
        F.struct(*(F.col(column) for column in CLIENTES_SOURCE_COLUMNS)),
        {"ignoreNullFields": "false"},
    )
    return raw.select(
        normalized_text(F.col("cliente_id")).alias("cliente_id"),
        normalized_text(F.col("nombres")).alias("nombres"),
        normalized_text(F.col("apellidos")).alias("apellidos"),
        F.lower(normalized_text(F.col("email"))).alias("email"),
        F.expr("try_cast(nullif(trim(fecha_nacimiento), '') AS DATE)").alias("fecha_nacimiento"),
        F.upper(normalized_text(F.col("pais_codigo"))).alias("pais_codigo"),
        F.upper(normalized_text(F.col("estado"))).alias("estado"),
        F.try_to_timestamp(
            normalized_text(F.col("fecha_actualizacion")),
            F.lit("yyyy-MM-dd'T'HH:mm:ssX"),
        ).alias("fecha_actualizacion"),
        payload.alias("_raw_payload"),
        "_source_system",
        "_source_file_path",
        "_source_file_modification_time",
        "_ingestion_batch_id",
        "_ingestion_run_id",
        "_ingested_at_utc",
        "_record_hash",
    )


def deduplicate(prepared: DataFrame) -> tuple[DataFrame, int]:
    return deterministic_latest(prepared, ["cliente_id"], "fecha_actualizacion")


def evaluate(prepared: DataFrame) -> tuple[DataFrame, dict[str, int], int]:
    rules = {
        "cliente_id_required": (
            "FAIL",
            F.col("cliente_id").isNull(),
        ),
        "cliente_updated_at_valid": (
            "FAIL",
            F.col("fecha_actualizacion").isNull(),
        ),
        "cliente_name_required": (
            "QUARANTINE",
            F.col("nombres").isNull() | F.col("apellidos").isNull(),
        ),
        "cliente_email_valid": (
            "QUARANTINE",
            F.col("email").isNull() | ~F.col("email").rlike(EMAIL_PATTERN),
        ),
        "cliente_birth_date_valid": (
            "QUARANTINE",
            F.col("fecha_nacimiento").isNull()
            | (F.col("fecha_nacimiento") < F.lit("1900-01-01"))
            | (F.col("fecha_nacimiento") > F.current_date()),
        ),
        "cliente_country_valid": (
            "QUARANTINE",
            F.col("pais_codigo").isNull() | ~F.col("pais_codigo").rlike("^[A-Z]{2}$"),
        ),
        "cliente_state_valid": (
            "QUARANTINE",
            F.col("estado").isNull() | ~F.col("estado").isin(*ALLOWED_STATES),
        ),
    }

    evaluated: dict[str, int] = {}
    rule_arrays = []
    fail_arrays = []
    for rule_id, (action, condition) in rules.items():
        evaluated[rule_id] = prepared.where(condition).count()
        rule_arrays.append(F.when(condition, F.lit(rule_id)))
        if action == "FAIL":
            fail_arrays.append(F.when(condition, F.lit(rule_id)))

    checked = prepared.withColumn(
        "_quality_rule_ids",
        F.array_compact(F.array(*rule_arrays)),
    ).withColumn(
        "_fail_rule_ids",
        F.array_compact(F.array(*fail_arrays)),
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
    observed_at = spark.sql("SELECT current_timestamp() AS ts").first()["ts"]
    actions = {
        "cliente_id_required": "FAIL",
        "cliente_updated_at_valid": "FAIL",
        "cliente_name_required": "QUARANTINE",
        "cliente_email_valid": "QUARANTINE",
        "cliente_birth_date_valid": "QUARANTINE",
        "cliente_country_valid": "QUARANTINE",
        "cliente_state_valid": "QUARANTINE",
    }
    rows = [
        (
            quality_run_id,
            batch_id,
            "clientes",
            "cliente_duplicate",
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
                "clientes",
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
    batch_id = require_safe_value(batch_id, "batch_id")
    quality_run_id = require_safe_value(quality_run_id, "quality_run_id")
    raw = spark.table(f"{catalog}.bronze.clientes_raw").where(
        F.col("_ingestion_batch_id") == batch_id
    )
    if raw.limit(1).count() == 0:
        raise ValueError(f"Bronze batch not found: {batch_id}")
    run_ids = [row[0] for row in raw.select("_ingestion_run_id").distinct().collect()]
    if len(run_ids) != 1:
        raise ValueError(f"Bronze batch {batch_id} has multiple ingestion run IDs")

    prepared = prepare(raw).cache()
    try:
        total = prepared.count()
        deduplicated, duplicate_count = deduplicate(prepared)
        checked, evaluated, fail_count = evaluate(deduplicated)
        metrics = build_metrics(spark, quality_run_id, batch_id, total, duplicate_count, evaluated)
        quarantine = checked.where(F.size("_quality_rule_ids") > 0).select(
            F.lit("clientes").alias("entity"),
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
            .drop("_raw_payload", "_quality_rule_ids", "_fail_rule_ids")
            .withColumnRenamed("_ingestion_batch_id", "_source_batch_id")
            .withColumn("_quality_run_id", F.lit(quality_run_id))
            .withColumn("_curated_at_utc", F.current_timestamp())
        )
        metadata = {
            "capability": "retail/clientes",
            "batch_id": batch_id,
            "quality_run_id": quality_run_id,
        }
        replace_where_value(
            metrics,
            f"{catalog}.silver.clientes_quality_metrics",
            "quality_run_id",
            quality_run_id,
            metadata,
        )
        replace_where_value(
            quarantine,
            f"{catalog}.silver.clientes_quarantine",
            "_quality_run_id",
            quality_run_id,
            metadata,
        )
        quarantined_count = quarantine.count()
        if fail_count:
            raise QualityGateError(f"Batch {batch_id} failed {fail_count} mandatory cliente checks")
        replace_where_value(
            curated,
            f"{catalog}.silver.clientes_curated",
            "_source_batch_id",
            batch_id,
            metadata,
        )
        return SilverResult(batch_id, quality_run_id, curated.count(), quarantined_count)
    finally:
        prepared.unpersist()
