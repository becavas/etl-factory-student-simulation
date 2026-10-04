"""Explicit Gold table contracts for retail/ventas."""

from pyspark.sql import SparkSession

from enterprise_fabric.shared.identifiers import require_safe_value


def ensure_gold_tables(spark: SparkSession, catalog: str) -> None:
    catalog = require_safe_value(catalog, "catalog")
    statements = (
        f"""
        CREATE TABLE IF NOT EXISTS {catalog}.gold.dim_cliente (
          cliente_sk STRING,
          cliente_id STRING,
          pais_codigo STRING,
          source_status STRING,
          is_active BOOLEAN,
          _last_change_batch_id STRING,
          _payload_hash STRING,
          _created_at_utc TIMESTAMP,
          _updated_at_utc TIMESTAMP
        ) USING DELTA
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {catalog}.gold.dim_producto (
          producto_sk STRING,
          producto_id STRING,
          nombre_producto STRING,
          marca STRING,
          categoria_id STRING,
          nombre_categoria STRING,
          moneda_lista STRING,
          precio_lista DECIMAL(18,2),
          source_status STRING,
          is_active BOOLEAN,
          _last_change_batch_id STRING,
          _payload_hash STRING,
          _created_at_utc TIMESTAMP,
          _updated_at_utc TIMESTAMP
        ) USING DELTA
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {catalog}.gold.fact_ventas (
          venta_linea_sk STRING,
          pedido_id STRING,
          item_id STRING,
          fecha_pedido DATE,
          cliente_sk STRING,
          producto_sk STRING,
          _source_cliente_id STRING,
          _source_producto_id STRING,
          cantidad INT,
          precio_unitario DECIMAL(18,2),
          importe_linea DECIMAL(18,2),
          moneda STRING,
          canal STRING,
          estado_pedido STRING,
          is_cancelled BOOLEAN,
          _last_change_batch_id STRING,
          _payload_hash STRING,
          _created_at_utc TIMESTAMP,
          _updated_at_utc TIMESTAMP
        ) USING DELTA
        """,
    )
    for statement in statements:
        spark.sql(statement)


def ensure_aggregate_table(spark: SparkSession, catalog: str) -> None:
    catalog = require_safe_value(catalog, "catalog")
    table_name = f"{catalog}.gold.agg_ventas_netas_diarias"
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
          fecha_pedido DATE COMMENT 'Fecha de negocio del pedido',
          canal STRING COMMENT 'Canal de venta publicado',
          moneda STRING COMMENT 'Unidad monetaria; versión 1.0.0 admite PEN',
          ventas_netas DECIMAL(28, 2) COMMENT 'Importe no cancelado',
          lineas_incluidas BIGINT COMMENT 'Líneas no canceladas incluidas',
          unidades_vendidas BIGINT COMMENT 'Unidades no canceladas incluidas',
          _metric_id STRING,
          _metric_version STRING,
          _source_max_updated_at_utc TIMESTAMP,
          _published_at_utc TIMESTAMP
        ) USING DELTA
        COMMENT 'KPI diario de ventas netas por canal y moneda'
        """
    )
