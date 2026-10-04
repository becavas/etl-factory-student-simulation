"""Idempotent multi-entity Bronze ingestion for retail/productos."""

from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from enterprise_fabric.retail.productos.schemas import (
    CATEGORIAS_SOURCE_COLUMNS,
    CATEGORIAS_SOURCE_SCHEMA,
    PRODUCTOS_SOURCE_COLUMNS,
    PRODUCTOS_SOURCE_SCHEMA,
)
from enterprise_fabric.shared.delta import replace_where_value
from enterprise_fabric.shared.identifiers import require_safe_value


@dataclass(frozen=True)
class BronzeResult:
    batch_id: str
    run_id: str
    productos_count: int
    categorias_count: int


def read_entity(
    spark: SparkSession,
    path: str,
    schema,
    source_columns: tuple[str, ...],
    entity: str,
    batch_id: str,
    run_id: str,
) -> DataFrame:
    raw = (
        spark.read.format("csv")
        .schema(schema)
        .option("header", "true")
        .option("enforceSchema", "false")
        .option("mode", "FAILFAST")
        .option("encoding", "UTF-8")
        .load(path)
    )
    source = F.struct(*(F.col(name) for name in source_columns))
    return raw.select(
        *source_columns,
        F.lit("productos_source").alias("_source_system"),
        F.lit(entity).alias("_source_entity"),
        F.col("_metadata.file_path").alias("_source_file_path"),
        F.col("_metadata.file_modification_time").alias("_source_file_modification_time"),
        F.lit(batch_id).alias("_ingestion_batch_id"),
        F.lit(run_id).alias("_ingestion_run_id"),
        F.current_timestamp().alias("_ingested_at_utc"),
        F.sha2(F.to_json(source, {"ignoreNullFields": "false"}), 256).alias("_record_hash"),
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
    root = source_volume_path.rstrip("/")
    definitions = (
        ("productos", PRODUCTOS_SOURCE_SCHEMA, PRODUCTOS_SOURCE_COLUMNS),
        ("categorias", CATEGORIAS_SOURCE_SCHEMA, CATEGORIAS_SOURCE_COLUMNS),
    )
    frames: dict[str, tuple[DataFrame, int]] = {}
    try:
        for entity, schema, columns in definitions:
            path = f"{root}/{entity}/batch_id={batch_id}"
            frame = read_entity(spark, path, schema, columns, entity, batch_id, run_id).cache()
            frames[entity] = (frame, frame.count())
            if frames[entity][1] == 0:
                raise ValueError(f"No {entity} found for batch {batch_id}")

        metadata = {
            "capability": "retail/productos",
            "batch_id": batch_id,
            "run_id": run_id,
        }
        for entity, (frame, _) in frames.items():
            replace_where_value(
                frame,
                f"{catalog}.bronze.{entity}_raw",
                "_ingestion_batch_id",
                batch_id,
                metadata,
            )
        return BronzeResult(batch_id, run_id, frames["productos"][1], frames["categorias"][1])
    finally:
        for frame, _ in frames.values():
            frame.unpersist()
