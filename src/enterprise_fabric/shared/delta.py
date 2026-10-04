"""Delta publication primitives with explicit execution metadata."""

import json

from pyspark.sql import DataFrame

from enterprise_fabric.shared.identifiers import require_safe_value


def replace_where_value(
    frame: DataFrame,
    table_name: str,
    predicate_column: str,
    predicate_value: str,
    metadata: dict[str, str],
) -> None:
    value = require_safe_value(predicate_value, predicate_column)
    try:
        columns = frame.columns
    except (AttributeError, ValueError):
        columns = None
    if columns is not None and predicate_column not in columns:
        raise ValueError(f"predicate column not present: {predicate_column}")
    if not predicate_column.replace("_", "a").isalnum():
        raise ValueError("predicate_column must be a simple column name")
    if not metadata:
        raise ValueError("metadata must not be empty")
    (
        frame.write.format("delta")
        .mode("overwrite")
        .option("replaceWhere", f"{predicate_column} = '{value}'")
        .option("userMetadata", json.dumps(metadata, sort_keys=True))
        .saveAsTable(table_name)
    )
