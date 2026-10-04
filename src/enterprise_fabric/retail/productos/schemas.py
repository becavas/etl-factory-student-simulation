"""Source schemas owned by retail/productos."""

from pyspark.sql.types import StringType, StructField, StructType

PRODUCTOS_SOURCE_COLUMNS = (
    "producto_id",
    "categoria_id",
    "nombre_producto",
    "marca",
    "moneda",
    "precio_lista",
    "estado",
    "fecha_actualizacion",
)
CATEGORIAS_SOURCE_COLUMNS = (
    "categoria_id",
    "nombre_categoria",
    "categoria_padre_id",
    "estado",
    "fecha_actualizacion",
)


def _strings(columns: tuple[str, ...]) -> StructType:
    return StructType([StructField(name, StringType(), True) for name in columns])


PRODUCTOS_SOURCE_SCHEMA = _strings(PRODUCTOS_SOURCE_COLUMNS)
CATEGORIAS_SOURCE_SCHEMA = _strings(CATEGORIAS_SOURCE_COLUMNS)
