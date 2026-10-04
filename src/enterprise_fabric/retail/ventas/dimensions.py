"""Type 1 dimensions for retail/ventas."""

from dataclasses import dataclass

from delta.tables import DeltaTable
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from enterprise_fabric.retail.ventas.keys import (
    UNKNOWN_SK,
    assert_unique,
    canonical_key,
    payload_hash,
)
from enterprise_fabric.shared.identifiers import require_safe_value

UNKNOWN_NATURAL_KEY = "__UNKNOWN__"


@dataclass(frozen=True)
class DimensionResult:
    batch_id: str
    snapshot_mode: str
    clientes_source_count: int
    productos_source_count: int


def validate_snapshot_mode(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in {"FULL", "INCREMENTAL"}:
        raise ValueError("snapshot_mode must be FULL or INCREMENTAL")
    return normalized


def _reject_reserved_key(frame: DataFrame, key: str, label: str) -> None:
    if frame.where(F.col(key) == UNKNOWN_NATURAL_KEY).limit(1).count():
        raise ValueError(f"{label} uses reserved natural key {UNKNOWN_NATURAL_KEY}")


def prepare_clientes(raw: DataFrame, batch_id: str) -> DataFrame:
    source = raw.where(F.col("_source_batch_id") == batch_id)
    _reject_reserved_key(source, "cliente_id", "clientes")
    selected = source.select(
        canonical_key("dim_cliente", ["cliente_id"]).alias("cliente_sk"),
        "cliente_id",
        "pais_codigo",
        F.col("estado").alias("source_status"),
        F.lit(True).alias("is_active"),
        F.lit(batch_id).alias("_last_change_batch_id"),
        payload_hash(
            "dim_cliente",
            ["cliente_id", "pais_codigo", "estado"],
        ).alias("_payload_hash"),
    )
    unknown = raw.sparkSession.createDataFrame(
        [(UNKNOWN_SK, UNKNOWN_NATURAL_KEY, None, "UNKNOWN", True, "SYSTEM", "UNKNOWN")],
        selected.schema,
    )
    result = selected.unionByName(unknown)
    assert_unique(result, ["cliente_id"], "dim_cliente source")
    return result


def prepare_productos(
    productos: DataFrame,
    categorias: DataFrame,
    batch_id: str,
) -> DataFrame:
    products = productos.where(F.col("_source_batch_id") == batch_id)
    categories = categorias.where(F.col("_source_batch_id") == batch_id).select(
        "categoria_id", "nombre_categoria"
    )
    _reject_reserved_key(products, "producto_id", "productos")
    assert_unique(categories, ["categoria_id"], "categorias input")
    joined = products.join(categories, on="categoria_id", how="left")
    selected = joined.select(
        canonical_key("dim_producto", ["producto_id"]).alias("producto_sk"),
        "producto_id",
        "nombre_producto",
        "marca",
        "categoria_id",
        "nombre_categoria",
        F.col("moneda").alias("moneda_lista"),
        "precio_lista",
        F.col("estado").alias("source_status"),
        F.lit(True).alias("is_active"),
        F.lit(batch_id).alias("_last_change_batch_id"),
        payload_hash(
            "dim_producto",
            [
                "producto_id",
                "nombre_producto",
                "marca",
                "categoria_id",
                "nombre_categoria",
                "moneda",
                "precio_lista",
                "estado",
            ],
        ).alias("_payload_hash"),
    )
    unknown = productos.sparkSession.createDataFrame(
        [
            (
                UNKNOWN_SK,
                UNKNOWN_NATURAL_KEY,
                "Unknown product",
                None,
                None,
                None,
                None,
                None,
                "UNKNOWN",
                True,
                "SYSTEM",
                "UNKNOWN",
            )
        ],
        selected.schema,
    )
    result = selected.unionByName(unknown)
    assert_unique(result, ["producto_id"], "dim_producto source")
    return result


def _merge_type1(
    spark: SparkSession,
    target_name: str,
    source: DataFrame,
    natural_key: str,
    attribute_columns: tuple[str, ...],
    snapshot_mode: str,
    batch_id: str,
) -> None:
    target = DeltaTable.forName(spark, target_name)
    updates = {
        column: f"s.{column}"
        for column in (*attribute_columns, "is_active", "_last_change_batch_id", "_payload_hash")
    }
    updates["_updated_at_utc"] = "current_timestamp()"
    inserts = {column: f"s.{column}" for column in source.columns}
    inserts["_created_at_utc"] = "current_timestamp()"
    inserts["_updated_at_utc"] = "current_timestamp()"

    builder = (
        target.alias("t")
        .merge(source.alias("s"), f"t.{natural_key} = s.{natural_key}")
        .whenMatchedUpdate(
            condition="t._payload_hash <> s._payload_hash OR t.is_active <> s.is_active",
            set=updates,
        )
        .whenNotMatchedInsert(values=inserts)
    )
    if snapshot_mode == "FULL":
        builder = builder.whenNotMatchedBySourceUpdate(
            condition=(f"t.{natural_key} <> '{UNKNOWN_NATURAL_KEY}' AND t.is_active = true"),
            set={
                "is_active": "false",
                "_last_change_batch_id": f"'{require_safe_value(batch_id, 'batch_id')}'",
                "_updated_at_utc": "current_timestamp()",
            },
        )
    builder.execute()


def publish_dimensions(
    spark: SparkSession,
    catalog: str,
    batch_id: str,
    snapshot_mode: str,
) -> DimensionResult:
    batch_id = require_safe_value(batch_id, "batch_id")
    snapshot_mode = validate_snapshot_mode(snapshot_mode)
    clientes = prepare_clientes(spark.table(f"{catalog}.silver.clientes_curated"), batch_id).cache()
    productos = prepare_productos(
        spark.table(f"{catalog}.silver.productos_curated"),
        spark.table(f"{catalog}.silver.categorias_curated"),
        batch_id,
    ).cache()
    try:
        clientes_count = clientes.where(F.col("cliente_id") != UNKNOWN_NATURAL_KEY).count()
        productos_count = productos.where(F.col("producto_id") != UNKNOWN_NATURAL_KEY).count()
        if clientes_count == 0 or productos_count == 0:
            raise ValueError(f"Dimension inputs are empty for batch {batch_id}")
        _merge_type1(
            spark,
            f"{catalog}.gold.dim_cliente",
            clientes,
            "cliente_id",
            ("cliente_sk", "pais_codigo", "source_status"),
            snapshot_mode,
            batch_id,
        )
        _merge_type1(
            spark,
            f"{catalog}.gold.dim_producto",
            productos,
            "producto_id",
            (
                "producto_sk",
                "nombre_producto",
                "marca",
                "categoria_id",
                "nombre_categoria",
                "moneda_lista",
                "precio_lista",
                "source_status",
            ),
            snapshot_mode,
            batch_id,
        )
        return DimensionResult(batch_id, snapshot_mode, clientes_count, productos_count)
    finally:
        clientes.unpersist()
        productos.unpersist()
