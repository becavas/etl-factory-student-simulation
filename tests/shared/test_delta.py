from unittest.mock import MagicMock

import pytest

from enterprise_fabric.shared.delta import replace_where_value


def test_replace_where_rejects_missing_column():
    frame = MagicMock()
    frame.columns = ["other_col", "data"]
    with pytest.raises(ValueError, match="predicate column not present"):
        replace_where_value(
            frame,
            "test_table",
            "batch_id",
            "training_001",
            {"capability": "test"},
        )


def test_replace_where_rejects_invalid_column_name():
    frame = MagicMock()
    frame.columns = ["batch id; drop table"]
    with pytest.raises(ValueError, match="must be a simple column name"):
        replace_where_value(
            frame,
            "test_table",
            "batch id; drop table",
            "training_001",
            {"capability": "test"},
        )


def test_replace_where_rejects_empty_metadata():
    frame = MagicMock()
    frame.columns = ["batch_id"]
    with pytest.raises(ValueError, match="metadata must not be empty"):
        replace_where_value(frame, "test_table", "batch_id", "training_001", {})


def test_replace_where_rejects_unsafe_predicate_value():
    frame = MagicMock()
    frame.columns = ["batch_id"]
    with pytest.raises(ValueError, match="must contain only safe identifier"):
        replace_where_value(
            frame,
            "test_table",
            "batch_id",
            "batch' OR '1'='1",
            {"capability": "test"},
        )


def test_replace_where_writes_delta_with_expected_options():
    frame = MagicMock()
    frame.columns = ["_source_batch_id", "value"]
    writer = MagicMock()
    frame.write.format.return_value = writer
    writer.mode.return_value = writer
    writer.option.return_value = writer

    metadata = {"capability": "retail/test", "batch_id": "training_001"}
    replace_where_value(
        frame,
        "cat.silver.test_table",
        "_source_batch_id",
        "training_001",
        metadata,
    )

    frame.write.format.assert_called_once_with("delta")
    writer.mode.assert_called_once_with("overwrite")
    writer.option.assert_any_call("replaceWhere", "_source_batch_id = 'training_001'")
    writer.option.assert_any_call(
        "userMetadata",
        '{"batch_id": "training_001", "capability": "retail/test"}',
    )
    writer.saveAsTable.assert_called_once_with("cat.silver.test_table")
