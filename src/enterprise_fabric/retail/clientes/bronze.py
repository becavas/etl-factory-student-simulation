"""Idempotent Bronze ingestion for retail/clientes."""

from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from enterprise_fabric.retail.clientes.schemas import (
    CLIENTES_SOURCE_COLUMNS,
    CLIENTES_SOURCE_SCHEMA,
)
from enterprise_fabric.shared.delta import replace_where_value
from enterprise_fabric.shared.identifiers import require_safe_value


@dataclass(frozen=True)
class BronzeResult:
    batch_id: str
    run_id: str
    row_count: int
    table_name: str


def validate_identifier(value: str, field: str) -> str:
    return require_safe_value(value, field)


def read_batch(
    spark: SparkSession,
    path: str,
    batch_id: str,
    run_id: str,
) -> DataFrame:
    raw = (
        spark.read.format("csv")
        .schema(CLIENTES_SOURCE_SCHEMA)
        .option("header", "true")
        .option("enforceSchema", "false")
        .option("mode", "FAILFAST")
        .option("encoding", "UTF-8")
        .load(path)
    )
    source = F.struct(*(F.col(column) for column in CLIENTES_SOURCE_COLUMNS))
    return raw.select(
        *CLIENTES_SOURCE_COLUMNS,
        F.lit("clientes_source").alias("_source_system"),
        F.col("_metadata.file_path").alias("_source_file_path"),
        F.col("_metadata.file_modification_time").alias("_source_file_modification_time"),
        F.lit(batch_id).alias("_ingestion_batch_id"),
        F.lit(run_id).alias("_ingestion_run_id"),
        F.current_timestamp().alias("_ingested_at_utc"),
        F.sha2(F.to_json(source, {"ignoreNullFields": "false"}), 256).alias("_record_hash"),
    )


def replace_batch(df: DataFrame, table_name: str, batch_id: str, run_id: str) -> None:
    batch_id = require_safe_value(batch_id, "batch_id")
    metadata = {
        "capability": "retail/clientes",
        "batch_id": batch_id,
        "run_id": run_id,
    }
    replace_where_value(
        df,
        table_name,
        "_ingestion_batch_id",
        batch_id,
        metadata,
    )


def ingest_bronze(
    spark: SparkSession,
    catalog: str,
    source_volume_path: str,
    batch_id: str,
    run_id: str,
) -> BronzeResult:
    batch_id = require_safe_value(batch_id, "batch_id")
    run_id = require_safe_value(run_id, "run_id")
    source_path = f"{source_volume_path.rstrip('/')}/clientes/batch_id={batch_id}"
    clientes = read_batch(spark, source_path, batch_id, run_id).cache()
    try:
        row_count = clientes.count()
        if row_count == 0:
            raise ValueError(f"No clientes found for batch {batch_id}")
        table_name = f"{catalog}.bronze.clientes_raw"
        replace_batch(clientes, table_name, batch_id, run_id)
        return BronzeResult(batch_id, run_id, row_count, table_name)
    finally:
        clientes.unpersist()
