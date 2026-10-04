"""Canonical deterministic keys for retail/ventas."""

from collections.abc import Sequence

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from enterprise_fabric.shared.identifiers import require_safe_value

UNKNOWN_SK = "0" * 64


def canonical_key(namespace: str, columns: Sequence[str]) -> Column:
    """SHA-256 over a versioned JSON struct with stable field order."""
    namespace = require_safe_value(namespace, "namespace")
    if not columns:
        raise ValueError("columns must not be empty")
    payload = F.to_json(
        F.struct(
            *(
                F.col(name).cast("string").alias(f"key_{index}")
                for index, name in enumerate(columns)
            )
        ),
        {"ignoreNullFields": "false"},
    )
    return F.sha2(F.concat(F.lit(f"{namespace}:v1:"), payload), 256)


def payload_hash(namespace: str, columns: Sequence[str]) -> Column:
    return canonical_key(f"payload_{namespace}", columns)


def assert_unique(frame: DataFrame, keys: Sequence[str], label: str) -> None:
    if not keys:
        raise ValueError("keys must not be empty")
    duplicates = frame.groupBy(*keys).count().where(F.col("count") > 1).limit(1)
    if duplicates.count():
        example = duplicates.first().asDict()
        raise ValueError(f"{label} has duplicate MERGE keys: {example}")
