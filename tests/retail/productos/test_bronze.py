from unittest.mock import MagicMock, patch

import pytest
from py4j.protocol import Py4JJavaError
from pyspark.sql.types import (
    StringType,
    StructField,
    StructType,
)

from enterprise_fabric.retail.productos.bronze import (
    BronzeResult,
    ingest_bronze,
    read_entity,
)
from enterprise_fabric.retail.productos.schemas import (
    PRODUCTOS_SOURCE_COLUMNS,
    PRODUCTOS_SOURCE_SCHEMA,
)


def test_read_entity_adds_complete_lineage_and_hash(spark, tmp_path):
    csv_file = tmp_path / "batch_id=b1" / "part-0.csv"
    csv_file.parent.mkdir(parents=True)
    csv_file.write_text(
        "producto_id,categoria_id,nombre_producto,marca,moneda,precio_lista,estado,fecha_actualizacion\n"
        "P1,C1,Laptop,BrandX,USD,999.99,ACTIVO,2026-01-01T10:00:00Z\n",
        encoding="utf-8",
    )
    df = read_entity(
        spark,
        str(csv_file.parent),
        PRODUCTOS_SOURCE_SCHEMA,
        PRODUCTOS_SOURCE_COLUMNS,
        "productos",
        "b1",
        "r1",
    )
    row = df.first()
    assert row["_source_system"] == "productos_source"
    assert row["_source_entity"] == "productos"
    assert row["_ingestion_batch_id"] == "b1"
    assert row["_ingestion_run_id"] == "r1"
    assert row["_record_hash"] is not None
    assert len(row["_record_hash"]) == 64


def test_read_entity_rejects_corrupted_csv_failfast(spark, tmp_path):
    csv_file = tmp_path / "batch_id=b1" / "corrupted.csv"
    csv_file.parent.mkdir(parents=True)
    # Extra columns that do not match schema under mode FAILFAST
    csv_file.write_text(
        "col1,col2\nval1,val2,extra_val\n",
        encoding="utf-8",
    )
    schema = StructType([StructField("col1", StringType()), StructField("col2", StringType())])
    with pytest.raises(Py4JJavaError):
        df = read_entity(
            spark,
            str(csv_file.parent),
            schema,
            ("col1", "col2"),
            "test_entity",
            "b1",
            "r1",
        )
        df.collect()


def test_ingest_bronze_empty_batch_raises_value_error(spark, tmp_path):
    # Empty directories
    (tmp_path / "productos" / "batch_id=empty_001").mkdir(parents=True)
    (tmp_path / "categorias" / "batch_id=empty_001").mkdir(parents=True)
    p_file = tmp_path / "productos" / "batch_id=empty_001" / "empty.csv"
    p_file.write_text(
        "producto_id,categoria_id,nombre_producto,marca,moneda,precio_lista,estado,fecha_actualizacion\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="No productos found"):
        ingest_bronze(spark, "test_cat", str(tmp_path), "empty_001", "run1")


def test_ingest_bronze_writes_both_entities():
    spark = MagicMock()
    with (
        patch("enterprise_fabric.retail.productos.bronze.read_entity") as mock_read,
        patch("enterprise_fabric.retail.productos.bronze.replace_where_value") as mock_replace,
    ):
        mock_df = MagicMock()
        mock_df.cache.return_value = mock_df
        mock_df.count.return_value = 5
        mock_read.return_value = mock_df

        res = ingest_bronze(
            spark,
            "retail_sbx_a001",
            "/Volumes/retail_sbx_a001/landing/productos_source",
            "training_001",
            "run_001",
        )
        assert res == BronzeResult("training_001", "run_001", 5, 5)
        assert mock_replace.call_count == 2
        # Verify calls for both tables
        tables = [call.args[1] for call in mock_replace.call_args_list]
        assert "retail_sbx_a001.bronze.productos_raw" in tables
        assert "retail_sbx_a001.bronze.categorias_raw" in tables


@pytest.mark.parametrize("val", ["", "bad batch", "b' OR 1=1", "a" * 65])
def test_ingest_bronze_validates_batch_and_run_id(spark, val):
    with pytest.raises(ValueError):
        ingest_bronze(spark, "cat", "/vol", val, "run1")
    with pytest.raises(ValueError):
        ingest_bronze(spark, "cat", "/vol", "batch1", val)
