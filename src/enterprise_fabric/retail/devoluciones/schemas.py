"""Source schemas owned by the retail/devoluciones capability."""

from pyspark.sql.types import StringType, StructField, StructType

DEVOLUCIONES_SOURCE_COLUMNS = (
    "devolucion_id",
    "pedido_id",
    "producto_id",
    "fecha_devolucion",
    "motivo",
    "estado",
    "importe_reembolsado",
    "moneda",
    "updated_at",
)


def string_schema(columns: tuple[str, ...]) -> StructType:
    """Build a nullable string schema that preserves raw source values."""
    return StructType([StructField(column, StringType(), nullable=True) for column in columns])


DEVOLUCIONES_SOURCE_SCHEMA = string_schema(DEVOLUCIONES_SOURCE_COLUMNS)
