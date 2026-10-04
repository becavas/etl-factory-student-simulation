from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from pyspark.sql import Row

from enterprise_fabric.retail.productos.silver import (
    QualityGateError,
    category_duplicate_profile,
    prepare_categorias,
    prepare_productos,
    publish_silver,
    with_category_rules,
    with_product_rules,
)
from enterprise_fabric.shared.spark import deterministic_latest

COVERED_GUARANTEES = {
    "PRO-SI-001",
    "PRO-SI-002",
    "PRO-SI-003",
    "PRO-SI-004",
    "PRO-SI-005",
    "PRO-SI-006",
}

RAW_CATEGORY_SCHEMA = (
    "categoria_id string, nombre_categoria string, categoria_padre_id string, "
    "estado string, fecha_actualizacion string, _source_system string, _source_entity string, "
    "_source_file_path string, _source_file_modification_time timestamp, "
    "_ingestion_batch_id string, _ingestion_run_id string, "
    "_ingested_at_utc timestamp, _record_hash string"
)

RAW_PRODUCT_SCHEMA = (
    "producto_id string, categoria_id string, nombre_producto string, marca string, "
    "moneda string, precio_lista string, estado string, fecha_actualizacion string, "
    "_source_system string, _source_entity string, _source_file_path string, "
    "_source_file_modification_time timestamp, _ingestion_batch_id string, "
    "_ingestion_run_id string, _ingested_at_utc timestamp, _record_hash string"
)


def make_raw_product(
    spark,
    producto_id="P-001",
    categoria_id="C-001",
    nombre="Laptop",
    marca="Brand",
    moneda="USD",
    precio="999.99",
    estado="ACTIVO",
    fecha="2026-01-01T12:00:00Z",
    batch_id="b1",
    run_id="r1",
    hash_val="hash1",
):
    return spark.createDataFrame(
        [
            (
                producto_id,
                categoria_id,
                nombre,
                marca,
                moneda,
                precio,
                estado,
                fecha,
                "productos_source",
                "productos",
                "/vol/p.csv",
                datetime(2026, 1, 1),
                batch_id,
                run_id,
                datetime(2026, 1, 1),
                hash_val,
            )
        ],
        schema=RAW_PRODUCT_SCHEMA,
    )


def make_raw_category(
    spark,
    categoria_id="C-001",
    nombre="Computo",
    padre_id=None,
    estado="ACTIVO",
    fecha="2026-01-01T12:00:00Z",
    batch_id="b1",
    run_id="r1",
    hash_val="hash1",
):
    return spark.createDataFrame(
        [
            (
                categoria_id,
                nombre,
                padre_id,
                estado,
                fecha,
                "productos_source",
                "categorias",
                "/vol/c.csv",
                datetime(2026, 1, 1),
                batch_id,
                run_id,
                datetime(2026, 1, 1),
                hash_val,
            )
        ],
        schema=RAW_CATEGORY_SCHEMA,
    )


def test_prepare_productos_normalizes_and_types_fields(spark):
    df = make_raw_product(
        spark,
        precio=" 1250.50 ",
        moneda=" usd ",
        fecha="2026-02-01T10:00:00Z",
    )
    prepared = prepare_productos(df)
    row = prepared.first()
    assert row["precio_lista"] == Decimal("1250.50")
    assert row["moneda"] == "USD"
    assert row["fecha_actualizacion"] is not None
    assert row["_raw_payload"] is not None


def test_prepare_categorias_normalizes_and_types_fields(spark):
    df = make_raw_category(
        spark,
        nombre="  Hogar  ",
        estado=" activo ",
        fecha="2026-02-01T10:00:00Z",
    )
    prepared = prepare_categorias(df)
    row = prepared.first()
    assert row["nombre_categoria"] == "Hogar"
    assert row["estado"] == "ACTIVO"
    assert row["fecha_actualizacion"] is not None


def test_conflicting_category_is_not_silently_selected(spark):
    rows = spark.createDataFrame(
        [
            (
                "CAT-1",
                "Tecnología",
                None,
                "ACTIVO",
                "2026-01-01T00:00:00Z",
                "productos_source",
                "categorias",
                "/vol/c.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "hash_tech",
            ),
            (
                "CAT-1",
                "Hogar",
                None,
                "ACTIVO",
                "2026-01-01T00:00:00Z",
                "productos_source",
                "categorias",
                "/vol/c.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "hash_hogar",
            ),
        ],
        schema=RAW_CATEGORY_SCHEMA,
    )
    prepared = prepare_categorias(rows)
    duplicates, conflicts = category_duplicate_profile(prepared)
    assert duplicates == 1
    assert conflicts == 1


def test_identical_category_repetition_is_observed_not_conflicted(spark):
    rows = spark.createDataFrame(
        [
            (
                "CAT-1",
                "Tecnología",
                None,
                "ACTIVO",
                "2026-01-01T00:00:00Z",
                "productos_source",
                "categorias",
                "/vol/c.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "hash_tech",
            ),
            (
                "CAT-1",
                "Tecnología",
                None,
                "ACTIVO",
                "2026-01-01T00:00:00Z",
                "productos_source",
                "categorias",
                "/vol/c.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "hash_tech",
            ),
        ],
        schema=RAW_CATEGORY_SCHEMA,
    )
    prepared = prepare_categorias(rows)
    duplicates, conflicts = category_duplicate_profile(prepared)
    assert duplicates == 1
    assert conflicts == 0


def test_category_rules_fail_on_missing_id_and_parent_self(spark):
    rows = spark.createDataFrame(
        [
            Row(
                categoria_id=None,
                nombre_categoria="Cat",
                categoria_padre_id=None,
                estado="ACTIVO",
                fecha_actualizacion=datetime(2026, 1, 1),
                _record_hash="h1",
            ),
            Row(
                categoria_id="C-1",
                nombre_categoria="Cat",
                categoria_padre_id="C-1",  # self parent
                estado="ACTIVO",
                fecha_actualizacion=datetime(2026, 1, 1),
                _record_hash="h2",
            ),
        ],
        schema=(
            "categoria_id string, nombre_categoria string, categoria_padre_id string, "
            "estado string, fecha_actualizacion timestamp, _record_hash string"
        ),
    )
    empty_conflicts = spark.createDataFrame([], "categoria_id string")
    checked = with_category_rules(rows, empty_conflicts)
    results = checked.collect()
    # Row 0 has categoria_id_required in fail rules
    assert "categoria_id_required" in results[0]["_fail_rule_ids"]
    # Row 1 has categoria_parent_not_self in quality rules
    assert "categoria_parent_not_self" in results[1]["_quality_rule_ids"]


def test_product_rules_quarantine_orphan_and_invalid_price(spark):
    products = spark.createDataFrame(
        [
            Row(
                producto_id="P-1",
                categoria_id="C-UNKNOWN",
                nombre_producto="Prod",
                marca="Brand",
                moneda="USD",
                precio_lista=Decimal("-10.00"),
                estado="ACTIVO",
                fecha_actualizacion=datetime(2026, 1, 1),
                _record_hash="h1",
            )
        ]
    )
    categories = spark.createDataFrame([Row(categoria_id="C-EXISTING")])
    checked = with_product_rules(products, categories)
    row = checked.first()
    assert "producto_category_exists" in row["_quality_rule_ids"]
    assert "producto_price_valid" in row["_quality_rule_ids"]
    # Price is quarantine, not fail
    assert len(row["_fail_rule_ids"]) == 0


def test_publish_silver_raises_on_unaligned_bronze_runs(spark):
    p_raw = make_raw_product(spark, batch_id="b1", run_id="run_A")
    c_raw = make_raw_category(spark, batch_id="b1", run_id="run_B")
    mock_table = {
        "cat.bronze.productos_raw": p_raw,
        "cat.bronze.categorias_raw": c_raw,
    }
    with patch.object(spark, "table", side_effect=lambda name: mock_table[name]):
        with pytest.raises(ValueError, match="do not share one ingestion run"):
            publish_silver(spark, "cat", "b1", "qrun1")


def test_publish_silver_raises_quality_gate_error_on_conflict(spark):
    p_raw = make_raw_product(spark, batch_id="b1", run_id="r1")
    c_raw = spark.createDataFrame(
        [
            (
                "C-1",
                "Tecnología",
                None,
                "ACTIVO",
                "2026-01-01T00:00:00Z",
                "productos_source",
                "categorias",
                "/vol/c.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "hash_a",
            ),
            (
                "C-1",
                "Hogar",
                None,
                "ACTIVO",
                "2026-01-01T00:00:00Z",
                "productos_source",
                "categorias",
                "/vol/c.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "hash_b",
            ),
        ],
        schema=RAW_CATEGORY_SCHEMA,
    )
    mock_table = {
        "cat.bronze.productos_raw": p_raw,
        "cat.bronze.categorias_raw": c_raw,
    }
    with (
        patch.object(spark, "table", side_effect=lambda name: mock_table[name]),
        patch("enterprise_fabric.retail.productos.silver.replace_where_value") as mock_replace,
    ):
        with pytest.raises(QualityGateError, match=r"failed \d+ mandatory checks"):
            publish_silver(spark, "cat", "b1", "qrun_fail")

        # Verify metrics and quarantine were written, but NOT curated
        tables_written = [call.args[1] for call in mock_replace.call_args_list]
        assert "cat.silver.productos_quality_metrics" in tables_written
        assert "cat.silver.productos_quarantine" in tables_written
        assert "cat.silver.productos_curated" not in tables_written
        assert "cat.silver.categorias_curated" not in tables_written


def test_product_deduplication_keeps_latest_source_record(spark):
    older = make_raw_product(
        spark,
        producto_id="P-001",
        fecha="2026-01-01T10:00:00Z",
        precio="50.00",
        hash_val="hash_older",
    )
    newer = make_raw_product(
        spark,
        producto_id="P-001",
        fecha="2026-01-01T12:00:00Z",
        precio="75.00",
        hash_val="hash_newer",
    )
    raw = older.unionByName(newer)
    prepared = prepare_productos(raw)
    deduped, dup_count = deterministic_latest(prepared, ["producto_id"], "fecha_actualizacion")
    assert dup_count == 1
    assert deduped.count() == 1
    row = deduped.first()
    assert row["producto_id"] == "P-001"
    assert row["precio_lista"] == Decimal("75.00")


def test_publish_silver_allows_partial_publication_with_quarantine(spark):
    c_raw = spark.createDataFrame(
        [
            (
                "C-1",
                "Tecnología",
                None,
                "ACTIVO",
                "2026-01-01T10:00:00Z",
                "productos_source",
                "categorias",
                "/vol/c.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "h_c1",
            ),
            (
                "C-2",
                "Hogar",
                None,
                "INVALID_STATE",
                "2026-01-01T10:00:00Z",
                "productos_source",
                "categorias",
                "/vol/c.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "h_c2",
            ),
        ],
        schema=RAW_CATEGORY_SCHEMA,
    )
    p_raw = spark.createDataFrame(
        [
            (
                "P-1",
                "C-1",
                "Laptop",
                "BrandX",
                "USD",
                "999.00",
                "ACTIVO",
                "2026-01-01T10:00:00Z",
                "productos_source",
                "productos",
                "/vol/p.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "h_p1",
            ),
            (
                "P-2",
                "C-1",
                "Mouse",
                "BrandY",
                "USD",
                "-5.00",
                "ACTIVO",
                "2026-01-01T10:00:00Z",
                "productos_source",
                "productos",
                "/vol/p.csv",
                datetime(2026, 1, 1),
                "b1",
                "r1",
                datetime(2026, 1, 1),
                "h_p2",
            ),
        ],
        schema=RAW_PRODUCT_SCHEMA,
    )
    mock_table = {
        "cat.bronze.productos_raw": p_raw,
        "cat.bronze.categorias_raw": c_raw,
    }
    with (
        patch.object(spark, "table", side_effect=lambda name: mock_table[name]),
        patch("enterprise_fabric.retail.productos.silver.replace_where_value") as mock_replace,
    ):
        result = publish_silver(spark, "cat", "b1", "qrun_partial")
        assert result.productos_count == 1
        assert result.categorias_count == 1
        assert result.quarantined_count > 0

        tables_written = [call.args[1] for call in mock_replace.call_args_list]
        assert "cat.silver.productos_curated" in tables_written
        assert "cat.silver.categorias_curated" in tables_written
        assert "cat.silver.productos_quarantine" in tables_written
        assert "cat.silver.productos_quality_metrics" in tables_written
