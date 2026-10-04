import json
from pathlib import Path

import pytest

from enterprise_fabric.retail.clientes.bronze import (
    read_batch,
    replace_batch,
    validate_identifier,
)
from enterprise_fabric.retail.clientes.schemas import CLIENTES_SOURCE_COLUMNS

COVERED_GUARANTEES = {"CLI-001", "CLI-002"}


class RecordingWriter:
    def __init__(self):
        self.format_name = None
        self.mode_name = None
        self.options = {}
        self.table_name = None

    def format(self, value):
        self.format_name = value
        return self

    def mode(self, value):
        self.mode_name = value
        return self

    def option(self, key, value):
        self.options[key] = value
        return self

    def saveAsTable(self, value):  # noqa: N802 - mirrors the PySpark API
        self.table_name = value


class FrameWithRecordingWriter:
    def __init__(self):
        self.columns = ["_ingestion_batch_id"]
        self.write = RecordingWriter()


def _write_source(path: Path) -> None:
    path.write_text(
        ",".join(CLIENTES_SOURCE_COLUMNS)
        + "\n"
        + "CLI-001,Ana,Paredes,ana@example.test,1990-04-17,PE,ACTIVO,"
        + "2026-01-01T10:00:00Z\n",
        encoding="utf-8",
    )


def test_read_batch_preserves_source_strings_and_adds_lineage(spark, tmp_path):
    source = tmp_path / "clientes.csv"
    _write_source(source)
    row = read_batch(
        spark,
        str(source),
        batch_id="test_batch",
        run_id="run_001",
    ).first()
    assert all(row[column] is not None for column in CLIENTES_SOURCE_COLUMNS)
    assert row["fecha_nacimiento"] == "1990-04-17"
    assert row["_source_system"] == "clientes_source"
    assert row["_source_file_path"].endswith("clientes.csv")
    assert row["_ingestion_batch_id"] == "test_batch"
    assert row["_ingestion_run_id"] == "run_001"
    assert len(row["_record_hash"]) == 64


def test_replace_batch_uses_selective_predicate_and_commit_metadata():
    frame = FrameWithRecordingWriter()
    replace_batch(
        frame,
        "retail_sbx_alumno01.bronze.clientes_raw",
        "test_batch",
        "run_001",
    )
    assert frame.write.format_name == "delta"
    assert frame.write.mode_name == "overwrite"
    assert frame.write.options["replaceWhere"] == ("_ingestion_batch_id = 'test_batch'")
    metadata = json.loads(frame.write.options["userMetadata"])
    assert metadata == {
        "batch_id": "test_batch",
        "capability": "retail/clientes",
        "run_id": "run_001",
    }
    assert frame.write.table_name == "retail_sbx_alumno01.bronze.clientes_raw"


@pytest.mark.parametrize("value", ["", "../batch", "batch id", "' OR 1=1"])
def test_identifier_rejects_unsafe_values(value):
    with pytest.raises(ValueError, match="safe identifier"):
        validate_identifier(value, "batch_id")
