-- ==============================================================================
-- retail_governance_checks.sql
-- Consultas de auditoría e inventario de gobernanza según Fase 15 §§12, 13, 18 y 19.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Inventario de Owners Unity Catalog por Catálogo (§12)
-- ------------------------------------------------------------------------------
-- Ejecutar cada consulta en el workspace y perfil autorizado para su catálogo:
-- - Sandbox: catálogo `retail_sbx_a001` (Perfil CLI `sandbox`, workspace 7405615183307398)
-- - DEV: catálogo `retail_dev` (Perfil CLI `dev` / `sandbox`, workspace 7405615183307398)
-- - CERTI: catálogo `retail_certi` (Perfil CLI `certi-platform`, workspace 7405611412963889)
-- - PROD: catálogo `retail_prod` (Perfil CLI `prod-platform`, workspace 7405609727000776)

-- 1.1 Contexto Sandbox (retail_sbx_a001):
SELECT table_catalog,
       table_schema,
       table_name,
       table_type,
       table_owner,
       created_by,
       last_altered_by
FROM system.information_schema.tables
WHERE table_catalog = 'retail_sbx_a001'
  AND table_schema IN ('bronze', 'silver', 'gold')
ORDER BY table_catalog, table_schema, table_name;

-- 1.2 Contexto DEV (retail_dev):
-- SELECT table_catalog, table_schema, table_name, table_type, table_owner, created_by, last_altered_by
-- FROM system.information_schema.tables
-- WHERE table_catalog = 'retail_dev' AND table_schema IN ('bronze', 'silver', 'gold')
-- ORDER BY table_catalog, table_schema, table_name;

-- 1.3 Contexto CERTI (retail_certi):
-- Ejecutar en workspace CERTI con perfil `certi-platform`.
-- WHERE table_catalog = 'retail_certi' AND table_schema IN ('bronze', 'silver', 'gold');

-- 1.4 Contexto PROD (retail_prod):
-- Ejecutar en workspace PROD con perfil `prod-platform`.
-- WHERE table_catalog = 'retail_prod' AND table_schema IN ('bronze', 'silver', 'gold');

-- ------------------------------------------------------------------------------
-- 2. Inventario de Privilegios y Grants (§13)
-- ------------------------------------------------------------------------------
-- Evalúa privilegios directos y heredados por catálogo y schema.
-- Nota de observación: 0 filas es un resultado observado de esta consulta acotada, sujeto
-- a la visibilidad y alcance evaluado; no excluye grants directos asignados a otros objetos o principales.
SELECT table_catalog,
       table_schema,
       table_name,
       grantee,
       privilege_type,
       inherited_from
FROM system.information_schema.table_privileges
WHERE table_catalog = 'retail_sbx_a001'
  AND table_schema IN ('bronze', 'silver', 'gold')
ORDER BY table_catalog, table_schema, table_name, grantee, privilege_type;

-- ------------------------------------------------------------------------------
-- 3. Validación de Comments y Governed Tags en Activo Sandbox Lab (§18)
-- ------------------------------------------------------------------------------
-- NOTA IMPORTANTE: La recreación del clon con CREATE OR REPLACE restablece la tabla
-- y elimina comentarios, tags y estado de ciclo de vida previos. No es una operación inocua.
-- La preparación activa inicial y la posterior transición a `deprecated` deben
-- gestionarse como etapas separadas y trazables.

-- 3.1 Consulta de tabla y owner:
SELECT table_catalog,
       table_schema,
       table_name,
       comment,
       table_owner
FROM retail_sbx_a001.information_schema.tables
WHERE table_schema = 'silver'
  AND table_name = 'clientes_governance_lab';

-- 3.2 Consulta de tags de tabla:
SELECT catalog_name,
       schema_name,
       table_name,
       tag_name,
       tag_value
FROM retail_sbx_a001.information_schema.table_tags
WHERE schema_name = 'silver'
  AND table_name = 'clientes_governance_lab'
ORDER BY tag_name;

-- 3.3 Consulta de tags de columna:
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

-- ------------------------------------------------------------------------------
-- 4. Linaje Histórico de Capabilities (§19)
-- ------------------------------------------------------------------------------
-- Consulta relaciones fuente -> destino en el workspace sandbox.
-- Se filtra target_table_full_name IS NOT NULL para distinguir relaciones reales
-- de transformación frente a lecturas o scans sin tabla de destino.
SELECT event_time,
       workspace_id,
       source_table_full_name,
       target_table_full_name
FROM system.access.table_lineage
WHERE target_table_full_name IS NOT NULL
  AND (source_table_full_name LIKE 'retail_sbx_a001.%'
       OR target_table_full_name LIKE 'retail_sbx_a001.%')
ORDER BY event_time DESC
LIMIT 50;

-- ------------------------------------------------------------------------------
-- 5. Auditoría de Actividades en Metadatos (§19)
-- ------------------------------------------------------------------------------
-- Consulta eventos de auditoría acotados al workspace, actor y ventana temporal
-- del ejercicio para correlación verificable sin exponer eventos ajenos.
SELECT event_time,
       workspace_id,
       service_name,
       action_name,
       user_identity.email AS actor_email,
       to_json(request_params) AS params,
       response.status_code AS response_code
FROM system.access.audit
WHERE workspace_id = '7405615183307398'
  AND user_identity.email = 'bcastillo@techdic.onmicrosoft.com'
  AND event_date >= '2026-10-20'
  AND event_time >= '2026-10-21T04:40:00Z'
  AND event_time <= '2026-10-21T04:45:00Z'
ORDER BY event_time DESC
LIMIT 50;
