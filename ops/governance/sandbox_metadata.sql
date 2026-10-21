-- ==============================================================================
-- sandbox_metadata.sql
-- Creación y etiquetado del activo de laboratorio en Unity Catalog (Fase 15 §16)
-- Target acotado exclusivamente a: retail_sbx_a001.silver.clientes_governance_lab
-- ==============================================================================

-- 1. Crear clon superficial a partir de la tabla curada existente
CREATE OR REPLACE TABLE retail_sbx_a001.silver.clientes_governance_lab
SHALLOW CLONE retail_sbx_a001.silver.clientes_curated;

-- 2. Asignar comentario descriptivo a la tabla
COMMENT ON TABLE retail_sbx_a001.silver.clientes_governance_lab IS
  'Laboratorio sintético para validar comments, tags y grants; no es fuente productiva.';

-- 3. Asignar comentario a la columna email
ALTER TABLE retail_sbx_a001.silver.clientes_governance_lab
ALTER COLUMN email COMMENT
  'Email sintético de contacto; tratar según la clasificación corporativa aplicable.';

-- 4. Asignar governed tags aprobados a nivel de tabla
ALTER TABLE retail_sbx_a001.silver.clientes_governance_lab
SET TAGS (
  'data_domain' = 'retail',
  'data_classification' = 'confidential',
  'lifecycle' = 'active'
);

-- 5. Asignar governed tag de clasificación a la columna email
ALTER TABLE retail_sbx_a001.silver.clientes_governance_lab
ALTER COLUMN email
SET TAGS ('data_classification' = 'restricted');
