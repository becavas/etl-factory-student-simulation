"""Idempotent Bronze ingestion for retail/clientes."""

import json
import re
from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from enterprise_fabric.retail.clientes.schemas import (
    CLIENTES_SOURCE_COLUMNS,
    CLIENTES_SOURCE_SCHEMA,
)

BATCH_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


@dataclass(frozen=True)
class BronzeResult:
    batch_id: str
    run_id: str
    row_count: int
    table_name: str


def validate_identifier(value: str, field: str) -> str:
    if not BATCH_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must contain only safe identifier characters")
    return value


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
    batch_id = validate_identifier(batch_id, "batch_id")
    metadata = json.dumps(
        {"capability": "retail/clientes", "batch_id": batch_id, "run_id": run_id},
        sort_keys=True,
    )
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("replaceWhere", f"_ingestion_batch_id = '{batch_id}'")
        .option("userMetadata", metadata)
        .saveAsTable(table_name)
    )


def ingest_bronze(
    spark: SparkSession,
    catalog: str,
    source_volume_path: str,
    batch_id: str,
    run_id: str,
) -> BronzeResult:
    batch_id = validate_identifier(batch_id, "batch_id")
    run_id = validate_identifier(run_id, "run_id")
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
