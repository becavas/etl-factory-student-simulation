"""Fact sales line preparation and idempotent Delta MERGE."""

from dataclasses import dataclass
from decimal import Decimal

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


@dataclass(frozen=True)
class FactResult:
    batch_id: str
    source_count: int
    unknown_cliente_count: int
    unknown_producto_count: int


def reconcile_orders(pedidos: DataFrame, items: DataFrame) -> None:
    item_totals = items.groupBy("pedido_id").agg(F.sum("importe_linea").alias("items_total"))
    mismatches = (
        pedidos.select("pedido_id", "monto_total")
        .join(item_totals, on="pedido_id", how="left")
        .where(
            F.col("items_total").isNull()
            | (F.abs(F.col("monto_total") - F.col("items_total")) > F.lit(Decimal("0.01")))
        )
    )
    if mismatches.limit(1).count():
        raise ValueError(f"Order total reconciliation failed: {mismatches.first().asDict()}")


def prepare_fact(
    pedidos: DataFrame,
    items: DataFrame,
    clientes: DataFrame,
    productos: DataFrame,
    batch_id: str,
) -> DataFrame:
    headers = pedidos.where(F.col("_source_batch_id") == batch_id).select(
        "pedido_id",
        "cliente_id",
        "fecha_pedido",
        "canal",
        "moneda",
        "monto_total",
        "estado",
    )
    lines = items.where(F.col("_source_batch_id") == batch_id).select(
        "pedido_id",
        "item_id",
        "producto_id",
        "cantidad",
        "precio_unitario",
        "importe_linea",
    )
    assert_unique(headers, ["pedido_id"], "pedidos input")
    assert_unique(lines, ["pedido_id", "item_id"], "pedido_items input")
    if headers.limit(1).count() == 0 or lines.limit(1).count() == 0:
        raise ValueError(f"Fact inputs are empty for batch {batch_id}")
    reconcile_orders(headers, lines)

    active_clients = clientes.where(F.col("is_active")).select(
        F.col("cliente_id").alias("_dim_cliente_id"), "cliente_sk"
    )
    active_products = productos.where(F.col("is_active")).select(
        F.col("producto_id").alias("_dim_producto_id"), "producto_sk"
    )
    joined = (
        lines.join(headers, on="pedido_id", how="inner")
        .join(active_clients, F.col("cliente_id") == F.col("_dim_cliente_id"), "left")
        .join(active_products, F.col("producto_id") == F.col("_dim_producto_id"), "left")
    )
    result = joined.select(
        canonical_key("fact_ventas", ["pedido_id", "item_id"]).alias("venta_linea_sk"),
        "pedido_id",
        "item_id",
        "fecha_pedido",
        F.coalesce(F.col("cliente_sk"), F.lit(UNKNOWN_SK)).alias("cliente_sk"),
        F.coalesce(F.col("producto_sk"), F.lit(UNKNOWN_SK)).alias("producto_sk"),
        F.col("cliente_id").alias("_source_cliente_id"),
        F.col("producto_id").alias("_source_producto_id"),
        "cantidad",
        "precio_unitario",
        "importe_linea",
        "moneda",
        "canal",
        F.col("estado").alias("estado_pedido"),
        (F.col("estado") == F.lit("CANCELADO")).alias("is_cancelled"),
        F.lit(batch_id).alias("_last_change_batch_id"),
    )
    payload_columns = [
        "pedido_id",
        "item_id",
        "fecha_pedido",
        "cliente_sk",
        "producto_sk",
        "_source_cliente_id",
        "_source_producto_id",
        "cantidad",
        "precio_unitario",
        "importe_linea",
        "moneda",
        "canal",
        "estado_pedido",
        "is_cancelled",
    ]
    result = result.withColumn("_payload_hash", payload_hash("fact_ventas", payload_columns))
    assert_unique(result, ["venta_linea_sk"], "fact_ventas source")
    if result.where(F.col("venta_linea_sk") == UNKNOWN_SK).limit(1).count():
        raise ValueError("Calculated fact key collides with UNKNOWN_SK")
    return result


def merge_fact(spark: SparkSession, target_name: str, source: DataFrame) -> None:
    updates = {column: f"s.{column}" for column in source.columns if column != "venta_linea_sk"}
    updates["_updated_at_utc"] = "current_timestamp()"
    inserts = {column: f"s.{column}" for column in source.columns}
    inserts["_created_at_utc"] = "current_timestamp()"
    inserts["_updated_at_utc"] = "current_timestamp()"
    (
        DeltaTable.forName(spark, target_name)
        .alias("t")
        .merge(source.alias("s"), "t.venta_linea_sk = s.venta_linea_sk")
        .whenMatchedUpdate(condition="t._payload_hash <> s._payload_hash", set=updates)
        .whenNotMatchedInsert(values=inserts)
        .execute()
    )


def publish_fact(spark: SparkSession, catalog: str, batch_id: str) -> FactResult:
    batch_id = require_safe_value(batch_id, "batch_id")
    source = prepare_fact(
        spark.table(f"{catalog}.silver.pedidos_curated"),
        spark.table(f"{catalog}.silver.pedido_items_curated"),
        spark.table(f"{catalog}.gold.dim_cliente"),
        spark.table(f"{catalog}.gold.dim_producto"),
        batch_id,
    ).cache()
    try:
        source_count = source.count()
        unknown_clients = source.where(F.col("cliente_sk") == UNKNOWN_SK).count()
        unknown_products = source.where(F.col("producto_sk") == UNKNOWN_SK).count()
        merge_fact(spark, f"{catalog}.gold.fact_ventas", source)
        return FactResult(batch_id, source_count, unknown_clients, unknown_products)
    finally:
        source.unpersist()
