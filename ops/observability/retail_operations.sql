-- =============================================================================
-- Consultas de Observabilidad Operativa — Dominio Retail
-- =============================================================================
-- Referencias: system.lakeflow (Jobs), DQ Metrics, system.access (Lineage/Audit),
-- system.billing (Usage)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Trazabilidad y Estado de Ejecuciones del Parent Job (system.lakeflow)
-- Agrega slices de tiempo por run_id para evitar sobreestimar ejecuciones.
-- -----------------------------------------------------------------------------
WITH current_jobs AS (
  SELECT workspace_id, job_id, name,
         ROW_NUMBER() OVER (
           PARTITION BY workspace_id, job_id ORDER BY change_time DESC
         ) AS rn
  FROM system.lakeflow.jobs
), runs AS (
  SELECT workspace_id, job_id, run_id, trigger_type,
         MIN(period_start_time) AS started_at,
         MAX(period_end_time) AS ended_at,
         MAX_BY(result_state, period_end_time) AS result_state,
         MAX_BY(termination_code, period_end_time) AS termination_code
  FROM system.lakeflow.job_run_timeline
  WHERE period_start_time >= CURRENT_TIMESTAMP() - INTERVAL 30 DAYS
  GROUP BY workspace_id, job_id, run_id, trigger_type
)
SELECT j.name, r.*,
       TIMESTAMPDIFF(MINUTE, started_at, ended_at) AS duration_minutes
FROM runs r
JOIN current_jobs j USING (workspace_id, job_id)
WHERE j.rn = 1 AND j.name = 'retail-domain-e2e'
ORDER BY started_at DESC;

-- -----------------------------------------------------------------------------
-- 2. Métricas de Calidad de Datos (Data Quality - Silver)
-- Consolida violaciones FAIL por capability, batch y quality_run_id en los últimos 30 días.
-- -----------------------------------------------------------------------------
SELECT 'pedidos' AS capability, batch_id, quality_run_id,
       SUM(CASE WHEN action = 'FAIL' THEN failed_records ELSE 0 END) AS fail_count,
       MAX(observed_at_utc) AS observed_at_utc
FROM retail_prod.silver.pedidos_quality_metrics
WHERE observed_at_utc >= CURRENT_TIMESTAMP() - INTERVAL 30 DAYS
GROUP BY batch_id, quality_run_id
UNION ALL
SELECT 'clientes', batch_id, quality_run_id,
       SUM(CASE WHEN action = 'FAIL' THEN failed_records ELSE 0 END),
       MAX(observed_at_utc)
FROM retail_prod.silver.clientes_quality_metrics
WHERE observed_at_utc >= CURRENT_TIMESTAMP() - INTERVAL 30 DAYS
GROUP BY batch_id, quality_run_id
UNION ALL
SELECT 'productos', batch_id, quality_run_id,
       SUM(CASE WHEN action = 'FAIL' THEN failed_records ELSE 0 END),
       MAX(observed_at_utc)
FROM retail_prod.silver.productos_quality_metrics
WHERE observed_at_utc >= CURRENT_TIMESTAMP() - INTERVAL 30 DAYS
GROUP BY batch_id, quality_run_id
ORDER BY observed_at_utc DESC;

-- -----------------------------------------------------------------------------
-- 3. Freshness y Completitud en Capa Gold
-- Verifica fecha_pedido, publicación UTC y volumen neto diario.
-- -----------------------------------------------------------------------------
SELECT
  fecha_pedido,
  MAX(_published_at_utc) AS published_at_utc,
  COUNT(*) AS kpi_rows,
  SUM(ventas_netas) AS ventas_netas
FROM retail_prod.gold.agg_ventas_netas_diarias
GROUP BY fecha_pedido
ORDER BY fecha_pedido DESC
LIMIT 31;

-- -----------------------------------------------------------------------------
-- 4. Lineage de Tablas en Unity Catalog (system.access.table_lineage)
-- Identifica dependencias upstream/downstream en el catálogo retail_prod.
-- -----------------------------------------------------------------------------
SELECT event_time, source_table_full_name, target_table_full_name,
       created_by, entity_type, entity_id
FROM system.access.table_lineage
WHERE event_time >= CURRENT_TIMESTAMP() - INTERVAL 7 DAYS
  AND (
    source_table_full_name LIKE 'retail_prod.%'
    OR target_table_full_name LIKE 'retail_prod.%'
  )
ORDER BY event_time DESC;

-- -----------------------------------------------------------------------------
-- 5. Auditoría de Plataforma y Seguridad (system.access.audit)
-- Registra acciones sobre jobs y Unity Catalog en los últimos 7 días.
-- -----------------------------------------------------------------------------
SELECT event_time, workspace_id, service_name, action_name,
       user_identity, request_params, response
FROM system.access.audit
WHERE event_time >= CURRENT_TIMESTAMP() - INTERVAL 7 DAYS
  AND service_name IN ('jobs', 'unityCatalog')
ORDER BY event_time DESC;

-- -----------------------------------------------------------------------------
-- 6. Atribución de Consumo y Cómputo (system.billing.usage)
-- Agrega DBU facturables atribuidos a jobs en los últimos 30 días.
-- -----------------------------------------------------------------------------
SELECT usage_date,
       usage_metadata.job_id AS job_id,
       usage_metadata.job_run_id AS job_run_id,
       sku_name,
       usage_unit,
       SUM(usage_quantity) AS usage_quantity
FROM system.billing.usage
WHERE usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
  AND billing_origin_product = 'JOBS'
  AND usage_metadata.job_id IS NOT NULL
GROUP BY ALL
HAVING usage_quantity <> 0
ORDER BY usage_date DESC, usage_quantity DESC;
