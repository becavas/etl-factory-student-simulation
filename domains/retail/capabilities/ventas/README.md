# Capability retail/ventas

## Propósito

Construcción y publicación del modelo dimensional Gold (`dim_cliente`, `dim_producto`, `fact_ventas`) y métricas semánticas agregadas (`agg_ventas_netas_diarias`) en Unity Catalog (`retail_sbx_a001`). Consume datos curados de Silver producidos por `pedidos`, `clientes` y `productos`.

## Ownership

- Data Owner: `becavas` (autor, platform owner y laboratorio aprobado en simulación; ref: `docs/platform-dependencies.md`).
- Technical Owner: `becavas` (Data Engineering Retail).
- Revisor GitHub: `becavas83` (Identidad Revisora en simulación con permiso write).
- Operación y Soporte: `becavas` (consulte `docs/platform-dependencies.md` y `docs/operations/retail-runbook.md`).

## Clasificación y acceso

- Clasificación: `confidential` para hechos transaccionales y dimensiones vinculadas a clientes; `internal` para dimensiones de catálogo de productos y métricas agregadas desidentificadas.
- Minimización: `dim_cliente` excluye nombres, apellidos y emails directos, conservando solo atributos analíticos minimizados.
- Acceso: Administrado centralmente en Unity Catalog (`retail_sbx_a001` en sandbox; service principals en ambientes compartidos).

## Entradas

Tablas Silver consumidas como fuentes upstream gobernadas:
- `silver.pedidos_curated`
- `silver.pedido_items_curated`
- `silver.clientes_curated`
- `silver.productos_curated`
- `silver.categorias_curated`

## Salidas y grano

| Tabla | Capa | Grano | Tipo de Carga | Política de Ausencia |
|---|---|---|---|---|
| `gold.dim_cliente` | Gold | Una fila por `cliente_id` | Type 1 `MERGE` | Desactiva solo con snapshot `FULL` |
| `gold.dim_producto` | Gold | Una fila por `producto_id` | Type 1 `MERGE` | Desactiva solo con snapshot `FULL` |
| `gold.fact_ventas` | Gold | Una fila por (`pedido_id`, `item_id`) | Upsert `MERGE` | Conserva líneas previas (no borra por omisión) |
| `gold.agg_ventas_netas_diarias` | Gold | Una fila por (`fecha_pedido`, `canal`, `moneda`) | Reemplazo selectivo (`replaceWhere`) | Elimina agregado previo si la fecha se cancela |

## Garantías verificables

<!-- guarantees:start -->
| ID | Garantía | Acción | Descripción |
|---|---|---|---|
| `VEN-IN-001` | Entradas Silver completas | FAIL | Las cinco entradas Silver existen para el batch solicitado antes de publicar Gold. |
| `VEN-IN-002` | Unicidad estricta de MERGE | FAIL | Cada fuente tiene una fila como máximo por clave de MERGE antes de escribir en Delta. |
| `VEN-DI-001` | Claves canónicas versionadas | FAIL | Las surrogate keys usan encoding canónico versionado `v1` sobre JSON determinista. |
| `VEN-DI-002` | Unknown member reservado | FAIL | El miembro desconocido existe con 64 ceros y clave reservada `__UNKNOWN__`, nunca se desactiva. |
| `VEN-DI-003` | Type 1 por payload hash | OBSERVE | La actualización Type 1 solo modifica atributos si `_payload_hash` cambia. |
| `VEN-DI-004` | Ausencias solo en FULL | OBSERVE | Dimensiones ausentes solo se desactivan ante snapshot `FULL` explícito. |
| `VEN-FA-001` | Grano del hecho unitario | FAIL | `fact_ventas` mantiene exactamente una fila por (`pedido_id`, `item_id`). |
| `VEN-FA-002` | Reconciliación pedido/líneas | FAIL | El importe sumado de líneas reconcilia contra `monto_total` del pedido (tolerancia 0.01). |
| `VEN-FA-003` | Asignación de unknown member | OBSERVE | Dimensiones no encontradas o inactivas asignan `UNKNOWN_SK` sin perder la natural key. |
| `VEN-FA-004` | Resolución de datos tardíos | OBSERVE | Late arrival actualiza la clave foránea del hecho sin duplicar la línea. |
| `VEN-FA-005` | Preservación de cancelaciones | OBSERVE | Cancelaciones auditan con `is_cancelled=true`; omisiones no borran hechos. |
| `VEN-MG-001` | Reproceso idempotente | OBSERVE | Segunda ejecución idéntica reporta 0 inserts y 0 updates en métricas Delta. |
| `VEN-CO-001` | Compute compartido en Job | OBSERVE | Tasks reutilizan cluster compartido (`ventas_shared_job_compute`). |
| `VEN-KPI-001` | Fórmula y filtros contract | FAIL | Fórmula y filtros coinciden con el contrato semántico versión 1.0.0. |
| `VEN-KPI-002` | Grano único de agregado | FAIL | Máximo una fila por (`fecha_pedido`, `canal`, `moneda`) en la tabla agregada. |
| `VEN-KPI-003` | Moneda única sin conversión | FAIL | Solo se admite PEN; presencia de otra moneda elegible aborta la publicación. |
| `VEN-KPI-004` | Reconciliación pre-escritura | FAIL | Diferencia absoluta entre el hecho y el KPI no supera 0.01 PEN antes de persistir. |
| `VEN-KPI-005` | Recomputación de fechas | OBSERVE | `FULL` cubre historia e `INCREMENTAL` recalcula fechas anteriores y nuevas completas. |
| `VEN-KPI-006` | Cumplimiento de frescura | OBSERVE | Publicación ocurre dentro de las 4 horas posteriores al éxito del hecho. |
| `VEN-KPI-007` | Consistencia de contrato | FAIL | Modificaciones en semántica, fórmula o grano rompen pruebas sin coordinación de contrato. |
<!-- guarantees:end -->

## Operación

- Spec declarativa: [`specs/jobs.yml`](specs/jobs.yml).
- Recurso generado: [`resources/jobs.generated.yml`](resources/jobs.generated.yml).
- Generación de recursos Bundle (ejecutar desde la raíz del repositorio):
  ```bash
  python -m tools.bundle_generator generate --spec domains/retail/capabilities/ventas/specs/jobs.yml
  ```
- Despliegue y validación de Bundle (ejecutar desde el directorio de la capability `domains/retail/capabilities/ventas`, donde se ubica `databricks.yml`):
  ```bash
  databricks bundle validate --target sandbox --profile sandbox
  databricks bundle deploy --target sandbox --profile sandbox
  databricks bundle run ventas_gold_job --target sandbox --profile sandbox -- --batch_id=training_001
  ```
- Diagnóstico y rollback: Consulte `docs/operations/retail-runbook.md`.

## Lifecycle

- Estado actual: `active`.
- Transiciones: Cambios de estado (`proposed` -> `active` -> `deprecated` -> `retired`) requieren PR aprobada por code owner, verificación de reportes downstream y cumplimiento de `docs/operations/deprecation-checklist.md`.
