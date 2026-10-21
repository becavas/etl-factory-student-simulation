# Capability retail/pedidos

## Propósito

Publicar pedidos e items recibidos desde `landing.pedidos_source` hacia Bronze trazable y Silver conformada con calidad observable y deduplicación intra-batch determinista.

## Ownership

- Data Owner: `becavas` (autor, platform owner y laboratorio aprobado en simulación; ref: `docs/platform-dependencies.md`).
- Technical Owner: `becavas` (Data Engineering Retail).
- Revisor GitHub: `becavas83` (Identidad Revisora en simulación con permiso write).
- Operación y Soporte: `becavas` (consulte `docs/platform-dependencies.md` y `docs/operations/retail-runbook.md`).

## Clasificación y acceso

- Clasificación: `internal` para datos transaccionales de pedidos; `restricted` para metadatos o atributos sensibles si aplican.
- Consumo esperado: Capability downstream `ventas` y pipelines analíticos autorizados.
- Acceso: Administrado centralmente en Unity Catalog (`retail_sbx_a001` en sandbox; service principals en ambientes compartidos).

## Entradas

| Dataset | Ruta lógica | Formato | Garantía |
|---|---|---|---|
| Pedidos | `pedidos/batch_id=<batch_id>` | CSV con header | Batch inmutable al declararse listo |
| Items | `pedido_items/batch_id=<batch_id>` | CSV con header | Mismo batch lógico que pedidos |

Volume físico de sandbox: `retail_sbx_a001.landing.pedidos_source`.

## Salidas y grano

| Tabla | Capa | Grano | Estrategia |
|---|---|---|---|
| `bronze.pedidos_raw` | Bronze | Fila recibida por pedido y archivo | Reemplazo selectivo por batch (`replaceWhere`) |
| `bronze.pedido_items_raw` | Bronze | Fila recibida por item y archivo | Reemplazo selectivo por batch (`replaceWhere`) |
| `silver.pedidos_curated` | Silver | (`pedido_id`, `_source_batch_id`) | Deduplicación intra-batch determinista |
| `silver.pedido_items_curated` | Silver | (`pedido_id`, `item_id`, `_source_batch_id`) | Deduplicación intra-batch determinista |
| `silver.pedidos_quarantine` | Silver | Registro rechazado + `_quality_run_id` | Preservación de payload y reglas violadas |
| `silver.pedidos_quality_metrics` | Silver | Regla + entidad + `quality_run_id` | Conteos y estado por ejecución |

## Garantías verificables

<!-- guarantees:start -->
| ID | Garantía | Comportamiento |
|---|---|---|
| `PED-BR-001` | Ingesta Bronze estructurada | FAILFAST en lectura CSV con schema explícito. |
| `PED-BR-002` | Reproceso idempotente | Reemplazo exacto por `batch_id` sin duplicar filas. |
| `PED-SI-001` | Obligatoriedad de claves | `pedido_id`, `item_id` nulos o inválidos van a quarantine o abortan curated. |
| `PED-SI-002` | Moneda y montos válidos | Validación de montos no negativos y monedas permitidas. |
| `PED-SI-003` | Deduplicación determinista | Mayor recencia o criterio de desempate determinista. |
| `PED-SI-004` | Integridad referencial item-pedido | Items sin cabecera de pedido van a cuarentena. |
<!-- guarantees:end -->

## Operación

- Spec declarativa de automatización: [`specs/jobs.yml`](specs/jobs.yml).
- Recurso generado para Databricks Asset Bundles: [`resources/jobs.generated.yml`](resources/jobs.generated.yml).
- Generación de recursos Bundle:
  ```bash
  python -m tools.bundle_generator generate --spec domains/retail/capabilities/pedidos/specs/jobs.yml
  ```
- Despliegue y ejecución en sandbox:
  ```bash
  databricks bundle validate --target sandbox --profile sandbox
  databricks bundle deploy --target sandbox --profile sandbox
  databricks bundle run pedidos_e2e_job --target sandbox --profile sandbox -- --batch_id=training_001
  ```
- Diagnóstico y rollback: Consulte `docs/operations/retail-runbook.md`.

## Lifecycle

- Estado actual: `active`.
- Transiciones: Cambios de estado (`proposed` -> `active` -> `deprecated` -> `retired`) requieren PR aprobada por code owner, verificación de dependencias downstream (`ventas`) y cumplimiento de `docs/operations/deprecation-checklist.md`.
