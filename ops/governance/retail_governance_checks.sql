-- ==============================================================================
-- retail_governance_checks.sql
-- Consultas de auditoría e inventario de gobernanza según Fase 15 §§12, 13 y 18.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Inventario de Owners Unity Catalog (§12)
-- ------------------------------------------------------------------------------
-- Ejecutar en el workspace correspondiente a cada catálogo para evitar limitaciones
-- por aislamiento de workspace bindings. En Sandbox/DEV: adb-7405615183307398.
-- En CERTI: adb-7405608948004942. En PROD: adb-7405605191440281.
SELECT table_catalog,
       table_schema,
       table_name,
       table_type,
       table_owner,
       created_by,
       last_altered_by
FROM system.information_schema.tables
WHERE table_catalog IN ('retail_sbx_a001', 'retail_dev', 'retail_certi', 'retail_prod')
  AND table_schema IN ('bronze', 'silver', 'gold')
ORDER BY table_catalog, table_schema, table_name;

-- ------------------------------------------------------------------------------
-- 2. Inventario de Privilegios y Grants (§13)
-- ------------------------------------------------------------------------------
-- Evalúa privilegios directos y heredados por catálogo y schema.
-- Comparar contra la matriz de mínimos privilegios aprobada.
SELECT table_catalog,
       table_schema,
       table_name,
       grantee,
       privilege_type,
       inherited_from
FROM system.information_schema.table_privileges
WHERE table_catalog IN ('retail_sbx_a001', 'retail_dev', 'retail_certi', 'retail_prod')
  AND table_schema IN ('bronze', 'silver', 'gold')
ORDER BY table_catalog, table_schema, table_name, grantee, privilege_type;

-- ------------------------------------------------------------------------------
-- 3. Validación de Comments y Governed Tags en Activo Sandbox Lab (§18)
-- ------------------------------------------------------------------------------
-- Consulta específica sobre el activo de laboratorio en retail_sbx_a001.
SELECT table_catalog,
       table_schema,
       table_name,
       comment,
       table_owner
FROM retail_sbx_a001.information_schema.tables
WHERE table_schema = 'silver'
  AND table_name = 'clientes_governance_lab';

SELECT catalog_name,
       schema_name,
       table_name,
       tag_name,
       tag_value
FROM retail_sbx_a001.information_schema.table_tags
WHERE schema_name = 'silver'
  AND table_name = 'clientes_governance_lab'
ORDER BY tag_name;

SELECT catalog_name,
       schema_name,
       table_name,
       column_name,
       tag_name,
       tag_value
FROM retail_sbx_a001.information_schema.column_tags
WHERE schema_name = 'silver'
  AND table_name = 'clientes_governance_lab'
ORDER BY column_name, tag_name;
