"""Unit tests for retail/ventas dimensions preparation."""

import pytest
from pyspark.sql.types import (
    StringType,
    StructField,
    StructType,
)

from enterprise_fabric.retail.ventas.dimensions import (
    UNKNOWN_NATURAL_KEY,
    prepare_clientes,
    prepare_productos,
    validate_snapshot_mode,
)
from enterprise_fabric.retail.ventas.keys import UNKNOWN_SK


def test_validate_snapshot_mode():
    assert validate_snapshot_mode("full") == "FULL"
    assert validate_snapshot_mode("INCREMENTAL") == "INCREMENTAL"
    with pytest.raises(ValueError, match="snapshot_mode must be FULL or INCREMENTAL"):
        validate_snapshot_mode("INVALID")


def test_prepare_clientes_filters_batch_and_minimizes_pii(spark):
    schema = StructType(
        [
            StructField("cliente_id", StringType(), True),
            StructField("nombre", StringType(), True),
            StructField("email", StringType(), True),
            StructField("pais_codigo", StringType(), True),
            StructField("estado", StringType(), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    data = [
        ("CLI-1", "Alice", "alice@test.com", "PE", "ACTIVO", "batch-1"),
        ("CLI-2", "Bob", "bob@test.com", "CO", "ACTIVO", "batch-2"),
    ]
    raw = spark.createDataFrame(data, schema)
    result = prepare_clientes(raw, "batch-1")

    # Verify columns minimize PII
    assert "nombre" not in result.columns
    assert "email" not in result.columns
    assert "cliente_sk" in result.columns
    assert "_payload_hash" in result.columns

    rows = result.collect()
    # 1 batch record + 1 unknown member
    assert len(rows) == 2

    # Verify unknown member
    unknown_row = [r for r in rows if r.cliente_id == UNKNOWN_NATURAL_KEY][0]
    assert unknown_row.cliente_sk == UNKNOWN_SK
    assert unknown_row.source_status == "UNKNOWN"
    assert unknown_row.is_active is True

    # Verify real record
    real_row = [r for r in rows if r.cliente_id == "CLI-1"][0]
    assert real_row.cliente_sk != UNKNOWN_SK
    assert len(real_row.cliente_sk) == 64
    assert real_row.pais_codigo == "PE"


def test_prepare_clientes_rejects_reserved_natural_key(spark):
    schema = StructType(
        [
            StructField("cliente_id", StringType(), True),
            StructField("pais_codigo", StringType(), True),
            StructField("estado", StringType(), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    data = [(UNKNOWN_NATURAL_KEY, "PE", "ACTIVO", "batch-1")]
    raw = spark.createDataFrame(data, schema)
    with pytest.raises(ValueError, match="uses reserved natural key"):
        prepare_clientes(raw, "batch-1")


def test_prepare_clientes_rejects_duplicate_key(spark):
    schema = StructType(
        [
            StructField("cliente_id", StringType(), True),
            StructField("pais_codigo", StringType(), True),
            StructField("estado", StringType(), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    data = [
        ("CLI-1", "PE", "ACTIVO", "batch-1"),
        ("CLI-1", "CO", "INACTIVO", "batch-1"),
    ]
    raw = spark.createDataFrame(data, schema)
    with pytest.raises(ValueError, match="duplicate MERGE keys"):
        prepare_clientes(raw, "batch-1")


def test_prepare_productos_joins_categories_and_includes_unknown(spark):
    prod_schema = StructType(
        [
            StructField("producto_id", StringType(), True),
            StructField("nombre_producto", StringType(), True),
            StructField("marca", StringType(), True),
            StructField("categoria_id", StringType(), True),
            StructField("moneda", StringType(), True),
            StructField("precio_lista", StringType(), True),
            StructField("estado", StringType(), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    cat_schema = StructType(
        [
            StructField("categoria_id", StringType(), True),
            StructField("nombre_categoria", StringType(), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    prod_data = [
        ("PROD-1", "Laptop", "BrandX", "CAT-1", "PEN", "1200.00", "ACTIVO", "batch-1"),
    ]
    cat_data = [
        ("CAT-1", "Computo", "batch-1"),
    ]
    products = spark.createDataFrame(prod_data, prod_schema)
    categories = spark.createDataFrame(cat_data, cat_schema)

    result = prepare_productos(products, categories, "batch-1")
    rows = result.collect()
    assert len(rows) == 2  # 1 prod + 1 unknown

    prod_row = [r for r in rows if r.producto_id == "PROD-1"][0]
    assert prod_row.producto_sk != UNKNOWN_SK
    assert prod_row.nombre_categoria == "Computo"
    assert prod_row.moneda_lista == "PEN"

    unknown_row = [r for r in rows if r.producto_id == UNKNOWN_NATURAL_KEY][0]
    assert unknown_row.producto_sk == UNKNOWN_SK
    assert unknown_row.nombre_producto == "Unknown product"


def test_prepare_productos_rejects_duplicate_product(spark):
    prod_schema = StructType(
        [
            StructField("producto_id", StringType(), True),
            StructField("nombre_producto", StringType(), True),
            StructField("marca", StringType(), True),
            StructField("categoria_id", StringType(), True),
            StructField("moneda", StringType(), True),
            StructField("precio_lista", StringType(), True),
            StructField("estado", StringType(), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    cat_schema = StructType(
        [
            StructField("categoria_id", StringType(), True),
            StructField("nombre_categoria", StringType(), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    prod_data = [
        ("PROD-1", "Laptop", "BrandX", "CAT-1", "PEN", "1200.00", "ACTIVO", "batch-1"),
        ("PROD-1", "Laptop 2", "BrandX", "CAT-1", "PEN", "1300.00", "ACTIVO", "batch-1"),
    ]
    products = spark.createDataFrame(prod_data, prod_schema)
    categories = spark.createDataFrame([], cat_schema)
    with pytest.raises(ValueError, match="duplicate MERGE keys"):
        prepare_productos(products, categories, "batch-1")
