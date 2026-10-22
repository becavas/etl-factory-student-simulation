# Capability retail/devoluciones

## Propósito

Publicar devoluciones de productos válidas, tipadas, deduplicadas y trazables desde Landing hasta Silver en Unity Catalog (`retail_sbx_a001`).

El alcance de esta capability de onboarding comprende la ingestión Bronze cruda, la publicación Silver tipada (`curated`), la segregación de registros anómalos (`quarantine`) y la persistencia de evidencia auditable (`quality_metrics`). La conformación Gold y la promoción a ambientes compartidos permanecen fuera de alcance durante este ejercicio de evaluación en sandbox.

## Ownership

- Data Owner: `becavas` / `bcastillo@techdic.onmicrosoft.com` (autor, platform owner y laboratorio aprobado en simulación; ref: `docs/platform-dependencies.md`).
- Technical Owner: `becavas` (Data Engineering Retail).
- Revisor GitHub: `becavas83` (Identidad Revisora en simulación con permiso write).
- Operación y Soporte: `becavas` (consulte `docs/platform-dependencies.md` y `docs/operations/retail-runbook.md`).

## Clasificación y acceso

- Clasificación general: `financial/internal` a nivel de tablas.
- Clasificación de columna `motivo`: Clasificada como texto potencialmente sensible (`confidential`/sensible). Queda estrictamente prohibido registrar su contenido textual o valores de fila completa en logs de aplicación, trazas de excepción, mensajes de fallo o atributos de métricas.
- Justificación de pertenencia y límites de capability: Las tablas `bronze.devoluciones_raw`, `silver.devoluciones_curated`, `silver.devoluciones_quarantine` y `silver.devoluciones_quality_metrics` pertenecen a la misma capability `retail/devoluciones` porque comparten un único data owner (`becavas`), el mismo technical owner (`becavas`), el mismo ciclo de vida gobernado y el mismo SLA operativo. Las salidas de quarantine y quality metrics constituyen la evidencia directa y acoplada del control de calidad de devoluciones.
- Acceso: Administrado centralmente en Unity Catalog (`retail_sbx_a001` en sandbox; service principals en ambientes compartidos).

## Entradas

| Dataset | Ruta lógica | Formato | Garantía |
|---|---|---|---|
| Devoluciones | `devoluciones/batch_id=<batch_id>/devoluciones.csv` | CSV con header | Batch inmutable al declararse listo |

- Volume físico de sandbox: `retail_sbx_a001.landing.devoluciones_source`.
- Cutoff y manifest: Cada entrega contiene su respectivo `manifest.json` con conteos y checksum SHA-256 verificado antes de la ingestión.
- Dependencia upstream: Requiere la existencia y publicación previa de los pedidos Silver del mismo lote (`retail_sbx_a001.silver.pedidos_curated` donde `_source_batch_id == batch_id`).

## Salidas y grano

| Tabla | Capa | Grano | Uso |
|---|---|---|---|
| `bronze.devoluciones_raw` | Bronze | Fila fuente recibida | Preservación cruda y lineage técnico |
| `silver.devoluciones_curated` | Silver | (`devolucion_id`, `_source_batch_id`) | Registro tipado, deduplicado y validado |
| `silver.devoluciones_quarantine` | Silver | Fila rechazada + `_quality_run_id` | Payload crudo y reglas de validación violadas |
| `silver.devoluciones_quality_metrics` | Silver | Regla + `quality_run_id` | Evidencia de calidad y métricas por ejecución |

## Garantías verificables

<!-- guarantees:start -->
| ID | Garantía |
|---|---|
| `DEV-001` | Bronze conserva 9 columnas fuente como string y agrega lineage técnico (`_source_system`, `_source_file_path`, etc.). |
| `DEV-002` | Reprocesamiento idempotente: reejecutar un batch reemplaza exactamente la partición del batch en Bronze y Silver sin alterar otros lotes. |
| `DEV-003` | Silver normaliza strings, castea tolerante fecha ISO, timestamp UTC y monto decimal(18,2). |
| `DEV-004` | Deduplicación determinista: entre duplicados con mismo `devolucion_id` se selecciona el registro con mayor `updated_at`. |
| `DEV-005` | Conflicto de empate: registros con mismo `devolucion_id`, mismo `updated_at` máximo y diferente payload activan `devolucion_tie_conflict` (FAIL) bloqueando curated. |
| `DEV-006` | Reglas de cuarentena: `fecha_devolucion` nula, `motivo` nulo, `importe_reembolsado` negativo/nulo o `moneda != 'PEN'` se aíslan en quarantine sin abortar curated si no hay fallos fatales. |
| `DEV-007` | Integridad referencial y obligatoriedad: `devolucion_id`, `updated_at`, `producto_id`, `estado` inválido o `pedido_id` inexistente en pedidos Silver del mismo batch activan `FAIL`, impidiendo la publicación curated (`QualityGateError`). |
| `DEV-008` | Privacidad de datos: el campo `motivo` nunca se registra en logs, mensajes de excepción, trazabilidad ni atributos de métricas. |
| `DEV-009` | Quarantine y métricas preservan `quality_run_id`, `batch_id` y lineage técnico sin sobrescribir ejecuciones anteriores. |
| `DEV-010` | Generación de bundles y validación: la spec [`specs/jobs.yml`](specs/jobs.yml) genera recursos conformes al generador gobernado. |
<!-- guarantees:end -->

## Operación

- Runbook operativo detallado: Consulte el apartado específico en [`docs/operations/retail-runbook.md`](../../../../docs/operations/retail-runbook.md#f-protocolo-operativo-y-de-recuperación-capability-retaildevoluciones-sandbox).
- Criterio de ejecución operativa: Ventana operativa del laboratorio acotada a **hasta 60 minutos de tiempo transcurrido inicio-fin por run sandbox**, evaluada midiendo la duración total efectiva de ejecución. Esta ventana no proviene de un timeout global a nivel de parent Job (inexistente en la plataforma/spec), sino de un criterio de seguimiento del laboratorio, complementado por los límites a nivel de tarea declarados (`timeout_seconds: 1800` en Bronze y Silver, con 1 reintento tras 60s en Bronze). No constituye un SLA productivo ni cuenta con servicios corporativos de alerta automatizada externos; rige el seguimiento del Job y la bitácora auditable de la sesión.
- Idempotencia lógica gobernada: La garantía de no duplicación y reemplazo exacto se implementa lógicamente mediante predicados selectivos `replaceWhere` (`_ingestion_batch_id` en Bronze y `_source_batch_id` en Silver Curated). No requiere ni afirma particionado físico en disco para satisfacer la idempotencia a nivel de tabla Delta.
- Spec declarativa: [`specs/jobs.yml`](specs/jobs.yml).
- Recurso generado: [`resources/jobs.generated.yml`](resources/jobs.generated.yml).
- Generación y verificación de bundles (ejecutar desde la raíz del repositorio):
  ```bash
  python -m tools.bundle_generator generate --spec domains/retail/capabilities/devoluciones/specs/jobs.yml
  python -m tools.bundle_generator generate --all --check
  ```
- Despliegue y ejecución en sandbox (ejecutar desde `domains/retail/capabilities/devoluciones`):
  ```bash
  set -a
  source ../../../../.env.local
  set +a
  databricks bundle validate --target sandbox
  databricks bundle plan --target sandbox
  databricks bundle deploy --target sandbox
  databricks bundle run --target sandbox --params batch_id=2026-08-20 devoluciones_pipeline_job
  ```
- Gestión de incidencias, alertas y escalamiento:
  - Fallos en Bronze: Task configurada con reintento acotado (1 reintento tras 60s) para mitigar fallos transitorios de red/compute.
  - Fallos en Silver / DQ: Sin reintento automático ante fallos deterministas. En caso de `QualityGateError`, el Job termina en estado `FAILED`. El operador debe inspeccionar `silver.devoluciones_quality_metrics` y `silver.devoluciones_quarantine` (sin exponer `motivo`). Si el batch de origen contiene datos inválidos, el lote se declara defectuoso e inmutable; el emisor debe generar y publicar un nuevo batch sucesor corregido.
  - Escalamiento: Data Engineering Retail (`becavas`) y Data Platform.

## Lifecycle

- Estado actual: `proposed`.
- Transición a `active`: Requiere la aprobación de la PR por el code owner (`becavas83`), verificación técnica satisfactoria y cierre de gates locales.
- Retiro: Cualquier propuesta de deprecación exige registrar la justificación en `docs/operations/deprecation-checklist.md`, verificar ausencia de consumidores y requerir aprobación expresa del data owner.
