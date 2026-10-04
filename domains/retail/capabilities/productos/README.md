# Capability: retail/productos

## 1. Identificación y Gobernanza

- **Dominio**: `retail`
- **Capability**: `productos`
- **Owner Técnico**: Data Engineering (@becavas)
- **Data Owner**: Retail Product Team
- **Clasificación de Datos**: Interno / Operativo
- **SLO de Ingesta**: Batch diario / bajo demanda

---

## 2. Propósito y Alcance

La capability `retail/productos` es responsable de la ingesta, tipado, validación de calidad y publicación de los catálogos maestros de **productos** y **categorías** desde el landing zone administrado por la plataforma hasta las capas Bronze y Silver en Unity Catalog (`retail_sbx_a001`).

Mantiene dos entidades desacopladas pero gobernadas bajo una misma capability con despliegue y ciclo de vida unificados:
- `productos`: Entidad principal de catálogo de ítems vendibles.
- `categorias`: Entidad de referencia que jerarquiza los productos.

---

## 3. Fuentes y Entidades de Entrada

Ubicación en Landing Volume:
`/Volumes/retail_sbx_a001/landing/productos_source/`
- `productos/batch_id=<batch_id>/*.csv`
- `categorias/batch_id=<batch_id>/*.csv`

Todas las columnas de entrada se reciben como strings UTF-8:
- **productos**: `producto_id`, `categoria_id`, `nombre_producto`, `marca`, `moneda`, `precio_lista`, `estado`, `fecha_actualizacion`
- **categorias**: `categoria_id`, `nombre_categoria`, `categoria_padre_id`, `estado`, `fecha_actualizacion`

---

## 4. Salidas y Almacenamiento en Unity Catalog

| Tabla | Capa | Grano | Estrategia de Idempotencia |
|---|---|---|---|
| `bronze.productos_raw` | Bronze | Fila producto recibida | `replaceWhere` por `_ingestion_batch_id` |
| `bronze.categorias_raw` | Bronze | Fila categoría recibida | `replaceWhere` por `_ingestion_batch_id` |
| `silver.productos_curated` | Silver | (`producto_id`, `_source_batch_id`) | Dedupe determinista + `replaceWhere` por `_source_batch_id` |
| `silver.categorias_curated` | Silver | (`categoria_id`, `_source_batch_id`) | Control de conflicto + `replaceWhere` por `_source_batch_id` |
| `silver.productos_quarantine` | Silver | Fila no conforme + `quality_run_id` | `replaceWhere` por `_quality_run_id` |
| `silver.productos_quality_metrics` | Silver | Regla + entidad + `quality_run_id` | `replaceWhere` por `quality_run_id` |

---

## 5. Garantías de Calidad y Contratos de Datos

<!-- guarantees:start -->
| ID | Garantía | Acción | Descripción |
|---|---|---|---|
| `PRO-BR-001` | Schema fuente explícito | FAIL técnico | Lectura CSV en modo FAILFAST con StructType predefinido para ambas entidades. |
| `PRO-BR-002` | Linaje técnico completo | FAIL técnico | Inyección de `_source_system`, `_source_entity`, `_source_file_path`, `_source_file_modification_time`, `_ingestion_batch_id`, `_ingestion_run_id`, `_ingested_at_utc`, `_record_hash`. |
| `PRO-BR-003` | Reproceso idempotente | FAIL técnico | Reproceso de un batch reemplaza exactamente las particiones del batch sin afectar otros lotes. |
| `PRO-SI-001` | Identificadores y fechas obligatorios | FAIL | `producto_id`, `categoria_id` y `fecha_actualizacion` no nulos y válidos. Un fallo detiene la publicación curated. |
| `PRO-SI-002` | Atributos de producto válidos | QUARANTINE | Nombre no nulo, moneda permitida (`PEN`, `USD`), precio >= 0, estado (`ACTIVO`, `INACTIVO`). |
| `PRO-SI-003` | Atributos de categoría válidos | QUARANTINE | Nombre no nulo, estado permitido (`ACTIVO`, `INACTIVO`), y padre distinto a sí misma. |
| `PRO-SI-004` | Integridad referencial de categoría | QUARANTINE | Producto debe referenciar una `categoria_id` presente en las categorías válidas del mismo lote. |
| `PRO-SI-005` | Duplicado exacto de categoría | OBSERVE | Repetición idéntica de payload se observa en métricas y se deduplica determinísticamente. |
| `PRO-SI-006` | Conflicto de categoría | FAIL | Mismo `categoria_id` con payloads distintos detiene la publicación de curated para evitar decisiones arbitrarias. |
| `PRO-PK-001` | Wheel instalado | FAIL técnico | Las tasks se ejecutan instalando el wheel `enterprise-fabric` sin dependencias de `sys.path` ni `PYTHONPATH`. |
<!-- guarantees:end -->

---

## 6. Política de Duplicados y Conflictos en Categorías

1. **Repetición exacta (`OBSERVE`)**: Si múltiples registros tienen el mismo `categoria_id` y el mismo hash de negocio (`_record_hash`), se registra en `categoria_duplicate` y se conserva una fila determinísticamente por fecha de actualización.
2. **Conflicto de negocio (`FAIL`)**: Si existen registros con el mismo `categoria_id` pero con distinto payload (`_record_hash`), se activa la regla `categoria_conflicting_duplicate`. Esto preserva las métricas y la cuarentena, pero **aborta la publicación a curated** (lanzando `QualityGateError`) para impedir resoluciones silenciosas no autorizadas por el Data Owner.

---

## 7. Runbook Operativo

### Requisitos Previos
- Workspace Databricks autenticado (perfil `sandbox`).
- Variables de entorno:
  ```bash
  export BUNDLE_VAR_catalog="retail_sbx_a001"
  export BUNDLE_VAR_source_volume_path="/Volumes/retail_sbx_a001/landing/productos_source"
  export BUNDLE_VAR_policy_id="0014E7B094CA30EB"
  ```

### Despliegue del Bundle
```bash
cd domains/retail/capabilities/productos
databricks bundle deploy --target sandbox --profile sandbox
```

### Ejecución de Lote Normal
```bash
databricks bundle run productos_e2e_job \
  --target sandbox \
  --profile sandbox \
  -- --batch_id=training_001
```

### Monitoreo y Verificación SQL
```sql
SELECT * FROM retail_sbx_a001.silver.productos_quality_metrics
WHERE quality_run_id = '<job_run_id>'
ORDER BY entity, rule_id;

SELECT * FROM retail_sbx_a001.silver.productos_quarantine
WHERE _quality_run_id = '<job_run_id>';
```
