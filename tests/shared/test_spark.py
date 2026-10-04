from datetime import datetime

from pyspark.sql import Row
from pyspark.sql import functions as F

from enterprise_fabric.shared.spark import deterministic_latest, normalized_text


def test_normalized_text_trims_and_converts_empty_to_null(spark):
    rows = spark.createDataFrame([(1, "  value  "), (2, "   "), (3, None)], ["position", "raw"])
    result = rows.select("position", normalized_text(F.col("raw")).alias("value")).orderBy(
        "position"
    )
    assert [row.value for row in result.collect()] == [
        "value",
        None,
        None,
    ]


def test_dedup_is_deterministic_and_preserves_incomplete_keys(spark):
    rows = spark.createDataFrame(
        [
            Row(
                id="P-1",
                updated=datetime(2026, 1, 1),
                _source_file_modification_time=datetime(2026, 1, 1),
                _record_hash="a",
            ),
            Row(
                id="P-1",
                updated=datetime(2026, 1, 2),
                _source_file_modification_time=datetime(2026, 1, 1),
                _record_hash="b",
            ),
            Row(
                id=None,
                updated=None,
                _source_file_modification_time=datetime(2026, 1, 1),
                _record_hash="c",
            ),
        ]
    )
    selected, duplicates = deterministic_latest(rows, ["id"], "updated")
    result = {(row.id, row._record_hash) for row in selected.collect()}
    assert duplicates == 1
    assert result == {("P-1", "b"), (None, "c")}
