from pathlib import Path

import pytest
from pyspark.sql import Row

from enterprise_fabric.retail.pedidos.bronze import (
    parse_bool,
    read_source_batch,
    replace_batch,
    validate_batch_id,
)
from enterprise_fabric.retail.pedidos.schemas import (
    PEDIDOS_SOURCE_COLUMNS,
    PEDIDOS_SOURCE_SCHEMA,
)


def write_csv(path: Path, header: str, row: str) -> None:
    path.mkdir(parents=True)
    (path / "data.csv").write_text(f"{header}\n{row}\n", encoding="utf-8")


def test_schema_preserves_source_columns_as_strings() -> None:
    assert tuple(PEDIDOS_SOURCE_SCHEMA.fieldNames()) == PEDIDOS_SOURCE_COLUMNS
    assert {field.dataType.simpleString() for field in PEDIDOS_SOURCE_SCHEMA} == {"string"}


def test_read_source_batch_adds_traceability(spark, tmp_path: Path) -> None:
    source = tmp_path / "pedidos"
    write_csv(
        source,
        ",".join(PEDIDOS_SOURCE_COLUMNS),
        "PED-001,CLI-001,2026-01-10,2026-01-10T10:00:00Z,WEB,PEN,25.50,CREADO",
    )
    result = read_source_batch(
        spark,
        str(source),
        PEDIDOS_SOURCE_SCHEMA,
        PEDIDOS_SOURCE_COLUMNS,
        "training_001",
        "run-123",
    )
    row = result.collect()[0]
    assert row["_ingestion_batch_id"] == "training_001"
    assert row["_ingestion_run_id"] == "run-123"
    assert row["_source_file_path"].endswith("data.csv")
    assert len(row["_record_hash"]) == 64


def test_hash_ignores_run_metadata(spark, tmp_path: Path) -> None:
    source = tmp_path / "pedidos"
    write_csv(
        source,
        ",".join(PEDIDOS_SOURCE_COLUMNS),
        "PED-001,CLI-001,2026-01-10,2026-01-10T10:00:00Z,WEB,PEN,25.50,CREADO",
    )
    first = (
        read_source_batch(
            spark, str(source), PEDIDOS_SOURCE_SCHEMA, PEDIDOS_SOURCE_COLUMNS, "b1", "run-1"
        )
        .select("_record_hash")
        .first()[0]
    )
    second = (
        read_source_batch(
            spark, str(source), PEDIDOS_SOURCE_SCHEMA, PEDIDOS_SOURCE_COLUMNS, "b1", "run-2"
        )
        .select("_record_hash")
        .first()[0]
    )
    assert first == second


def test_invalid_header_fails_before_publication(spark, tmp_path: Path) -> None:
    source = tmp_path / "pedidos"
    invalid_columns = ("pedido_codigo", *PEDIDOS_SOURCE_COLUMNS[1:])
    write_csv(
        source,
        ",".join(invalid_columns),
        "PED-001,CLI-001,2026-01-10,2026-01-10T10:00:00Z,WEB,PEN,25.50,CREADO",
    )
    result = read_source_batch(
        spark, str(source), PEDIDOS_SOURCE_SCHEMA, PEDIDOS_SOURCE_COLUMNS, "b1", "run-1"
    )
    with pytest.raises(Exception, match="CSV header does not conform"):
        result.collect()


class RecordingWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def format(self, value: str):
        self.calls.append(("format", value, None))
        return self

    def mode(self, value: str):
        self.calls.append(("mode", value, None))
        return self

    def option(self, key: str, value: str):
        self.calls.append(("option", key, value))
        return self

    def saveAsTable(self, value: str) -> None:
        self.calls.append(("saveAsTable", value, None))


def test_replace_batch_uses_selective_overwrite() -> None:
    writer = RecordingWriter()
    dataframe = Row(write=writer)
    replace_batch(dataframe, "retail_sbx_alumno01.bronze.pedidos_raw", "batch_001", "run-1")
    assert ("mode", "overwrite", None) in writer.calls
    assert ("option", "replaceWhere", "_ingestion_batch_id = 'batch_001'") in writer.calls
    assert ("saveAsTable", "retail_sbx_alumno01.bronze.pedidos_raw", None) in writer.calls


@pytest.mark.parametrize("value", ["bad value", "x' OR 1=1 --", "", "a" * 65])
def test_validate_batch_id_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError, match="batch_id"):
        validate_batch_id(value)


def test_parse_bool_is_explicit() -> None:
    assert parse_bool("true") is True
    assert parse_bool("FALSE") is False
    with pytest.raises(ValueError, match="Boolean"):
        parse_bool("yes")
