"""Batch Bronze ingestion for retail/pedidos."""

from __future__ import annotations

from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType

from enterprise_fabric.retail.pedidos.schemas import (
    PEDIDO_ITEMS_SOURCE_COLUMNS,
    PEDIDO_ITEMS_SOURCE_SCHEMA,
    PEDIDOS_SOURCE_COLUMNS,
    PEDIDOS_SOURCE_SCHEMA,
)
from enterprise_fabric.shared.delta import replace_where_value
from enterprise_fabric.shared.identifiers import require_safe_value


@dataclass(frozen=True)
class BronzeResult:
    batch_id: str
    run_id: str
    pedidos_count: int
    pedido_items_count: int
    pedidos_table: str
    pedido_items_table: str


def validate_batch_id(batch_id: str) -> str:
    """Validate the identifier before using it in paths and SQL predicates."""
    return require_safe_value(batch_id, "batch_id")


def parse_bool(value: str) -> bool:
    """Parse an explicit Job string parameter without truthy surprises."""
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError("Boolean parameters must be 'true' or 'false'")
    return normalized == "true"


def read_source_batch(
    spark: SparkSession,
    path: str,
    schema: StructType,
    source_columns: tuple[str, ...],
    batch_id: str,
    run_id: str,
) -> DataFrame:
    """Read one immutable CSV batch and append technical lineage columns."""
    raw = (
        spark.read.format("csv")
        .schema(schema)
        .option("header", "true")
        .option("enforceSchema", "false")
        .option("mode", "FAILFAST")
        .option("encoding", "UTF-8")
        .load(path)
    )
    source_struct = F.struct(*(F.col(column) for column in source_columns))
    return raw.select(
        *source_columns,
        F.lit("pedidos_source").alias("_source_system"),
        F.col("_metadata.file_path").alias("_source_file_path"),
        F.col("_metadata.file_modification_time").alias("_source_file_modification_time"),
        F.lit(batch_id).alias("_ingestion_batch_id"),
        F.lit(run_id).alias("_ingestion_run_id"),
        F.current_timestamp().alias("_ingested_at_utc"),
        F.sha2(F.to_json(source_struct, {"ignoreNullFields": "false"}), 256).alias("_record_hash"),
    )


def replace_batch(df: DataFrame, table_name: str, batch_id: str, run_id: str) -> None:
    """Atomically replace one batch within one Delta table."""
    validated_batch_id = validate_batch_id(batch_id)
    metadata = {
        "capability": "retail/pedidos",
        "batch_id": batch_id,
        "run_id": run_id,
    }
    replace_where_value(
        df,
        table_name,
        "_ingestion_batch_id",
        validated_batch_id,
        metadata,
    )


def ingest_bronze(
    spark: SparkSession,
    catalog: str,
    source_volume_path: str,
    batch_id: str,
    run_id: str,
    fail_after_pedidos: bool = False,
) -> BronzeResult:
    """Validate both inputs, then publish the two Bronze tables in order."""
    validated_batch_id = validate_batch_id(batch_id)
    run_id = require_safe_value(run_id, "run_id")
    base_path = source_volume_path.rstrip("/")
    pedidos_path = f"{base_path}/pedidos/batch_id={validated_batch_id}"
    items_path = f"{base_path}/pedido_items/batch_id={validated_batch_id}"

    pedidos = read_source_batch(
        spark,
        pedidos_path,
        PEDIDOS_SOURCE_SCHEMA,
        PEDIDOS_SOURCE_COLUMNS,
        validated_batch_id,
        run_id,
    ).cache()
    items = read_source_batch(
        spark,
        items_path,
        PEDIDO_ITEMS_SOURCE_SCHEMA,
        PEDIDO_ITEMS_SOURCE_COLUMNS,
        validated_batch_id,
        run_id,
    ).cache()

    try:
        pedidos_count = pedidos.count()
        items_count = items.count()
        if pedidos_count == 0 or items_count == 0:
            raise ValueError("Both source datasets must contain at least one row")

        pedidos_table = f"{catalog}.bronze.pedidos_raw"
        items_table = f"{catalog}.bronze.pedido_items_raw"
        replace_batch(pedidos, pedidos_table, validated_batch_id, run_id)

        if fail_after_pedidos:
            raise RuntimeError("Controlled failure after pedidos_raw commit")

        replace_batch(items, items_table, validated_batch_id, run_id)
        return BronzeResult(
            batch_id=validated_batch_id,
            run_id=run_id,
            pedidos_count=pedidos_count,
            pedido_items_count=items_count,
            pedidos_table=pedidos_table,
            pedido_items_table=items_table,
        )
    finally:
        pedidos.unpersist()
        items.unpersist()
