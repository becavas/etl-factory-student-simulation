"""Unit tests for retail/ventas fact preparation and order reconciliation."""

from decimal import Decimal

import pytest
from pyspark.sql.types import (
    BooleanType,
    DecimalType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from enterprise_fabric.retail.ventas.fact import prepare_fact, reconcile_orders
from enterprise_fabric.retail.ventas.keys import UNKNOWN_SK


def test_reconcile_orders_succeeds_on_matching_totals(spark):
    orders = spark.createDataFrame(
        [("PED-1", Decimal("100.00")), ("PED-2", Decimal("50.00"))],
        ["pedido_id", "monto_total"],
    )
    items = spark.createDataFrame(
        [
            ("PED-1", Decimal("60.00")),
            ("PED-1", Decimal("40.00")),
            ("PED-2", Decimal("50.00")),
        ],
        ["pedido_id", "importe_linea"],
    )
    reconcile_orders(orders, items)


def test_reconcile_orders_fails_on_mismatch(spark):
    orders = spark.createDataFrame([("PED-1", Decimal("100.00"))], ["pedido_id", "monto_total"])
    items = spark.createDataFrame([("PED-1", Decimal("95.00"))], ["pedido_id", "importe_linea"])
    with pytest.raises(ValueError, match="Order total reconciliation failed"):
        reconcile_orders(orders, items)


def test_reconcile_orders_fails_on_missing_items(spark):
    orders = spark.createDataFrame([("PED-1", Decimal("100.00"))], ["pedido_id", "monto_total"])
    items = spark.createDataFrame(
        [],
        StructType(
            [
                StructField("pedido_id", StringType(), True),
                StructField("importe_linea", DecimalType(18, 2), True),
            ]
        ),
    )
    with pytest.raises(ValueError, match="Order total reconciliation failed"):
        reconcile_orders(orders, items)


def test_prepare_fact_assigns_unknown_sk_when_dimension_missing(spark):
    pedidos_schema = StructType(
        [
            StructField("pedido_id", StringType(), True),
            StructField("cliente_id", StringType(), True),
            StructField("fecha_pedido", StringType(), True),
            StructField("canal", StringType(), True),
            StructField("moneda", StringType(), True),
            StructField("monto_total", DecimalType(18, 2), True),
            StructField("estado", StringType(), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    items_schema = StructType(
        [
            StructField("pedido_id", StringType(), True),
            StructField("item_id", StringType(), True),
            StructField("producto_id", StringType(), True),
            StructField("cantidad", IntegerType(), True),
            StructField("precio_unitario", DecimalType(18, 2), True),
            StructField("importe_linea", DecimalType(18, 2), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    dim_cli_schema = StructType(
        [
            StructField("cliente_id", StringType(), True),
            StructField("cliente_sk", StringType(), True),
            StructField("is_active", BooleanType(), True),
        ]
    )
    dim_prod_schema = StructType(
        [
            StructField("producto_id", StringType(), True),
            StructField("producto_sk", StringType(), True),
            StructField("is_active", BooleanType(), True),
        ]
    )

    pedidos = spark.createDataFrame(
        [
            (
                "PED-1",
                "CLI-MISSING",
                "2026-01-01",
                "ONLINE",
                "PEN",
                Decimal("100.00"),
                "COMPLETADO",
                "batch-1",
            )
        ],
        pedidos_schema,
    )
    items = spark.createDataFrame(
        [("PED-1", "ITEM-1", "PROD-1", 1, Decimal("100.00"), Decimal("100.00"), "batch-1")],
        items_schema,
    )
    # CLI-MISSING not in dim_cliente
    clientes = spark.createDataFrame([], dim_cli_schema)
    productos = spark.createDataFrame([("PROD-1", "prod-sk-1", True)], dim_prod_schema)

    result = prepare_fact(pedidos, items, clientes, productos, "batch-1")
    row = result.first()

    assert row.cliente_sk == UNKNOWN_SK
    assert row._source_cliente_id == "CLI-MISSING"
    assert row.producto_sk == "prod-sk-1"
    assert row._source_producto_id == "PROD-1"
    assert row.is_cancelled is False
    assert len(row.venta_linea_sk) == 64
    assert len(row._payload_hash) == 64


def test_prepare_fact_ignores_inactive_dimensions(spark):
    pedidos_schema = StructType(
        [
            StructField("pedido_id", StringType(), True),
            StructField("cliente_id", StringType(), True),
            StructField("fecha_pedido", StringType(), True),
            StructField("canal", StringType(), True),
            StructField("moneda", StringType(), True),
            StructField("monto_total", DecimalType(18, 2), True),
            StructField("estado", StringType(), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    items_schema = StructType(
        [
            StructField("pedido_id", StringType(), True),
            StructField("item_id", StringType(), True),
            StructField("producto_id", StringType(), True),
            StructField("cantidad", IntegerType(), True),
            StructField("precio_unitario", DecimalType(18, 2), True),
            StructField("importe_linea", DecimalType(18, 2), True),
            StructField("_source_batch_id", StringType(), True),
        ]
    )
    dim_cli_schema = StructType(
        [
            StructField("cliente_id", StringType(), True),
            StructField("cliente_sk", StringType(), True),
            StructField("is_active", BooleanType(), True),
        ]
    )
    dim_prod_schema = StructType(
        [
            StructField("producto_id", StringType(), True),
            StructField("producto_sk", StringType(), True),
            StructField("is_active", BooleanType(), True),
        ]
    )

    pedidos = spark.createDataFrame(
        [
            (
                "PED-1",
                "CLI-INACTIVE",
                "2026-01-01",
                "ONLINE",
                "PEN",
                Decimal("50.00"),
                "CANCELADO",
                "batch-1",
            )
        ],
        pedidos_schema,
    )
    items = spark.createDataFrame(
        [("PED-1", "ITEM-1", "PROD-1", 1, Decimal("50.00"), Decimal("50.00"), "batch-1")],
        items_schema,
    )
    clientes = spark.createDataFrame([("CLI-INACTIVE", "cli-sk-old", False)], dim_cli_schema)
    productos = spark.createDataFrame([("PROD-1", "prod-sk-1", True)], dim_prod_schema)

    result = prepare_fact(pedidos, items, clientes, productos, "batch-1")
    row = result.first()
    # Inactive dimension should fall back to UNKNOWN_SK
    assert row.cliente_sk == UNKNOWN_SK
    assert row.is_cancelled is True
