# Capability retail/productos

## Propósito

Ingesta, validación de calidad y publicación de los catálogos maestros de productos y categorías desde el landing zone hasta las capas Bronze y Silver en Unity Catalog (`retail_sbx_a001`).

## Ownership

- Data Owner: `becavas` (autor, platform owner y laboratorio aprobado en simulación; ref: `docs/platform-dependencies.md`).
- Technical Owner: `becavas` (Data Engineering Retail).
- Revisor GitHub: `becavas83` (Identidad Revisora en simulación con permiso write).
- Operación y Soporte: `becavas` (consulte `docs/platform-dependencies.md` y `docs/operations/retail-runbook.md`).

## Clasificación y acceso

- Clasificación: `internal` para catálogos y listas de precios maestros.
- Consumo esperado: Capability downstream `ventas` (dimensión producto) y aplicaciones comerciales.
- Acceso: Administrado centralmente en Unity Catalog (`retail_sbx_a001` en sandbox; service principals en ambientes compartidos).

## Entradas

| Dataset | Ruta lógica | Formato | Garantía |
|---|---|---|---|
| Productos | `productos/batch_id=<batch_id>` | CSV con header | Batch inmutable al declararse listo |
| Categorías | `categorias/batch_id=<batch_id>` | CSV con header | Batch inmutable al declararse listo |

Volume físico de sandbox: `retail_sbx_a001.landing.productos_source`.

## Salidas y grano

| Tabla | Capa | Grano | Estrategia de Idempotencia |
|---|---|---|---|
| `bronze.productos_raw` | Bronze | Fila producto recibida | `replaceWhere` por `_ingestion_batch_id` |
| `bronze.categorias_raw` | Bronze | Fila categoría recibida | `replaceWhere` por `_ingestion_batch_id` |
| `silver.productos_curated` | Silver | (`producto_id`, `_source_batch_id`) | Deduplicación determinista + `replaceWhere` |
| `silver.categorias_curated` | Silver | (`categoria_id`, `_source_batch_id`) | Control de conflicto + `replaceWhere` |
| `silver.productos_quarantine` | Silver | Fila no conforme + `quality_run_id` | `replaceWhere` por `_quality_run_id` |
| `silver.productos_quality_metrics` | Silver | Regla + entidad + `quality_run_id` | `replaceWhere` por `quality_run_id` |

## Garantías verificables

<!-- guarantees:start -->
| ID | Garantía | Acción | Descripción |
|---|---|---|---|
| `PRO-BR-001` | Schema fuente explícito | FAIL técnico | Lectura CSV en modo FAILFAST con StructType predefinido para ambas entidades. |
| `PRO-BR-002` | Linaje técnico completo | FAIL técnico | Inyección de metadatos de batch, run, archivo y record hash. |
| `PRO-BR-003` | Reproceso idempotente | FAIL técnico | Reproceso de un batch reemplaza exactamente las particiones del batch. |
| `PRO-SI-001` | Identificadores y fechas obligatorios | FAIL | `producto_id`, `categoria_id` y `fecha_actualizacion` válidos; detiene curated si fallan. |
| `PRO-SI-002` | Atributos de producto válidos | QUARANTINE | Nombre no nulo, moneda permitida (`PEN`, `USD`), precio >= 0, estado activo/inactivo. |
| `PRO-SI-003` | Atributos de categoría válidos | QUARANTINE | Nombre no nulo, estado permitido, padre distinto a sí misma. |
| `PRO-SI-004` | Integridad referencial de categoría | QUARANTINE | Producto debe referenciar categoría válida del mismo lote. |
| `PRO-SI-005` | Duplicado exacto de categoría | OBSERVE | Repetición idéntica de payload se observa y deduplica determinísticamente. |
| `PRO-SI-006` | Conflicto de categoría | FAIL | Mismo `categoria_id` con distinto payload detiene publicación curated (`QualityGateError`). |
| `PRO-PK-001` | Wheel instalado | FAIL técnico | Ejecución mediante wheel `enterprise-fabric` sin dependencias de PYTHONPATH. |
<!-- guarantees:end -->

## Operación

- Spec declarativa: [`specs/jobs.yml`](specs/jobs.yml).
- Recurso generado: [`resources/jobs.generated.yml`](resources/jobs.generated.yml).
- Generación de recursos Bundle (ejecutar desde la raíz del repositorio):
  ```bash
  python -m tools.bundle_generator generate --spec domains/retail/capabilities/productos/specs/jobs.yml
  ```
- Despliegue y validación de Bundle (ejecutar desde el directorio de la capability `domains/retail/capabilities/productos`, donde se ubica `databricks.yml`):
  ```bash
  databricks bundle validate --target sandbox --profile sandbox
  databricks bundle deploy --target sandbox --profile sandbox
  databricks bundle run productos_e2e_job --target sandbox --profile sandbox -- --batch_id=training_001
  ```
- Diagnóstico y rollback: Consulte `docs/operations/retail-runbook.md`.

## Lifecycle

- Estado actual: `active`.
- Transiciones: Cambios de estado (`proposed` -> `active` -> `deprecated` -> `retired`) requieren PR aprobada por code owner, verificación de consumidores (`ventas`) y registro conforme a `docs/operations/deprecation-checklist.md`.
