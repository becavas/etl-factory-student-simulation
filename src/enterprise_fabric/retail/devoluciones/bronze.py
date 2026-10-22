"""Idempotent Bronze ingestion for retail/devoluciones."""

import csv
import io
from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

from enterprise_fabric.retail.devoluciones.schemas import (
    DEVOLUCIONES_SOURCE_COLUMNS,
    DEVOLUCIONES_SOURCE_SCHEMA,
)
from enterprise_fabric.shared.delta import replace_where_value
from enterprise_fabric.shared.identifiers import require_safe_value


class IngestionError(RuntimeError):
    """Raised when ingestion fails due to malformed input, missing headers or missing batches."""


@dataclass(frozen=True)
class BronzeResult:
    batch_id: str
    run_id: str
    row_count: int
    table_name: str


def validate_identifier(value: str, field: str) -> str:
    """Validate identifier against strict naming rules."""
    return require_safe_value(value, field)


def validate_csv_header(spark: SparkSession, path: str, batch_id: str) -> None:
    """Validate that source CSV contains exactly the declared header columns.

    Checks the first line as text without triggering Spark's CSVHeaderChecker
    which would print data values to stderr / exception if the header is missing.
    """
    try:
        first_rows = spark.read.text(path).limit(1).collect()
    except Exception as exc:
        raise IngestionError(f"Failed to access source path for batch {batch_id}: {exc}") from None

    if not first_rows:
        raise IngestionError(
            f"Source batch {batch_id} is empty or missing data files. "
            "Raw record content redacted for privacy."
        )

    first_line = first_rows[0][0].lstrip("\ufeff").strip()
    reader = csv.reader(io.StringIO(first_line))
    header_cols = [col.strip() for col in next(reader, [])]

    if header_cols != list(DEVOLUCIONES_SOURCE_COLUMNS):
        raise IngestionError(
            f"Invalid or missing CSV header in batch {batch_id}. "
            "Expected declared columns. Raw record content redacted for privacy."
        )


def read_batch(
    spark: SparkSession,
    path: str,
    batch_id: str,
    run_id: str,
) -> DataFrame:
    """Read one immutable CSV batch and append technical lineage columns.

    Validates header explicitly and uses PERMISSIVE mode with a dedicated
    corrupt record column to detect malformed inputs without leaking sensitive
    column values (such as motivo) into Spark task error logs or stack traces.
    """
    validate_csv_header(spark, path, batch_id)

    schema_with_corrupt = StructType(
        list(DEVOLUCIONES_SOURCE_SCHEMA.fields)
        + [StructField("_corrupt_record", StringType(), True)]
    )
    raw = (
        spark.read.format("csv")
        .schema(schema_with_corrupt)
        .option("header", "true")
        .option("enforceSchema", "false")
        .option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", "_corrupt_record")
        .option("encoding", "UTF-8")
        .load(path)
    )
    source = F.struct(*(F.col(column) for column in DEVOLUCIONES_SOURCE_COLUMNS))
    safe_hash = F.when(
        F.col("_corrupt_record").isNotNull(),
        F.raise_error(
            F.lit(
                f"Malformed CSV record detected during ingestion of batch {batch_id}. "
                "Raw record content redacted for privacy."
            )
        ),
    ).otherwise(F.sha2(F.to_json(source, {"ignoreNullFields": "false"}), 256))
    return raw.select(
        *DEVOLUCIONES_SOURCE_COLUMNS,
        F.lit(batch_id).alias("batch_id"),
        F.lit("devoluciones_source").alias("_source_system"),
        F.col("_metadata.file_path").alias("_source_file_path"),
        F.col("_metadata.file_modification_time").alias("_source_file_modification_time"),
        F.lit(batch_id).alias("_ingestion_batch_id"),
        F.lit(run_id).alias("_ingestion_run_id"),
        F.current_timestamp().alias("_ingested_at_utc"),
        safe_hash.alias("_record_hash"),
    )


def replace_batch(df: DataFrame, table_name: str, batch_id: str, run_id: str) -> None:
    """Atomically replace one batch partition in Bronze Delta table."""
    batch_id = require_safe_value(batch_id, "batch_id")
    metadata = {
        "capability": "retail/devoluciones",
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
    """Validate input, read source batch, and publish to bronze.devoluciones_raw."""
    batch_id = require_safe_value(batch_id, "batch_id")
    run_id = require_safe_value(run_id, "run_id")
    source_path = f"{source_volume_path.rstrip('/')}/devoluciones/batch_id={batch_id}"
    devoluciones = read_batch(spark, source_path, batch_id, run_id).cache()
    try:
        row_count = devoluciones.count()
        if row_count == 0:
            raise ValueError(f"No devoluciones found for batch {batch_id}")
        table_name = f"{catalog}.bronze.devoluciones_raw"
        replace_batch(devoluciones, table_name, batch_id, run_id)
        return BronzeResult(batch_id, run_id, row_count, table_name)
    except IngestionError:
        raise
    except Exception as exc:
        msg = str(exc)
        if "Malformed CSV record detected" in msg:
            raise IngestionError(
                f"Ingestion failed for batch {batch_id}: malformed records detected in source. "
                "Raw record content redacted for privacy."
            ) from None
        raise
    finally:
        devoluciones.unpersist()
