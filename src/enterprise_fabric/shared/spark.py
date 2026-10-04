"""Small Spark primitives shared by capabilities."""

from collections.abc import Sequence

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F


def normalized_text(column: Column) -> Column:
    """Trim text and represent an empty string as null."""
    trimmed = F.trim(column)
    return F.when(trimmed == "", F.lit(None)).otherwise(trimmed)


def deterministic_latest(
    frame: DataFrame,
    keys: Sequence[str],
    recency_column: str,
) -> tuple[DataFrame, int]:
    """Keep one complete-key row and preserve incomplete keys for quality rules."""
    if not keys:
        raise ValueError("keys must not be empty")
    missing = [
        name
        for name in (*keys, recency_column, "_source_file_modification_time", "_record_hash")
        if name not in frame.columns
    ]
    if missing:
        raise ValueError(f"missing deduplication columns: {sorted(set(missing))}")

    complete_condition = F.lit(True)
    for key in keys:
        complete_condition = complete_condition & F.col(key).isNotNull()
    complete = frame.where(complete_condition)
    incomplete = frame.where(~complete_condition)

    duplicate_row = (
        complete.groupBy(*keys)
        .count()
        .select(
            F.coalesce(
                F.sum(F.greatest(F.col("count") - F.lit(1), F.lit(0))),
                F.lit(0),
            ).alias("duplicate_count")
        )
        .first()
    )
    window = Window.partitionBy(*keys).orderBy(
        F.col(recency_column).desc_nulls_last(),
        F.col("_source_file_modification_time").desc_nulls_last(),
        F.col("_record_hash").desc(),
    )
    latest = (
        complete.withColumn("_dedup_rank", F.row_number().over(window))
        .where(F.col("_dedup_rank") == 1)
        .drop("_dedup_rank")
    )
    return latest.unionByName(incomplete), int(duplicate_row[0])
