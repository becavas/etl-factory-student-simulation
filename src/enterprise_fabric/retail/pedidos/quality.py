"""Small, explicit data-quality primitives for retail/pedidos."""

from dataclasses import dataclass

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from enterprise_fabric.shared.spark import normalized_text


@dataclass(frozen=True)
class Rule:
    rule_id: str
    action: str
    invalid_when: Column


METRICS_SCHEMA = StructType(
    [
        StructField("quality_run_id", StringType(), False),
        StructField("batch_id", StringType(), False),
        StructField("entity", StringType(), False),
        StructField("rule_id", StringType(), False),
        StructField("action", StringType(), False),
        StructField("failed_records", LongType(), False),
        StructField("total_records", LongType(), False),
        StructField("observed_at_utc", TimestampType(), False),
    ]
)


def normalize_text(column: Column) -> Column:
    """Trim a source string and represent blanks as null."""
    return normalized_text(column)


def duplicate_excess_count(df: DataFrame, keys: list[str]) -> int:
    """Count rows exceeding one occurrence for complete business keys."""
    complete_key = F.lit(True)
    for key in keys:
        complete_key = complete_key & F.col(key).isNotNull()
    row = (
        df.where(complete_key)
        .groupBy(*keys)
        .count()
        .select(F.coalesce(F.sum(F.greatest(F.col("count") - 1, F.lit(0))), F.lit(0)))
        .first()
    )
    return int(row[0])


def rule_counts(df: DataFrame, rules: list[Rule]) -> dict[str, int]:
    """Evaluate all rules for one entity in a single aggregation."""
    if not rules:
        return {}
    row = df.agg(
        *(
            F.coalesce(
                F.sum(F.when(rule.invalid_when, F.lit(1)).otherwise(F.lit(0))),
                F.lit(0),
            ).alias(rule.rule_id)
            for rule in rules
        )
    ).first()
    return {rule.rule_id: int(row[rule.rule_id]) for rule in rules}


def add_rule_ids(df: DataFrame, rules: list[Rule]) -> DataFrame:
    """Attach array of violated rule IDs to each row."""
    rule_expressions = [F.when(rule.invalid_when, F.lit(rule.rule_id)) for rule in rules]
    return df.withColumn(
        "_quality_rule_ids",
        F.array_compact(F.array(*rule_expressions)),
    )


def build_metrics(
    spark: SparkSession,
    quality_run_id: str,
    batch_id: str,
    entity: str,
    total_records: int,
    rules: list[Rule],
    counts: dict[str, int],
) -> DataFrame:
    """Return explicit metric rows preserving one common observation timestamp."""
    observed_at = spark.sql("SELECT current_timestamp() AS ts").first()["ts"]
    rows = [
        (
            quality_run_id,
            batch_id,
            entity,
            rule.rule_id,
            rule.action,
            counts[rule.rule_id],
            total_records,
            observed_at,
        )
        for rule in rules
    ]
    return spark.createDataFrame(rows, METRICS_SCHEMA)
