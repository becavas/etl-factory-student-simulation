"""Source schemas owned by retail/clientes."""

from pyspark.sql.types import StringType, StructField, StructType

CLIENTES_SOURCE_COLUMNS = (
    "cliente_id",
    "nombres",
    "apellidos",
    "email",
    "fecha_nacimiento",
    "pais_codigo",
    "estado",
    "fecha_actualizacion",
)

CLIENTES_SOURCE_SCHEMA = StructType(
    [StructField(column, StringType(), True) for column in CLIENTES_SOURCE_COLUMNS]
)
