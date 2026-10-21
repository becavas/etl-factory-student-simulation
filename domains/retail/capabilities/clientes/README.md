# Capability retail/clientes

## Propósito

Publicar el catálogo maestro de clientes sintéticos tipados, deduplicados y trazables desde Landing hasta Silver en Unity Catalog (`retail_sbx_a001`).

## Ownership

- Data Owner: `becavas` (autor, platform owner y laboratorio aprobado en simulación; ref: `docs/platform-dependencies.md`).
- Technical Owner: `becavas` (Data Engineering Retail).
- Revisor GitHub: `becavas83` (Identidad Revisora en simulación con permiso write).
- Operación y Soporte: `becavas` (consulte `docs/platform-dependencies.md` y `docs/operations/retail-runbook.md`).

## Clasificación y acceso

- Clasificación: `confidential` a nivel de tabla; columna `email` clasificada como `restricted` (datos personales sintéticos sujetos a políticas corporativas).
- Consumo esperado: Capability downstream `ventas` (para conformación dimensional) y procesos analíticos autorizados.
- Acceso: Administrado centralmente en Unity Catalog (`retail_sbx_a001` en sandbox; service principals en ambientes compartidos).

## Entradas

| Dataset | Ruta lógica | Formato | Garantía |
|---|---|---|---|
| Clientes | `clientes/batch_id=<batch_id>` | CSV con header | Batch inmutable al declararse listo |

Volume físico de sandbox: `retail_sbx_a001.landing.clientes_source`.

## Salidas y grano

| Tabla | Capa | Grano | Uso |
|---|---|---|---|
| `bronze.clientes_raw` | Bronze | Fila fuente recibida | Preservación cruda y lineage técnico |
| `silver.clientes_curated` | Silver | (`cliente_id`, `_source_batch_id`) | Registro tipado, deduplicado y validado |
| `silver.clientes_quarantine` | Silver | Fila rechazada + `quality_run_id` | Payload crudo y reglas de validación violadas |
| `silver.clientes_quality_metrics` | Silver | Regla + `quality_run_id` | Evidencia de calidad y métricas por ejecución |

## Garantías verificables

<!-- guarantees:start -->
| ID | Garantía |
|---|---|
| `CLI-001` | Bronze conserva columnas fuente como string y agrega lineage técnico. |
| `CLI-002` | Reprocesar un batch reemplaza exactamente las particiones del batch sin afectar otros lotes. |
| `CLI-003` | Silver normaliza strings vacíos y tipa fechas y timestamps de forma tolerante. |
| `CLI-004` | Un duplicado conserva el registro con mayor recencia y desempate determinista. |
| `CLI-005` | El email se normaliza a minúsculas y formato inválido va a quarantine. |
| `CLI-006` | Fecha de nacimiento futura, país inválido y estado desconocido van a quarantine. |
| `CLI-007` | ID o timestamp obligatorio inválido persiste evidencia y falla Silver (`QualityGateError`). |
| `CLI-008` | Métricas y quarantine conservan batch, quality run y lineage fuente. |
<!-- guarantees:end -->

## Operación

- Spec declarativa: [`specs/jobs.yml`](specs/jobs.yml).
- Recurso generado: [`resources/jobs.generated.yml`](resources/jobs.generated.yml).
- Generación y validación:
  ```bash
  python -m tools.bundle_generator generate --spec domains/retail/capabilities/clientes/specs/jobs.yml
  ```
- Despliegue y ejecución:
  ```bash
  databricks bundle validate --target sandbox --profile sandbox
  databricks bundle deploy --target sandbox --profile sandbox
  databricks bundle run clientes_e2e_job --target sandbox --profile sandbox -- --batch_id=training_001
  ```
- Diagnóstico y rollback: Consulte `docs/operations/retail-runbook.md`.

## Lifecycle

- Estado actual: `active`.
- Transiciones: Cambios de estado (`proposed` -> `active` -> `deprecated` -> `retired`) requieren PR aprobada por code owner, verificación de consumidores (`ventas`) y registro conforme a `docs/operations/deprecation-checklist.md`.
