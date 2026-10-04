"""Typed Silver publication and explicit quality rules for retail/clientes."""

import json
from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from enterprise_fabric.retail.clientes.bronze import validate_identifier
from enterprise_fabric.retail.clientes.schemas import CLIENTES_SOURCE_COLUMNS

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


def _text(column_name: str):
    trimmed = F.trim(F.col(column_name))
    return F.when(trimmed == "", F.lit(None)).otherwise(trimmed)


def prepare(raw: DataFrame) -> DataFrame:
    payload = F.to_json(
        F.struct(*(F.col(column) for column in CLIENTES_SOURCE_COLUMNS)),
        {"ignoreNullFields": "false"},
    )
    return raw.select(
        _text("cliente_id").alias("cliente_id"),
        _text("nombres").alias("nombres"),
        _text("apellidos").alias("apellidos"),
        F.lower(_text("email")).alias("email"),
        F.expr("try_cast(nullif(trim(fecha_nacimiento), '') AS DATE)").alias("fecha_nacimiento"),
        F.upper(_text("pais_codigo")).alias("pais_codigo"),
        F.upper(_text("estado")).alias("estado"),
        F.try_to_timestamp(
            _text("fecha_actualizacion"),
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
    complete = prepared.where(F.col("cliente_id").isNotNull())
    incomplete = prepared.where(F.col("cliente_id").isNull())
    duplicate_row = (
        complete.groupBy("cliente_id")
        .count()
        .select(F.coalesce(F.sum(F.greatest(F.col("count") - 1, F.lit(0))), F.lit(0)))
        .first()
    )
    window = Window.partitionBy("cliente_id").orderBy(
        F.col("fecha_actualizacion").desc_nulls_last(),
        F.col("_source_file_modification_time").desc_nulls_last(),
        F.col("_record_hash").desc(),
    )
    latest = (
        complete.withColumn("_rank", F.row_number().over(window))
        .where(F.col("_rank") == 1)
        .drop("_rank")
    )
    return latest.unionByName(incomplete), int(duplicate_row[0])


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
            | (F.col("fecha_nacimiento") < F.lit("1900-01-01").cast("date"))
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
    row = prepared.agg(
        *(F.count(F.when(condition, 1)).alias(rule_id) for rule_id, (_, condition) in rules.items())
    ).first()
    counts = {rule_id: int(row[rule_id]) for rule_id in rules}
    rule_ids = F.array_compact(
        F.array(*(F.when(condition, F.lit(rule_id)) for rule_id, (_, condition) in rules.items()))
    )
    checked = prepared.withColumn("_quality_rule_ids", rule_ids)
    fail_count = sum(counts[rule_id] for rule_id, (action, _) in rules.items() if action == "FAIL")
    actions = {rule_id: action for rule_id, (action, _) in rules.items()}
    return checked, {**counts, "_actions": actions}, fail_count


def build_metrics(
    spark: SparkSession,
    quality_run_id: str,
    batch_id: str,
    total: int,
    duplicate_count: int,
    evaluated: dict,
) -> DataFrame:
    observed_at = spark.sql("SELECT current_timestamp() AS ts").first()["ts"]
    actions = evaluated["_actions"]
    values = [("cliente_duplicate", "OBSERVE", duplicate_count)] + [
        (rule_id, actions[rule_id], count)
        for rule_id, count in evaluated.items()
        if rule_id != "_actions"
    ]
    return spark.createDataFrame(
        [
            (quality_run_id, batch_id, "clientes", rule_id, action, count, total, observed_at)
            for rule_id, action, count in values
        ],
        "quality_run_id string, batch_id string, entity string, rule_id string, "
        "action string, failed_records long, total_records long, observed_at_utc timestamp",
    )


def _replace(df: DataFrame, table: str, predicate: str, metadata: dict) -> None:
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("replaceWhere", predicate)
        .option("userMetadata", json.dumps(metadata, sort_keys=True))
        .saveAsTable(table)
    )


def publish_silver(
    spark: SparkSession,
    catalog: str,
    batch_id: str,
    quality_run_id: str,
) -> SilverResult:
    batch_id = validate_identifier(batch_id, "batch_id")
    quality_run_id = validate_identifier(quality_run_id, "quality_run_id")
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
            .drop("_raw_payload", "_quality_rule_ids")
            .withColumnRenamed("_ingestion_batch_id", "_source_batch_id")
            .withColumn("_quality_run_id", F.lit(quality_run_id))
            .withColumn("_curated_at_utc", F.current_timestamp())
        )
        metadata = {
            "capability": "retail/clientes",
            "batch_id": batch_id,
            "quality_run_id": quality_run_id,
        }
        _replace(
            metrics,
            f"{catalog}.silver.clientes_quality_metrics",
            f"quality_run_id = '{quality_run_id}'",
            metadata,
        )
        _replace(
            quarantine,
            f"{catalog}.silver.clientes_quarantine",
            f"_quality_run_id = '{quality_run_id}'",
            metadata,
        )
        quarantined_count = quarantine.count()
        if fail_count:
            raise QualityGateError(f"Batch {batch_id} failed {fail_count} mandatory cliente checks")
        _replace(
            curated,
            f"{catalog}.silver.clientes_curated",
            f"_source_batch_id = '{batch_id}'",
            metadata,
        )
        return SilverResult(batch_id, quality_run_id, curated.count(), quarantined_count)
    finally:
        prepared.unpersist()
