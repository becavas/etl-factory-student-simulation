"""Source schemas owned by the retail/pedidos capability."""

from pyspark.sql.types import StringType, StructField, StructType

PEDIDOS_SOURCE_COLUMNS = (
    "pedido_id",
    "cliente_id",
    "fecha_pedido",
    "fecha_actualizacion",
    "canal",
    "moneda",
    "monto_total",
    "estado",
)

PEDIDO_ITEMS_SOURCE_COLUMNS = (
    "pedido_id",
    "item_id",
    "producto_id",
    "cantidad",
    "precio_unitario",
    "importe_linea",
    "fecha_actualizacion",
)


def string_schema(columns: tuple[str, ...]) -> StructType:
    """Build a nullable string schema that preserves raw source values."""
    return StructType([StructField(column, StringType(), nullable=True) for column in columns])


PEDIDOS_SOURCE_SCHEMA = string_schema(PEDIDOS_SOURCE_COLUMNS)
PEDIDO_ITEMS_SOURCE_SCHEMA = string_schema(PEDIDO_ITEMS_SOURCE_COLUMNS)
